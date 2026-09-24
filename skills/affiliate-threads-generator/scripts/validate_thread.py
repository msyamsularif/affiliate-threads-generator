#!/usr/bin/env python3
"""Lint a draft thread before it is shown to a human.

Runs the plugin's own guardrails, so a draft that passes here passes the same
checks ``threads_publish`` will run — failing here is much cheaper than failing
at publish time.

Exit codes
----------
0   no violations
1   violations found (details on stdout)
2   usage or input error

Usage
-----
    validate_thread.py --file draft.json
    cat draft.json | validate_thread.py --stdin
    validate_thread.py --file draft.json --product-id 12      # pull the URL from the Sheet
    validate_thread.py --file draft.json --product-id 12 --stage link
    validate_thread.py --file draft.json --format text

``--stage`` mirrors the publish tool. Under ``publish_mode: two_stage`` the
thread body is linted without the affiliate link and the disclosure (both belong
to the link reply), and the reply itself is linted as the single post it is.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bridge  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_thread.py",
        description="Check a draft thread against the hard guardrails.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", help="Path to a JSON draft.")
    source.add_argument("--stdin", action="store_true", help="Read the draft from stdin.")
    parser.add_argument("--product-id", default="", help="Look the row up for URL/name context.")
    parser.add_argument("--affiliate-url", default="", help="Affiliate URL to require in the copy.")
    parser.add_argument("--product-name", default="", help="Product name, for over-exposure checks.")
    parser.add_argument(
        "--stage",
        choices=("auto", "thread", "link"),
        default="auto",
        help=(
            "Which publish stage this draft is for. 'auto' follows the row when --product-id "
            "is given, and lints a whole thread otherwise."
        ),
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--sheet-tab", default="")
    return parser


def read_draft(args: argparse.Namespace) -> tuple[list[dict], str]:
    """Return ``(posts, product_id)`` from the requested source."""
    if args.stdin or not args.file:
        raw = sys.stdin.read()
    else:
        raw = Path(args.file).expanduser().read_text(encoding="utf-8")

    data = json.loads(raw)
    product_id = args.product_id

    if isinstance(data, dict):
        posts = data.get("posts") or []
        product_id = str(data.get("product_id") or product_id)
    elif isinstance(data, list):
        posts = data
    else:
        raise ValueError("the draft must be a JSON object or a JSON array")

    normalized: list[dict] = []
    for item in posts:
        if isinstance(item, str):
            normalized.append({"text": item, "image_url": ""})
        elif isinstance(item, dict):
            normalized.append(
                {
                    "text": str(item.get("text") or ""),
                    "image_url": str(item.get("image_url") or ""),
                }
            )
        else:
            raise ValueError(f"unsupported post entry: {type(item).__name__}")
    return normalized, product_id


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = _bridge.load("config")
        guardrails = _bridge.load("guardrails")
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        posts, product_id = read_draft(args)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2

    if not posts:
        print(json.dumps({"ok": False, "error": "the draft contains no posts"}), file=sys.stderr)
        return 2

    note = _bridge.settings_note()
    if note:
        print(f"note: {note}", file=sys.stderr)

    settings = config.resolve(
        {"spreadsheet_id": args.spreadsheet_id, "sheet_tab": args.sheet_tab}
    )

    affiliate_url = args.affiliate_url
    product_name = args.product_name
    row = None

    if product_id:
        try:
            sheets_client = _bridge.load("sheets_client")
            sheet = sheets_client.SheetClient(settings)
            row = sheet.find_by_id(product_id)
            if row is not None:
                affiliate_url = affiliate_url or row.affiliate_url
                product_name = product_name or row.product
        except Exception as exc:  # noqa: BLE001 - context lookup is best effort
            print(f"note: could not look up product {product_id}: {exc}", file=sys.stderr)

    stage = args.stage if args.stage != "auto" else _stage_for(row, settings)
    check_settings, deferred = _settings_for_stage(settings, stage)
    if deferred:
        print(
            "note: two-stage mode — the affiliate link and the disclosure belong to the link "
            "reply, so they are not required of this thread body.",
            file=sys.stderr,
        )

    report = guardrails.validate_thread(
        posts, check_settings, affiliate_url=affiliate_url, product_name=product_name
    )

    payload = {
        "ok": report.ok,
        "product_id": product_id or None,
        "stage": stage,
        "deferred": deferred,
        "posts": len(posts),
        "char_counts": [guardrails.threads_char_count(post["text"]) for post in posts],
        "link_counts": [guardrails.count_links(post["text"]) for post in posts],
        "limits": {
            "max_chars_per_post": check_settings.max_chars_per_post,
            "max_links_per_post": check_settings.max_links_per_post,
            "min_posts": check_settings.min_posts,
            "max_posts": check_settings.max_posts,
            "require_disclosure": check_settings.require_disclosure,
            "disclosure_style": check_settings.disclosure_style,
            "require_affiliate_url": check_settings.require_affiliate_url,
        },
        "violations": [item.as_dict() for item in report.violations],
        "warnings": [item.as_dict() for item in report.warnings],
    }

    if args.format == "text":
        _print_text(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if report.ok else 1


def _print_text(payload: dict) -> None:
    print(f"stage: {payload['stage']}  posts: {payload['posts']}  chars: {payload['char_counts']}  links: {payload['link_counts']}")
    print(f"limits: {payload['limits']}")
    if payload.get("deferred"):
        print(f"deferred to the link reply: {', '.join(payload['deferred'])}")
    print()
    if payload["violations"]:
        print(f"VIOLATIONS ({len(payload['violations'])}) — publishing would be refused:")
        for item in payload["violations"]:
            where = f" [post {item['post']}]" if "post" in item else ""
            print(f"  ✗ {item['code']}{where}: {item['message']}")
    else:
        print("VIOLATIONS: none — this draft passes the hard guardrails.")
    if payload["warnings"]:
        print()
        print(f"WARNINGS ({len(payload['warnings'])}) — signals, not blockers:")
        for item in payload["warnings"]:
            where = f" [post {item['post']}]" if "post" in item else ""
            print(f"  ! {item['code']}{where}: {item['message']}")


def _stage_for(row, settings) -> str:
    """Which publish stage a draft belongs to. ``auto`` follows the Sheet."""
    if row is None or not settings.two_stage:
        return "thread"
    return "link" if row.status.strip() == settings.link_pending_status else "thread"


def _settings_for_stage(settings, stage):  # noqa: ANN001, ANN201
    """The guardrail settings the matching publish call uses.

    Mirrors what ``threads_publish`` does per stage, so the lint cannot drift
    from the tool: two-stage threads defer the link and the disclosure to the
    reply, and a reply is a single post by definition.
    """
    if stage == "link":
        return dataclasses.replace(settings, min_posts=1, max_posts=1), []
    if settings.two_stage:
        return (
            dataclasses.replace(
                settings, require_affiliate_url=False, require_disclosure=False
            ),
            ["affiliate_url", "disclosure"],
        )
    return settings, []


if __name__ == "__main__":
    raise SystemExit(main())
