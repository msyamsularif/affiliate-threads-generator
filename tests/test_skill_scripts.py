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


def _write_jobs(home: Path, jobs: list[dict]) -> None:
    directory = home / "cron"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


class TestDoctorCronJobs:
    """Two jobs matter and they answer different questions: one runs the pipeline,
    the other keeps the Threads token alive. A refresh job names neither the skill
    nor the plugin, so it has to be found on its own terms — and a missing one has
    to fail loudly, because nothing else notices for sixty days."""

    def test_a_missing_table_fails_with_the_command_to_fix_it(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

        jobs, error = doctor._read_cron_jobs()

        assert jobs is None and "no cron job table" in error
        refresh = doctor._token_refresh_check(jobs, error)
        assert refresh["ok"] is False
        assert "hermes cron create" in refresh["hint"]

    def test_the_generation_job_is_not_a_refresh_job(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        _write_jobs(
            home,
            [
                {
                    "name": "affiliate-threads-generator",
                    "schedule": "0 8 * * 0,1,3,5",
                    "prompt": "Load the skill affiliate-threads-generator:affiliate-threads-generator",
                }
            ],
        )
        monkeypatch.setenv("HERMES_HOME", str(home))

        jobs, error = doctor._read_cron_jobs()

        assert doctor._cron_check(jobs, error)["ok"] is True
        refresh = doctor._token_refresh_check(jobs, error)
        assert refresh["ok"] is False
        assert refresh["detail"] == "no cron job refreshes the Threads token"

    def test_a_refresh_job_does_not_answer_for_the_generation_job(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        _write_jobs(home, [{"name": "threads-token-refresh", "schedule": "0 9 1 * *"}])
        monkeypatch.setenv("HERMES_HOME", str(home))

        jobs, error = doctor._read_cron_jobs()

        assert doctor._token_refresh_check(jobs, error)["ok"] is True
        assert doctor._cron_check(jobs, error)["ok"] is False

    @pytest.mark.parametrize(
        "job",
        [
            {"name": "threads-token-refresh", "schedule": "0 9 1 * *"},
            {"name": "monthly", "script": "refresh-threads-token.sh"},
            {"name": "monthly", "prompt": "Run scripts/threads_token.py refresh --write-env."},
            {"prompt": "Refresh the Threads access token, then restart the gateway."},
        ],
    )
    def test_every_wording_of_the_job_counts(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, job: dict
    ) -> None:
        home = tmp_path / "hermes"
        _write_jobs(home, [job])
        monkeypatch.setenv("HERMES_HOME", str(home))

        jobs, error = doctor._read_cron_jobs()

        assert doctor._token_refresh_check(jobs, error)["ok"] is True

    def test_an_unreadable_table_reports_the_reason(
        self, doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes"
        (home / "cron").mkdir(parents=True)
        (home / "cron" / "jobs.json").write_text('{"jobs": 3}', encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))

        jobs, error = doctor._read_cron_jobs()

        assert jobs is None
        assert error == "unexpected jobs.json shape"
        assert doctor._token_refresh_check(jobs, error)["ok"] is False
