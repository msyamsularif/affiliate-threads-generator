"""Hook tests.

The ``pre_tool_call`` hook is the load-bearing safety mechanism: it escalates
every publish to Hermes' own human-approval gate, which the model cannot bypass.
It has to fire for the right tool, and only for the right tool.
"""

from __future__ import annotations

import json

import pytest

from atg_plugin import hooks, runtime

AUDIT_KEY = "publish_audit"


class TestApprovalGate:
    def test_other_tools_are_untouched(self, ctx) -> None:  # noqa: ANN001
        for name in ("terminal", "write_file", "threads_check", "web_search"):
            assert hooks.on_pre_tool_call(tool_name=name, args={}) is None

    def test_threads_publish_is_escalated(self, ctx) -> None:  # noqa: ANN001
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish",
            args={"product_id": "12", "posts": [{"text": "hello"}]},
        )
        assert directive is not None
        assert directive["action"] == "approve"

    def test_the_message_identifies_the_product(self, ctx) -> None:  # noqa: ANN001
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish",
            args={"product_id": "12", "posts": [{"text": "a"}]},
        )
        assert "12" in directive["message"]

    def test_the_message_shows_the_copy_being_approved(self, ctx) -> None:  # noqa: ANN001
        posts = [{"text": "first post"}, {"text": "second post"}, {"text": "third post"}]
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish", args={"product_id": "12", "posts": posts}
        )
        for index, post in enumerate(posts, start=1):
            assert post["text"] in directive["message"]
            assert f"post {index}" in directive["message"].lower()
        assert "Posts: 3" in directive["message"]

    def test_the_message_warns_that_it_is_irreversible(self, ctx) -> None:  # noqa: ANN001
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish", args={"product_id": "12", "posts": [{"text": "a"}]}
        )
        assert "cannot be undone" in directive["message"]

    def test_a_very_long_thread_is_truncated(self, ctx) -> None:  # noqa: ANN001
        posts = [{"text": "x" * 500} for _ in range(10)]
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish", args={"product_id": "12", "posts": posts}
        )
        assert "truncated" in directive["message"]
        assert len(directive["message"]) < 5000

    def test_a_missing_product_id_still_gates(self, ctx) -> None:  # noqa: ANN001
        directive = hooks.on_pre_tool_call(tool_name="threads_publish", args={})
        assert directive is not None
        assert directive["action"] == "approve"
        assert "(no product_id)" in directive["message"]

    def test_malformed_posts_do_not_crash_the_gate(self, ctx) -> None:  # noqa: ANN001
        directive = hooks.on_pre_tool_call(
            tool_name="threads_publish", args={"product_id": "1", "posts": "not-a-list"}
        )
        assert directive is not None
        assert directive["action"] == "approve"

    def test_gate_can_be_disabled_by_config(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["require_approval_prompt"] = False
        assert (
            hooks.on_pre_tool_call(
                tool_name="threads_publish", args={"product_id": "1", "posts": [{"text": "a"}]}
            )
            is None
        )

    @pytest.mark.parametrize("value", ["false", "no", "0", False])
    def test_disable_accepts_common_falsy_forms(self, ctx, value: object) -> None:  # noqa: ANN001
        ctx.settings["require_approval_prompt"] = value
        assert hooks.on_pre_tool_call(tool_name="threads_publish", args={}) is None

    @pytest.mark.parametrize("value", ["true", "yes", "1", True])
    def test_truthy_forms_keep_the_gate_on(self, ctx, value: object) -> None:  # noqa: ANN001
        ctx.settings["require_approval_prompt"] = value
        assert hooks.on_pre_tool_call(tool_name="threads_publish", args={}) is not None

    def test_unrecognised_tool_names_return_none(self, ctx) -> None:  # noqa: ANN001
        assert hooks.on_pre_tool_call(tool_name="", args={}) is None
        assert hooks.on_pre_tool_call() is None


class TestAuditTrail:
    def test_other_tools_are_not_audited(self, ctx) -> None:  # noqa: ANN001
        hooks.on_post_tool_call(tool_name="terminal", args={"command": "ls"}, result="ok")
        assert runtime.state_get(AUDIT_KEY, default=[]) == []

    def test_a_successful_publish_is_recorded(self, ctx) -> None:  # noqa: ANN001
        result = json.dumps(
            {
                "ok": True,
                "status": "published",
                "threads_url": "https://www.threads.net/@tester/post/abc",
                "media_ids": ["abc"],
            }
        )
        hooks.on_post_tool_call(
            tool_name="threads_publish",
            args={"product_id": "12", "posts": [{"text": "a"}], "approval_note": "saya approve"},
            result=result,
            task_id="task-1",
            duration_ms=1234,
        )

        entries = runtime.state_get(AUDIT_KEY, default=[])
        assert len(entries) == 1
        entry = entries[0]
        assert entry["product_id"] == "12"
        assert entry["outcome"] == "published"
        assert entry["ok"] is True
        assert entry["threads_url"] == "https://www.threads.net/@tester/post/abc"
        assert entry["approval_note"] == "saya approve"
        assert entry["task_id"] == "task-1"
        assert entry["duration_ms"] == 1234
        assert entry["at"]  # timestamped

    def test_a_refusal_is_recorded_with_its_stage(self, ctx) -> None:  # noqa: ANN001
        result = json.dumps(
            {"ok": False, "stage": "precondition", "error": 'Status is "Hold"'}
        )
        hooks.on_post_tool_call(
            tool_name="threads_publish", args={"product_id": "12", "posts": []}, result=result
        )
        entry = runtime.state_get(AUDIT_KEY, default=[])[0]
        assert entry["ok"] is False
        assert entry["stage"] == "precondition"
        assert "Hold" in entry["error"]

    def test_threads_check_is_also_audited(self, ctx) -> None:  # noqa: ANN001
        hooks.on_post_tool_call(
            tool_name="threads_check", args={}, result=json.dumps({"ok": True, "status": "ready"})
        )
        assert runtime.state_get(AUDIT_KEY, default=[])[0]["tool"] == "threads_check"

    def test_a_malformed_result_does_not_crash_the_hook(self, ctx) -> None:  # noqa: ANN001
        hooks.on_post_tool_call(tool_name="threads_publish", args={}, result="not json at all")
        entry = runtime.state_get(AUDIT_KEY, default=[])[0]
        assert entry["product_id"] is None
        assert entry["ok"] is None

    def test_a_missing_result_does_not_crash_the_hook(self, ctx) -> None:  # noqa: ANN001
        hooks.on_post_tool_call(tool_name="threads_publish", args={})
        assert len(runtime.state_get(AUDIT_KEY, default=[])) == 1

    def test_the_audit_trail_is_capped(self, ctx) -> None:  # noqa: ANN001
        for index in range(60):
            hooks.on_post_tool_call(
                tool_name="threads_publish",
                args={"product_id": str(index)},
                result=json.dumps({"ok": True, "status": "published"}),
            )
        entries = runtime.state_get(AUDIT_KEY, default=[])
        assert len(entries) == 50
        # The oldest entries are the ones dropped.
        assert entries[0]["product_id"] == "10"
        assert entries[-1]["product_id"] == "59"

    def test_a_broken_state_store_does_not_break_the_tool_loop(self, monkeypatch, ctx) -> None:  # noqa: ANN001
        def explode(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            raise RuntimeError("state store is gone")

        monkeypatch.setattr(hooks.runtime, "state_get", explode)
        # Must not raise.
        hooks.on_post_tool_call(
            tool_name="threads_publish", args={"product_id": "1"}, result=json.dumps({"ok": True})
        )


class TestSkillPointer:
    """The bundled skill is namespaced and kept out of the skill index, so this
    hook is the only thing that tells the model it exists."""

    @pytest.mark.parametrize(
        "message",
        [
            "Buatkan content berikutnya.",
            "Generate lagi dong.",
            "Saya approve.",
            "Hold dulu yang ini.",
            "Yang ini jangan dipublish.",
            "Regenerate tapi angle-nya lebih ke traveller.",
            "Menurut kamu affiliate link-nya oke?",
        ],
    )
    def test_domain_messages_get_the_pointer(self, ctx, message: str) -> None:  # noqa: ANN001
        result = hooks.on_pre_llm_call(user_message=message)
        assert result is not None
        assert hooks.SKILL_ID in result["context"]

    @pytest.mark.parametrize(
        "message",
        [
            "",
            "What is the weather like in Jakarta?",
            "Refactor the auth middleware.",
            "cancel my subscription",
            "Summarize this pull request.",
        ],
    )
    def test_unrelated_messages_are_left_alone(self, ctx, message: str) -> None:  # noqa: ANN001
        assert hooks.on_pre_llm_call(user_message=message) is None

    def test_the_pointer_stays_one_line(self, ctx) -> None:  # noqa: ANN001
        result = hooks.on_pre_llm_call(user_message="Buatkan content berikutnya.")
        assert set(result) == {"context"}
        assert "\n" not in result["context"]
        assert len(result["context"]) < 400

    def test_it_can_be_turned_off(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["announce_skill"] = False
        assert hooks.on_pre_llm_call(user_message="Buatkan content berikutnya.") is None

    def test_a_missing_message_does_not_crash(self, ctx) -> None:  # noqa: ANN001
        assert hooks.on_pre_llm_call() is None
