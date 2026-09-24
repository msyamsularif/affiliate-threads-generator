"""Effective settings for one tool call.

Resolution order, highest priority first:

1. explicit arguments passed to the tool by the model
2. plugin settings (``plugins.entries.affiliate-threads-generator.settings.*``)
3. environment variables (``THREADS_ACCESS_TOKEN``, ``AFFILIATE_SHEET_ID``, ...)
4. the defaults in this module

Nothing here reaches out to the network, so it is safe to call on every request.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from . import runtime

# --------------------------------------------------------------------------- #
# Column layout — the Sheet contract from the specification
# --------------------------------------------------------------------------- #

#: Default layout: ``ID | Product | Description | Affiliate URL | Category | Threads URL | Status``
COLUMNS: dict[str, str] = {
    "id": "A",
    "product": "B",
    "description": "C",
    "affiliate_url": "D",
    "category": "E",
    "threads_url": "F",
    "status": "G",
}

_COLUMN_LETTER_RE = re.compile(r"[A-Z]{1,3}")

DEFAULT_TAB = "Sheet1"

#: Env var names consulted before falling back to a hard-coded default.
ENV_FALLBACKS: dict[str, str] = {
    "spreadsheet_id": "AFFILIATE_SHEET_ID",
    "sheet_tab": "AFFILIATE_SHEET_TAB",
    "threads_user_id": "THREADS_USER_ID",
    "google_api_path": "HERMES_GAPI_PATH",
    "google_api_command": "HERMES_GAPI_COMMAND",
}


def column_index(letter: str) -> int:
    """``"A"`` -> 1, ``"G"`` -> 7. Raises ``ValueError`` on junk."""
    letter = (letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", letter):
        raise ValueError(f"not a column letter: {letter!r}")
    total = 0
    for char in letter:
        total = total * 26 + (ord(char) - ord("A") + 1)
    return total


def column_letter(index: int) -> str:
    """1 -> ``"A"``, 27 -> ``"AA"``."""
    if index < 1:
        raise ValueError("column index must be >= 1")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _as_bool(value: Any, default: bool) -> bool:  # noqa: ANN401
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "y"}:
            return True
        if lowered in {"0", "false", "no", "off", "n"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value: Any, default: int) -> int:  # noqa: ANN401
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _disclosure_style(value: Any) -> str:  # noqa: ANN401
    """``tag`` or ``marker``; anything unrecognised falls back to ``marker``."""
    text = str(value or "").strip().lower()
    return text if text in DISCLOSURE_STYLES else DEFAULT_DISCLOSURE_STYLE


def _publish_mode(value: Any) -> str:  # noqa: ANN401
    """``two_stage`` or ``single``; anything unrecognised falls back to ``single``."""
    text = str(value or "").strip().lower()
    return text if text in PUBLISH_MODES else DEFAULT_PUBLISH_MODE


def _link_pending_status(settings: Settings) -> str:
    """The status that means "the thread is live, its link reply is not".

    It has to be a value no other part of the flow already uses: were it the
    eligible status the row could be published twice, and were it ``Hold`` the
    hold would read as a deferred link. A collision falls back to the default,
    and then to a default that cannot collide.
    """
    reserved = {
        settings.eligible_status,
        settings.done_status,
        settings.hold_status,
        settings.cancel_status,
        settings.in_progress_status,
    }
    candidate = settings.link_pending_status.strip()
    if not candidate or candidate in reserved:
        candidate = DEFAULT_LINK_PENDING_STATUS
    if candidate in reserved:
        candidate = f"{DEFAULT_LINK_PENDING_STATUS} (reply due)"
    return candidate


def _as_str_list(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:  # noqa: ANN401
    if value is None or value == "" or value == []:
        return default
    if isinstance(value, str):
        # Settings forms store list values as JSON; also accept a comma/newline list.
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return tuple(str(item) for item in parsed)
        return tuple(part.strip() for part in re.split(r"[,\n]", text) if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return default


def _as_columns(value: Any) -> dict[str, str]:  # noqa: ANN401
    """Build the effective column map, falling back to the documented layout.

    A layout that names the same column twice would silently corrupt writes, so
    a contradictory map is discarded wholesale rather than partially applied.
    """
    raw: Any = value  # noqa: ANN401
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return dict(COLUMNS)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return dict(COLUMNS)
    if not isinstance(raw, dict):
        return dict(COLUMNS)

    columns = dict(COLUMNS)
    for key, letter in raw.items():
        if key not in COLUMNS or not isinstance(letter, str):
            continue
        candidate = letter.strip().upper()
        if _COLUMN_LETTER_RE.fullmatch(candidate):
            columns[key] = candidate

    if len(set(columns.values())) != len(columns):
        return dict(COLUMNS)
    return columns


DEFAULT_DISCLOSURE_MARKERS: tuple[str, ...] = (
    "#ad",
    "#ads",
    "#affiliate",
    "#afiliasi",
    "link afiliasi",
    "affiliate link",
    "tautan afiliasi",
    "komisi",
    "paid partnership",
    "iklan berbayar",
)

#: How the disclosure has to be written.
#:
#: ``marker`` — any configured marker, in any post (the default, and the most
#: permissive shape).
#: ``tag`` — a hashtag marker from ``disclosure_markers`` must appear in the
#: final post. A bare ``#ad`` there is enough; no sentence mentioning commission
#: is needed, and markers of the sentence form do not satisfy it.
DISCLOSURE_STYLES: tuple[str, ...] = ("marker", "tag")
DEFAULT_DISCLOSURE_STYLE = "marker"

#: How the affiliate link reaches the thread.
#:
#: ``single`` — the whole thread, link included, publishes in one call.
#: ``two_stage`` — the thread publishes first and the row moves to
#: ``link_pending_status``; the affiliate link then goes out as a reply to it.
#: That is the "let the post collect views, then attach the link" tactic, and it
#: is only possible because the second half is a separate, human-approved call.
SINGLE_MODE = "single"
TWO_STAGE_MODE = "two_stage"
PUBLISH_MODES: tuple[str, ...] = (SINGLE_MODE, TWO_STAGE_MODE)
DEFAULT_PUBLISH_MODE = SINGLE_MODE

#: Status written after the first half of a two-stage publish.
DEFAULT_LINK_PENDING_STATUS = "Link Pending"

#: Fabricated-personal-experience patterns. The system has no first-hand
#: experience with any product and none is ever supplied, so these may not ship.
DEFAULT_BLOCKED_PHRASES: tuple[str, ...] = (
    # Past-tense first-hand claims
    r"\baku (sudah|udah|pernah|sering) (coba|nyoba|cobain|pakai|pake|beli|gunakan|pesan)\b",
    r"\bsaya (sudah|udah|pernah|sering) (coba|nyoba|cobain|pakai|pake|beli|gunakan|pesan)\b",
    # Present-tense first-hand claims ("Saya pakai ini setiap hari")
    r"\b(saya|aku) (pakai|pake|memakai|gunakan|menggunakan|pesan) (ini|itu|produk ini|produk itu|barang ini)\b",
    # Appeals to personal experience
    r"\bmenurut pengalaman (saya|aku)\b",
    r"\bpengalaman (saya|aku) (pakai|pake|memakai)\b",
    r"\bdi (rumah|kantor) (saya|aku) (pakai|pake)\b",
    # English equivalents
    r"\bi (have|'ve) (personally )?(tried|used|bought|tested)\b",
    r"\bi (use|used) (this|it) every day\b",
    r"\bwhen i (tried|used|bought|tested)\b",
    r"\bin my (own )?experience\b",
)


@dataclass(frozen=True)
class Settings:
    """Everything one publish/check call needs to know."""

    spreadsheet_id: str = ""
    sheet_tab: str = DEFAULT_TAB

    #: field name -> column letter. Defaults to the documented contract.
    columns: Mapping[str, str] = field(default_factory=lambda: dict(COLUMNS))

    # Status vocabulary
    eligible_status: str = "Ready To Generate"
    done_status: str = "Done"
    hold_status: str = "Hold"
    cancel_status: str = "Cancel"
    in_progress_status: str = "In Progress"

    # Publish guardrails
    require_disclosure: bool = True
    #: ``marker``: any configured marker, anywhere. ``tag``: a hashtag marker on
    #: the final post, which is enough on its own — see ``DISCLOSURE_STYLES``.
    disclosure_style: str = DEFAULT_DISCLOSURE_STYLE
    disclosure_markers: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_DISCLOSURE_MARKERS
    )
    require_affiliate_url: bool = True
    blocked_phrases: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_BLOCKED_PHRASES
    )
    min_posts: int = 3
    #: Upper bound on thread length. Long enough for the multi-sub-thread shape
    #: (a hook post, several short observations, a closing practical note), which
    #: a 6-post ceiling cut off mid-argument.
    max_posts: int = 10
    max_chars_per_post: int = 500
    max_links_per_post: int = 5
    container_wait_seconds: int = 5

    #: ``single`` or ``two_stage`` — see ``PUBLISH_MODES``.
    publish_mode: str = DEFAULT_PUBLISH_MODE
    #: Status written when a two-stage thread is live but its link reply is not
    #: posted yet. Normalised away from the other statuses in ``resolve()``.
    link_pending_status: str = DEFAULT_LINK_PENDING_STATUS

    # Structural soft signals — warnings only, never blocks. These are
    # thresholds, not bans: one "Jadi," is ordinary prose, three is a rhythm
    # problem. A value of 0 disables that signal.
    signposting_warning_threshold: int = 2
    transition_warning_threshold: int = 3
    enumeration_warning_threshold: int = 2
    spec_token_warning_threshold: int = 6

    # Sheets plumbing
    google_api_path: str = ""
    google_api_command: str = "{python} {script}"
    sheet_timeout_seconds: int = 60

    # Approval + audit
    require_approval_prompt: bool = True
    content_language: str = "id"

    # Credentials
    threads_access_token: str = ""
    threads_user_id: str = ""

    # ---- derived helpers -------------------------------------------------

    @property
    def last_column(self) -> str:
        return column_letter(max(column_index(letter) for letter in self.columns.values()))

    @property
    def full_range(self) -> str:
        return f"{self.sheet_tab}!A1:{self.last_column}"

    def row_range(self, row: int, *fields: str) -> str:
        """A1 range covering ``fields`` (keys of ``columns``) on ``row``."""
        names = fields or tuple(self.columns)
        indexes = sorted(column_index(self.columns[name]) for name in names)
        start, end = indexes[0], indexes[-1]
        return f"{self.sheet_tab}!{column_letter(start)}{row}:{column_letter(end)}{row}"

    def cell_range(self, row: int, field_name: str) -> str:
        letter = self.columns[field_name]
        return f"{self.sheet_tab}!{letter}{row}"

    @property
    def two_stage(self) -> bool:
        """Whether the affiliate link goes out as a separate reply."""
        return self.publish_mode == TWO_STAGE_MODE

    @property
    def credentials_configured(self) -> bool:
        return bool(self.threads_access_token)

    def public_summary(self) -> dict[str, Any]:
        """Settings safe to echo back to the model — no secrets."""
        return {
            "spreadsheet_id": self.spreadsheet_id or None,
            "sheet_tab": self.sheet_tab,
            "columns": dict(self.columns),
            "eligible_status": self.eligible_status,
            "done_status": self.done_status,
            "require_disclosure": self.require_disclosure,
            "disclosure_style": self.disclosure_style,
            "require_affiliate_url": self.require_affiliate_url,
            "min_posts": self.min_posts,
            "max_posts": self.max_posts,
            "publish_mode": self.publish_mode,
            "link_pending_status": self.link_pending_status,
            "max_chars_per_post": self.max_chars_per_post,
            "max_links_per_post": self.max_links_per_post,
            "container_wait_seconds": self.container_wait_seconds,
            "signposting_warning_threshold": self.signposting_warning_threshold,
            "transition_warning_threshold": self.transition_warning_threshold,
            "enumeration_warning_threshold": self.enumeration_warning_threshold,
            "spec_token_warning_threshold": self.spec_token_warning_threshold,
            "require_approval_prompt": self.require_approval_prompt,
            "content_language": self.content_language,
            "threads_credentials_configured": self.credentials_configured,
            "threads_user_id": self.threads_user_id or None,
            "google_api_path": self.google_api_path or None,
        }


def _lookup(key: str, default: Any) -> Any:  # noqa: ANN401
    value = runtime.get_setting(key, default=None)
    if value not in (None, "", [], {}):
        return value
    env_name = ENV_FALLBACKS.get(key)
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value
    return default


def resolve(overrides: dict[str, Any] | None = None) -> Settings:
    """Build the effective settings for this call."""
    base = Settings(
        spreadsheet_id=str(_lookup("spreadsheet_id", "") or "").strip(),
        sheet_tab=str(_lookup("sheet_tab", DEFAULT_TAB) or DEFAULT_TAB).strip() or DEFAULT_TAB,
        columns=_as_columns(_lookup("columns", None)),
        eligible_status=str(_lookup("eligible_status", "Ready To Generate")).strip(),
        done_status=str(_lookup("done_status", "Done")).strip(),
        hold_status=str(_lookup("hold_status", "Hold")).strip(),
        cancel_status=str(_lookup("cancel_status", "Cancel")).strip(),
        in_progress_status=str(_lookup("in_progress_status", "In Progress")).strip(),
        require_disclosure=_as_bool(_lookup("require_disclosure", True), True),
        disclosure_style=_disclosure_style(_lookup("disclosure_style", DEFAULT_DISCLOSURE_STYLE)),
        disclosure_markers=_as_str_list(
            _lookup("disclosure_markers", None), DEFAULT_DISCLOSURE_MARKERS
        ),
        require_affiliate_url=_as_bool(_lookup("require_affiliate_url", True), True),
        blocked_phrases=_as_str_list(
            _lookup("blocked_phrases", None), DEFAULT_BLOCKED_PHRASES
        ),
        min_posts=_as_int(_lookup("min_posts", 3), 3),
        max_posts=_as_int(_lookup("max_posts", 10), 10),
        publish_mode=_publish_mode(_lookup("publish_mode", DEFAULT_PUBLISH_MODE)),
        link_pending_status=str(
            _lookup("link_pending_status", DEFAULT_LINK_PENDING_STATUS) or ""
        ).strip(),
        max_chars_per_post=_as_int(_lookup("max_chars_per_post", 500), 500),
        max_links_per_post=_as_int(_lookup("max_links_per_post", 5), 5),
        container_wait_seconds=_as_int(_lookup("container_wait_seconds", 5), 5),
        signposting_warning_threshold=_as_int(_lookup("signposting_warning_threshold", 2), 2),
        transition_warning_threshold=_as_int(_lookup("transition_warning_threshold", 3), 3),
        enumeration_warning_threshold=_as_int(_lookup("enumeration_warning_threshold", 2), 2),
        spec_token_warning_threshold=_as_int(_lookup("spec_token_warning_threshold", 6), 6),
        google_api_path=str(_lookup("google_api_path", "") or "").strip(),
        google_api_command=str(_lookup("google_api_command", "{python} {script}")).strip()
        or "{python} {script}",
        sheet_timeout_seconds=_as_int(_lookup("sheet_timeout_seconds", 60), 60),
        require_approval_prompt=_as_bool(_lookup("require_approval_prompt", True), True),
        content_language=str(_lookup("content_language", "id") or "id").strip().lower(),
        threads_access_token=str(
            os.environ.get("THREADS_ACCESS_TOKEN", "")
            or _lookup("threads_access_token", "")
            or ""
        ).strip(),
        threads_user_id=str(_lookup("threads_user_id", "") or "").strip(),
    )

    if overrides:
        clean = {
            key: value
            for key, value in overrides.items()
            if value not in (None, "") and key in Settings.__dataclass_fields__
        }
        if "columns" in clean:
            clean["columns"] = _as_columns(clean["columns"])
        if clean:
            base = replace(base, **clean)

    if base.max_posts < 1:
        base = replace(base, max_posts=1)
    if base.min_posts < 1:
        base = replace(base, min_posts=1)
    if base.min_posts > base.max_posts:
        base = replace(base, min_posts=base.max_posts)
    base = replace(base, link_pending_status=_link_pending_status(base))
    return base
