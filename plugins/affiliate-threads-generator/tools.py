"""Tool handlers — the deterministic core.

Every handler follows the Hermes contract:

* signature ``def handler(args: dict, **kwargs) -> str``
* always return a JSON string, success and failure alike
* never raise — a raised exception fails the tool call and tells the model
  nothing useful

``threads_publish`` is the only path from this system to Meta Threads, and it
re-derives its own preconditions from the Sheet rather than trusting anything
the model said about them.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import config, guardrails, ledger
from .sheets_client import Row, SheetClient, SheetError
from .threads_client import ThreadsAPIError, ThreadsClient, normalize_posts

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _fail(stage: str, error: str, *, hint: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "stage": stage, "error": error}
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    return payload


def _truthy(value: Any) -> bool:  # noqa: ANN401
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


# --------------------------------------------------------------------------- #
# threads_publish
# --------------------------------------------------------------------------- #

def threads_publish(args: dict, **kwargs: Any) -> str:  # noqa: ANN401, ARG001
    try:
        return _json(_publish(args or {}))
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.exception("threads_publish crashed")
        return _json(_fail("internal", f"{type(exc).__name__}: {exc}"))


def _publish(args: dict[str, Any]) -> dict[str, Any]:
    settings = config.resolve(
        {
            "spreadsheet_id": args.get("spreadsheet_id"),
            "sheet_tab": args.get("sheet_tab"),
        }
    )

    # ---- 1. explicit approval -------------------------------------------
    if not _truthy(args.get("confirm_publish")):
        return _fail(
            "approval",
            "confirm_publish was not set, so nothing was published.",
            hint=(
                "Publishing is irreversible and needs an explicit human approval in the "
                "current conversation. Show the preview (with the Product ID) and wait for "
                "the human's own words before calling again."
            ),
        )

    product_id = str(args.get("product_id") or "").strip()
    if not product_id:
        return _fail("input", "product_id is required.")

    posts = normalize_posts(args.get("posts"))
    if not posts:
        return _fail("input", "posts is empty — there is nothing to publish.")

    topic_tag = str(args.get("topic_tag") or "").strip()

    # ---- 2. the Sheet is the state lock ---------------------------------
    try:
        sheet = SheetClient(settings)
        row = sheet.require_row(product_id)
    except SheetError as exc:
        return _fail("sheets_read", exc.message, hint=exc.hint)

    # ---- 3. repair an earlier half-finished publish ----------------------
    resync = _maybe_resync(sheet, settings, row)
    if resync is not None:
        return resync

    # ---- 4. re-validate the row's own state -----------------------------
    current_status = row.status.strip()
    if current_status != settings.eligible_status:
        return _fail(
            "precondition",
            f'Row {row.row_number} (ID {product_id}) has Status "{current_status}", not '
            f'"{settings.eligible_status}". Nothing was published.',
            hint=_status_hint(current_status, settings),
            current_status=current_status,
            expected_status=settings.eligible_status,
        )

    if row.threads_url.strip():
        return _fail(
            "precondition",
            f"Row {row.row_number} already has a Threads URL ({row.threads_url}). "
            "It looks like this product was published already, so nothing was published.",
            hint="Clear the Threads URL column deliberately if you really mean to publish again.",
        )

    # ---- 5. hard content guardrails --------------------------------------
    report = guardrails.validate_thread(
        posts,
        settings,
        affiliate_url=row.affiliate_url,
        product_name=row.product,
    )
    if not report.ok:
        return _fail(
            "guardrails",
            f"{len(report.violations)} hard rule(s) failed — nothing was published.",
            hint="Rewrite the flagged copy and show the human a new preview.",
            violations=[item.as_dict() for item in report.violations],
            warnings=[item.as_dict() for item in report.warnings],
        )

    # ---- 6. credentials ---------------------------------------------------
    if not settings.credentials_configured:
        return _fail(
            "credentials",
            "THREADS_ACCESS_TOKEN is not set, so nothing was published.",
            hint=(
                "Nothing was written to the Sheet either. Set it with "
                '`hermes config set THREADS_ACCESS_TOKEN "THQW..."`, or let Hermes prompt '
                "for it by loading this skill in the local CLI. The token needs the "
                "threads_basic and threads_content_publish scopes; see docs/threads-app-setup.md."
            ),
        )

    # ---- 7. publish -------------------------------------------------------
    client = ThreadsClient(settings.threads_access_token, settings.threads_user_id)
    try:
        result = client.publish_thread(
            posts,
            topic_tag=topic_tag,
            container_wait_seconds=settings.container_wait_seconds,
        )
    except ThreadsAPIError as exc:
        return _fail(
            "publish",
            f"the Threads API rejected the publish at stage '{exc.stage or 'unknown'}': {exc.message}",
            hint=(
                "Nothing was written to the Sheet. Common causes: an expired token, a missing "
                "threads_content_publish scope, or a rate limit (250 posts / 1000 replies per "
                "24h). Run threads_check to confirm the token state."
            ),
            api=exc.as_dict(),
            published_posts=0,
        )
    except ValueError as exc:
        return _fail("publish", f"could not start the publish: {exc}")

    # The posts are live from here on. Record that fact before touching the
    # Sheet, so a Sheet failure can never lead to a duplicate publish.
    ledger.record_published(
        product_id,
        media_ids=result.media_ids,
        permalink=result.permalink,
        posts_count=len(result.media_ids),
        published_at=_now(),
    )

    # ---- 8. record the business state ------------------------------------
    try:
        sheet.write_publish_result(
            row.row_number,
            threads_url=result.permalink,
            status=settings.done_status,
        )
    except SheetError as exc:
        return {
            "ok": True,
            "status": "published_sheet_write_failed",
            "product_id": product_id,
            "threads_url": result.permalink,
            "media_ids": result.media_ids,
            "posts_published": len(result.media_ids),
            "sheet": {"ok": False, "row": row.row_number, "error": exc.message, "hint": exc.hint},
            "next_step": (
                "The thread is live on Threads but the Sheet still shows the old Status. Do NOT "
                "publish again. Re-call threads_publish with the same product_id and it will "
                "only retry the Sheet write."
            ),
        }

    ledger.mark_sheet_synced(product_id, synced_at=_now())

    return {
        "ok": True,
        "status": "published",
        "product_id": product_id,
        "product": row.product,
        "threads_url": result.permalink,
        "media_ids": result.media_ids,
        "posts_published": len(result.media_ids),
        "sheet": {
            "ok": True,
            "row": row.row_number,
            "status": settings.done_status,
            "threads_url": result.permalink,
        },
        "warnings": [item.as_dict() for item in report.warnings],
        "next_step": (
            "Tell the human the thread is live with the URL, then save a short content-memory "
            "note (product_id, angle_type, topic, hook_pattern) for the novelty check."
        ),
    }


def _status_hint(current_status: str, settings: config.Settings) -> str:
    lookup = {
        settings.hold_status.lower(): "The human held this one. Resume it by setting Status back to the eligible value first.",
        settings.cancel_status.lower(): "This candidate was cancelled. Nothing to publish.",
        settings.done_status.lower(): "This one is already published.",
        settings.in_progress_status.lower(): "Generation is still in progress for this row.",
    }
    return lookup.get(
        current_status.lower(),
        f"Only rows whose Status is exactly \"{settings.eligible_status}\" may be published.",
    )


def _maybe_resync(
    sheet: SheetClient, settings: config.Settings, row: Row
) -> dict[str, Any] | None:
    """Finish a Sheet write that failed after a successful publish.

    Returns ``None`` when there is nothing to repair, so the caller continues
    with a normal publish.
    """
    record = ledger.get(row.id)
    if record is None or record.get("sheet_synced"):
        return None

    permalink = str(record.get("permalink") or "")
    if not permalink:
        ledger.forget(row.id)
        return None

    if row.threads_url.strip() == permalink and row.status.strip() == settings.done_status:
        ledger.mark_sheet_synced(row.id, synced_at=_now())
        return None

    try:
        sheet.write_publish_result(
            row.row_number, threads_url=permalink, status=settings.done_status
        )
    except SheetError as exc:
        return _fail(
            "sheets_write",
            f"this product was already published ({permalink}) but the Sheet write still fails: {exc.message}",
            hint=exc.hint or "Fix the Sheets access and call again — no duplicate will be published.",
            already_published=True,
            threads_url=permalink,
        )

    ledger.mark_sheet_synced(row.id, synced_at=_now())
    return {
        "ok": True,
        "status": "sheet_resynced",
        "product_id": row.id,
        "threads_url": permalink,
        "sheet": {"ok": True, "row": row.row_number, "status": settings.done_status},
        "note": (
            "This product had already been published; only the Sheet record was missing. "
            "Nothing new was published."
        ),
    }


# --------------------------------------------------------------------------- #
# threads_check
# --------------------------------------------------------------------------- #

def threads_check(args: dict, **kwargs: Any) -> str:  # noqa: ANN401, ARG001
    try:
        return _json(_check(args or {}))
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.exception("threads_check crashed")
        return _json(_fail("internal", f"{type(exc).__name__}: {exc}"))


def _check(args: dict[str, Any]) -> dict[str, Any]:
    settings = config.resolve(
        {
            "spreadsheet_id": args.get("spreadsheet_id"),
            "sheet_tab": args.get("sheet_tab"),
        }
    )

    want_token = _truthy(args.get("include_token", True))
    want_sheet = _truthy(args.get("include_sheet", True))
    want_candidate = _truthy(args.get("include_candidate", True))

    checks: dict[str, Any] = {}
    problems: list[str] = []

    # ---- credentials + identity -----------------------------------------
    if not settings.credentials_configured:
        checks["credentials"] = {
            "ok": False,
            "detail": "THREADS_ACCESS_TOKEN is not set.",
            "hint": (
                "Set it with `hermes config set THREADS_ACCESS_TOKEN \"THQW...\"`, or load "
                "this skill in the local CLI and let Hermes prompt for it. "
                "Anything that does not need to publish keeps working without it."
            ),
        }
        problems.append("threads credentials missing")
    else:
        checks["credentials"] = {"ok": True, "detail": "THREADS_ACCESS_TOKEN is set."}

    if want_token and settings.credentials_configured:
        client = ThreadsClient(settings.threads_access_token, settings.threads_user_id)
        try:
            me = client.get_me()
            detail: dict[str, Any] = {
                "id": str(me.get("id") or ""),
                "username": str(me.get("username") or ""),
            }
            try:
                token = client.debug_token()
                detail["token_valid"] = token.get("is_valid")
                detail["expires_at"] = _format_epoch(token.get("expires_at"))
                detail["data_access_expires_at"] = _format_epoch(token.get("data_access_expires_at"))
                scopes = token.get("scopes")
                if isinstance(scopes, list):
                    detail["scopes"] = scopes
                    if "threads_content_publish" not in scopes:
                        problems.append("token is missing the threads_content_publish scope")
            except ThreadsAPIError as exc:
                detail["token_debug_error"] = exc.message
            checks["threads_api"] = {"ok": True, "detail": detail}
        except ThreadsAPIError as exc:
            checks["threads_api"] = {
                "ok": False,
                "detail": exc.message,
                "api": exc.as_dict(),
                "hint": "Regenerate the long-lived token, or refresh it (scripts/threads_token.py).",
            }
            problems.append("threads api unreachable or token rejected")

    # ---- sheets ----------------------------------------------------------
    if want_sheet:
        try:
            sheet = SheetClient(settings)
            rows = sheet.read_rows()
            checks["sheets"] = {
                "ok": True,
                "detail": {
                    "spreadsheet_id": settings.spreadsheet_id,
                    "tab": settings.sheet_tab,
                    "rows": len(rows),
                    "google_api": str(getattr(sheet, "google_api", "") or "") or None,
                },
            }
        except SheetError as exc:
            checks["sheets"] = {"ok": False, "detail": exc.message, "hint": exc.hint}
            problems.append("google sheets unreachable")
        except Exception as exc:  # noqa: BLE001 - report, never raise
            checks["sheets"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
            problems.append("google sheets unreachable")

    # ---- next candidate --------------------------------------------------
    if want_candidate and checks.get("sheets", {}).get("ok"):
        try:
            candidate = sheet.next_eligible()  # type: ignore[possibly-undefined]
            checks["next_candidate"] = {
                "ok": True,
                "detail": candidate.as_dict(include_description=False) if candidate else None,
                "detail_note": None
                if candidate
                else (
                    "No row currently has Status "
                    f'"{settings.eligible_status}". Set one to that value when it is ready.'
                ),
            }
        except SheetError as exc:
            checks["next_candidate"] = {"ok": False, "detail": exc.message}

    return {
        "ok": not problems,
        "status": "ready" if not problems else "attention_needed",
        "problems": problems,
        "checks": checks,
        "settings": settings.public_summary(),
        "unsynced_publishes": ledger.unsynced_records(),
    }


def _format_epoch(value: Any) -> str | None:  # noqa: ANN401
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None
