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

``pre_llm_call``
    Points the agent at the bundled skill when a turn looks like Affiliate
    Threads work. A plugin skill is namespaced and kept out of the system
    prompt's skill index, so without this the model would never learn that
    ``affiliate-threads-generator:affiliate-threads-generator`` exists — the one
    thing that used to require installing the same skill a second time through
    the skills hub.
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

#: The plugin's own namespace, which is also the bundled skill's directory name.
PLUGIN_ID = runtime.PLUGIN_ID
SKILL_ID = f"{PLUGIN_ID}:{PLUGIN_ID}"

#: Phrases that mean "this turn is Affiliate Threads work", lowercased and
#: matched as substrings. Deliberately narrow: the words that only make sense
#: here, not the bare English verbs that show up in unrelated conversations.
_TRIGGERS = (
    "affiliate",
    "afiliasi",
    "buatkan content",
    "buat konten",
    "bikin konten",
    "generate lagi",
    "generate content",
    "regenerate",
    "hold dulu",
    "jangan dipublish",
    "saya approve",
    "post aja",
)

#: ``"threads"`` is deliberately not a trigger on its own: it is an ordinary
#: English word, and a question about Python threads or about the Threads
#: network in general is not this pipeline's work. The injected context is
#: appended to the user message on every matching turn for the rest of the
#: session, so a false positive is a standing tax on unrelated conversations,
#: not a one-off. Paired with the pipeline's own vocabulary it is unambiguous.
_THREADS = "threads"
_THREADS_CONTEXT = (
    "affiliate",
    "afiliasi",
    "konten",
    "content",
    "post",
    "publish",
    "preview",
    "generate",
    "schedule",
    "cron",
)

_SKILL_POINTER = (
    f"[{PLUGIN_ID}] This turn looks like Affiliate Threads work. Load the plugin's "
    f'bundled skill before answering: skill_view("{SKILL_ID}"). '
    "Publishing only ever happens through the threads_publish tool."
)


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
    ]
    # A deferred link reply is a different decision from the thread itself: one
    # post going up under a thread the human already approved. Say which one this
    # is, so the approval is about the right thing.
    stage = str(args.get("stage") or "").strip().lower()
    if stage == "link":
        lines.append("Stage: the deferred affiliate link reply to the live thread")
    elif stage == "thread":
        lines.append("Stage: the thread itself")
    lines.append("")
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
            "publish_stage": args.get("stage"),
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


def on_pre_llm_call(
    user_message: str = "",
    session_id: str = "",  # noqa: ARG001 - part of the hook payload
    **kwargs: Any,  # noqa: ANN401
) -> dict[str, str] | None:
    """Inject a pointer to the bundled skill when the turn is ours.

    Returns ``None`` for everything else, which is the normal case: an injection
    the model does not need still costs tokens on every turn of the session.
    """
    if not _setting_bool("announce_skill", default=True):
        return None
    if not _looks_like_our_work(user_message):
        return None
    return {"context": _SKILL_POINTER}


def _looks_like_our_work(user_message: str) -> bool:
    if not user_message:
        return False
    lowered = user_message.lower()
    if any(trigger in lowered for trigger in _TRIGGERS):
        return True
    return _THREADS in lowered and any(word in lowered for word in _THREADS_CONTEXT)


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
