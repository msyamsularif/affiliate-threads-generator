"""Lifecycle hooks.

``pre_tool_call``
    Escalates every ``threads_publish`` call to Hermes' own human-approval gate.
    This is the load-bearing one: the specification requires human approval
    before every publish, and an instruction the model is asked to follow is not
    a guarantee. The runtime enforcing it is.

``post_tool_call``
    Appends an audit line for publish attempts, in the log and in plugin state,
    so "what did this thing actually push?" is answerable without reading the
    model's transcript.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import runtime

logger = logging.getLogger(__name__)

_AUDIT_KEY = "publish_audit"
_AUDIT_LIMIT = 50

_WATCHED_TOOLS = {"threads_publish", "threads_check"}


def on_pre_tool_call(
    tool_name: str = "",
    args: dict | None = None,
    task_id: str = "",  # noqa: ARG001 - part of the hook payload
    **kwargs: Any,  # noqa: ANN401
) -> dict[str, Any] | None:
    """Ask the human to confirm before an irreversible publish executes."""
    if tool_name != "threads_publish":
        return None

    if not _setting_bool("require_approval_prompt", default=True):
        logger.info("approval gate disabled by config; threads_publish proceeds unprompted")
        return None

    args = args or {}
    product_id = str(args.get("product_id") or "(no product_id)")
    posts = args.get("posts") or []
    if not isinstance(posts, list):
        posts = []

    lines = [
        "Publish to Meta Threads?",
        f"Product ID: {product_id}",
        f"Posts: {len(posts)}",
        "",
    ]
    budget = 1800
    for index, post in enumerate(posts):
        text = post.get("text", "") if isinstance(post, dict) else str(post)
        block = f"--- post {index + 1} ---\n{text}"
        if len(block) > budget:
            block = block[:budget] + "\n[... truncated ...]"
        lines.append(block)
        budget -= len(block)
        if budget <= 0:
            lines.append("[... remaining posts truncated ...]")
            break

    lines.append("")
    lines.append(
        "This cannot be undone by this tool. Approve only if you already reviewed this exact "
        "copy in the conversation."
    )

    return {"action": "approve", "message": "\n".join(lines)}


def on_post_tool_call(
    tool_name: str = "",
    args: dict | None = None,
    result: str = "",
    task_id: str = "",
    duration_ms: int = 0,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """Record what a publish/check call actually did."""
    if tool_name not in _WATCHED_TOOLS:
        return

    args = args or {}
    parsed = _parse(result)
    outcome = str(parsed.get("status") or ("ok" if parsed.get("ok") else "error"))

    logger.info(
        "audit %s product_id=%s outcome=%s ok=%s duration_ms=%s",
        tool_name,
        args.get("product_id"),
        outcome,
        parsed.get("ok"),
        duration_ms,
    )
    if parsed.get("ok") is False:
        logger.warning(
            "audit %s failed at stage=%s: %s",
            tool_name,
            parsed.get("stage"),
            parsed.get("error"),
        )

    _append_audit(
        {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool_name,
            "task_id": task_id,
            "product_id": args.get("product_id"),
            "posts": len(args.get("posts") or []) if isinstance(args.get("posts"), list) else None,
            "outcome": outcome,
            "ok": parsed.get("ok"),
            "stage": parsed.get("stage"),
            "error": parsed.get("error"),
            "threads_url": parsed.get("threads_url"),
            "media_ids": parsed.get("media_ids"),
            "approval_note": args.get("approval_note"),
            "duration_ms": duration_ms,
        }
    )


def _parse(result: str) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    try:
        parsed = json.loads(result or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _append_audit(entry: dict[str, Any]) -> None:
    try:
        history = runtime.state_get(_AUDIT_KEY, default=[])
        if not isinstance(history, list):
            history = []
        history.append(entry)
        runtime.state_set(_AUDIT_KEY, history[-_AUDIT_LIMIT:])
    except Exception:  # pragma: no cover - auditing must never break the tool loop
        logger.debug("could not persist the publish audit entry", exc_info=True)


def _setting_bool(key: str, *, default: bool) -> bool:
    value = runtime.get_setting(key, default=None)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)
