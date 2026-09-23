"""Slash command tests.

The command is the human-facing entry point the bundle provides in place of a
hub-installed skill, so what it prints has to be true. It dispatches the real
``threads_check`` tool rather than re-implementing the checks — these tests pin
that down.
"""

from __future__ import annotations

import json

import pytest

from atg_plugin import commands


class FakeDispatchContext:
    """A context whose ``dispatch_tool`` returns a canned result."""

    def __init__(self, result: str = "{}", raises: Exception | None = None) -> None:
        self.result = result
        self.raises = raises
        self.calls: list[tuple[str, dict]] = []

    def dispatch_tool(self, name: str, args: dict) -> str:
        self.calls.append((name, args))
        if self.raises is not None:
            raise self.raises
        return self.result


def check_payload(**overrides: object) -> str:
    payload: dict = {
        "ok": True,
        "status": "ready",
        "problems": [],
        "checks": {
            "credentials": {"ok": True, "detail": "THREADS_ACCESS_TOKEN is set."},
            "next_candidate": {"ok": True, "detail": {"id": "3", "product": "Wireless Earbuds X"}},
        },
        "unsynced_publishes": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestUsage:
    def test_no_arguments_prints_usage(self) -> None:
        assert "affiliate-threads status" in commands.handle(None, "")

    @pytest.mark.parametrize("raw", ["help", "-h", "--help", "?", "  HELP  "])
    def test_help_forms_print_usage(self, raw: str) -> None:
        assert "affiliate-threads status" in commands.handle(None, raw)

    def test_an_unknown_subcommand_names_itself(self) -> None:
        out = commands.handle(None, "frobnicate")
        assert "frobnicate" in out
        assert "affiliate-threads status" in out

    def test_usage_never_calls_a_tool(self) -> None:
        ctx = FakeDispatchContext()
        commands.handle(ctx, "help")
        assert ctx.calls == []


class TestStatus:
    def test_it_dispatches_the_real_check_tool(self) -> None:
        ctx = FakeDispatchContext(check_payload())
        commands.handle(ctx, "status")
        assert ctx.calls == [("threads_check", {})]

    def test_it_renders_every_check(self) -> None:
        out = commands.handle(FakeDispatchContext(check_payload()), "status")
        assert "ready" in out
        assert "credentials" in out
        assert "THREADS_ACCESS_TOKEN is set." in out
        assert "next_candidate" in out
        assert "Wireless Earbuds X" in out

    def test_a_failing_check_is_marked_and_shows_its_hint(self) -> None:
        raw = check_payload(
            ok=False,
            status="attention_needed",
            problems=["google sheets unreachable"],
            checks={"sheets": {"ok": False, "detail": "no credentials", "hint": "Authorize it."}},
        )
        out = commands.handle(FakeDispatchContext(raw), "status")
        assert "✗ sheets" in out
        assert "Authorize it." in out
        assert "google sheets unreachable" in out

    def test_an_unsynced_publish_is_flagged_with_the_repair_instruction(self) -> None:
        raw = check_payload(unsynced_publishes=[{"product_id": "7"}])
        out = commands.handle(FakeDispatchContext(raw), "status")
        assert "7" in out
        assert "do not re-publish" in out

    def test_a_dispatch_failure_is_reported_not_raised(self) -> None:
        ctx = FakeDispatchContext(raises=RuntimeError("no tool registry"))
        out = commands.handle(ctx, "status")
        assert "no tool registry" in out

    def test_a_non_json_result_is_passed_through(self) -> None:
        out = commands.handle(FakeDispatchContext("plain text result"), "status")
        assert "plain text result" in out
