"""The weekly metrics fetch and its read-only summary.

Both scripts run outside Hermes under whatever ``python3`` the host provides, so
they reach the plugin through ``_bridge``. The tests monkeypatch the plugin's own
modules — which is the same module objects the scripts import — so the fake
Threads client and the fake Sheet are what the scripts actually call.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

from atg_plugin import ledger, sheets_client, threads_client
from conftest import PLUGIN_DIR

SCRIPTS = PLUGIN_DIR / "skills" / "affiliate-threads-generator" / "scripts"

AFFILIATE_URL = "https://shope.ee/abc123"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetch_metrics() -> ModuleType:
    return _load("atg_fetch_metrics", SCRIPTS / "fetch_metrics.py")


@pytest.fixture(scope="module")
def show_metrics() -> ModuleType:
    return _load("atg_show_metrics", SCRIPTS / "show_metrics.py")


class FakeThreadsClient:
    """Canned insights, with per-media failures for the error paths."""

    def __init__(
        self,
        *,
        media: dict | None = None,
        clicks: dict | None = None,
        fail_media: dict | None = None,
        fail_stable: dict | None = None,
        fail_clicks=None,  # noqa: ANN001
    ) -> None:
        self.media = media or {}
        self.clicks = clicks or {}
        self.fail_media = fail_media or {}
        self.fail_stable = fail_stable or {}
        self.fail_clicks = fail_clicks
        self.calls: list[tuple] = []

    def get_media_insights(self, media_id, metrics=None):  # noqa: ANN001, ANN201
        self.calls.append(("media", media_id, tuple(metrics) if metrics else None))
        if metrics is None and media_id in self.fail_media:
            raise self.fail_media[media_id]
        if metrics is not None and media_id in self.fail_stable:
            raise self.fail_stable[media_id]
        return dict(self.media.get(media_id, {}))

    def get_user_insights(self, metric, since=0, until=0):  # noqa: ANN001, ANN201
        self.calls.append(("user", metric, since, until))
        if self.fail_clicks is not None:
            raise self.fail_clicks
        return self.clicks


class FakeSheet:
    def __init__(self, rows=None, *, append_error=None, header=None):  # noqa: ANN001
        self.rows = rows or []
        self.append_error = append_error
        self.appended: list[list[str]] = []
        self.header = None
        self.tab = ""
        #: Canned row 1 for the header check; ``None`` means an empty tab.
        self.header_row = list(header) if header else None
        self.header_writes: list[tuple] = []
        self.header_reads: list[str] = []

    def read_rows(self):  # noqa: ANN201
        return self.rows

    def read_range(self, a1):  # noqa: ANN001, ANN201
        self.header_reads.append(a1)
        return [list(self.header_row)] if self.header_row else []

    def write_row(self, tab, row_number, values):  # noqa: ANN001, ANN201
        self.header_writes.append((tab, row_number, list(values)))
        self.header_row = list(values)

    def append_rows(self, tab, rows, header=()):  # noqa: ANN001, ANN201
        if self.append_error is not None:
            raise self.append_error
        self.tab = tab
        self.header = tuple(header)
        self.appended.extend([list(row) for row in rows])
        return 3


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    """Wire a fake client, Sheet and ledger into the modules the script uses."""

    def install(*, records, client, sheet):  # noqa: ANN001, ANN202
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
        monkeypatch.setattr(
            threads_client, "ThreadsClient", lambda token, user_id="", **kw: client
        )
        monkeypatch.setattr(sheets_client, "SheetClient", lambda settings, **kw: sheet)
        monkeypatch.setattr(ledger, "records", lambda: list(records))
        return client

    return install


def make_record(product_id="12", media_ids=("media-1",), days_ago=1, **metadata):  # noqa: ANN001, ANN201
    published = datetime.now(timezone.utc) - timedelta(days=days_ago)
    record = {
        "product_id": product_id,
        "media_ids": list(media_ids),
        "permalink": "https://www.threads.net/@you/post/media-1",
        "posts_count": len(media_ids),
        "published_at": published.isoformat(timespec="seconds"),
        "publish_mode": "single",
        "sheet_synced": True,
    }
    record.update(metadata)
    return record


def sheet_row(product_id="12", affiliate_url=AFFILIATE_URL):  # noqa: ANN001, ANN201
    return sheets_client.Row(
        row_number=2,
        values={
            "id": product_id,
            "product": "x",
            "affiliate_url": affiliate_url,
            "status": "Done",
        },
    )


def clicks_payload(*pairs):  # noqa: ANN001, ANN201
    return {
        "data": [
            {
                "name": "clicks",
                "link_total_values": [
                    {"value": count, "link_url": url} for url, count in pairs
                ],
            }
        ]
    }


#: Hermes files the state written through ``ctx.state`` under this namespace —
#: a digest of Hermes' own, so the metrics job has to find the file by its
#: payload, exactly like every other out-of-process reader.
HOST_NAMESPACE = "agent-plugin-affiliate-threads-generator-a1b2c3d4"


def _write_host_ledger(records: list[dict]) -> Path:
    """Write a host-namespaced ``state.json`` carrying ``publish_ledger``."""
    directory = Path(os.environ["HERMES_HOME"]) / "plugin-data" / HOST_NAMESPACE
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "state.json"
    path.write_text(
        json.dumps(
            {"publish_ledger": {str(record["product_id"]): record for record in records}}
        ),
        encoding="utf-8",
    )
    return path


class TestFetchMetrics:
    def test_a_happy_run_appends_one_row_per_post(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            media={"media-1": {"views": 1240, "likes": 45, "replies": 6}},
            clicks=clicks_payload((AFFILIATE_URL, 21)),
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main(["--format", "json"])

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fetched"] == 1
        assert payload["clicks"] == {"12": 21}
        assert payload["appended"] == 1
        assert sheet.tab == "Metrics"
        assert sheet.header == fetch_metrics.METRICS_HEADER
        row = sheet.appended[0]
        assert row[0] == "12"
        assert row[1] == "media-1"
        assert row[3] == "1240"
        assert row[9] == "21"
        assert len(row) == len(fetch_metrics.METRICS_HEADER)

    def test_attribution_metadata_reaches_the_new_columns(self, fetch_metrics, wired) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(
            records=[
                make_record(
                    angle_type="trade_off",
                    topic="power bank capacity vs weight",
                    hook_pattern="cost_statement",
                    cta_shape="kalau penasaran",
                )
            ],
            client=client,
            sheet=sheet,
        )

        fetch_metrics.main(["--format", "json"])

        row = sheet.appended[0]
        assert row[10] == "trade_off"
        assert row[11] == "cost_statement"
        assert row[12] == "kalau penasaran"
        assert row[13] == "power bank capacity vs weight"

    def test_a_record_without_metadata_writes_blanks_not_an_exception(self, fetch_metrics, wired) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main(["--format", "json"])

        assert code == 0
        assert sheet.appended[0][10:14] == ["", "", "", ""]

    def test_a_stale_ten_column_header_is_rewritten_before_appending(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()], header=HEADER_ROW)
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main([])  # text format

        assert code == 0
        assert sheet.header_reads == ["Metrics!A1:N1"]
        assert sheet.header_writes == [("Metrics", 1, list(fetch_metrics.METRICS_HEADER))]
        assert "Metrics header: upgraded to 14 columns" in capsys.readouterr().out

    def test_the_json_summary_reports_the_header_upgrade(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()], header=HEADER_ROW)
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main(["--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["header_upgraded"] is True

    def test_a_current_header_is_left_alone(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()], header=list(fetch_metrics.METRICS_HEADER))
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main(["--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["header_upgraded"] is False
        assert sheet.header_writes == []

    def test_an_empty_tab_gets_its_header_from_the_first_append(self, fetch_metrics, wired) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet()
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main(["--format", "json"])

        assert sheet.header_writes == []
        assert sheet.header == fetch_metrics.METRICS_HEADER

    def test_only_the_root_post_is_queried(self, fetch_metrics, wired) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record(media_ids=("media-1", "media-2", "media-3"))], client=client, sheet=sheet)

        fetch_metrics.main(["--format", "json"])

        media_calls = [call for call in client.calls if call[0] == "media"]
        assert media_calls == [("media", "media-1", None)]

    def test_posts_outside_the_window_are_skipped(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row(), sheet_row(product_id="99")])
        wired(
            records=[make_record(days_ago=1), make_record(product_id="99", days_ago=60)],
            client=client,
            sheet=sheet,
        )

        code = fetch_metrics.main(["--format", "json"])

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fetched"] == 1
        assert payload["skipped"] == 1
        assert all(call[1] == "media-1" for call in client.calls if call[0] == "media")

    def test_a_rejected_metric_set_falls_back_to_the_stable_subset(self, fetch_metrics, wired) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            media={"media-1": {"likes": 5, "replies": 1}},
            fail_media={"media-1": threads_client.ThreadsAPIError("bad metric", status=400)},
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main(["--format", "json"])

        assert code == 0
        media_calls = [call for call in client.calls if call[0] == "media"]
        assert media_calls[0][2] is None
        assert media_calls[1][2] == threads_client.STABLE_MEDIA_INSIGHT_METRICS
        assert sheet.appended[0][4] == "5"

    def test_one_failed_post_does_not_stop_the_others(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            media={"media-1": {"likes": 1}},
            fail_media={"media-2": threads_client.ThreadsAPIError("boom", status=500)},
        )
        sheet = FakeSheet([sheet_row(), sheet_row(product_id="13")])
        wired(
            records=[make_record(), make_record(product_id="13", media_ids=("media-2",))],
            client=client,
            sheet=sheet,
        )

        code = fetch_metrics.main(["--format", "json"])

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fetched"] == 1
        assert any("Product 13" in error for error in payload["errors"])

    def test_every_post_failing_is_an_error_exit(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            fail_media={"media-1": threads_client.ThreadsAPIError("boom", status=500)},
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main(["--format", "json"])

        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert sheet.appended == []

    def test_a_scope_error_says_how_to_fix_it(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            fail_media={"media-1": threads_client.ThreadsAPIError("permission denied", status=403)},
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main([])  # text format

        assert code == 1
        out = capsys.readouterr().out
        assert "threads_manage_insights" in out

    def test_nothing_in_the_window_is_not_an_error(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient()
        sheet = FakeSheet()
        wired(records=[make_record(days_ago=90)], client=client, sheet=sheet)

        code = fetch_metrics.main([])

        assert code == 0
        out = capsys.readouterr().out
        assert "No published post inside the 30d window" in out
        assert client.calls == []
        assert sheet.appended == []

    def test_a_dry_run_writes_nothing(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main(["--dry-run"])

        assert code == 0
        out = capsys.readouterr().out
        assert "dry run" in out
        assert sheet.appended == []
        assert sheet.header_writes == []
        assert sheet.header_reads == []

    def test_a_dry_run_prints_the_attribution_for_every_post(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(
            records=[
                make_record(
                    angle_type="trade_off",
                    topic="power bank capacity vs weight",
                    hook_pattern="cost_statement",
                    cta_shape="kalau penasaran",
                )
            ],
            client=client,
            sheet=sheet,
        )

        code = fetch_metrics.main(["--dry-run"])

        assert code == 0
        assert (
            "• Product 12 — angle trade_off · hook cost_statement · cta kalau penasaran "
            "· topic power bank capacity vs weight" in capsys.readouterr().out
        )

    def test_a_dry_run_says_when_a_post_has_no_attribution(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main(["--dry-run"])

        assert "• Product 12 — no attribution" in capsys.readouterr().out

    def test_the_text_summary_names_the_top_post_and_the_week_clicks(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            media={"media-1": {"views": 1240, "likes": 45, "replies": 6}},
            clicks=clicks_payload((AFFILIATE_URL, 21), ("https://example.com/other", 4)),
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main([])

        out = capsys.readouterr().out
        assert "Fetched 1 post(s)" in out
        assert "Top: Product 12 — 1,240 views" in out
        assert "Link clicks (7d): 25" in out
        assert "unmatched link(s)" in out
        assert "Metrics: 1 row(s) appended" in out

    def test_an_unmatched_link_is_reported_not_recorded(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(
            media={"media-1": {"likes": 1}},
            clicks=clicks_payload(("https://example.com/nobody", 4)),
        )
        sheet = FakeSheet([sheet_row()])
        wired(records=[make_record()], client=client, sheet=sheet)

        fetch_metrics.main(["--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["clicks"] == {}
        assert payload["unmatched_links"] == ["https://example.com/nobody"]
        assert sheet.appended[0][9] == "0"

    def test_a_sheet_append_failure_exits_with_the_hint(self, fetch_metrics, wired, capsys) -> None:  # noqa: ANN001
        client = FakeThreadsClient(media={"media-1": {"likes": 1}})
        sheet = FakeSheet(
            [sheet_row()],
            append_error=sheets_client.SheetError("no tab", hint="Create it."),
        )
        wired(records=[make_record()], client=client, sheet=sheet)

        code = fetch_metrics.main([])

        assert code == 1
        out = capsys.readouterr().out
        assert "could not update" in out
        assert "Create it." in out


class TestFetchMetricsFromDisk:
    """Every other test here monkeypatches ``ledger.records``, so the on-disk
    resolution the real job depends on is never exercised. These two do: the
    ledger is written where Hermes writes it, and read back through
    ``runtime.state_get`` with no fakes in between."""

    def test_the_ledger_is_read_through_a_host_namespaced_state_file(self) -> None:
        record = make_record()
        _write_host_ledger([record])

        assert [entry["product_id"] for entry in ledger.records()] == ["12"]

    def test_the_metrics_job_fetches_from_the_on_disk_ledger(
        self, fetch_metrics, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        record = make_record()
        _write_host_ledger([record])
        client = FakeThreadsClient(
            media={"media-1": {"views": 923, "likes": 4}},
            clicks=clicks_payload((AFFILIATE_URL, 10)),
        )
        sheet = FakeSheet([sheet_row()])
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
        monkeypatch.setattr(
            threads_client, "ThreadsClient", lambda token, user_id="", **kw: client
        )
        monkeypatch.setattr(sheets_client, "SheetClient", lambda settings, **kw: sheet)

        code = fetch_metrics.main(["--dry-run", "--format", "json"])

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fetched"] == 1
        assert payload["rows"][0][0] == record["product_id"]
        assert payload["rows"][0][3] == "923"
        assert payload["clicks"] == {record["product_id"]: 10}


class FakeShowSheet:
    def __init__(self, values):  # noqa: ANN001
        self.values = values
        self.reads: list[str] = []

    def read_range(self, a1):  # noqa: ANN001, ANN201
        self.reads.append(a1)
        return self.values


HEADER_ROW = [
    "Product ID",
    "Media ID",
    "Checked At",
    "Views",
    "Likes",
    "Replies",
    "Reposts",
    "Quotes",
    "Shares",
    "Link Clicks",
]


class TestShowMetrics:
    def test_it_prints_the_latest_snapshot_per_product(self, show_metrics, monkeypatch, capsys) -> None:  # noqa: ANN001
        values = [
            HEADER_ROW,
            ["12", "m1", "2026-09-29T03:00:00+00:00", "900", "30", "4", "", "", "", "10"],
            ["12", "m1", "2026-10-06T03:00:00+00:00", "1240", "45", "6", "", "", "", "21"],
        ]
        sheet = FakeShowSheet(values)
        monkeypatch.setattr(sheets_client, "SheetClient", lambda settings, **kw: sheet)

        code = show_metrics.main([])

        assert code == 0
        out = capsys.readouterr().out
        assert "2 snapshot row(s)" in out
        assert (
            "Product 12 — 1,240 views · 45 likes · 6 replies · 21 clicks (7d) · checked 2026-10-06"
            in out
        )

    def test_an_empty_tab_says_so(self, show_metrics, monkeypatch, capsys) -> None:  # noqa: ANN001
        monkeypatch.setattr(sheets_client, "SheetClient", lambda settings, **kw: FakeShowSheet([]))

        assert show_metrics.main([]) == 0
        assert "no snapshots yet" in capsys.readouterr().out

    def test_json_carries_numbers(self, show_metrics, monkeypatch, capsys) -> None:  # noqa: ANN001
        values = [
            HEADER_ROW,
            ["12", "m1", "2026-10-06T03:00:00+00:00", "1240", "45", "6", "", "", "", "21"],
        ]
        monkeypatch.setattr(
            sheets_client, "SheetClient", lambda settings, **kw: FakeShowSheet(values)
        )

        show_metrics.main(["--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["products"][0]["views"] == 1240
        assert payload["products"][0]["link_clicks"] == 21

    def test_rows_with_and_without_attribution_parse_together(self, show_metrics, monkeypatch, capsys) -> None:  # noqa: ANN001
        values = [
            HEADER_ROW,
            ["11", "m0", "2026-09-29T03:00:00+00:00", "900", "30", "4", "", "", "", "10"],
            [
                "12",
                "m1",
                "2026-10-06T03:00:00+00:00",
                "1240",
                "45",
                "6",
                "",
                "",
                "",
                "21",
                "trade_off",
                "cost_statement",
                "kalau penasaran",
                "power bank capacity vs weight",
            ],
        ]
        sheet = FakeShowSheet(values)
        monkeypatch.setattr(sheets_client, "SheetClient", lambda settings, **kw: sheet)

        code = show_metrics.main([])

        assert code == 0
        assert sheet.reads == ["Metrics!A1:N"]
        out = capsys.readouterr().out
        assert (
            "Product 11 — 900 views · 30 likes · 4 replies · 10 clicks (7d) · checked 2026-09-29"
            in out
        )
        assert (
            "Product 12 — 1,240 views · 45 likes · 6 replies · 21 clicks (7d) · "
            "checked 2026-10-06 · angle trade_off · hook cost_statement · "
            "cta kalau penasaran · topic power bank capacity vs weight" in out
        )

    def test_json_carries_attribution_and_keeps_the_existing_keys(self, show_metrics, monkeypatch, capsys) -> None:  # noqa: ANN001
        values = [
            HEADER_ROW,
            ["11", "m0", "2026-09-29T03:00:00+00:00", "900", "30", "4", "", "", "", "10"],
            [
                "12",
                "m1",
                "2026-10-06T03:00:00+00:00",
                "1240",
                "45",
                "6",
                "",
                "",
                "",
                "21",
                "trade_off",
                "cost_statement",
                "kalau penasaran",
                "power bank capacity vs weight",
            ],
        ]
        monkeypatch.setattr(
            sheets_client, "SheetClient", lambda settings, **kw: FakeShowSheet(values)
        )

        show_metrics.main(["--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        first, second = payload["products"]
        assert first["views"] == 900
        assert first["link_clicks"] == 10
        assert first["angle_type"] == ""
        assert first["topic"] == ""
        assert second["angle_type"] == "trade_off"
        assert second["hook_pattern"] == "cost_statement"
        assert second["cta_shape"] == "kalau penasaran"
        assert second["topic"] == "power bank capacity vs weight"
