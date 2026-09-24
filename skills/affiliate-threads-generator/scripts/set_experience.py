#!/usr/bin/env python3
"""Record whether the human has personally used a product — and their testimony.

This is the pipeline's Step 1.5 gate. A row whose answer is blank is asked about
before any research happens; the answer selects the guardrail mode the copy is
written and validated under:

* ``Used=No`` — ``none``: no first-hand claim can be substantiated.
* ``Used=Yes`` plus a testimony — ``firsthand``: first-hand claims are allowed,
  inside what the human actually wrote.

The testimony is stored verbatim — it is the human's own account, never a model
paraphrase — and only the ``Used`` / ``Testimonial`` cells are written.

Exit codes
----------
0   written (or already identical)
4   refused (ID not found, contradictory arguments)
1   the run failed

Usage
-----
    set_experience.py 12 --used no
    set_experience.py 12 --used yes --testimonial "Dipakai 3 bulan, pas buat kerja."
    set_experience.py 12 --used yes --testimonial-file testimony.txt
    set_experience.py 12 --used no --dry-run
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
        prog="set_experience.py",
        description="Record a row's Used / Testimonial answer in the affiliate Sheet.",
    )
    parser.add_argument("product_id", help="The row's ID value.")
    parser.add_argument(
        "--used",
        required=True,
        choices=("yes", "no"),
        help="Whether the human has personally used this product.",
    )
    parser.add_argument(
        "--testimonial",
        default="",
        help="The human's own account of using it. Stored verbatim. Only with --used yes.",
    )
    parser.add_argument(
        "--testimonial-file",
        default="",
        help="Read the testimony from a file instead of --testimonial.",
    )
    parser.add_argument(
        "--expect",
        default="",
        help='Only write when the row currently reads this Used value (e.g. "" or "Yes").',
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing."
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--sheet-tab", default="")
    return parser


def _refuse(payload: dict) -> int:
    print(json.dumps({"ok": False, "stage": "refused", **payload}, ensure_ascii=False))
    return 4


def _read_testimonial(args: argparse.Namespace) -> str:
    if args.testimonial_file:
        return Path(args.testimonial_file).expanduser().read_text(encoding="utf-8").strip()
    return args.testimonial.strip()


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

    if args.testimonial_file and args.testimonial:
        return _refuse(
            {
                "error": "pass --testimonial or --testimonial-file, not both.",
                "hint": "They set the same value; pick one.",
            }
        )

    try:
        testimonial = _read_testimonial(args)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1

    used = "Yes" if args.used == "yes" else "No"
    if used == "No" and testimonial:
        return _refuse(
            {
                "error": 'a "No" answer clears the Testimonial; it cannot carry one.',
                "hint": (
                    "Drop --testimonial for a No answer. If the product was used after all, "
                    "write --used yes with the testimony."
                ),
            }
        )

    settings = config.resolve(
        {"spreadsheet_id": args.spreadsheet_id, "sheet_tab": args.sheet_tab}
    )

    try:
        sheet = sheets_client.SheetClient(settings)
        row = sheet.find_by_id(args.product_id)
    except sheets_client.SheetError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": exc.message}, ensure_ascii=False))
        return 1

    if row is None:
        return _refuse(
            {
                "error": f"No row with ID {args.product_id!r} in {settings.sheet_tab}.",
                "hint": "Check the Product ID against the sheet's ID column.",
            }
        )

    if args.expect and row.used.strip().casefold() != args.expect.strip().casefold():
        return _refuse(
            {
                "error": (
                    f'Expected Used "{args.expect}" but the row currently reads "{row.used}". '
                    "Nothing was written."
                ),
                "current_used": row.used,
            }
        )

    written_testimonial = "" if used == "No" else testimonial
    mode = config.experience_mode(used, written_testimonial)

    if row.used.strip() == used and row.testimonial.strip() == written_testimonial:
        payload = {
            "ok": True,
            "status": "unchanged",
            "product_id": row.id,
            "sheet_row": row.row_number,
            "used": used,
            "experience_mode": mode,
            "message": f"Row {row.row_number} already records Used={used}.",
        }
        print(
            payload["message"]
            if args.format == "text"
            else json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return 0

    if args.dry_run:
        payload = {
            "ok": True,
            "status": "dry_run",
            "product_id": row.id,
            "sheet_row": row.row_number,
            "from": {"used": row.used, "testimonial": row.testimonial or None},
            "to": {"used": used, "testimonial": written_testimonial or None},
            "experience_mode": mode,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        sheet.write_experience(row.row_number, used=used, testimonial=written_testimonial)
    except sheets_client.SheetError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": exc.message}, ensure_ascii=False))
        return 1

    payload = {
        "ok": True,
        "status": "written",
        "product_id": row.id,
        "product": row.product,
        "sheet_row": row.row_number,
        "used": used,
        "testimonial": written_testimonial or None,
        "experience_mode": mode,
        "message": (
            f'Row {row.row_number} (ID {row.id}): Used="{used}", '
            f"experience mode: {mode}."
        ),
    }
    if used == "Yes" and not written_testimonial:
        payload["note"] = (
            "Used=Yes with an empty testimony validates as mode none — the copy may not claim "
            "anything first-hand yet. Ask once more for the testimony."
        )
    if args.format == "text":
        print(payload["message"])
        if payload.get("note"):
            print(f"note: {payload['note']}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
