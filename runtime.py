"""Plugin-scoped runtime access: settings, durable state, and the host context.

Hermes hands ``register(ctx)`` a ``PluginContext`` once at startup, but tool
handlers and hook callbacks only receive ``(args, **kwargs)``. This module is
the single place that bridges the two, and it degrades gracefully when it is
used outside Hermes (unit tests, one-off scripts) by falling back to a
profile-local JSON file for state.

Settings take the same shape. Inside Hermes the host resolves
``plugins.entries.<id>.settings.*`` for us; outside it, there is no ``ctx`` — so
this module reads that same ``config.yaml`` itself (``config_file.py``) rather
than falling straight through to the defaults. Without that, a script would
enforce different guardrails than the tool it is supposed to predict.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import config_file

logger = logging.getLogger(__name__)

#: The plugin's own id — the manifest's ``name``, the install directory, and the
#: name this plugin's data is filed under. Defined here, the lowest layer, so
#: every module that needs it reads one literal.
PLUGIN_ID = "affiliate-threads-generator"

_lock = threading.RLock()
_ctx: Any = None
_fallback_state_path: Path | None = None

#: Last ``config.yaml`` read, keyed by ``(path, mtime_ns, size)`` so a tool call
#: resolving ~30 settings does not re-read the file 30 times.
_config_file_cache: tuple[tuple[str, int, int], config_file.ConfigFile] | None = None


def bind(ctx: Any) -> None:  # noqa: ANN401 - PluginContext is host-provided
    """Remember the host plugin context. Called once from ``register(ctx)``."""
    global _ctx
    with _lock:
        _ctx = ctx


def context() -> Any:  # noqa: ANN401
    """The bound ``PluginContext``, or ``None`` when running outside Hermes."""
    return _ctx


def has_context() -> bool:
    return _ctx is not None


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

def get_setting(key: str, default: Any = None) -> Any:  # noqa: ANN401
    """Read a plugin setting, tolerating any host-side failure.

    Resolution is: ``plugins.entries.<id>.settings.<key>`` (via ``ctx.get_config``
    inside Hermes, or read from ``config.yaml`` when there is no host context) ->
    environment variable -> ``default``.
    """
    ctx = _ctx
    if ctx is not None:
        try:
            value = ctx.get_config(key, default=None)
        except Exception:  # pragma: no cover - defensive
            logger.debug("ctx.get_config(%r) failed", key, exc_info=True)
            value = None
        if value not in (None, "", [], {}):
            return value

    value = config_file_settings().get(key)
    if value not in (None, "", [], {}):
        return value

    env_key = key.upper()
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return default


def _read_config_file() -> config_file.ConfigFile:
    """The plugin's settings block, cached until the file itself changes."""
    global _config_file_cache

    path = config_file.config_path()
    try:
        stat = path.stat()
        stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        with _lock:
            _config_file_cache = None
        return config_file.ConfigFile(path=path)

    with _lock:
        if _config_file_cache is not None and _config_file_cache[0] == stamp:
            return _config_file_cache[1]
        result = config_file.load(PLUGIN_ID, path=path)
        _config_file_cache = (stamp, result)
    if result.warning:
        logger.warning("plugin settings: %s", result.warning)
    return result


def config_file_settings() -> dict[str, Any]:
    """``plugins.entries.<id>.settings`` from Hermes' ``config.yaml``.

    Empty when there is no config file, and also when it exists but could not be
    read confidently — ``settings_note()`` is the case a caller should surface
    to the human.
    """
    return dict(_read_config_file().settings)


def settings_source() -> dict[str, Any]:
    """Where settings are coming from, for the doctor and the scripts."""
    path = config_file.config_path()
    if _ctx is not None:
        return {"source": "host", "path": str(path), "warning": ""}
    result = _read_config_file()
    if not result.found:
        return {"source": "defaults", "path": str(path), "warning": ""}
    return {
        "source": "config_file" if not result.warning else "defaults",
        "path": str(path),
        "settings": len(result.settings),
        "warning": result.warning,
    }


def settings_note() -> str:
    """A one-line warning when the plugin's settings could not be read.

    Empty in the normal case. Scripts print this to stderr so a lint that ran
    with different rules than the publish tool says so, instead of implying a
    clean bill of health.
    """
    if _ctx is not None:
        return ""
    return _read_config_file().warning


def set_setting(key: str, value: Any) -> bool:  # noqa: ANN401
    """Persist a plugin setting. Returns ``False`` when no host context exists."""
    ctx = _ctx
    if ctx is None:
        return False
    try:
        ctx.set_config(key, value)
        return True
    except Exception:  # pragma: no cover - defensive
        logger.debug("ctx.set_config(%r) failed", key, exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Durable state
# --------------------------------------------------------------------------- #

def state_get(key: str, default: Any = None) -> Any:  # noqa: ANN401
    """Read plugin-owned runtime state (profile-scoped, atomic on the host)."""
    ctx = _ctx
    if ctx is not None:
        try:
            return ctx.state.get(key, default=default)
        except Exception:  # pragma: no cover - defensive
            logger.debug("ctx.state.get(%r) failed", key, exc_info=True)
    store = _read_fallback_state()
    return store.get(key, default)


def state_set(key: str, value: Any) -> None:  # noqa: ANN401
    """Write plugin-owned runtime state."""
    ctx = _ctx
    if ctx is not None:
        try:
            ctx.state.set(key, value)
            return
        except Exception:  # pragma: no cover - defensive
            logger.debug("ctx.state.set(%r) failed", key, exc_info=True)
    store = _read_fallback_state()
    store[key] = value
    _write_fallback_state(store)


def _fallback_state_file() -> Path:
    """Where this plugin's state lives when there is no host context.

    Inside Hermes, ``ctx.state`` is the writer and Hermes namespaces a native
    plugin's state as ``plugin-data/agent-plugin-<slug>-<hash>/`` — a deliberate
    choice on its side, Windows-safe and collision-proof, but not derivable from
    the plugin id. This fallback therefore lands in a *sibling* directory, and
    the two can legitimately disagree. Anything reading state from disk has to
    key on the payload rather than the path; ``scripts/doctor.py`` scans the
    whole ``plugin-data`` tree for exactly that reason.

    ``plugins.plugin_storage.plugin_data_dir`` is the sanctioned helper and
    resolves this same ``plugin-data/<plugin>/`` path, so it is preferred when
    Hermes is importable. It is imported lazily because this module is also
    loaded by the skill's scripts, which may run outside Hermes' venv.
    """
    global _fallback_state_path
    if _fallback_state_path is None:
        try:
            from plugins.plugin_storage import plugin_data_dir

            _fallback_state_path = plugin_data_dir(PLUGIN_ID) / "state.json"
        except Exception:  # noqa: BLE001 - not importable outside Hermes
            root = os.environ.get("HERMES_HOME")
            base = Path(root) if root else Path.home() / ".hermes"
            _fallback_state_path = base / "plugin-data" / PLUGIN_ID / "state.json"
    return _fallback_state_path


def _read_fallback_state() -> dict:
    path = _fallback_state_file()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        logger.warning("plugin state at %s is unreadable; starting fresh", path)
        return {}


def _write_fallback_state(store: dict) -> None:
    path = _fallback_state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(store, handle, ensure_ascii=False, indent=2, sort_keys=True)
            tmp = Path(handle.name)
        tmp.replace(path)
    except OSError:  # pragma: no cover - defensive
        logger.warning("could not persist plugin state to %s", path, exc_info=True)


def reset_for_tests() -> None:
    """Drop the bound context and cached reads (test helper)."""
    global _ctx, _fallback_state_path, _config_file_cache
    with _lock:
        _ctx = None
        _fallback_state_path = None
        _config_file_cache = None
