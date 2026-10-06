"""Resolving the fallback state file by payload, not by path.

Inside Hermes, ``ctx.state`` is the writer and Hermes files a native plugin's
state under ``plugin-data/agent-plugin-<slug>-<hash>/`` — a digest over the
plugin key, not derivable from the plugin id. Outside Hermes, ``runtime.py``
reads state straight off disk, so it has to find that file the way
``scripts/doctor.py`` does: by the keys it carries, not by the directory it
lives in. A script that resolves the wrong path reports "nothing" in perfect
silence, which is exactly how the weekly metrics job lost the publish ledger.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from atg_plugin import runtime

#: The namespace Hermes gives a native plugin's data; the digest is Hermes'
#: own, so it cannot be derived from the plugin id — that is the point.
HOST_NAMESPACE = "agent-plugin-affiliate-threads-generator-a1b2c3d4"
#: The path-derived default a fresh install writes to.
DEFAULT_NAMESPACE = "affiliate-threads-generator"

LEDGER = {"publish_ledger": {"12": {"product_id": "12", "media_ids": ["ABC"]}}}
AUDIT = {"publish_audit": [{"tool": "threads_check"}]}


def _home() -> Path:
    """The ``HERMES_HOME`` the autouse ``clean_runtime`` fixture chose."""
    return Path(os.environ["HERMES_HOME"])


def _default_file() -> Path:
    return _home() / "plugin-data" / DEFAULT_NAMESPACE / "state.json"


def _write_state(namespace: str, payload: dict, *, mtime_ns: int | None = None) -> Path:
    directory = _home() / "plugin-data" / namespace
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


class TestFallbackStateResolution:
    """The read side has to match how Hermes writes state."""

    def test_a_host_namespaced_file_is_found(self) -> None:
        path = _write_state(HOST_NAMESPACE, LEDGER)

        assert runtime._fallback_state_file() == path
        assert runtime.state_get("publish_ledger") == LEDGER["publish_ledger"]

    def test_another_plugins_state_is_never_returned(self) -> None:
        _write_state("some-other-plugin", {"cursor": {"page": 2}})

        assert runtime._fallback_state_file() == _default_file()
        assert runtime.state_get("publish_ledger", default=None) is None

    def test_the_path_derived_file_wins_when_it_carries_state(self) -> None:
        default = _write_state(DEFAULT_NAMESPACE, LEDGER, mtime_ns=1_000_000_000)
        _write_state(HOST_NAMESPACE, LEDGER, mtime_ns=2_000_000_000)

        assert runtime._fallback_state_file() == default

    def test_the_newest_host_file_wins(self) -> None:
        _write_state("agent-plugin-some-other-plugin-deadbeef", LEDGER, mtime_ns=1_000_000_000)
        newest = _write_state(HOST_NAMESPACE, LEDGER, mtime_ns=2_000_000_000)

        assert runtime._fallback_state_file() == newest

    def test_a_default_without_plugin_keys_defers_to_the_host_file(self) -> None:
        _write_state(DEFAULT_NAMESPACE, {"unrelated": True})
        host = _write_state(HOST_NAMESPACE, AUDIT)

        assert runtime._fallback_state_file() == host
        assert runtime.state_get("publish_audit") == AUDIT["publish_audit"]

    def test_an_unreadable_candidate_is_skipped_not_fatal(self) -> None:
        broken = _home() / "plugin-data" / "agent-plugin-broken-a1b2c3d4"
        broken.mkdir(parents=True)
        (broken / "state.json").write_text("{not json", encoding="utf-8")
        host = _write_state(HOST_NAMESPACE, LEDGER)

        assert runtime._fallback_state_file() == host

    def test_only_unreadable_state_is_not_fatal(self) -> None:
        broken = _home() / "plugin-data" / HOST_NAMESPACE
        broken.mkdir(parents=True)
        (broken / "state.json").write_text("{not json", encoding="utf-8")

        assert runtime.state_get("publish_ledger", default=None) is None
        assert runtime._fallback_state_file() == _default_file()

    def test_a_fresh_install_writes_to_the_path_derived_default(self) -> None:
        runtime.state_set("publish_ledger", {"12": {"product_id": "12"}})

        assert runtime._fallback_state_file() == _default_file()
        assert json.loads(_default_file().read_text(encoding="utf-8")) == {
            "publish_ledger": {"12": {"product_id": "12"}}
        }

    def test_a_write_lands_in_the_resolved_host_file(self) -> None:
        host = _write_state(HOST_NAMESPACE, LEDGER)

        runtime.state_set("publish_audit", AUDIT["publish_audit"])

        assert runtime._fallback_state_file() == host
        payload = json.loads(host.read_text(encoding="utf-8"))
        assert payload["publish_ledger"] == LEDGER["publish_ledger"]
        assert payload["publish_audit"] == AUDIT["publish_audit"]
