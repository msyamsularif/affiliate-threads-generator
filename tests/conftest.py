"""Test fixtures.

The plugin lives at the repository root, and the directory name contains
hyphens, so it cannot be imported as a normal package. It is registered in
``sys.modules`` under a clean name instead — the same trick the skill's
``_bridge.py`` uses, which also means the tests exercise the exact code path the
scripts do.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = "atg_plugin"

if PACKAGE not in sys.modules:
    # Execute the plugin's real __init__.py so `register(ctx)` exists to be tested,
    # while making the hyphenated directory importable under a clean package name.
    _spec = importlib.util.spec_from_file_location(
        PACKAGE,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[PACKAGE] = _module
    _spec.loader.exec_module(_module)

from atg_plugin import config, guardrails, ledger, runtime, threads_client  # noqa: E402

TEST_SHEET_ID = "sheet-test-123"
TEST_TOKEN = "test-access-token"


class FakeState:
    """Stands in for ``ctx.state`` — a dict with a ``set`` method."""

    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key: str, default=None):  # noqa: ANN001, ANN201
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:  # noqa: ANN001
        self.data[key] = value


class FakeContext:
    """Minimal ``PluginContext`` — enough for settings and state."""

    def __init__(self, settings: dict | None = None) -> None:
        self.settings = dict(settings or {})
        self.state = FakeState()
        self.saved: dict = {}

    def get_config(self, key: str, default=None):  # noqa: ANN001, ANN201
        return self.settings.get(key, default)

    def set_config(self, key: str, value) -> None:  # noqa: ANN001
        self.saved[key] = value
        self.settings[key] = value


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolate runtime state and the environment for every test."""
    runtime.reset_for_tests()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    for name in ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "AFFILIATE_SHEET_ID", "AFFILIATE_SHEET_TAB"):
        monkeypatch.delenv(name, raising=False)
    yield
    runtime.reset_for_tests()


@pytest.fixture
def ctx() -> FakeContext:
    """A bound fake context with safe defaults (no sleeping in tests)."""
    context = FakeContext(
        {
            "spreadsheet_id": TEST_SHEET_ID,
            "sheet_tab": "Sheet1",
            "container_wait_seconds": 0,
        }
    )
    runtime.bind(context)
    return context


@pytest.fixture
def settings() -> config.Settings:
    return config.Settings(
        spreadsheet_id=TEST_SHEET_ID,
        sheet_tab="Sheet1",
        threads_access_token=TEST_TOKEN,
        threads_user_id="user-1",
        container_wait_seconds=0,
    )


def build_good_thread(affiliate_url: str = "https://shope.ee/abc123") -> list[dict]:
    """A draft that passes every hard guardrail."""
    return [
        {"text": "Semua orang beli power bank berdasarkan angka mAh terbesar di kotaknya."},
        {"text": "Masalahnya: kapasitas besar selalu berarti berat. 380g itu terasa di saku."},
        {"text": f"Detail lengkapnya ada di sini buat yang penasaran: {affiliate_url}"},
        {"text": f"Link afiliasi: saya dapat komisi kalau kamu beli lewat sini. {affiliate_url}"},
    ]


def scripted_transport(responses: list[tuple[int, dict]]):
    """Return a transport that yields ``responses`` in order, recording requests."""
    calls: list[tuple[str, str, dict | None]] = []
    queue = list(responses)

    def transport(method: str, url: str, data: dict | None):
        calls.append((method, url, data))
        if not queue:
            raise AssertionError(f"unexpected extra request: {method} {url}")
        return queue.pop(0)

    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def happy_path_responses(posts: int = 3) -> list[tuple[int, dict]]:
    """Responses for a clean publish of ``posts`` text-only posts."""
    responses: list[tuple[int, dict]] = []
    for index in range(posts):
        responses.append((200, {"id": f"container-{index + 1}"}))
        responses.append((200, {"id": f"container-{index + 1}", "status": "FINISHED"}))
        responses.append((200, {"id": f"media-{index + 1}"}))
    responses.append(
        (
            200,
            {
                "id": "media-1",
                "permalink": "https://www.threads.net/@tester/post/media-1",
                "username": "tester",
            },
        )
    )
    return responses


__all__ = [
    "FakeContext",
    "FakeState",
    "PLUGIN_DIR",
    "TEST_SHEET_ID",
    "TEST_TOKEN",
    "build_good_thread",
    "config",
    "guardrails",
    "happy_path_responses",
    "ledger",
    "runtime",
    "scripted_transport",
    "threads_client",
]
