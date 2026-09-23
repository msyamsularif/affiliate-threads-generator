#!/usr/bin/env python3
"""Threads token operations — status, refresh, exchange.

A long-lived Threads user token is valid for 60 days and can be refreshed before
it expires. This is an ops action, not a business-state change, which is why it
lives in the skill rather than in the plugin's tool surface.

Environment
-----------
THREADS_ACCESS_TOKEN    the current token
THREADS_APP_SECRET      needed only for `exchange`

Usage
-----
    threads_token.py status
    threads_token.py refresh --write-env
    threads_token.py exchange --short-token <SHORT_LIVED_TOKEN> --write-env
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

ROOT_BASE = "https://graph.threads.net"  # the token endpoints live outside /v1.0


def hermes_home() -> Path:
    root = os.environ.get("HERMES_HOME", "").strip()
    return Path(root).expanduser() if root else Path.home() / ".hermes"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="threads_token.py",
        description="Inspect, refresh or exchange the Threads user access token.",
    )
    parser.add_argument("action", choices=("status", "refresh", "exchange"))
    parser.add_argument("--short-token", default="", help="For `exchange`: the short-lived token.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Persist the new token into $HERMES_HOME/.env (THREADS_ACCESS_TOKEN=...).",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = _bridge.load("config")
        threads_client = _bridge.load("threads_client")
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    settings = config.resolve()
    token = settings.threads_access_token
    if not token:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "THREADS_ACCESS_TOKEN is not set.",
                    "hint": (
                        "Set it with `hermes config set THREADS_ACCESS_TOKEN \"THQW...\"`, or "
                        "load the skill in the local CLI and let Hermes prompt for it. "
                        "See docs/credentials.md."
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 1

    try:
        if args.action == "status":
            return _status(config, threads_client, settings, args)
        if args.action == "refresh":
            return _refresh(threads_client, settings, args)
        return _exchange(threads_client, settings, args)
    except threads_client.ThreadsAPIError as exc:
        print(
            json.dumps(
                {"ok": False, "stage": exc.stage, "error": exc.message, "api": exc.as_dict()},
                ensure_ascii=False,
            )
        )
        return 1


def _status(config, threads_client, settings, args) -> int:  # noqa: ANN001
    client = threads_client.ThreadsClient(settings.threads_access_token, settings.threads_user_id)
    me = client.get_me()
    payload: dict = {
        "ok": True,
        "user_id": str(me.get("id") or ""),
        "username": str(me.get("username") or ""),
        "configured_user_id": settings.threads_user_id or None,
    }
    try:
        debug = client.debug_token()
        expires_at = debug.get("expires_at")
        payload["token_valid"] = debug.get("is_valid")
        payload["expires_at"] = _iso(expires_at)
        payload["days_remaining"] = _days(expires_at)
        payload["scopes"] = debug.get("scopes")
        if debug.get("is_valid") is False:
            payload["ok"] = False
            payload["hint"] = "The token is invalid. Run `exchange` with a fresh short-lived token."
        elif isinstance(payload.get("days_remaining"), (int, float)) and payload["days_remaining"] < 7:
            payload["hint"] = (
                "Token expires within a week. Run `refresh --write-env` to extend it another 60 days."
            )
    except threads_client.ThreadsAPIError as exc:
        payload["token_debug_error"] = exc.message

    _emit(payload, args)
    return 0 if payload.get("ok") else 1


def _refresh(threads_client, settings, args) -> int:  # noqa: ANN001
    client = threads_client.ThreadsClient(
        settings.threads_access_token, settings.threads_user_id, base_url=ROOT_BASE
    )
    body = client._call(  # noqa: SLF001 - the refresh endpoint is not part of the publishing API
        "GET", "/refresh_access_token", params={"grant_type": "th_refresh_token"}, stage="refresh"
    )
    new_token = str(body.get("access_token") or "")
    if not new_token:
        print(json.dumps({"ok": False, "error": "no access_token in the refresh response", "body": body}))
        return 1

    payload = {
        "ok": True,
        "action": "refresh",
        "expires_in": body.get("expires_in"),
        "token": _mask(new_token),
        "written_to_env": False,
    }
    if args.write_env:
        payload["written_to_env"] = _write_env(new_token)
        payload["env_path"] = str(hermes_home() / ".env")
    else:
        payload["token_full"] = new_token
        payload["hint"] = (
            "Not persisted. Re-run with --write-env, or copy token_full into "
            "~/.hermes/.env as THREADS_ACCESS_TOKEN and restart the gateway."
        )
    _emit(payload, args)
    return 0


def _exchange(threads_client, settings, args) -> int:  # noqa: ANN001
    if not args.short_token:
        print(json.dumps({"ok": False, "error": "--short-token is required for exchange."}))
        return 1
    app_secret = os.environ.get("THREADS_APP_SECRET", "").strip()
    if not app_secret:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "THREADS_APP_SECRET is not set.",
                    "hint": (
                        "The exchange endpoint needs the Threads app secret. Set it with "
                        "`hermes config set THREADS_APP_SECRET \"<secret>\"` before running "
                        "`exchange` — see docs/credentials.md."
                        "~/.hermes/.env as THREADS_APP_SECRET."
                    ),
                }
            )
        )
        return 1

    client = threads_client.ThreadsClient(args.short_token, settings.threads_user_id, base_url=ROOT_BASE)
    body = client._call(  # noqa: SLF001
        "GET",
        "/access_token",
        params={"grant_type": "th_exchange_token", "client_secret": app_secret},
        stage="exchange",
    )
    new_token = str(body.get("access_token") or "")
    if not new_token:
        print(json.dumps({"ok": False, "error": "no access_token in the exchange response", "body": body}))
        return 1

    payload = {
        "ok": True,
        "action": "exchange",
        "expires_in": body.get("expires_in"),
        "token": _mask(new_token),
        "written_to_env": False,
    }
    if args.write_env:
        payload["written_to_env"] = _write_env(new_token)
        payload["env_path"] = str(hermes_home() / ".env")
    else:
        payload["token_full"] = new_token
        payload["hint"] = "Not persisted. Re-run with --write-env to store it."
    _emit(payload, args)
    return 0


def _write_env(token: str) -> bool:
    """Rewrite ``THREADS_ACCESS_TOKEN`` in $HERMES_HOME/.env, preserving everything else."""
    env_path = hermes_home() / ".env"
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    except OSError:
        return False

    pattern = re.compile(r"^THREADS_ACCESS_TOKEN=.*$", re.MULTILINE)
    line = f"THREADS_ACCESS_TOKEN={token}"
    if pattern.search(existing):
        updated = pattern.sub(line, existing, count=1)
    else:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        updated = f"{existing}{separator}{line}\n"

    try:
        env_path.write_text(updated, encoding="utf-8")
        env_path.chmod(0o600)
    except OSError:
        return False
    return True


def _mask(token: str) -> str:
    return f"{token[:8]}...{token[-4:]}" if len(token) > 16 else "***"


def _iso(value) -> str | None:  # noqa: ANN001
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def _days(value) -> float | None:  # noqa: ANN001
    try:
        remaining = int(value) - int(datetime.now(tz=timezone.utc).timestamp())
        return round(remaining / 86400, 1)
    except (TypeError, ValueError):
        return None


def _emit(payload: dict, args: argparse.Namespace) -> None:
    if args.format == "text":
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
