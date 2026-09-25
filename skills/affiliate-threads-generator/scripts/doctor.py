#!/usr/bin/env python3
"""Health check for the whole Affiliate Threads setup.

Answers "is this thing actually wired up?" without guessing. Run it before
telling a human that something is broken.

Checks
------
1. the plugin is installed and its modules import
2. the effective settings resolve (spreadsheet, tab, guardrail knobs)
3. where those settings came from — the host, ``config.yaml``, or the defaults
4. the Threads token works, and when it expires
5. the Google Sheet is reachable through the bundled google-workspace skill
6. the next eligible candidate, if any
7. the bundled skill is present where Hermes loads it
8. a cron job exists for this skill
9. a cron job keeps the Threads token alive (it lasts 60 days, and nothing here
   renews it on its own)
10. any publish that went live without its Sheet write landing

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
                f"topic_tag={'required' if settings.require_topic_tag else 'off'}"
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

    # ---- 3. where the settings came from ---------------------------------
    try:
        source = _bridge.load("runtime").settings_source()
    except Exception as exc:  # noqa: BLE001
        source = {"source": "unknown", "path": "", "warning": f"{type(exc).__name__}: {exc}"}

    kind = source.get("source")
    if kind == "host":
        detail = "resolved by the Hermes host context"
    elif kind == "config_file":
        detail = f"{source.get('settings', 0)} setting(s) read from {source.get('path')}"
    elif kind == "defaults":
        detail = f"nothing set in {source.get('path')} — defaults and environment are in effect"
    else:
        detail = f"settings source unknown ({kind})"

    warning = str(source.get("warning") or "")
    checks.append(
        {
            "check": "plugin_settings",
            "ok": not warning,
            "detail": f"{detail} — {warning}" if warning else detail,
            "hint": (
                "These scripts read plugins.entries.affiliate-threads-generator.settings.* "
                "themselves when they run outside Hermes, and that read failed. Install PyYAML "
                "for the interpreter that runs them (`python3 -m pip install pyyaml`), or run "
                "them with the interpreter Hermes uses. Until then the defaults and the "
                "environment win here, which can differ from what threads_publish enforces."
            )
            if warning
            else None,
        }
    )

    # ---- 4. Threads token ------------------------------------------------
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

    # ---- 5 + 6. Sheets and the next candidate ----------------------------
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

    # ---- 7. the bundled skill --------------------------------------------
    # The skill ships inside the plugin and the plugin registers it, so this
    # checks the copy Hermes actually loads. Nothing is installed into
    # ~/.hermes/skills/ and nothing needs to be.
    bundled_skill = _bridge.plugin_path() / "skills" / SKILL_NAME / "SKILL.md"
    checks.append(
        {
            "check": "bundled_skill",
            "ok": bundled_skill.is_file(),
            "detail": str(bundled_skill)
            if bundled_skill.is_file()
            else f"missing at {bundled_skill}",
            "hint": None
            if bundled_skill.is_file()
            else (
                "Reinstall the plugin: hermes plugins install "
                "msyamsularif/affiliate-threads-generator --enable"
            ),
        }
    )

    # ---- 8. cron jobs -----------------------------------------------------
    jobs, jobs_error = _read_cron_jobs()
    checks.append(_cron_check(jobs, jobs_error))
    checks.append(_token_refresh_check(jobs, jobs_error))

    # ---- 9. unsynced publishes -------------------------------------------
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


#: What to do when nothing renews the token. The 60-day cliff is the one setup gap
#: that stays invisible until publishing stops, so the hint carries the whole fix.
TOKEN_REFRESH_HINT = (
    "The token lasts 60 days and nothing in this plugin renews it, so publishing stops on "
    'day 60. Create the job: hermes cron create "0 9 1 * *" "Refresh the Threads token" '
    "--no-agent --script refresh-threads-token.sh --deliver telegram "
    '--name "threads-token-refresh" — the script it runs is in '
    "docs/threads-app-setup.md#automate-it."
)


def _read_cron_jobs() -> tuple[list[dict] | None, str]:
    """The cron job table, or ``(None, reason)`` when it cannot be read."""
    jobs_path = hermes_home() / "cron" / "jobs.json"
    if not jobs_path.is_file():
        return None, f"no cron job table at {jobs_path}"
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"could not read {jobs_path}: {exc}"

    jobs = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return None, "unexpected jobs.json shape"
    return [job for job in jobs if isinstance(job, dict)], ""


def _job_summary(job: dict) -> str:
    return (
        f"{job.get('name') or job.get('id')} [{job.get('schedule')}] "
        f"next={job.get('next_run_at') or 'n/a'} enabled={job.get('enabled', True)}"
    )


def _cron_check(jobs: list[dict] | None, error: str) -> dict:
    if jobs is None:
        return {
            "check": "cron_job",
            "ok": False,
            "detail": error,
            "hint": "See docs/cron-setup.md to schedule Mon/Wed/Fri/Sun 08:00 Asia/Jakarta.",
        }

    # A job either attaches the skill by name, or names it in the prompt — which
    # is what the bundle-only setup does, since cron resolves a bare name
    # against the installed skills and this one is namespaced.
    namespaced = f"{PLUGIN_NAME}:{SKILL_NAME}"
    matches = [job for job in jobs if _references_skill(job, namespaced)]
    if not matches:
        return {
            "check": "cron_job",
            "ok": False,
            "detail": "no cron job references this skill",
            "hint": "See docs/cron-setup.md for the command; the plugin's after-install.md "
            "walks through it.",
        }

    return {
        "check": "cron_job",
        "ok": True,
        "detail": "; ".join(_job_summary(job) for job in matches),
    }


def _references_skill(job: dict, namespaced: str) -> bool:
    skills = job.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    return (
        SKILL_NAME in skills
        or namespaced in str(job.get("prompt") or "")
        or PLUGIN_NAME in str(job.get("name") or "")
    )


def _token_refresh_check(jobs: list[dict] | None, error: str) -> dict:
    """Whether something renews the token before the 60 days run out.

    Its own check, not part of ``cron_job``: a refresh job neither names this
    skill nor attaches it, so the job that keeps publishing alive would otherwise
    be the one nobody looks for.
    """
    if jobs is None:
        return {
            "check": "token_refresh_job",
            "ok": False,
            "detail": error,
            "hint": TOKEN_REFRESH_HINT,
        }

    matches = [job for job in jobs if _looks_like_token_refresh(job)]
    if not matches:
        return {
            "check": "token_refresh_job",
            "ok": False,
            "detail": "no cron job refreshes the Threads token",
            "hint": TOKEN_REFRESH_HINT,
        }

    return {
        "check": "token_refresh_job",
        "ok": True,
        "detail": "; ".join(_job_summary(job) for job in matches),
    }


def _looks_like_token_refresh(job: dict) -> bool:
    """Match on script, name or prompt — the operator names the job.

    A false positive costs one green line; a false negative nags about a job that
    exists, so this leans generous on the two words that mean the same thing in
    any wording of it.
    """
    haystack = " ".join(str(job.get(key) or "") for key in ("script", "name", "prompt")).lower()
    if "threads_token" in haystack or "refresh_access_token" in haystack:
        return True
    words = set(re.findall(r"[a-z0-9]+", haystack))
    return "token" in words and "refresh" in words


def _unsynced_publishes() -> list[dict]:
    """Best-effort read of the plugin's publish ledger, outside Hermes.

    Which directory holds the ledger depends on who wrote it, and the two do
    not agree. Inside Hermes the plugin writes through ``ctx.state``, and Hermes
    namespaces a native plugin's state as
    ``plugin-data/agent-plugin-<slug>-<hash>/`` rather than by the plugin id —
    Windows-safe and collision-proof, but not derivable from this plugin's name.
    Outside Hermes, ``runtime.py`` falls back to ``plugin-data/<plugin>/``, which
    is also the ``plugin_data_dir()`` convention.

    So do not derive the path. Walk ``plugin-data`` and key on the payload: any
    ``state.json`` carrying a ``publish_ledger`` is this plugin's, wherever it
    landed. A ledger that goes unfound here is a publish that went live without
    its Sheet write going unnoticed, which is the one thing this check exists
    for.
    """
    root = hermes_home() / "plugin-data"
    if not root.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(root.glob("*/state.json")):
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
