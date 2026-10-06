#!/usr/bin/env python3
"""Weekly Threads insights fetch — the Monday metrics job.

Reads the publish ledger for posts published inside the window, pulls each
root post's lifetime insights plus the account's 7-day link-click totals from
the Threads Insights API, and appends one row per post to the plugin-owned
Metrics tab. Each row also carries the content shape the publish recorded —
angle type, hook pattern, CTA shape and topic — which only the ledger knows.
The cron job delivers the summary it prints, so the summary is the weekly
report.

Environment
-----------
THREADS_ACCESS_TOKEN    a token carrying ``threads_manage_insights``
AFFILIATE_SHEET_ID      the spreadsheet that holds the Metrics tab

Usage
-----
    fetch_metrics.py                 # fetch, append, print the summary
    fetch_metrics.py --dry-run       # fetch and print; write nothing
    fetch_metrics.py --format json

Exit codes
----------
0   at least one post fetched, or nothing was inside the window
1   nothing could be fetched (auth, scope, Sheet, or every post failed)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bridge  # noqa: E402

#: Columns of the plugin-owned Metrics tab, in order. The four attribution
#: columns were appended at the end so rows written before them stay readable.
METRICS_HEADER = (
    "Product ID",
    "Media ID",
    "Checked At",
    "Views",
    "Likes",
    "Replies",
    "Reposts",
    "Quotes",
    "Shares",
    "Link Clicks",
    "Angle Type",
    "Hook Pattern",
    "CTA Shape",
    "Topic",
)

#: How far back the account-level click window reaches. The job runs weekly,
#: so this is "clicks gained since the last run, give or take a day".
CLICK_WINDOW_DAYS = 7

SCOPE_HINT = (
    "The token is missing the threads_manage_insights scope. Re-authorize the Meta app "
    "with threads_basic, threads_content_publish and threads_manage_insights, exchange the "
    "code for a long-lived token, and store it with "
    "threads_token.py exchange --short-token <token> --write-env — see "
    "docs/threads-app-setup.md."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_metrics.py",
        description=(
            "Fetch Threads insights for recently published posts and append them to "
            "the Metrics tab."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print without writing to the Sheet.",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=0,
        help="Override the metrics_window_days setting for this run.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = _bridge.load("config")
        ledger = _bridge.load("ledger")
        sheets_client = _bridge.load("sheets_client")
        threads_client = _bridge.load("threads_client")
    except RuntimeError as exc:
        _fail(str(exc), args)
        return 1

    settings = config.resolve()
    note = _bridge.settings_note()
    if note:
        print(note, file=sys.stderr)

    if not settings.threads_access_token:
        _fail(
            "THREADS_ACCESS_TOKEN is not set.",
            args,
            hint="Set it with `hermes config set THREADS_ACCESS_TOKEN \"THQW...\"` — see docs/credentials.md.",
        )
        return 1

    client = threads_client.ThreadsClient(settings.threads_access_token, settings.threads_user_id)
    try:
        return _run(args, settings, client, ledger, sheets_client, threads_client)
    except threads_client.ThreadsAPIError as exc:  # pragma: no cover - backstop
        _fail(exc.message, args, hint=_api_hint(exc))
        return 1


def _run(
    args: argparse.Namespace,
    settings,  # noqa: ANN001 - plugin Settings, imported through the bridge
    client,  # noqa: ANN001 - ThreadsClient
    ledger,  # noqa: ANN001 - plugin module
    sheets_client,  # noqa: ANN001 - plugin module
    threads_client,  # noqa: ANN001 - plugin module
) -> int:
    now = datetime.now(timezone.utc)
    window_days = args.window_days if args.window_days > 0 else settings.metrics_window_days
    cutoff = now - timedelta(days=window_days)
    checked_at = now.isoformat(timespec="seconds")

    records = []
    skipped = 0
    for record in ledger.records():
        published = _parse_published(record.get("published_at"))
        if published is None or published < cutoff:
            skipped += 1
            continue
        records.append(record)
    records.sort(key=_record_sort_key)

    if not records:
        return _emit(
            args,
            checked_at=checked_at,
            window_days=window_days,
            skipped=skipped,
            rows=[],
            summaries=[],
            clicks={},
            unmatched=[],
            errors=[],
            appended=0,
            first_row=0,
            scope_error=False,
            header_upgraded=False,
            empty=True,
        )

    try:
        sheet = sheets_client.SheetClient(settings)
        sheet_rows = sheet.read_rows()
    except sheets_client.SheetError as exc:
        _fail(f"could not read the candidate table: {exc.message}", args, hint=exc.hint)
        return 1

    affiliate_by_product = {
        row.id.strip(): row.affiliate_url.strip()
        for row in sheet_rows
        if row.id.strip() and row.affiliate_url.strip()
    }

    errors: list[str] = []
    scope_error = False

    clicks: dict[str, int] = {}
    unmatched: list[tuple[str, int]] = []
    raw_clicks, click_error = _fetch_clicks(client, threads_client, now)
    if click_error:
        errors.append(click_error)
    else:
        clicks, unmatched = _attribute_clicks(raw_clicks, affiliate_by_product)

    rows: list[list[str]] = []
    summaries: list[dict] = []
    for record in records:
        product_id = str(record.get("product_id") or "").strip()
        media_ids = record.get("media_ids") or []
        root = str(media_ids[0]).strip() if isinstance(media_ids, list) and media_ids else ""
        if not root:
            errors.append(f"Product {product_id}: the ledger record carries no media id")
            continue
        try:
            values = _fetch_media_values(client, threads_client, root)
        except threads_client.ThreadsAPIError as exc:
            errors.append(f"Product {product_id}: {exc.message}")
            scope_error = scope_error or _is_scope_error(exc)
            continue
        rows.append(
            [
                product_id,
                root,
                checked_at,
                _cell(values.get("views")),
                _cell(values.get("likes")),
                _cell(values.get("replies")),
                _cell(values.get("reposts")),
                _cell(values.get("quotes")),
                _cell(values.get("shares")),
                str(clicks.get(product_id, 0)),
                _cell(record.get("angle_type")),
                _cell(record.get("hook_pattern")),
                _cell(record.get("cta_shape")),
                _cell(record.get("topic")),
            ]
        )
        summaries.append({"product_id": product_id, **values})

    appended = 0
    first_row = 0
    header_upgraded = False
    if rows and not args.dry_run:
        try:
            header_upgraded = _upgrade_header(sheet, settings.metrics_tab, sheets_client)
            first_row = sheet.append_rows(settings.metrics_tab, rows, header=METRICS_HEADER)
            appended = len(rows)
        except sheets_client.SheetError as exc:
            _fail(
                f"could not update the {settings.metrics_tab!r} tab: {exc.message}",
                args,
                hint=exc.hint,
            )
            return 1

    return _emit(
        args,
        checked_at=checked_at,
        window_days=window_days,
        skipped=skipped,
        rows=rows,
        summaries=summaries,
        clicks=clicks,
        unmatched=unmatched,
        errors=errors,
        appended=appended,
        first_row=first_row,
        scope_error=scope_error,
        header_upgraded=header_upgraded,
        empty=False,
    )


def _upgrade_header(sheet, tab: str, sheets_client) -> bool:  # noqa: ANN001
    """Rewrite the Metrics header when it predates the current column set.

    ``append_rows`` writes a header only into an empty tab, so a tab created
    before attribution existed keeps its 10-column header and the new rows
    would land under stale labels. Row 1 is compared with ``METRICS_HEADER``
    and rewritten when it differs; an empty tab is left alone — ``append_rows``
    writes the header there. Only row 1 of the plugin-owned tab is ever
    touched.
    """
    try:
        values = sheet.read_range(f"{tab}!A1:N1")
    except sheets_client.SheetError as exc:
        raise sheets_client.SheetError(
            exc.message,
            stage=exc.stage,
            hint=exc.hint
            or (
                f"Check that a tab named {tab!r} exists in the spreadsheet — create it "
                "if not; see docs/google-sheets-setup.md."
            ),
        ) from exc
    row = values[0] if values else []
    if not any(str(cell).strip() for cell in row):
        return False
    if [str(cell).strip() for cell in row] == list(METRICS_HEADER):
        return False
    sheet.write_row(tab, 1, METRICS_HEADER)
    return True


def _fetch_clicks(client, threads_client, now: datetime) -> tuple[dict[str, int], str]:  # noqa: ANN001
    since = int((now - timedelta(days=CLICK_WINDOW_DAYS)).timestamp())
    until = int(now.timestamp())
    try:
        body = client.get_user_insights("clicks", since=since, until=until)
    except threads_client.ThreadsAPIError as exc:
        return {}, f"link clicks: {exc.message}"
    return _link_totals(body), ""


def _fetch_media_values(client, threads_client, media_id: str) -> dict[str, int]:  # noqa: ANN001
    try:
        return client.get_media_insights(media_id)
    except threads_client.ThreadsAPIError as exc:
        if exc.status != 400:
            raise
    # The platform rejected the full metric set (a metric can be unavailable for
    # a post type); retry with the stable subset rather than losing the post.
    return client.get_media_insights(media_id, metrics=threads_client.STABLE_MEDIA_INSIGHT_METRICS)


def _link_totals(body: dict) -> dict[str, int]:
    """``link_total_values`` from a ``clicks`` insights payload → ``{url: count}``."""
    totals: dict[str, int] = {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return totals
    for entry in data:
        if not isinstance(entry, dict) or str(entry.get("name") or "") != "clicks":
            continue
        values = entry.get("link_total_values")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            url = str(item.get("link_url") or "").strip()
            value = item.get("value")
            if url and isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[url] = totals.get(url, 0) + int(value)
    return totals


def _attribute_clicks(
    link_totals: dict[str, int],
    affiliate_by_product: dict[str, str],
) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """Map clicked URLs back to products by exact affiliate-URL match.

    Unmatched links are returned rather than dropped silently — the operator
    should hear about a click that belonged to nobody. The first product whose
    affiliate URL matches wins, which is all a duplicate URL deserves.
    """
    by_product: dict[str, int] = {}
    unmatched: list[tuple[str, int]] = []
    for url, count in link_totals.items():
        matched = ""
        for product_id, affiliate_url in affiliate_by_product.items():
            if url == affiliate_url:
                matched = product_id
                break
        if not matched:
            unmatched.append((url, count))
            continue
        by_product[matched] = by_product.get(matched, 0) + count
    return by_product, unmatched


def _emit(
    args: argparse.Namespace,
    *,
    checked_at: str,
    window_days: int,
    skipped: int,
    rows: list[list[str]],
    summaries: list[dict],
    clicks: dict[str, int],
    unmatched: list[tuple[str, int]],
    errors: list[str],
    appended: int,
    first_row: int,
    scope_error: bool,
    header_upgraded: bool,
    empty: bool,
) -> int:
    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": bool(rows) or empty,
                    "checked_at": checked_at,
                    "window_days": window_days,
                    "fetched": len(rows),
                    "skipped": skipped,
                    "rows": rows,
                    "clicks": clicks,
                    "unmatched_links": [url for url, _ in unmatched],
                    "errors": errors,
                    "appended": appended,
                    "first_row": first_row or None,
                    "header_upgraded": header_upgraded,
                    "dry_run": bool(args.dry_run),
                },
                ensure_ascii=False,
            )
        )
        return 0 if rows or empty else 1

    local = datetime.fromisoformat(checked_at).astimezone()
    lines = [f"📊 Threads metrics — {local.strftime('%a %Y-%m-%d %H:%M %Z')}"]

    if empty:
        lines.append(f"No published post inside the {window_days}d window — nothing fetched.")
    else:
        lines.append(f"Fetched {len(rows)} post(s) · {skipped} outside the {window_days}d window")
        top = _top_line(summaries)
        if top:
            lines.append(top)
        lines.append(_clicks_line(clicks, unmatched))
        if args.dry_run:
            lines.extend(_attribution_lines(rows))
            lines.append("→ Metrics: dry run — nothing written")
        elif appended:
            if header_upgraded:
                lines.append("→ Metrics header: upgraded to 14 columns")
            lines.append(f"→ Metrics: {appended} row(s) appended from row {first_row}")

    for error in errors:
        lines.append(f"⚠ {error}")
    if scope_error:
        lines.append(f"→ {SCOPE_HINT}")

    print("\n".join(lines))
    return 0 if rows or empty else 1


def _attribution_lines(rows: list[list[str]]) -> list[str]:
    """One line per fetched post showing the attribution it carries.

    Dry-run only: it is how the operator checks what the next real run would
    write, without the tab being touched.
    """
    lines = []
    for row in rows:
        parts = [
            f"{label} {value}"
            for label, value in (
                ("angle", row[10]),
                ("hook", row[11]),
                ("cta", row[12]),
                ("topic", row[13]),
            )
            if value
        ]
        lines.append(f"• Product {row[0]} — {' · '.join(parts) if parts else 'no attribution'}")
    return lines


def _top_line(summaries: list[dict]) -> str:
    if not summaries:
        return ""

    def score(item: dict) -> tuple[int, int, int]:
        return (
            int(item.get("views") or 0),
            int(item.get("likes") or 0),
            int(item.get("replies") or 0),
        )

    best = max(summaries, key=score)
    if score(best) == (0, 0, 0):
        return ""
    parts = []
    for key, label in (("views", "views"), ("likes", "likes"), ("replies", "replies")):
        value = best.get(key)
        if value:
            parts.append(f"{int(value):,} {label}")
    return f"Top: Product {best.get('product_id')} — " + " · ".join(parts)


def _clicks_line(clicks: dict[str, int], unmatched: list[tuple[str, int]]) -> str:
    total = sum(clicks.values()) + sum(count for _, count in unmatched)
    line = f"Link clicks ({CLICK_WINDOW_DAYS}d): {total}"
    parts = [
        f"Product {product_id}: {count}"
        for product_id, count in sorted(clicks.items(), key=lambda item: _product_sort_key(item[0]))
        if count
    ]
    if parts:
        line += " — " + " · ".join(parts)
    if unmatched:
        line += f" (+{sum(count for _, count in unmatched)} unmatched link(s))"
    return line


def _parse_published(raw) -> datetime | None:  # noqa: ANN001
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _record_sort_key(record: dict) -> tuple[int, float, str]:
    raw = str(record.get("product_id") or "").strip()
    try:
        return (0, float(raw), "")
    except ValueError:
        return (1, 0.0, raw)


def _product_sort_key(product_id: str) -> tuple[int, float, str]:
    raw = str(product_id or "").strip()
    try:
        return (0, float(raw), "")
    except ValueError:
        return (1, 0.0, raw)


def _cell(value) -> str:  # noqa: ANN001
    return "" if value is None else str(value)


def _is_scope_error(exc) -> bool:  # noqa: ANN001
    text = f"{exc.message} {exc.code if exc.code is not None else ''}".lower()
    return (
        exc.status == 403
        or exc.code in {10, 200}
        or "scope" in text
        or "permission" in text
    )


def _api_hint(exc) -> str:  # noqa: ANN001
    return SCOPE_HINT if _is_scope_error(exc) else ""


def _fail(message: str, args: argparse.Namespace, *, hint: str = "") -> None:
    if args.format == "json":
        payload = {"ok": False, "error": message}
        if hint:
            payload["hint"] = hint
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"✗ {message}")
    if hint:
        print(f"→ {hint}")


if __name__ == "__main__":
    sys.exit(main())
