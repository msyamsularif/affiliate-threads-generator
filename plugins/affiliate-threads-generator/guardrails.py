"""Hard and soft content guardrails, enforced in code before anything is published.

Two classes of finding:

``violations``
    Hard stops. ``threads_publish`` refuses to publish when any are present.
    These are the rules a model must not be trusted to self-police: platform
    limits, the affiliate disclosure, and the fabricated-personal-experience ban.

``warnings``
    Soft signals — the anti-slop "suspicious phrase" list and similar. They are
    reported back to the model so it can rewrite, but they never block.

Nothing here does I/O, so it is cheap to run on every draft.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .config import Settings

# --------------------------------------------------------------------------- #
# Character counting
# --------------------------------------------------------------------------- #

def threads_char_count(text: str) -> int:
    """Threads' own character rule: an emoji counts as its UTF-8 byte length.

    Every non-ASCII character is charged its UTF-8 length rather than 1, which
    is exact for emoji and conservative for accented Latin text. A plain
    ``len()`` would happily let an emoji-heavy post through and then fail
    server-side.
    """
    total = 0
    for char in text or "":
        total += 1 if ord(char) < 0x80 else len(char.encode("utf-8"))
    return total


# --------------------------------------------------------------------------- #
# Link counting
# --------------------------------------------------------------------------- #

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]]+", re.IGNORECASE)
_TRAILING_JUNK = ".,;:!?)]}"


def extract_links(text: str) -> list[str]:
    """Unique URLs in ``text``, in first-seen order, normalised for comparison."""
    seen: dict[str, None] = {}
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(_TRAILING_JUNK)
        key = url.lower()
        key = re.sub(r"^https?://", "", key).rstrip("/")
        if key not in seen:
            seen[key] = None
    return list(seen)


def count_links(text: str) -> int:
    return len(extract_links(text))


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    code: str
    message: str
    post_index: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.post_index is not None:
            payload["post"] = self.post_index + 1
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class GuardrailReport:
    violations: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": [item.as_dict() for item in self.violations],
            "warnings": [item.as_dict() for item in self.warnings],
        }


# --------------------------------------------------------------------------- #
# Anti-slop phrase list (spec section 10.7) — warnings only
# --------------------------------------------------------------------------- #

DEFAULT_SUSPICIOUS_PHRASES: tuple[str, ...] = (
    "praktis dan nyaman digunakan",
    "cocok untuk berbagai kebutuhan",
    "wajib banget punya",
    "solusi yang tepat untuk kamu",
    "solusi yang tepat untuk anda",
    "di era sekarang",
    "tidak perlu khawatir lagi",
    "worth it banget",
    "game changer",
    "must have",
    "solusi terbaik",
    "kualitas terjamin",
)

#: Phrases that read as an obvious model tic rather than a person writing.
DEFAULT_AI_TIC_PHRASES: tuple[str, ...] = (
    "sebagai kesimpulan",
    "dalam kesimpulan",
    "penting untuk dicatat bahwa",
    "tidak hanya itu",
    "mari kita bahas",
    "in conclusion",
    "it is important to note",
    "let's dive in",
    "delve into",
    "in today's fast-paced",
)

_DISCLOSURE_SIGNAL_RE = re.compile(
    r"(#ad\b|#ads\b|#affiliate\b|#afiliasi\b|afiliasi|affiliate|komisi|berbayar|sponsor|paid partnership)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# The validator
# --------------------------------------------------------------------------- #

def validate_thread(
    posts: Sequence[dict[str, Any]],
    settings: Settings,
    *,
    affiliate_url: str = "",
    product_name: str = "",
    suspicious_phrases: Iterable[str] = DEFAULT_SUSPICIOUS_PHRASES,
    ai_tic_phrases: Iterable[str] = DEFAULT_AI_TIC_PHRASES,
) -> GuardrailReport:
    """Check a thread against every rule that must not depend on model judgement."""
    report = GuardrailReport()

    # ---- shape ----------------------------------------------------------
    if not posts:
        report.violations.append(
            Finding("no_posts", "The thread is empty — there is nothing to publish.")
        )
        return report

    if len(posts) < settings.min_posts:
        report.violations.append(
            Finding(
                "too_few_posts",
                f"The thread has {len(posts)} post(s); at least {settings.min_posts} are required. "
                "A thread that short reads as an advertisement, not a conversation.",
                detail={"min": settings.min_posts, "actual": len(posts)},
            )
        )
    if len(posts) > settings.max_posts:
        report.violations.append(
            Finding(
                "too_many_posts",
                f"The thread has {len(posts)} posts; at most {settings.max_posts} are allowed.",
                detail={"max": settings.max_posts, "actual": len(posts)},
            )
        )

    # ---- per-post limits -------------------------------------------------
    for index, post in enumerate(posts):
        text = str(post.get("text") or "")
        if not text.strip():
            report.violations.append(
                Finding("empty_post", "This post has no text.", post_index=index)
            )
            continue

        char_count = threads_char_count(text)
        if char_count > settings.max_chars_per_post:
            report.violations.append(
                Finding(
                    "post_too_long",
                    f"{char_count} characters; Threads allows {settings.max_chars_per_post}. "
                    "Emoji are counted as their UTF-8 byte length.",
                    post_index=index,
                    detail={"count": char_count, "limit": settings.max_chars_per_post},
                )
            )

        links = count_links(text)
        if links > settings.max_links_per_post:
            report.violations.append(
                Finding(
                    "too_many_links",
                    f"{links} unique links in one post; Threads rejects more than "
                    f"{settings.max_links_per_post}.",
                    post_index=index,
                    detail={"count": links, "limit": settings.max_links_per_post},
                )
            )

        image_url = str(post.get("image_url") or "").strip()
        if image_url and not image_url.lower().startswith("https://"):
            report.violations.append(
                Finding(
                    "bad_image_url",
                    "image_url must be a public https:// URL — Threads fetches it itself.",
                    post_index=index,
                )
            )

    # ---- fabricated personal experience (hard rule) ----------------------
    for index, post in enumerate(posts):
        text = str(post.get("text") or "")
        for pattern in settings.blocked_phrases:
            try:
                match = re.search(pattern, text, re.IGNORECASE)
            except re.error:
                continue  # a user-supplied pattern that will not compile is not our problem
            if match:
                report.violations.append(
                    Finding(
                        "fabricated_personal_experience",
                        f'Blocked phrase "{match.group(0)}". This system has no first-hand '
                        "experience with the product, so it may never claim any. Rewrite as an "
                        'observation: "Dari spesifikasi produk...", "Berdasarkan review yang '
                        'tersedia...", "Untuk skenario seperti ini...".',
                        post_index=index,
                        detail={"match": match.group(0)},
                    )
                )

    # ---- affiliate disclosure (hard rule) --------------------------------
    if settings.require_disclosure:
        markers = tuple(marker.lower() for marker in settings.disclosure_markers)
        if not any(
            marker in str(post.get("text") or "").lower()
            for post in posts
            for marker in markers
        ):
            report.violations.append(
                Finding(
                    "missing_disclosure",
                    "No post carries an affiliate disclosure. Add one of: "
                    + ", ".join(settings.disclosure_markers[:6])
                    + ". Reducing the hard-sell tone is fine; hiding the commercial "
                    "relationship is not.",
                )
            )

    # ---- affiliate URL (hard rule) ---------------------------------------
    if settings.require_affiliate_url:
        if not affiliate_url:
            report.violations.append(
                Finding(
                    "affiliate_url_missing_from_row",
                    "The Sheet row has no Affiliate URL, so the CTA cannot be built. Fill in the "
                    "Affiliate URL column first.",
                )
            )
        elif not _contains_url(posts, affiliate_url):
            report.violations.append(
                Finding(
                    "affiliate_url_not_in_thread",
                    "The row's Affiliate URL does not appear in any post. The link is the point "
                    "of the affiliate relationship — put it in the final post.",
                )
            )

    # ---- soft signals ----------------------------------------------------
    if affiliate_url and not settings.require_disclosure and not _contains_disclosure_signal(posts):
        report.warnings.append(
            Finding(
                "disclosure_not_obvious",
                "Disclosure is not enforced by config, but no post reads as a disclosure. "
                "Consider adding one.",
            )
        )

    lowered_posts = [str(post.get("text") or "").lower() for post in posts]
    for phrase in suspicious_phrases:
        needle = phrase.lower()
        for index, text in enumerate(lowered_posts):
            if needle in text:
                report.warnings.append(
                    Finding(
                        "generic_phrase",
                        f'"{phrase}" carries no specific information. Replace it with something '
                        "only true of this product.",
                        post_index=index,
                        detail={"phrase": phrase},
                    )
                )
                break

    for phrase in ai_tic_phrases:
        needle = phrase.lower()
        for index, text in enumerate(lowered_posts):
            if needle in text:
                report.warnings.append(
                    Finding(
                        "obvious_ai_phrase",
                        f'"{phrase}" reads as machine-written filler.',
                        post_index=index,
                        detail={"phrase": phrase},
                    )
                )
                break

    if product_name:
        mentions = sum(
            1 for text in lowered_posts if product_name.lower() in text
        )
        if mentions > 3:
            report.warnings.append(
                Finding(
                    "product_overexposed",
                    f"The product name appears in {mentions} posts. The product should support "
                    "the story, not be the story.",
                )
            )

    return report


def _contains_url(posts: Sequence[dict[str, Any]], url: str) -> bool:
    needle = url.strip().rstrip("/").lower()
    needle = re.sub(r"^https?://", "", needle)
    for post in posts:
        for found in extract_links(str(post.get("text") or "")):
            if found == needle or needle in found or found in needle:
                return True
    return False


def _contains_disclosure_signal(posts: Sequence[dict[str, Any]]) -> bool:
    return any(
        _DISCLOSURE_SIGNAL_RE.search(str(post.get("text") or "")) for post in posts
    )
