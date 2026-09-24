"""End-to-end integration through the real code paths.

The unit tests stub the Sheet client. This one does not: it writes a fake
``google_api.py`` to disk, points the settings at it, and lets
``threads_publish`` shell out exactly as it does in production. Only the Threads
API is faked, because that is the one boundary we cannot exercise locally.

What it proves:

* the subprocess plumbing to the bundled google-workspace skill works
* a row is read, validated, published, and written back in one call
* a second attempt for the same product is refused by the Sheet's own state
* the publish ledger ends up consistent
"""

from __future__ import annotations

import ast
import importlib
import json
import textwrap
from pathlib import Path

import pytest

from atg_plugin import ledger, runtime, tools
from conftest import PLUGIN_DIR, happy_path_responses, scripted_transport

FAKE_GAPI = '''\
#!/usr/bin/env python3
"""Fake google-workspace CLI: just enough `sheets get` / `sheets update`."""
import json
import sys
from pathlib import Path

STATE = Path({state!r})
args = sys.argv[1:]

if len(args) < 2 or args[0] != "sheets":
    print(json.dumps({{"error": "unsupported command"}}), file=sys.stderr)
    sys.exit(2)

command = args[1]
if command == "get":
    print(STATE.read_text(encoding="utf-8"))
elif command == "update":
    values = json.loads(args[args.index("--values") + 1])[0]
    ref = args[3].split("!")[1].split(":")[0]
    column = "".join(ch for ch in ref if ch.isalpha())
    row_number = int("".join(ch for ch in ref if ch.isdigit()))
    start = 0
    for ch in column:
        start = start * 26 + (ord(ch) - ord("A") + 1)
    sheet = json.loads(STATE.read_text(encoding="utf-8"))
    while len(sheet) < row_number:
        sheet.append([])
    row = sheet[row_number - 1]
    while len(row) < start + len(values) - 1:
        row.append("")
    for offset, value in enumerate(values):
        row[start - 1 + offset] = value
    STATE.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({{"status": "ok", "updatedCells": len(values)}}))
else:
    print(json.dumps({{"error": f"unknown command {{command}}"}}), file=sys.stderr)
    sys.exit(2)
'''

SHEET = [
    ["ID", "Product", "Description", "Affiliate URL", "Category", "Threads URL", "Used", "Testimonial", "Status"],
    ["1", "Power Bank 20000mAh", "Matte black, 380g", "https://shope.ee/aaa", "Power Bank", "https://t/x", "", "", "Done"],
    ["2", "Wireless Earbuds X", "TWS, BT 5.3, 6 jam, IPX4", "https://shope.ee/bbb", "Audio", "", "", "", "Ready To Generate"],
]

AFFILIATE_URL = "https://shope.ee/bbb"

POSTS = [
    {"text": "Klaim 6 jam per charge itu angka yang menarik, tapi ada satu hal yang jarang dibahas."},
    {"text": "Dari spesifikasi produknya: BT 5.3 dan IPX4. Kombinasi ini yang biasanya bikin beda di luar ruangan."},
    {"text": "Keterbatasannya: angka 6 jam itu untuk volume normal. Pasang volume penuh terus, angkanya turun."},
    {"text": f"Detail lengkapnya di sini:\n{AFFILIATE_URL}"},
]


@pytest.fixture
def end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # noqa: ANN201
    """Wire a real SheetClient against a fake google_api.py, plus a fake Threads API."""
    state = tmp_path / "sheet.json"
    state.write_text(json.dumps(SHEET, ensure_ascii=False), encoding="utf-8")

    gapi = tmp_path / "google_api.py"
    gapi.write_text(textwrap.dedent(FAKE_GAPI.format(state=str(state))), encoding="utf-8")

    monkeypatch.setenv("HERMES_GAPI_PATH", str(gapi))
    monkeypatch.setenv("AFFILIATE_SHEET_ID", "integration-sheet")
    monkeypatch.setenv("AFFILIATE_SHEET_TAB", "Sheet1")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "integration-token")
    monkeypatch.setenv("THREADS_USER_ID", "user-1")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    class FakeState:
        def __init__(self) -> None:
            self.data: dict = {}

        def get(self, key: str, default=None):  # noqa: ANN001, ANN201
            return self.data.get(key, default)

        def set(self, key: str, value) -> None:  # noqa: ANN001
            self.data[key] = value

    class FakeCtx:
        def __init__(self) -> None:
            self.settings = {
                "spreadsheet_id": "integration-sheet",
                "sheet_tab": "Sheet1",
                "container_wait_seconds": 0,
            }
            self.state = FakeState()

        def get_config(self, key: str, default=None):  # noqa: ANN001, ANN201
            return self.settings.get(key, default)

    runtime.bind(FakeCtx())

    transport = scripted_transport(happy_path_responses(posts=len(POSTS)))

    def factory(access_token, user_id="", **kwargs):  # noqa: ANN001, ANN202
        module = importlib.import_module("atg_plugin.threads_client")
        return module.ThreadsClient(
            access_token, user_id, transport=transport, sleep=lambda _s: None, max_retries=0
        )

    monkeypatch.setattr(tools, "ThreadsClient", factory)

    def read_sheet() -> list[list[str]]:
        return json.loads(state.read_text(encoding="utf-8"))

    return {"transport": transport, "read_sheet": read_sheet, "state_path": state}


def call(args: dict) -> dict:
    """Call the tool the way the skill does, topic tag included.

    ``require_topic_tag`` is on by default, so every thread publish needs one;
    the reply stage ignores it because a tag belongs to the root post.
    """
    return json.loads(tools.threads_publish({"topic_tag": "audio bluetooth", **args}))


def install_transport(monkeypatch: pytest.MonkeyPatch, transport) -> None:  # noqa: ANN001
    """Point the tool at a scripted Threads transport."""

    def factory(access_token, user_id="", **kwargs):  # noqa: ANN001, ANN202
        module = importlib.import_module("atg_plugin.threads_client")
        return module.ThreadsClient(
            access_token, user_id, transport=transport, sleep=lambda _s: None, max_retries=0
        )

    monkeypatch.setattr(tools, "ThreadsClient", factory)


class TestFullPublishCycle:
    def test_publishes_and_records_the_row(self, end_to_end) -> None:  # noqa: ANN001
        before = end_to_end["read_sheet"]()
        assert before[2][8] == "Ready To Generate"
        assert before[2][5] == ""

        result = call(
            {
                "product_id": "2",
                "posts": POSTS,
                "confirm_publish": True,
                "approval_note": "saya approve",
            }
        )

        assert result["ok"] is True, result
        assert result["status"] == "published"

        after = end_to_end["read_sheet"]()
        assert after[2][8] == "Done"
        assert after[2][5] == "https://www.threads.net/@tester/post/media-1"
        # The other rows are untouched.
        assert after[1][8] == "Done"
        assert after[1][5] == "https://t/x"
        assert after[0] == before[0]

    def test_the_second_attempt_is_refused_by_the_sheet(self, end_to_end) -> None:  # noqa: ANN001
        first = call({"product_id": "2", "posts": POSTS, "confirm_publish": True})
        assert first["ok"] is True
        calls_after_publish = len(end_to_end["transport"].calls)

        second = call({"product_id": "2", "posts": POSTS, "confirm_publish": True})

        assert second["ok"] is False
        assert second["stage"] == "precondition"
        assert second["current_status"] == "Done"
        # The Sheet already knows, so nothing was even sent to Threads.
        assert len(end_to_end["transport"].calls) == calls_after_publish

    def test_the_ledger_matches_the_sheet(self, end_to_end) -> None:  # noqa: ANN001
        call({"product_id": "2", "posts": POSTS, "confirm_publish": True})
        record = ledger.get("2")
        assert record is not None
        assert record["sheet_synced"] is True
        assert record["permalink"] == "https://www.threads.net/@tester/post/media-1"
        assert ledger.unsynced_records() == []

    def test_a_held_row_is_never_published(self, end_to_end) -> None:  # noqa: ANN001
        # Simulate the human replying "hold" between the preview and the approval.
        sheet = end_to_end["read_sheet"]()
        sheet[2][8] = "Hold"
        end_to_end["state_path"].write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")

        result = call({"product_id": "2", "posts": POSTS, "confirm_publish": True})

        assert result["ok"] is False
        assert result["stage"] == "precondition"
        assert end_to_end["transport"].calls == []
        assert end_to_end["read_sheet"]()[2][8] == "Hold"

    def test_guardrails_run_against_the_real_row(self, end_to_end) -> None:  # noqa: ANN001
        """The affiliate URL is taken from the Sheet, not from the caller."""
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/SOMETHING-ELSE"},
        ]
        result = call({"product_id": "2", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "affiliate_url_not_in_thread" in {item["code"] for item in result["violations"]}
        assert end_to_end["transport"].calls == []

    def test_missing_google_api_is_reported_cleanly(self, monkeypatch, end_to_end) -> None:  # noqa: ANN001
        monkeypatch.setenv("HERMES_GAPI_PATH", str(Path("/nonexistent/google_api.py")))
        monkeypatch.setattr(
            "atg_plugin.sheets_client.discover_google_api", lambda explicit="": None
        )
        result = call({"product_id": "2", "posts": POSTS, "confirm_publish": True})
        assert result["ok"] is False
        assert result["stage"] == "sheets_read"
        assert "google_api.py" in result["error"]
        assert result["hint"]


class TestTwoStageCycle:
    """The deferred-link flow, through the real Sheet plumbing.

    Nothing here is new plumbing except the mode: the first call parks the row in
    the link-pending status, the second attaches the affiliate link as a reply,
    and the Sheet's own state is what tells the second call which half it is.
    """

    THREAD = [
        {"text": "Klaim 6 jam per charge itu menarik, tapi ada satu hal yang jarang dibahas."},
        {"text": "Dari spesifikasi produknya: BT 5.3 dan IPX4."},
        {"text": "Keterbatasannya: angka 6 jam itu untuk volume normal."},
    ]
    LINK_REPLY = [{"text": f"Detail lengkapnya di sini: {AFFILIATE_URL}\n\nLink afiliasi."}]

    def test_the_thread_goes_out_first_and_the_link_follows(self, end_to_end, monkeypatch) -> None:  # noqa: ANN001
        runtime.context().settings["publish_mode"] = "two_stage"
        transport = scripted_transport(
            happy_path_responses(posts=3)
            + [
                (200, {"id": "container-link"}),
                (200, {"id": "container-link", "status": "FINISHED"}),
                (200, {"id": "media-link"}),
            ]
        )
        install_transport(monkeypatch, transport)

        first = call({"product_id": "2", "posts": self.THREAD, "confirm_publish": True})

        assert first["ok"] is True, first
        assert first["status"] == "published_awaiting_link"
        after_first = end_to_end["read_sheet"]()
        assert after_first[2][8] == "Link Pending"
        assert after_first[2][5] == "https://www.threads.net/@tester/post/media-1"
        assert "shope.ee" not in json.dumps(self.THREAD)

        second = call({"product_id": "2", "posts": self.LINK_REPLY, "confirm_publish": True})

        assert second["ok"] is True, second
        assert second["status"] == "link_reply_published"
        assert second["link_media_id"] == "media-link"
        after_second = end_to_end["read_sheet"]()
        assert after_second[2][8] == "Done"
        assert after_second[2][5] == after_first[2][5]  # the thread URL is unchanged
        # The reply really was a reply: it answers the last post of the thread.
        assert transport.calls[-3][2]["reply_to_id"] == "media-3"
        assert ledger.get("2")["link_sheet_synced"] is True

    def test_the_reply_is_still_held_to_the_hard_rules(self, end_to_end, monkeypatch) -> None:  # noqa: ANN001
        runtime.context().settings["publish_mode"] = "two_stage"
        transport = scripted_transport(happy_path_responses(posts=3))
        install_transport(monkeypatch, transport)
        call({"product_id": "2", "posts": self.THREAD, "confirm_publish": True})
        calls = len(transport.calls)

        result = call(
            {
                "product_id": "2",
                "posts": [{"text": "Linknya ada di bio ya."}],
                "confirm_publish": True,
            }
        )

        assert result["stage"] == "guardrails"
        assert len(transport.calls) == calls
        assert end_to_end["read_sheet"]()[2][8] == "Link Pending"


class TestPythonCompatibility:
    def test_module_imports_under_the_running_interpreter(self) -> None:
        """Guards against import-time-only failures in older interpreters."""
        for name in (
            "config",
            "guardrails",
            "hooks",
            "ledger",
            "runtime",
            "schemas",
            "sheets_client",
            "threads_client",
            "tools",
        ):
            importlib.import_module(f"atg_plugin.{name}")

    def test_no_pep604_unions_are_evaluated_at_import_time(self) -> None:
        """``X | Y`` is fine inside an annotation, but not as a runtime expression.

        The plugin's modules are imported by the skill's scripts, which run under
        whatever ``python3`` the host provides — on macOS that is often 3.9, where
        evaluating ``dict[str, str] | None`` raises ``TypeError``.
        """
        offenders: list[str] = []

        for path in sorted(PLUGIN_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:  # module level only
                value = getattr(node, "value", None)
                if value is None:
                    continue
                for candidate in ast.walk(value):
                    if not isinstance(candidate, ast.BinOp | ast.BitOr):
                        continue
                    operands = (candidate.left, candidate.right)
                    if any(isinstance(op, ast.Subscript) for op in operands):
                        offenders.append(f"{path.name}:{candidate.lineno}")

        assert not offenders, (
            "PEP 604 unions evaluated at import time break Python 3.9 "
            f"(which the skill scripts may run on): {offenders}"
        )

    def test_the_transport_alias_is_importable(self) -> None:
        module = importlib.import_module("atg_plugin.threads_client")
        assert module.Transport is not None
