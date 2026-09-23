"""The skill's helper scripts.

They run outside Hermes — no ``ctx``, no plugin loader — and read the plugin's
durable state straight off disk. That is the one place where guessing at a path
fails silently: a script looking in the wrong directory reports "nothing wrong"
instead of erroring, so the check it performs quietly stops existing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from conftest import PLUGIN_DIR

DOCTOR_PATH = (
    PLUGIN_DIR / "skills" / "affiliate-threads-generator" / "scripts" / "doctor.py"
)

#: The two namespaces a ledger can end up under. Inside Hermes, ``ctx.state`` is
#: the writer and Hermes files a native plugin's state under
#: ``agent-plugin-<slug>-<hash>/`` — the digest is Hermes' own, so the directory
#: name cannot be derived from the plugin id, which is the point of these tests.
RUNTIME_NAMESPACE = "agent-plugin-affiliate-threads-generator-a1b2c3d4"
SCRIPT_NAMESPACE = "affiliate-threads-generator"


@pytest.fixture(scope="module")
def doctor() -> ModuleType:
    """Load ``doctor.py`` by path — it is a script, not an importable package."""
    spec = importlib.util.spec_from_file_location("atg_doctor", DOCTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_ledger(home: Path, namespace: str, *, synced: bool) -> None:
    directory = home / "plugin-data" / namespace
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "state.json").write_text(
        json.dumps(
            {
                "publish_ledger": {
                    "12": {
                        "product_id": "12",
                        "media_ids": ["ABC"],
                        "permalink": "https://www.threads.net/@you/post/ABC",
                        "sheet_synced": synced,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


class TestDoctorLedgerDiscovery:
    """``_unsynced_publishes`` is reached directly: the doctor's earlier checks
    need an installed plugin under ``$HERMES_HOME``, and this is the one check
    whose answer depends on a directory it has to find for itself."""

    def test_finds_a_publish_written_through_ctx_state(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        _write_ledger(home, RUNTIME_NAMESPACE, synced=False)
        monkeypatch.setenv("HERMES_HOME", str(home))

        records = doctor._unsynced_publishes()

        assert [record["product_id"] for record in records] == ["12"]

    def test_finds_a_publish_written_by_the_scripts(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        _write_ledger(home, SCRIPT_NAMESPACE, synced=False)
        monkeypatch.setenv("HERMES_HOME", str(home))

        records = doctor._unsynced_publishes()

        assert [record["product_id"] for record in records] == ["12"]

    def test_a_synced_publish_is_not_reported(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        _write_ledger(home, RUNTIME_NAMESPACE, synced=True)
        monkeypatch.setenv("HERMES_HOME", str(home))

        assert doctor._unsynced_publishes() == []

    def test_another_plugins_state_is_ignored(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        directory = home / "plugin-data" / "some-other-plugin"
        directory.mkdir(parents=True)
        (directory / "state.json").write_text(
            json.dumps({"cursor": {"page": 2}}), encoding="utf-8"
        )
        monkeypatch.setenv("HERMES_HOME", str(home))

        assert doctor._unsynced_publishes() == []

    def test_missing_state_home_is_not_fatal(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nothing-here"))

        assert doctor._unsynced_publishes() == []

    def test_unreadable_state_is_not_fatal(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        directory = home / "plugin-data" / RUNTIME_NAMESPACE
        directory.mkdir(parents=True)
        (directory / "state.json").write_text('{"publish_ledger":', encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))

        assert doctor._unsynced_publishes() == []
