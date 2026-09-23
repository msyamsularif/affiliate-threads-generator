"""Tool handler tests.

These cover the properties the specification calls non-negotiable:

* nothing is published without an explicit confirmation
* the Sheet's own state is re-validated, in code, every time
* a failed publish never changes the Sheet
* a successful publish that could not record itself is repaired, not repeated
"""

from __future__ import annotations

import json

import pytest

from atg_plugin import ledger, sheets_client, threads_client, tools
from conftest import happy_path_responses, scripted_transport

AFFILIATE_URL = "https://shope.ee/abc123"


def make_row(
    *,
    product_id: str = "12",
    status: str = "Ready To Generate",
    threads_url: str = "",
    affiliate_url: str = AFFILIATE_URL,
    product: str = "Power Bank 20000mAh",
    row_number: int = 14,
) -> sheets_client.Row:
    return sheets_client.Row(
        row_number=row_number,
        values={
            "id": product_id,
            "product": product,
            "description": "Matte black, 380g, 22.5W PD",
            "affiliate_url": affiliate_url,
            "category": "Power Bank",
            "threads_url": threads_url,
            "status": status,
        },
    )


class FakeSheet:
    """In-memory stand-in for ``sheets_client.SheetClient``."""

    def __init__(self, rows: list[sheets_client.Row] | None = None, *, fail_write: bool = False):
        self.rows = {row.id: row for row in (rows or [])}
        self.fail_write = fail_write
        self.writes: list[dict] = []
        self.reads: list[str] = []

    def require_row(self, product_id: str) -> sheets_client.Row:
        self.reads.append(product_id)
        row = self.rows.get(str(product_id).strip())
        if row is None:
            raise sheets_client.SheetError(
                f"no row with ID {product_id!r} in Sheet1", stage="sheets_read"
            )
        return row

    def write_publish_result(self, row_number: int, *, threads_url: str, status: str) -> None:
        if self.fail_write:
            raise sheets_client.SheetError("sheet is read-only right now", stage="sheets_write")
        self.writes.append({"row": row_number, "threads_url": threads_url, "status": status})

    # -- used by threads_check -------------------------------------------

    def read_rows(self) -> list[sheets_client.Row]:
        return list(self.rows.values())

    def next_eligible(self) -> sheets_client.Row | None:
        eligible = [row for row in self.rows.values() if row.status == "Ready To Generate"]
        return min(eligible, key=lambda row: int(row.id)) if eligible else None

    @property
    def google_api(self) -> str:
        return "/fake/google_api.py"


@pytest.fixture
def publish_env(monkeypatch: pytest.MonkeyPatch, ctx):  # noqa: ANN001, ANN201
    """Wire a fake Sheet + fake Threads transport into the tools module."""
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("THREADS_USER_ID", "user-1")

    def install(sheet: FakeSheet, transport=None):  # noqa: ANN001, ANN202
        monkeypatch.setattr(tools, "SheetClient", lambda settings, **kwargs: sheet)
        if transport is not None:

            def factory(access_token, user_id="", **kwargs):  # noqa: ANN001, ANN202
                return threads_client.ThreadsClient(
                    access_token, user_id, transport=transport, sleep=lambda _s: None, max_retries=0
                )

            monkeypatch.setattr(tools, "ThreadsClient", factory)
        return sheet

    return install


def call(args: dict) -> dict:
    return json.loads(tools.threads_publish(args))


class TestApprovalIsRequired:
    def test_missing_confirm_publish_is_refused(self, publish_env) -> None:  # noqa: ANN001
        sheet = publish_env(FakeSheet([make_row()]))
        result = call({"product_id": "12", "posts": [{"text": "a"}]})
        assert result["ok"] is False
        assert result["stage"] == "approval"
        assert sheet.reads == []  # the Sheet was never even read

    def test_confirm_publish_false_is_refused(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        result = call({"product_id": "12", "posts": [{"text": "a"}], "confirm_publish": False})
        assert result["stage"] == "approval"

    def test_missing_product_id_is_refused(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        result = call({"posts": [{"text": "a"}], "confirm_publish": True})
        assert result["stage"] == "input"

    def test_empty_posts_is_refused(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        result = call({"product_id": "12", "posts": [], "confirm_publish": True})
        assert result["stage"] == "input"


class TestPreconditions:
    def test_unknown_product_id(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(product_id="99")]))
        result = call({"product_id": "12", "posts": [{"text": "a"}], "confirm_publish": True})
        assert result["stage"] == "sheets_read"

    @pytest.mark.parametrize("status", ["Hold", "Cancel", "Done", "In Progress", ""])
    def test_any_other_status_is_refused(self, publish_env, status: str) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(status=status)]))
        result = call({"product_id": "12", "posts": [{"text": "a"}], "confirm_publish": True})
        assert result["ok"] is False
        assert result["stage"] == "precondition"
        assert result["current_status"] == status

    def test_status_comparison_is_exact(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(status="ready to generate")]))
        result = call({"product_id": "12", "posts": [{"text": "a"}], "confirm_publish": True})
        assert result["stage"] == "precondition"

    def test_an_already_published_row_is_refused(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(threads_url="https://threads.net/x")]))
        result = call({"product_id": "12", "posts": [{"text": "a"}], "confirm_publish": True})
        assert result["stage"] == "precondition"
        assert "already" in result["error"].lower()


class TestGuardrails:
    def test_too_few_posts_blocks_publishing(self, publish_env) -> None:  # noqa: ANN001
        sheet = publish_env(FakeSheet([make_row()]))
        result = call(
            {"product_id": "12", "posts": [{"text": "only one"}], "confirm_publish": True}
        )
        assert result["stage"] == "guardrails"
        assert "too_few_posts" in {item["code"] for item in result["violations"]}
        assert sheet.writes == []

    def test_missing_disclosure_blocks_publishing(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"detail: {AFFILIATE_URL}"},
        ]
        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "missing_disclosure" in {item["code"] for item in result["violations"]}

    def test_fabricated_experience_blocks_publishing(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        posts = [
            {"text": "Aku sudah coba ini seminggu."},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]
        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "fabricated_personal_experience" in {item["code"] for item in result["violations"]}

    def test_soft_warnings_do_not_block(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=3))
        sheet = publish_env(FakeSheet([make_row()]), transport)
        posts = [
            {"text": "Produk ini praktis dan nyaman digunakan."},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]
        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["ok"] is True
        assert result["warnings"]
        assert len(sheet.writes) == 1


class TestCredentials:
    def test_missing_token_refuses_without_touching_anything(self, publish_env, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
        sheet = publish_env(FakeSheet([make_row()]))
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]
        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "credentials"
        assert sheet.writes == []


class TestHappyPath:
    def test_publishes_and_records_the_business_state(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=4))
        sheet = publish_env(FakeSheet([make_row()]), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "c"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]

        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        assert result["ok"] is True
        assert result["status"] == "published"
        assert result["posts_published"] == 4
        assert result["threads_url"] == "https://www.threads.net/@tester/post/media-1"

        assert sheet.writes == [
            {
                "row": 14,
                "threads_url": "https://www.threads.net/@tester/post/media-1",
                "status": "Done",
            }
        ]

        record = ledger.get("12")
        assert record is not None
        assert record["sheet_synced"] is True
        assert record["media_ids"] == ["media-1", "media-2", "media-3", "media-4"]

    def test_a_failed_publish_never_changes_the_sheet(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(
            [
                (200, {"id": "container-1"}),
                (200, {"status": "FINISHED"}),
                (400, {"error": {"code": 100, "message": "rate limited"}}),
            ]
        )
        sheet = publish_env(FakeSheet([make_row()]), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]

        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        assert result["ok"] is False
        assert result["stage"] == "publish"
        assert "rate limited" in result["error"]
        assert sheet.writes == []
        assert ledger.get("12") is None

    def test_a_partial_publish_creates_no_ledger_record(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(
            [
                (200, {"id": "container-1"}),
                (200, {"status": "FINISHED"}),
                (200, {"id": "media-1"}),
                (400, {"error": {"code": 100, "message": "second post rejected"}}),
            ]
        )
        sheet = publish_env(FakeSheet([make_row()]), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]
        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["ok"] is False
        assert sheet.writes == []
        assert ledger.get("12") is None


class TestSheetWriteFailureRecovery:
    def test_published_but_sheet_write_failed_is_reported_clearly(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=3))
        sheet = publish_env(FakeSheet([make_row()], fail_write=True), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]

        result = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        assert result["ok"] is True
        assert result["status"] == "published_sheet_write_failed"
        assert "do not publish again" in result["next_step"].lower()

        record = ledger.get("12")
        assert record is not None
        assert record["sheet_synced"] is False
        assert sheet.writes == []

    def test_the_retry_repairs_the_sheet_instead_of_republishing(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=3))
        sheet = publish_env(FakeSheet([make_row()], fail_write=True), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]

        first = call({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert first["status"] == "published_sheet_write_failed"
        calls_after_first_publish = len(transport.calls)

        # The Sheet recovers.
        sheet.fail_write = False
        second = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        assert second["ok"] is True
        assert second["status"] == "sheet_resynced"
        assert second["threads_url"] == first["threads_url"]
        assert len(transport.calls) == calls_after_first_publish  # nothing new published
        assert sheet.writes == [
            {
                "row": 14,
                "threads_url": "https://www.threads.net/@tester/post/media-1",
                "status": "Done",
            }
        ]
        assert ledger.get("12")["sheet_synced"] is True

    def test_resync_still_failing_reports_the_live_url(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=3))
        publish_env(FakeSheet([make_row()], fail_write=True), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]

        call({"product_id": "12", "posts": posts, "confirm_publish": True})
        calls_after_first_publish = len(transport.calls)
        second = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        assert second["ok"] is False
        assert second["stage"] == "sheets_write"
        assert second["already_published"] is True
        assert second["threads_url"] == "https://www.threads.net/@tester/post/media-1"
        assert len(transport.calls) == calls_after_first_publish

    def test_resync_is_skipped_when_the_sheet_already_agrees(self, publish_env) -> None:  # noqa: ANN001
        transport = scripted_transport(happy_path_responses(posts=3))
        sheet = publish_env(FakeSheet([make_row()], fail_write=True), transport)
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": f"#afiliasi {AFFILIATE_URL}"},
        ]
        call({"product_id": "12", "posts": posts, "confirm_publish": True})

        # Someone fixed the Sheet by hand.
        sheet.rows["12"] = make_row(
            status="Done", threads_url="https://www.threads.net/@tester/post/media-1"
        )
        sheet.fail_write = False
        second = call({"product_id": "12", "posts": posts, "confirm_publish": True})

        # The precondition check now sees a non-eligible row and refuses cleanly.
        assert second["ok"] is False
        assert second["stage"] == "precondition"
        assert ledger.get("12")["sheet_synced"] is True


class TestThreadsCheck:
    def test_reports_missing_credentials(self, ctx) -> None:  # noqa: ANN001
        result = json.loads(tools.threads_check({}))
        assert result["ok"] is False
        assert result["checks"]["credentials"]["ok"] is False
        assert "threads credentials missing" in result["problems"]

    def test_reports_settings_without_leaking_secrets(self, publish_env) -> None:  # noqa: ANN001
        result = json.loads(tools.threads_check({"include_sheet": False, "include_token": False}))
        assert "test-token" not in json.dumps(result)
        assert result["settings"]["threads_credentials_configured"] is True

    def test_sheet_probe_reports_the_next_candidate(self, publish_env) -> None:  # noqa: ANN001
        rows = [
            make_row(product_id="1", status="Done"),
            make_row(product_id="2", status="Ready To Generate", row_number=3),
            make_row(product_id="3", status="Ready To Generate", row_number=4),
        ]
        publish_env(FakeSheet(rows))

        result = json.loads(tools.threads_check({"include_token": False}))
        assert result["checks"]["sheets"]["ok"] is True
        # Lowest numeric ID wins, and already-Done rows are excluded.
        assert result["checks"]["next_candidate"]["detail"]["id"] == "2"

    def test_no_candidate_is_reported_as_a_note_not_an_error(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(product_id="1", status="Done")]))

        result = json.loads(tools.threads_check({"include_token": False}))
        assert result["checks"]["next_candidate"]["ok"] is True
        assert result["checks"]["next_candidate"]["detail"] is None
        assert "No row currently has Status" in result["checks"]["next_candidate"]["detail_note"]


class TestHandlersNeverRaise:
    def test_threads_publish_swallows_unexpected_errors(self, monkeypatch) -> None:  # noqa: ANN001
        def explode(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            raise RuntimeError("catastrophic")

        monkeypatch.setattr(tools, "config", type("X", (), {"resolve": staticmethod(explode)}))
        payload = json.loads(tools.threads_publish({"product_id": "1", "confirm_publish": True}))
        assert payload["ok"] is False
        assert payload["stage"] == "internal"

    def test_threads_check_swallows_unexpected_errors(self, monkeypatch) -> None:  # noqa: ANN001
        def explode(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            raise RuntimeError("catastrophic")

        monkeypatch.setattr(tools, "config", type("X", (), {"resolve": staticmethod(explode)}))
        payload = json.loads(tools.threads_check({}))
        assert payload["ok"] is False
        assert payload["stage"] == "internal"
