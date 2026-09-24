#!/usr/bin/env python3
"""Deterministic candidate selection.

Re-reads the Sheet on every call and returns exactly one candidate: the row whose
``Status`` is exactly the eligible value, with the lowest numeric ``ID``. Never
falls back to a different status.

Exit codes
----------
0   a candidate was found
3   no row is eligible (not an error — just nothing to do)
1   the run failed (Sheet unreachable, misconfigured, ...)

Usage
-----
    select_candidate.py                       # next eligible, summary
    select_candidate.py --full                # next eligible, incl. Description
    select_candidate.py --id 12 --full        # one specific row
    select_candidate.py --format text
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
        prog="select_candidate.py",
        description="Pick the single eligible candidate from the affiliate Sheet.",
    )
    parser.add_argument("--id", dest="product_id", default="", help="Fetch one specific row by ID.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include the Description column (the seller's background material).",
    )
    parser.add_argument(
        "--format", choices=("json", "text"), default="json", help="Output format."
    )
    parser.add_argument("--spreadsheet-id", default="", help="Override the configured spreadsheet.")
    parser.add_argument("--sheet-tab", default="", help="Override the configured tab name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = _bridge.load("config")
        sheets_client = _bridge.load("sheets_client")
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    note = _bridge.settings_note()
    if note:
        print(f"note: {note}", file=sys.stderr)

    settings = config.resolve(
        {"spreadsheet_id": args.spreadsheet_id, "sheet_tab": args.sheet_tab}
    )

    try:
        sheet = sheets_client.SheetClient(settings)
        if args.product_id:
            row = sheet.find_by_id(args.product_id)
            rows_total = None
        else:
            rows_total = len(sheet.read_rows())
            row = sheet.next_eligible()
    except sheets_client.SheetError as exc:
        payload = {"ok": False, "stage": exc.stage or "sheets", "error": exc.message}
        if exc.hint:
            payload["hint"] = exc.hint
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1

    payload: dict = {
        "ok": True,
        "eligible_status": settings.eligible_status,
        "sheet_tab": settings.sheet_tab,
        "candidate": row.as_dict(include_description=args.full) if row else None,
    }
    if rows_total is not None:
        payload["rows_scanned"] = rows_total

    if row is None:
        if args.product_id:
            payload["message"] = f"No row with ID {args.product_id!r} was found."
        else:
            payload["message"] = (
                f'No row currently has Status "{settings.eligible_status}". '
                "Nothing to generate. Do not pick a row with a different status."
            )
        payload["ok"] = True
        payload["nothing_eligible"] = True
    else:
        payload["message"] = f"Selected product ID {row.id} ({row.product})."

    if args.format == "text":
        _print_text(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 3 if payload.get("nothing_eligible") else 0


def _print_text(payload: dict) -> None:
    candidate = payload.get("candidate")
    print(payload.get("message", ""))
    if not candidate:
        return
    print()
    print(f"  ID          {candidate.get('id')}")
    print(f"  Product     {candidate.get('product')}")
    print(f"  Category    {candidate.get('category')}")
    print(f"  Status      {candidate.get('status')}")
    print(f"  Sheet row   {candidate.get('row')}")
    print(f"  Affiliate   {candidate.get('affiliate_url')}")
    if "description" in candidate:
        print()
        print("  Description:")
        for line in str(candidate["description"]).splitlines():
            print(f"    {line}")


if __name__ == "__main__":
    raise SystemExit(main())
