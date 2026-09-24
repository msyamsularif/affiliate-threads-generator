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
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from . import config, guardrails, ledger
from .sheets_client import Row, SheetClient, SheetError
from .threads_client import ThreadsAPIError, ThreadsClient, normalize_posts

logger = logging.getLogger(__name__)

#: Publish stages. ``auto`` follows the Sheet's own state — an eligible row
#: starts the thread, a row in ``link_pending_status`` gets its deferred link
#: reply. See ``config.PUBLISH_MODES`` for the two-call flow this serves.
STAGE_AUTO = "auto"
STAGE_THREAD = "thread"
STAGE_LINK = "link"
PUBLISH_STAGES = (STAGE_AUTO, STAGE_THREAD, STAGE_LINK)


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

    requested_stage = str(args.get("stage") or STAGE_AUTO).strip().lower()
    if requested_stage not in PUBLISH_STAGES:
        return _fail(
            "input",
            f'stage must be one of: {", ".join(PUBLISH_STAGES)}. Got "{requested_stage}".',
        )

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

    # ---- 4. which half of a publish is this? -----------------------------
    stage, refusal = _resolve_stage(requested_stage, settings, row)
    if refusal is not None:
        return refusal
    if stage == STAGE_LINK:
        return _publish_link_reply(settings, sheet, row, posts)

    # ---- 5. hard content guardrails --------------------------------------
    # In two-stage mode the link is deferred to a reply: the thread body is not
    # required to carry it. That requirement lives on the reply instead, in
    # `_publish_link_reply`, which is where the link actually belongs. The
    # topic tag is checked here because it belongs to the root post, which only
    # this half publishes.
    check_settings = (
        replace(settings, require_affiliate_url=False)
        if settings.two_stage
        else settings
    )
    # The experience mode comes from the row itself, so the model cannot pick
    # it: a first-hand claim is only ever valid against a stored testimony.
    experience = row.experience_mode()
    report = guardrails.validate_thread(
        posts,
        check_settings,
        affiliate_url=row.affiliate_url,
        product_name=row.product,
        topic_tag=topic_tag,
        experience=experience,
        testimonial=row.testimonial,
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
        publish_mode=settings.publish_mode,
    )

    # In two-stage mode the row is parked here, not finished: the deferred link
    # reply is what completes it, and this status is what stops the row from
    # being published a second time in the meantime.
    status_after = settings.link_pending_status if settings.two_stage else settings.done_status

    # ---- 8. record the business state ------------------------------------
    try:
        sheet.write_publish_result(
            row.row_number,
            threads_url=result.permalink,
            status=status_after,
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

    payload: dict[str, Any] = {
        "ok": True,
        "status": "published_awaiting_link" if settings.two_stage else "published",
        "product_id": product_id,
        "product": row.product,
        "topic_tag": topic_tag or None,
        "experience": experience,
        "threads_url": result.permalink,
        "media_ids": result.media_ids,
        "posts_published": len(result.media_ids),
        "sheet": {
            "ok": True,
            "row": row.row_number,
            "status": status_after,
            "threads_url": result.permalink,
        },
        "warnings": [item.as_dict() for item in report.warnings],
        "next_step": (
            "Tell the human the thread is live with the URL, then save a short content-memory "
            "note (product_id, angle_type, topic, hook_pattern) for the novelty check."
        ),
    }
    if settings.two_stage:
        payload["deferred_link"] = {
            "stage": STAGE_LINK,
            "affiliate_url": row.affiliate_url,
            "status_written": status_after,
            "requires": (
                "one reply post carrying the affiliate URL, sent once the "
                "thread has had the views the human is waiting for"
            ),
        }
        payload["next_step"] = (
            f"The thread is live, without the affiliate link. The row now reads "
            f'Status "{status_after}", which is what marks it as waiting for the link reply — '
            "nothing else can publish it while it says that. When the human decides the post "
            "has been seen, call threads_publish again with the same product_id, "
            f'stage "{STAGE_LINK}", and posts holding that single reply.'
        )
    return payload


def _resolve_stage(
    requested: str, settings: config.Settings, row: Row
) -> tuple[str, dict[str, Any] | None]:
    """Decide whether this call starts a thread or attaches the deferred link.

    ``auto`` follows the Sheet's own state, the same lock every other
    precondition in this tool trusts. Returns the stage and, when the call cannot
    run, the refusal payload to send back.
    """
    status = row.status.strip()
    where = f"Row {row.row_number} (ID {row.id})"

    wants_link = requested == STAGE_LINK or (
        requested == STAGE_AUTO and settings.two_stage and status == settings.link_pending_status
    )
    if wants_link:
        if not settings.two_stage:
            return "", _fail(
                "precondition",
                'stage "link" belongs to publish_mode "two_stage", and this plugin publishes '
                "the whole thread in one call.",
                hint=(
                    'Either put the link in the thread and publish it, or set publish_mode to '
                    '"two_stage" if the link is meant to follow as a reply.'
                ),
            )
        if status != settings.link_pending_status:
            return "", _fail(
                "precondition",
                f'{where} has Status "{status}", not "{settings.link_pending_status}", so no '
                "published thread is waiting for its link reply.",
                hint=_stage_hint(settings, row),
                current_status=status,
                expected_status=settings.link_pending_status,
            )
        return STAGE_LINK, None

    if status != settings.eligible_status:
        return "", _fail(
            "precondition",
            f'{where} has Status "{status}", not "{settings.eligible_status}". Nothing was '
            "published.",
            hint=_stage_hint(settings, row),
            current_status=status,
            expected_status=settings.eligible_status,
        )

    if row.threads_url.strip():
        return "", _fail(
            "precondition",
            f"{where} already has a Threads URL ({row.threads_url}). It looks like this "
            "product was published already, so nothing was published.",
            hint="Clear the Threads URL column deliberately if you really mean to publish again.",
        )
    return STAGE_THREAD, None


def _publish_link_reply(
    settings: config.Settings, sheet: SheetClient, row: Row, posts: list[dict[str, str]]
) -> dict[str, Any]:
    """Publish the deferred affiliate link as a reply to the live thread."""
    if len(posts) != 1:
        return _fail(
            "input",
            f'stage "{STAGE_LINK}" publishes the reply alone, so posts must hold exactly one '
            f"post; got {len(posts)}.",
            hint=(
                "Send the reply copy by itself: the affiliate URL, in one "
                "post, appended to the thread that is already live."
            ),
        )

    if not row.threads_url.strip():
        return _fail(
            "precondition",
            f"Row {row.row_number} (ID {row.id}) has no Threads URL, so there is no thread to "
            "reply to.",
            hint="The deferred link reply attaches to the thread published earlier — publish that first.",
        )

    record = ledger.get(row.id) or {}
    media_ids = [str(item) for item in record.get("media_ids") or []]
    if not media_ids:
        return _fail(
            "precondition",
            "The publish ledger has no record of a thread for this product, so the reply has "
            "nothing to attach to.",
            hint=(
                "A reply needs the media id of the post it answers, and only the ledger holds "
                "it. Post the link reply by hand in the Threads app, then set the row's Status "
                "to Done yourself."
            ),
            threads_url=row.threads_url,
        )

    # One post, replying to a live thread: the length rules still apply, the
    # count rules are about the reply itself, and the link is the whole point of
    # this call. No topic tag is checked: a tag belongs to the root post, which
    # this call does not publish.
    report = guardrails.validate_thread(
        posts,
        replace(settings, min_posts=1, max_posts=1),
        affiliate_url=row.affiliate_url,
        product_name=row.product,
        topic_tag=None,
        experience=row.experience_mode(),
        testimonial=row.testimonial,
    )
    if not report.ok:
        return _fail(
            "guardrails",
            f"{len(report.violations)} hard rule(s) failed on the link reply — nothing was published.",
            hint="Fix the flagged copy and show the human a new preview before trying again.",
            violations=[item.as_dict() for item in report.violations],
            warnings=[item.as_dict() for item in report.warnings],
        )

    if not settings.credentials_configured:
        return _fail(
            "credentials",
            "THREADS_ACCESS_TOKEN is not set, so nothing was published.",
            hint=(
                "The thread is live and untouched. Set the token, then re-call with the same "
                "product_id and stage \"link\"."
            ),
        )

    client = ThreadsClient(settings.threads_access_token, settings.threads_user_id)
    try:
        media_id = client.publish_reply(
            text=posts[0]["text"],
            reply_to_id=media_ids[-1],
            image_url=posts[0]["image_url"],
            container_wait_seconds=settings.container_wait_seconds,
        )
    except ThreadsAPIError as exc:
        return _fail(
            "publish",
            f"the Threads API rejected the link reply at stage '{exc.stage or 'unknown'}': {exc.message}",
            hint=(
                "The thread itself is untouched and nothing was written to the Sheet. Run "
                "threads_check if the token state is in doubt."
            ),
            api=exc.as_dict(),
            published_posts=0,
        )
    except ValueError as exc:
        return _fail("publish", f"could not start the link reply publish: {exc}")

    # Live from here on, so record it before the Sheet write can fail.
    ledger.record_link_reply(row.id, media_id=media_id, posted_at=_now())

    try:
        sheet.write_publish_result(
            row.row_number, threads_url=row.threads_url, status=settings.done_status
        )
    except SheetError as exc:
        return {
            "ok": True,
            "status": "link_published_sheet_write_failed",
            "product_id": row.id,
            "threads_url": row.threads_url,
            "link_media_id": media_id,
            "sheet": {"ok": False, "row": row.row_number, "error": exc.message, "hint": exc.hint},
            "next_step": (
                f'The link reply is live, but the Sheet still reads "{settings.link_pending_status}". '
                'Do NOT post it again. Re-call threads_publish with the same product_id and stage '
                f'"{STAGE_LINK}" and it will only repair the Sheet write.'
            ),
        }

    ledger.mark_link_sheet_synced(row.id, synced_at=_now())

    return {
        "ok": True,
        "status": "link_reply_published",
        "product_id": row.id,
        "product": row.product,
        "threads_url": row.threads_url,
        "link_media_id": media_id,
        "sheet": {
            "ok": True,
            "row": row.row_number,
            "status": settings.done_status,
            "threads_url": row.threads_url,
        },
        "warnings": [item.as_dict() for item in report.warnings],
        "next_step": (
            "Tell the human the link reply is live on the thread, with the URL. Then save the "
            "content-memory note (product_id, angle_type, topic, hook_pattern) for the novelty "
            "check."
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


def _stage_hint(settings: config.Settings, row: Row) -> str:
    """What this row's status allows, given the configured publish mode."""
    if not settings.two_stage:
        return _status_hint(row.status.strip(), settings)
    return (
        f'In two-stage mode only "{settings.eligible_status}" (publish the thread) and '
        f'"{settings.link_pending_status}" (attach its link reply) can be published. '
        + _status_hint(row.status.strip(), settings)
    )


def _maybe_resync(
    sheet: SheetClient, settings: config.Settings, row: Row
) -> dict[str, Any] | None:
    """Finish a Sheet write that failed after something already went live.

    Two halves can be left unwritten: the thread publish, and the deferred link
    reply. The ledger records both the moment they are public, so a retry for the
    same product finishes the Sheet instead of posting a second time.

    Returns ``None`` when there is nothing to repair, so the caller continues
    with a normal publish.
    """
    record = ledger.get(row.id)
    if record is None:
        return None

    permalink = str(record.get("permalink") or "")
    if not permalink:
        ledger.forget(row.id)
        return None

    unfinished = _unfinished_sheet_write(record, settings)
    if unfinished is None:
        return None
    status, half = unfinished

    if row.threads_url.strip() == permalink and row.status.strip() == status:
        _mark_sheet_synced(row.id, half)
        return None

    try:
        sheet.write_publish_result(
            row.row_number, threads_url=permalink, status=status
        )
    except SheetError as exc:
        return _fail(
            "sheets_write",
            f"this product was already published ({permalink}) but the Sheet write still fails: {exc.message}",
            hint=exc.hint or "Fix the Sheets access and call again — nothing will be published twice.",
            already_published=True,
            threads_url=permalink,
        )

    _mark_sheet_synced(row.id, half)
    return {
        "ok": True,
        "status": "sheet_resynced",
        "product_id": row.id,
        "threads_url": permalink,
        "sheet": {"ok": True, "row": row.row_number, "status": status},
        "note": (
            "The link reply for this product was already posted; only the Sheet record was "
            "missing. Nothing new was published."
            if half == "link"
            else "This product had already been published; only the Sheet record was missing. "
            "Nothing new was published."
        ),
    }


def _unfinished_sheet_write(
    record: dict[str, Any], settings: config.Settings
) -> tuple[str, str] | None:
    """``(status, half)`` the ledger still owes the Sheet, or ``None``.

    ``half`` is ``"thread"`` for the publish itself and ``"link"`` for the
    deferred link reply, and only decides which bookkeeping flag gets cleared.
    """
    if not record.get("sheet_synced"):
        status = (
            settings.link_pending_status
            if record.get("publish_mode") == config.TWO_STAGE_MODE
            else settings.done_status
        )
        return status, "thread"
    if record.get("link_media_id") and not record.get("link_sheet_synced"):
        return settings.done_status, "link"
    return None


def _mark_sheet_synced(product_id: str, half: str) -> None:
    if half == "link":
        ledger.mark_link_sheet_synced(product_id, synced_at=_now())
    else:
        ledger.mark_sheet_synced(product_id, synced_at=_now())


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

        # A two-stage thread is live but unfinished until its link reply lands.
        # Nothing is broken while it waits, so this is a status line, not a
        # problem — but it is the one thing that only shows up in the Sheet.
        waiting = [
            row.as_dict(include_description=False)
            for row in rows  # type: ignore[possibly-undefined]
            if settings.two_stage and row.status.strip() == settings.link_pending_status
        ]
        checks["link_replies_pending"] = {
            "ok": True,
            "detail": waiting or None,
            "detail_note": None
            if waiting
            else (
                "No published thread is waiting for its link reply."
                if settings.two_stage
                else f'publish_mode is "{settings.publish_mode}", so no link replies are deferred.'
            ),
        }

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
