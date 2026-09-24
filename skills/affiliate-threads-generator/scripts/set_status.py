#!/usr/bin/env python3
"""Set a candidate's Status in the Sheet — the hold / cancel / resume action.

The script re-reads the row, verifies the ID matches, and then writes only the
Status cell. It refuses to set ``Done``: that state belongs to ``threads_publish``
and only after the posts are actually live.

Exit codes
----------
0   written
4   refused (ID not found, or the status is not settable by hand)
1   the run failed

Usage
-----
    set_status.py 12 Hold
    set_status.py 12 Cancel
    set_status.py 12 "Ready To Generate"      # resume
    set_status.py 12 Hold --expect "Ready To Generate"
    set_status.py 12 Hold --dry-run
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
        prog="set_status.py",
        description="Set a candidate row's Status in the affiliate Sheet.",
    )
    parser.add_argument("product_id", help="The row's ID value.")
    parser.add_argument("status", help='The new status, e.g. "Hold". Quote values with spaces.')
    parser.add_argument(
        "--expect",
        default="",
        help="Only write when the current status equals this value (race guard).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing."
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--sheet-tab", default="")
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
    new_status = args.status.strip()

    # `Done` is written by threads_publish, after a confirmed media id. Writing it
    # by hand would make the Sheet lie about a thread that may not exist.
    if new_status.lower() == settings.done_status.lower():
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "refused",
                    "error": (
                        f'"{settings.done_status}" is written only by the threads_publish tool, '
                        "after the posts are confirmed live. It cannot be set by hand."
                    ),
                    "hint": "Use the threads_publish tool instead.",
                },
                ensure_ascii=False,
            )
        )
        return 4

    try:
        sheet = sheets_client.SheetClient(settings)
        row = sheet.find_by_id(args.product_id)
    except sheets_client.SheetError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": exc.message}, ensure_ascii=False))
        return 1

    if row is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "refused",
                    "error": f"No row with ID {args.product_id!r} in {settings.sheet_tab}.",
                    "hint": "Check the Product ID against the sheet's ID column.",
                },
                ensure_ascii=False,
            )
        )
        return 4

    current = row.status.strip()
    if args.expect and current != args.expect.strip():
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "refused",
                    "error": (
                        f'Expected status "{args.expect}" but the row currently has "{current}". '
                        "Nothing was written."
                    ),
                    "current_status": current,
                },
                ensure_ascii=False,
            )
        )
        return 4

    if current == new_status:
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "unchanged",
                    "product_id": row.id,
                    "sheet_row": row.row_number,
                    "status_value": current,
                    "message": f'Row {row.row_number} already has Status "{current}".',
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "dry_run",
                    "product_id": row.id,
                    "sheet_row": row.row_number,
                    "from": current,
                    "to": new_status,
                },
                ensure_ascii=False,
            )
        )
        return 0

    try:
        sheet.write_status(row.row_number, new_status)
    except sheets_client.SheetError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": exc.message}, ensure_ascii=False))
        return 1

    payload = {
        "ok": True,
        "status": "written",
        "product_id": row.id,
        "product": row.product,
        "sheet_row": row.row_number,
        "from": current,
        "to": new_status,
        "message": f'Row {row.row_number} (ID {row.id}) Status: "{current}" -> "{new_status}".',
    }
    if args.format == "text":
        print(payload["message"])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
