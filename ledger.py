"""Idempotency ledger for publishing.

Publishing is the one irreversible side effect in this system, and it is a
two-part operation: (1) posts go live on Threads, (2) the Sheet is updated to
``Status=Done`` with the Threads URL. Part 1 can succeed while part 2 fails —
a Sheet outage, a revoked scope, a process killed mid-write.

Without a record of part 1, the honest retry is to publish again, which would
duplicate the thread on a public profile. This ledger is that record: it is
written *immediately* after the posts go live and before the Sheet write, so a
retry for the same product can finish the Sheet write instead of re-publishing.

It is deliberately small: the Sheet remains the business source of truth, and
Hermes' own memory remains the content-novelty store. This only answers one
question — "did we already push this product to Threads?".
"""

from __future__ import annotations

from typing import Any

from . import runtime

_LEDGER_KEY = "publish_ledger"
_HISTORY_LIMIT = 200


def _load() -> dict[str, dict[str, Any]]:
    data = runtime.state_get(_LEDGER_KEY, default={})
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _save(ledger: dict[str, dict[str, Any]]) -> None:
    if len(ledger) > _HISTORY_LIMIT:
        ordered = sorted(
            ledger.items(),
            key=lambda item: str(item[1].get("published_at") or ""),
            reverse=True,
        )
        ledger = dict(ordered[:_HISTORY_LIMIT])
    runtime.state_set(_LEDGER_KEY, ledger)


def get(product_id: str) -> dict[str, Any] | None:
    return _load().get(str(product_id))


def record_published(
    product_id: str,
    *,
    media_ids: list[str],
    permalink: str,
    posts_count: int,
    published_at: str,
    publish_mode: str = "single",
) -> dict[str, Any]:
    """Record a confirmed publish. ``sheet_synced`` starts false on purpose.

    ``publish_mode`` decides what the Sheet still has to be told: in ``single``
    mode the publish is finished once ``Status=Done`` lands, while a ``two_stage``
    thread is finished only after the deferred link reply.
    """
    ledger = _load()
    record = {
        "product_id": str(product_id),
        "media_ids": list(media_ids),
        "permalink": permalink,
        "posts_count": posts_count,
        "published_at": published_at,
        "publish_mode": publish_mode,
        "sheet_synced": False,
        "sheet_synced_at": None,
    }
    ledger[str(product_id)] = record
    _save(ledger)
    return record


def record_link_reply(
    product_id: str, *, media_id: str, posted_at: str
) -> dict[str, Any] | None:
    """Record the deferred link reply going live, before the Sheet write.

    Same reason as ``record_published``: the reply is public the moment the API
    returns, so the record exists before anything can fail around it.
    """
    ledger = _load()
    record = ledger.get(str(product_id))
    if record is None:
        return None
    record["link_media_id"] = media_id
    record["link_posted_at"] = posted_at
    record["link_sheet_synced"] = False
    _save(ledger)
    return record


def mark_link_sheet_synced(product_id: str, *, synced_at: str) -> dict[str, Any] | None:
    ledger = _load()
    record = ledger.get(str(product_id))
    if record is None:
        return None
    record["link_sheet_synced"] = True
    record["link_sheet_synced_at"] = synced_at
    _save(ledger)
    return record


def mark_sheet_synced(product_id: str, *, synced_at: str) -> dict[str, Any] | None:
    ledger = _load()
    record = ledger.get(str(product_id))
    if record is None:
        return None
    record["sheet_synced"] = True
    record["sheet_synced_at"] = synced_at
    _save(ledger)
    return record


def forget(product_id: str) -> None:
    ledger = _load()
    if ledger.pop(str(product_id), None) is not None:
        _save(ledger)


def unsynced_records() -> list[dict[str, Any]]:
    return [record for record in _load().values() if not record.get("sheet_synced")]
