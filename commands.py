"""The plugin's in-session slash command.

A bundled skill is namespaced (``affiliate-threads-generator:affiliate-threads-generator``)
and kept out of the system prompt's skill index, so on its own it gives a human
no obvious way in. This command is that way in: ``/affiliate-threads status``
runs the same read-only preflight the model would run through ``threads_check``,
with no second install and no model turn.

Nothing that changes business state moves here. Generating a thread is still a
natural-language request that runs the skill, and publishing still goes through
the approval gate.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

USAGE = "\n".join(
    [
        "Affiliate Threads",
        "",
        "  /affiliate-threads status   Credentials, Threads token, the Sheet, and the",
        "                              next eligible candidate. Read-only.",
        "  /affiliate-threads help     This message.",
        "",
        'To generate a thread, just ask in words — "Buatkan content berikutnya."',
        "Publishing always needs a human approval.",
    ]
)


def handle(ctx: Any, raw_args: str = "") -> str:  # noqa: ANN401 - PluginContext is host-provided
    """Dispatch the subcommand in ``raw_args``. Never raises."""
    words = (raw_args or "").split()
    subcommand = words[0].lower() if words else "help"

    if subcommand in {"help", "-h", "--help", "?"}:
        return USAGE
    if subcommand == "status":
        return _status(ctx)
    return f"Unknown subcommand {subcommand!r}.\n\n{USAGE}"


def _status(ctx: Any) -> str:  # noqa: ANN401
    # dispatch_tool goes through the normal tool pipeline, so this is the same
    # call the model would make — not a second implementation of the checks.
    try:
        raw = ctx.dispatch_tool("threads_check", {})
    except Exception as exc:  # noqa: BLE001 - the command answers, it does not crash
        logger.warning("dispatch_tool(threads_check) failed", exc_info=True)
        return f"threads_check could not run: {type(exc).__name__}: {exc}"

    payload = _parse(raw)
    if payload is None:
        return str(raw)

    verdict = payload.get("status") or ("ready" if payload.get("ok") else "attention_needed")
    lines = [f"Affiliate Threads — {verdict}", ""]

    checks = payload.get("checks")
    if isinstance(checks, dict):
        for name, check in checks.items():
            if not isinstance(check, dict):
                continue
            lines.append(f"  {'✓' if check.get('ok') else '✗'} {name}: {_detail(check.get('detail'))}")
            if not check.get("ok") and check.get("hint"):
                lines.append(f"      → {check['hint']}")

    problems = payload.get("problems")
    if isinstance(problems, list) and problems:
        lines.extend(["", "Problems: " + "; ".join(str(problem) for problem in problems)])

    unsynced = payload.get("unsynced_publishes")
    if isinstance(unsynced, list) and unsynced:
        ids = ", ".join(
            str(record.get("product_id")) for record in unsynced if isinstance(record, dict)
        )
        lines.extend(
            [
                "",
                f"⚠ {len(unsynced)} publish(es) went live without their Sheet write: {ids}",
                "  Repair with threads_publish for the same product_id — do not re-publish.",
            ]
        )

    return "\n".join(lines)


def _detail(detail: Any) -> str:  # noqa: ANN401
    if detail is None:
        return "n/a"
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False)


def _parse(raw: Any) -> dict | None:  # noqa: ANN401
    """The tool result as a dict, or ``None`` when it is not JSON we can read."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None
