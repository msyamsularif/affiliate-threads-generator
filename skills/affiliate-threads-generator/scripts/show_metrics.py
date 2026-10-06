#!/usr/bin/env python3
"""Latest Threads metrics per product — read-only.

Prints one line per product from the plugin-owned Metrics tab (its most recent
snapshot), plus the click totals that snapshot recorded and the content shape
the row carries (angle, hook, CTA, topic) when it has one. Answers "how is it
going?" without touching the Threads API or spending a model turn.

Usage
-----
    show_metrics.py
    show_metrics.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bridge  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="show_metrics.py",
        description="Show the latest Metrics-tab snapshot per product.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = _bridge.load("config")
        sheets_client = _bridge.load("sheets_client")
    except RuntimeError as exc:
        _fail(str(exc), args)
        return 1

    settings = config.resolve()
    note = _bridge.settings_note()
    if note:
        print(note, file=sys.stderr)

    try:
        sheet = sheets_client.SheetClient(settings)
        values = sheet.read_range(f"{settings.metrics_tab}!A1:N")
    except sheets_client.SheetError as exc:
        _fail(
            f"could not read the {settings.metrics_tab!r} tab: {exc.message}",
            args,
            hint=exc.hint,
        )
        return 1

    rows = _data_rows(values)
    latest: dict[str, list[str]] = {}
    for row in rows:
        product_id = _cell(row, 0)
        if product_id:
            latest[product_id] = row  # appended in order — the last one wins

    ordered = [latest[key] for key in sorted(latest, key=_product_sort_key)]

    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": True,
                    "tab": settings.metrics_tab,
                    "snapshots": len(rows),
                    "products": [_payload(row) for row in ordered],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not rows:
        print(
            f"The {settings.metrics_tab!r} tab has no snapshots yet — the weekly job writes "
            "the first ones, or run fetch_metrics.py now."
        )
        return 0

    print(f"📊 Metrics — latest snapshot per product ({len(rows)} snapshot row(s))")
    print()
    for row in ordered:
        print(_line(row))
    return 0


def _data_rows(values: list[list[str]]) -> list[list[str]]:
    if not values:
        return []
    first = str(values[0][0] if values[0] else "").strip().upper()
    body = values[1:] if first == "PRODUCT ID" else values
    return [row for row in body if any(str(cell).strip() for cell in row)]


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def _line(row: list[str]) -> str:
    product_id = _cell(row, 0)
    parts = []
    for index, label in (
        (3, "views"),
        (4, "likes"),
        (5, "replies"),
        (6, "reposts"),
        (7, "quotes"),
        (8, "shares"),
    ):
        value = _cell(row, index)
        if value:
            parts.append(f"{_fmt(value)} {label}")
    clicks = _cell(row, 9)
    if clicks:
        parts.append(f"{clicks} clicks (7d)")
    checked = _cell(row, 2)
    when = checked[:10] if checked else "unknown date"
    line = f"Product {product_id} — {' · '.join(parts) or 'no data'} · checked {when}"
    attribution = _attribution(row)
    if attribution:
        line += f" · {attribution}"
    return line


def _attribution(row: list[str]) -> str:
    """The content shape the row carries; ``""`` for pre-attribution rows."""
    return " · ".join(
        f"{label} {value}"
        for label, value in (
            ("angle", _cell(row, 10)),
            ("hook", _cell(row, 11)),
            ("cta", _cell(row, 12)),
            ("topic", _cell(row, 13)),
        )
        if value
    )


def _payload(row: list[str]) -> dict:
    def number(index: int) -> int | None:
        value = _cell(row, index)
        if not value:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    return {
        "product_id": _cell(row, 0),
        "media_id": _cell(row, 1),
        "checked_at": _cell(row, 2),
        "views": number(3),
        "likes": number(4),
        "replies": number(5),
        "reposts": number(6),
        "quotes": number(7),
        "shares": number(8),
        "link_clicks": number(9),
        "angle_type": _cell(row, 10),
        "hook_pattern": _cell(row, 11),
        "cta_shape": _cell(row, 12),
        "topic": _cell(row, 13),
    }


def _fmt(value: str) -> str:
    try:
        return f"{int(float(value)):,}"
    except ValueError:
        return value


def _product_sort_key(product_id: str) -> tuple[int, float, str]:
    raw = str(product_id or "").strip()
    try:
        return (0, float(raw), "")
    except ValueError:
        return (1, 0.0, raw)


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
