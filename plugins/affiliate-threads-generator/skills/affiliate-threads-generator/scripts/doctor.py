#!/usr/bin/env python3
"""Health check for the whole Affiliate Threads setup.

Answers "is this thing actually wired up?" without guessing. Run it before
telling a human that something is broken.

Checks
------
1. the plugin is installed and its modules import
2. the effective settings resolve (spreadsheet, tab, guardrail knobs)
3. the Threads token works, and when it expires
4. the Google Sheet is reachable through the bundled google-workspace skill
5. the next eligible candidate, if any
6. the standalone skill copy exists (needed for cron's ``--skill`` lookup)
7. a cron job exists for this skill
8. any publish that went live without its Sheet write landing

Exit codes
----------
0   everything requested passed
1   at least one check failed

Usage
-----
    doctor.py
    doctor.py --format json
    doctor.py --no-network          # skip the API/Sheet probes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bridge  # noqa: E402

SKILL_NAME = "affiliate-threads-generator"
PLUGIN_NAME = "affiliate-threads-generator"


def hermes_home() -> Path:
    root = os.environ.get("HERMES_HOME", "").strip()
    return Path(root).expanduser() if root else Path.home() / ".hermes"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctor.py", description="Check the Affiliate Threads setup end to end."
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--no-network", action="store_true", help="Skip the Threads API and Google Sheets probes."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    checks: list[dict] = []

    # ---- 1. plugin ------------------------------------------------------
    try:
        config = _bridge.load("config")
        plugin_dir = _bridge.plugin_path()
        checks.append(
            {
                "check": "plugin",
                "ok": True,
                "detail": f"found at {plugin_dir} (v{_plugin_version(plugin_dir)})",
            }
        )
    except RuntimeError as exc:
        checks.append({"check": "plugin", "ok": False, "detail": str(exc)})
        _emit(checks, args)
        return 1

    try:
        sheets_client = _bridge.load("sheets_client")
        threads_client = _bridge.load("threads_client")
        import_ok = True
        import_error = ""
    except Exception as exc:  # noqa: BLE001
        import_ok = False
        import_error = f"{type(exc).__name__}: {exc}"

    if not import_ok:
        checks.append({"check": "modules", "ok": False, "detail": import_error})

    settings = config.resolve()

    # ---- 2. settings ----------------------------------------------------
    checks.append(
        {
            "check": "settings",
            "ok": bool(settings.spreadsheet_id),
            "detail": (
                f"spreadsheet={settings.spreadsheet_id or 'MISSING'} "
                f"tab={settings.sheet_tab} eligible={settings.eligible_status!r} "
                f"disclosure={'required' if settings.require_disclosure else 'off'}"
            ),
            "hint": None
            if settings.spreadsheet_id
            else (
                "Set AFFILIATE_SHEET_ID — `hermes config set AFFILIATE_SHEET_ID \"<id>\"`, "
                "or load the skill in the local CLI and let Hermes prompt for it "
                "(see docs/credentials.md)."
            ),
        }
    )

    # ---- 3. Threads token ------------------------------------------------
    if not settings.credentials_configured:
        checks.append(
            {
                "check": "threads_credentials",
                "ok": False,
                "detail": "THREADS_ACCESS_TOKEN is not set",
                "hint": "Set it with `hermes config set THREADS_ACCESS_TOKEN \"THQW...\"`, "
                "or load this skill in the local CLI and let Hermes prompt for it "
                "(see docs/credentials.md).",
            }
        )
    elif args.no_network:
        checks.append({"check": "threads_credentials", "ok": True, "detail": "set (not probed)"})
    else:
        try:
            client = threads_client.ThreadsClient(
                settings.threads_access_token, settings.threads_user_id
            )
            me = client.get_me()
            detail = f"@{me.get('username')} (id {me.get('id')})"
            ok = True
            hint = None
            try:
                debug = client.debug_token()
                days = _days(debug.get("expires_at"))
                detail += f"; token valid={debug.get('is_valid')}, expires in {days} days"
                if days is not None and days < 7:
                    hint = "Refresh the token: scripts/threads_token.py refresh --write-env"
            except threads_client.ThreadsAPIError as exc:
                detail += f"; token debug unavailable ({exc.message})"
            checks.append({"check": "threads_api", "ok": ok, "detail": detail, "hint": hint})
        except threads_client.ThreadsAPIError as exc:
            checks.append(
                {
                    "check": "threads_api",
                    "ok": False,
                    "detail": exc.message,
                    "hint": "Regenerate or refresh the token (scripts/threads_token.py).",
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append({"check": "threads_api", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})

    # ---- 4 + 5. Sheets and the next candidate ----------------------------
    sheet = None
    if args.no_network:
        checks.append({"check": "sheets", "ok": True, "detail": "skipped (--no-network)"})
    else:
        try:
            sheet = sheets_client.SheetClient(settings)
            rows = sheet.read_rows()
            checks.append(
                {
                    "check": "sheets",
                    "ok": True,
                    "detail": (
                        f"{len(rows)} data row(s) in {settings.sheet_tab}; "
                        f"google_api={sheet.google_api}"
                    ),
                }
            )
        except sheets_client.SheetError as exc:
            checks.append({"check": "sheets", "ok": False, "detail": exc.message, "hint": exc.hint})
        except Exception as exc:  # noqa: BLE001
            checks.append({"check": "sheets", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})

    if sheet is not None:
        try:
            candidate = sheet.next_eligible()
            checks.append(
                {
                    "check": "next_candidate",
                    "ok": True,
                    "detail": (
                        f"ID {candidate.id} — {candidate.product} (row {candidate.row_number})"
                        if candidate
                        else f'no row has Status "{settings.eligible_status}"'
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append({"check": "next_candidate", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})

    # ---- 6. standalone skill copy ---------------------------------------
    skill_copy = hermes_home() / "skills" / SKILL_NAME / "SKILL.md"
    checks.append(
        {
            "check": "skill_installed",
            "ok": skill_copy.is_file(),
            "detail": str(skill_copy) if skill_copy.is_file() else f"missing at {skill_copy}",
            "hint": None
            if skill_copy.is_file()
            else "Run ./install.sh — cron's --skill flag looks up the unqualified skill name.",
        }
    )

    # ---- 7. cron job ------------------------------------------------------
    checks.append(_cron_check())

    # ---- 8. unsynced publishes -------------------------------------------
    unsynced = _unsynced_publishes()
    checks.append(
        {
            "check": "unsynced_publishes",
            "ok": not unsynced,
            "detail": (
                "none"
                if not unsynced
                else f"{len(unsynced)} publish(es) went live without their Sheet write: "
                + ", ".join(str(record.get("product_id")) for record in unsynced)
            ),
            "hint": None
            if not unsynced
            else "Call threads_publish with the same product_id to repair the Sheet — do not re-publish.",
        }
    )

    _emit(checks, args)
    return 0 if all(check["ok"] for check in checks) else 1


def _emit(checks: list[dict], args: argparse.Namespace) -> None:
    if args.format == "json":
        print(json.dumps({"ok": all(c["ok"] for c in checks), "checks": checks}, ensure_ascii=False, indent=2))
        return

    failed = 0
    for check in checks:
        mark = "✓" if check["ok"] else "✗"
        if not check["ok"]:
            failed += 1
        print(f"  {mark} {check['check']}: {check['detail']}")
        if not check["ok"] and check.get("hint"):
            print(f"      → {check['hint']}")
    print()
    print(f"{len(checks) - failed}/{len(checks)} checks passed.")


def _plugin_version(plugin_dir: Path) -> str:
    try:
        text = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def _days(epoch) -> float | None:  # noqa: ANN001
    try:
        return round((int(epoch) - int(datetime.now(tz=timezone.utc).timestamp())) / 86400, 1)
    except (TypeError, ValueError):
        return None


def _cron_check() -> dict:
    jobs_path = hermes_home() / "cron" / "jobs.json"
    if not jobs_path.is_file():
        return {
            "check": "cron_job",
            "ok": False,
            "detail": f"no cron job table at {jobs_path}",
            "hint": "See docs/cron-setup.md to schedule Mon/Wed/Fri/Sun 08:00 Asia/Jakarta.",
        }
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"check": "cron_job", "ok": False, "detail": f"could not read {jobs_path}: {exc}"}

    jobs = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return {"check": "cron_job", "ok": False, "detail": "unexpected jobs.json shape"}

    matches = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        skills = job.get("skills") or []
        if isinstance(skills, str):
            skills = [skills]
        if SKILL_NAME in skills or PLUGIN_NAME in str(job.get("name") or ""):
            matches.append(job)

    if not matches:
        return {
            "check": "cron_job",
            "ok": False,
            "detail": "no cron job references this skill",
            "hint": "See docs/cron-setup.md, or accept the blueprint with /suggestions.",
        }

    summary = "; ".join(
        f"{job.get('name') or job.get('id')} [{job.get('schedule')}] "
        f"next={job.get('next_run_at') or 'n/a'} enabled={job.get('enabled', True)}"
        for job in matches
    )
    return {"check": "cron_job", "ok": True, "detail": summary}


def _unsynced_publishes() -> list[dict]:
    """Best-effort read of the plugin's publish ledger, outside Hermes."""
    data_dir = hermes_home() / "plugin-data" / PLUGIN_NAME
    if not data_dir.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(data_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ledger = payload.get("publish_ledger") if isinstance(payload, dict) else None
        if isinstance(ledger, dict):
            records.extend(
                record
                for record in ledger.values()
                if isinstance(record, dict) and not record.get("sheet_synced")
            )
    return records


if __name__ == "__main__":
    raise SystemExit(main())
