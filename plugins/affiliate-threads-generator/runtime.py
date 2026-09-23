"""Plugin-scoped runtime access: settings, durable state, and the host context.

Hermes hands ``register(ctx)`` a ``PluginContext`` once at startup, but tool
handlers and hook callbacks only receive ``(args, **kwargs)``. This module is
the single place that bridges the two, and it degrades gracefully when it is
used outside Hermes (unit tests, one-off scripts) by falling back to a
profile-local JSON file for state.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_ctx: Any = None
_fallback_state_path: Path | None = None


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

    Resolution is: ``plugins.entries.<id>.settings.<key>`` in ``config.yaml``
    (via ``ctx.get_config``) -> environment variable -> ``default``.
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

    env_key = key.upper()
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    return default


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
    global _fallback_state_path
    if _fallback_state_path is None:
        root = os.environ.get("HERMES_HOME")
        base = Path(root) if root else Path.home() / ".hermes"
        _fallback_state_path = base / "plugin-data" / "affiliate-threads-generator" / "state.json"
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
    """Drop the bound context and the fallback state path (test helper)."""
    global _ctx, _fallback_state_path
    with _lock:
        _ctx = None
        _fallback_state_path = None
