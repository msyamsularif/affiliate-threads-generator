"""Hard and soft content guardrails, enforced in code before anything is published.

Two classes of finding:

``violations``
    Hard stops. ``threads_publish`` refuses to publish when any are present.
    These are the rules a model must not be trusted to self-police: platform
    limits, the personal-experience provenance rule
    (a blanket ban in ``none`` mode, grounded-claim checks in ``firsthand``
    mode), guarantee/absolute language, hashtags left in the copy, and a topic
    tag the API would reject.

``warnings``
    Soft signals: the affiliate-cliché phrase list, funnel language, the
    seller-viewpoint list (copy written from the seller's seat, or a claim
    repeated from the Description), and a handful of cheap structural counters
    (signposting, transition density, enumeration, spec density). They are
    reported back to the model so it can rewrite, but they never block — and
    none of them is proof that a text is AI-written. The prose audit itself
    belongs to the external ``antislop`` / ``antislop-copywriting`` skills,
    not here.

Nothing here does I/O, so it is cheap to run on every draft.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .config import EXPERIENCE_MODES, FIRSTHAND_MODE, NONE_MODE, Settings

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
# Hashtags
# --------------------------------------------------------------------------- #

def extract_hashtags(text: str) -> list[str]:
    """Hashtag-shaped tokens in ``text``, without the ``#`` and de-duplicated.

    URL fragments are masked first, so ``https://example.com/#top`` is a link
    and not a tag, and pure numbers are skipped because ``#1`` is a number sign
    rather than a topic on Threads.
    """
    cleaned = _URL_RE.sub(" ", text or "")
    seen: dict[str, None] = {}
    for match in _HASHTAG_RE.finditer(cleaned):
        token = match.group(1)
        if token.isdigit():
            continue
        seen.setdefault(token, None)
    return list(seen)


def _hashtags_allowed(settings: Settings) -> set[str]:
    """Tags the copy may keep: ``allowed_hashtags``, and nothing else.

    Empty by default. The copy carries no hashtags at all unless an operator
    deliberately allowlists a token like ``#ootd``.
    """
    allowed = {
        str(tag).strip().lower().lstrip("#") for tag in settings.allowed_hashtags if str(tag).strip()
    }
    return {tag for tag in allowed if tag}


# --------------------------------------------------------------------------- #
# Topic tags
# --------------------------------------------------------------------------- #

def topic_tag_problem(tag: str) -> str:
    """Why ``tag`` cannot be sent as Threads' ``topic_tag``, or ``""``.

    The API's own limits: at least 1 and at most 50 characters, with periods
    and ampersands rejected. A leading ``#`` is how the tag is *displayed*; the
    parameter takes the bare topic, so one is reported here rather than sent and
    double-tagged.
    """
    text = (tag or "").strip()
    if not text:
        return "The topic tag is empty."
    if text.startswith("#"):
        return (
            f'Write the topic without the leading "#": "{text.lstrip("#").strip()}", not "{text}". '
            "The parameter takes the bare topic."
        )
    if len(text) > TOPIC_TAG_MAX_CHARS:
        return (
            f"The topic tag is {len(text)} characters; Threads allows at most "
            f"{TOPIC_TAG_MAX_CHARS}."
        )
    if "\n" in text or "\r" in text:
        return "The topic tag has to be one line."
    forbidden = [char for char in TOPIC_TAG_FORBIDDEN_CHARS if char in text]
    if forbidden:
        return (
            "Threads rejects "
            + " and ".join(f'"{char}"' for char in forbidden)
            + " in a topic tag."
        )
    return ""


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
# Soft-signal vocabularies (warnings only)
# --------------------------------------------------------------------------- #
#
# Deliberately small. The generic AI-prose catalogue — fake-candid openers,
# rule-of-three, negative parallelism, staccato drama, filler — belongs to the
# external antislop skills, which are better at prose than a substring list.
# What stays here is what is specific to affiliate product copy.

DEFAULT_SUSPICIOUS_PHRASES: tuple[str, ...] = (
    "praktis dan nyaman digunakan",
    "cocok untuk berbagai kebutuhan",
    "wajib banget punya",
    "solusi yang tepat untuk kamu",
    "kualitas terjamin",
    "worth it banget",
    "game changer",
    "must have",
)

#: Sentence openers that narrate the reasoning instead of carrying meaning.
#: Matched only at a sentence boundary, so "jadi" inside "menjadi" is invisible.
DEFAULT_TRANSITION_WORDS: tuple[str, ...] = (
    "jadi",
    "makanya",
    "contohnya",
    "dengan kata lain",
    "kesimpulannya",
    "singkatnya",
)

#: Enumeration markers, matched only when followed by a comma or colon — so
#: "pertama kali" does not count, but "Pertama, ... Kedua, ..." does.
DEFAULT_ENUMERATION_WORDS: tuple[str, ...] = (
    "pertama",
    "kedua",
    "ketiga",
    "keempat",
)

#: Meta-commentary that announces what the text is about to do.
DEFAULT_SIGNPOSTING_PHRASES: tuple[str, ...] = (
    "mari kita bahas",
    "di artikel ini",
    "kali ini kita akan",
    "sebelum masuk ke",
    "yang perlu kamu tahu",
    "perlu dicatat bahwa",
    "let's dive in",
    "here's what you need to know",
)

#: A number with a unit — the cheapest deterministic proxy for spec dumping.
_SPEC_TOKEN_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:mah|wh|kwh|watt|volt|gram|kg|mg|cm|mm|km|ml|liter"
    r"|jam|menit|detik|inci|inch|w|v|g|l)\b"
    r"|\d+(?:[.,]\d+)?\s*[\"\u201d]",
    re.IGNORECASE,
)

#: Hashtag-shaped tokens. Threads is not Instagram: exactly one tag per post is
#: clickable, it is called a topic tag, and it is set through the API's
#: ``topic_tag`` parameter instead of being written into the copy. A trail of
#: hashtags at the end of a reply therefore buys nothing and reads as spam, so
#: the copy carries none unless the operator explicitly allowlists a token
#: (``allowed_hashtags``).
_HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)

#: The platform's own limits, from the Threads API's ``topic_tag`` parameter.
TOPIC_TAG_MAX_CHARS = 50
TOPIC_TAG_FORBIDDEN_CHARS = (".", "&")

#: Funnel language: copy whose only job is to move the reader toward the link
#: instead of giving them something to click *for*. Warnings only — the fix is a
#: rewrite — but this is the pattern that makes a thread read as an
#: advertisement, so it is worth saying out loud every time.
DEFAULT_FUNNEL_PHRASES: tuple[str, ...] = (
    "link di bio",
    "cek bio",
    "link di bawah",
    "link-nya di bawah",
    "cek link di bawah",
    "link menyusul",
    "link di reply",
    "cek reply",
    "klik link",
    "dm aku",
    "dm aja",
    "chat aku",
    "komen dulu",
    "buruan",
    "jangan sampai kehabisan",
)

#: The seller's seat: copy that repeats the seller's own words or speaks from
#: their side of the counter. The `Description` column orients the research —
#: it is never copy material, and neither its claims nor its voice belong in
#: the thread, attributed or not (``references/category-playbook.md``).
#: Warnings only: the honest fix is a rewrite, and a human chooses the wording.
DEFAULT_SELLER_VIEWPOINT_PHRASES: tuple[str, ...] = (
    # The seller's claim standing in for evidence
    "di deskripsi produknya",
    "klaim di deskripsi",
    "menurut deskripsi produk",
    "di halaman produknya",
    "menurut penjual",
    "kata penjual",
    "kata sellernya",
    "produsen mengklaim",
    "menurut produsen",
    # Seller-brochure vocabulary: praise, urgency, category superlatives
    "kualitas premium",
    "harga terjangkau",
    "solusi terbaik",
    "best seller",
    "wajib punya",
    "segera beli",
    "dapatkan sekarang",
    "diskon gila",
    "buruan checkout",
)


# --------------------------------------------------------------------------- #
# Experience provenance helpers (used only in firsthand mode)
# --------------------------------------------------------------------------- #

#: Person nouns from the second-hand family in ``DEFAULT_BLOCKED_PHRASES``,
#: grouped by spelling (temen/teman is one person). A second-hand claim may
#: only name a person the stored testimony names — the same claim wearing
#: someone else is still a claim, and the reader reads it as the writer's own.
_SECOND_HAND_PERSON_GROUPS: tuple[tuple[str, ...], ...] = (
    ("anak",),
    ("bayi",),
    ("adik",),
    ("kakak",),
    ("istri",),
    ("suami",),
    ("ibu",),
    ("bapak",),
    ("temen", "teman"),
    ("sahabat",),
    ("sepupu",),
)

#: Quantified details — a number with a unit, or a frequency phrase. Inside a
#: first-hand sentence these are the details a reader trusts most, so they must
#: appear in the stored testimony too: an invented "tahan 2 hari" is exactly
#: the amplification the provenance rule exists to stop.
_EXPERIENCE_DETAIL_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:x|kali|hari|minggu|bulan|tahun|jam|menit|detik|malam"
    r"|pcs|buah|tablet|kapsul|botol|sachet)\b"
    r"|(?:setiap|tiap|per) (?:hari|minggu|bulan|tahun|malam)\b",
    re.IGNORECASE,
)

#: The pronouns that make a sentence first-hand. Deliberately the same set the
#: blocked-phrase defaults cover.
_FIRST_PERSON_RE = re.compile(r"\b(aku|saya|gua|gue)\b|\bi\b", re.IGNORECASE)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _testimonial_covers(token: str, testimonial: str) -> bool:
    """Whether the stored testimony contains ``token`` in any casing/spacing."""
    return _normalize_for_match(token) in _normalize_for_match(testimonial)


def _unnamed_person(match_text: str, testimonial: str) -> str:
    """The person a second-hand match names that the testimony does not, or ""."""
    for group in _SECOND_HAND_PERSON_GROUPS:
        if not any(re.search(rf"\b{re.escape(alias)}", match_text, re.IGNORECASE) for alias in group):
            continue
        if any(_testimonial_covers(alias, testimonial) for alias in group):
            return ""
        return group[0]
    return ""


# --------------------------------------------------------------------------- #
# The validator
# --------------------------------------------------------------------------- #

def validate_thread(
    posts: Sequence[dict[str, Any]],
    settings: Settings,
    *,
    affiliate_url: str = "",
    product_name: str = "",
    topic_tag: str | None = None,
    experience: str = NONE_MODE,
    testimonial: str = "",
    suspicious_phrases: Iterable[str] = DEFAULT_SUSPICIOUS_PHRASES,
    funnel_phrases: Iterable[str] = DEFAULT_FUNNEL_PHRASES,
    seller_viewpoint_phrases: Iterable[str] = DEFAULT_SELLER_VIEWPOINT_PHRASES,
    transition_words: Iterable[str] = DEFAULT_TRANSITION_WORDS,
    enumeration_words: Iterable[str] = DEFAULT_ENUMERATION_WORDS,
    signposting_phrases: Iterable[str] = DEFAULT_SIGNPOSTING_PHRASES,
) -> GuardrailReport:
    """Check a thread against every rule that must not depend on model judgement.

    ``topic_tag`` is the tag that will actually be sent with this publish. Pass
    the string (``""`` included, which is how "no tag was chosen" is checked
    against ``settings.require_topic_tag``), or ``None`` when the caller has no
    topic tag to check — a deferred link reply, for instance, or a unit test
    about the copy itself. The tag is metadata: it never appears in the posts.

    ``experience`` and ``testimonial`` come from the Sheet row, never from the
    model. ``firsthand`` (``Used=Yes`` plus a non-empty testimony) is the only
    mode where first-hand claims may ship, and even then nothing may go beyond
    what the testimony says. Everything else validates in ``none`` mode.
    """
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

    # ---- personal experience: provenance, not a blanket ban --------------
    # The system itself has no first-hand experience; what it can have is the
    # human's, stored in the Sheet (``Used`` + ``Testimonial``). The tool
    # derives the mode from that row — never the model — and it decides which
    # half of this rule runs:
    #
    # * ``none``      — nothing on file can substantiate a first-hand claim, so
    #                   a blocked phrase is a violation, exactly as before.
    # * ``firsthand`` — first-hand claims are allowed; what stays checked is
    #                   that the copy does not invent beyond the testimony.
    mode = experience if experience in EXPERIENCE_MODES else NONE_MODE
    testimonial_text = str(testimonial or "")

    for index, post in enumerate(posts):
        text = str(post.get("text") or "")
        if not text.strip():
            continue

        if mode == FIRSTHAND_MODE:
            # A second-hand claim may only name a person the testimony names.
            for pattern in settings.blocked_phrases:
                try:
                    match = re.search(pattern, text, re.IGNORECASE)
                except re.error:
                    continue
                if not match:
                    continue
                person = _unnamed_person(match.group(0), testimonial_text)
                if person:
                    report.violations.append(
                        Finding(
                            "experience_attribution_unsupported",
                            f'This post claims something about "{person}", but the stored '
                            "testimony never mentions that person. A second-hand claim is "
                            "still a claim: use the person the testimony actually describes, "
                            "or drop it.",
                            post_index=index,
                            detail={"match": match.group(0), "person": person},
                        )
                    )

            # Quantified details in a first-hand sentence must come from it too.
            for sentence in _SENTENCE_SPLIT_RE.split(text):
                if not _FIRST_PERSON_RE.search(sentence):
                    continue
                for detail in _EXPERIENCE_DETAIL_RE.finditer(sentence):
                    token = detail.group(0)
                    if _testimonial_covers(token, testimonial_text):
                        continue
                    report.violations.append(
                        Finding(
                            "experience_detail_unsupported",
                            f'"{token}" sits in a first-hand sentence but does not appear in '
                            "the stored testimony. First-hand copy may not add detail the human "
                            "did not write: drop the number, or use the wording the testimony "
                            "actually has.",
                            post_index=index,
                            detail={"detail": token},
                        )
                    )
        else:
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

    # ---- amplifier language (hard rule, both modes) ----------------------
    # A personal account is one data point. Guarantees and absolutes turn it
    # into a promise the operator cannot make — with or without testimony.
    for index, post in enumerate(posts):
        text = str(post.get("text") or "")
        for pattern in settings.amplifier_phrases:
            try:
                match = re.search(pattern, text, re.IGNORECASE)
            except re.error:
                continue
            if match:
                report.violations.append(
                    Finding(
                        "amplifier_language",
                        f'"{match.group(0)}" is a guarantee the copy cannot support. Even a '
                        "genuine first-hand account is one experience, not a promise — say what "
                        "it does for this case, hedged, or drop the claim.",
                        post_index=index,
                        detail={"match": match.group(0)},
                    )
                )

    # ---- hashtags in the copy (hard rule) --------------------------------
    # Threads turns exactly one tag per post into a clickable topic and that tag
    # is set through `topic_tag`. Hashtags written into the copy cannot add
    # reach, so they only make the post look like a listing. The copy therefore
    # carries none, unless the operator allowlists a token.
    allowed_tags = _hashtags_allowed(settings)
    for index, post in enumerate(posts):
        offenders = [
            tag for tag in extract_hashtags(str(post.get("text") or "")) if tag.lower() not in allowed_tags
        ]
        if offenders:
            listed = ", ".join(f"#{tag}" for tag in offenders)
            report.violations.append(
                Finding(
                    "hashtag_in_copy",
                    f"{listed} in the copy. Threads is not Instagram: one tag per post becomes the "
                    "topic tag, and that tag is set through the topic_tag parameter instead of "
                    "being written in the text. Hashtags left in the copy add no reach and read as "
                    "spam — put the topic in topic_tag and drop the trail. Only hashtags the "
                    "operator explicitly allowlists (allowed_hashtags) may stay.",
                    post_index=index,
                    detail={"tags": offenders},
                )
            )

    # ---- topic tag (hard rule when the operator asks for one) -------------
    # The tag is how a post reaches its topic feed and, when that topic has a
    # Threads community, the community itself. It is metadata, so it is checked
    # here rather than in the copy — but it is checked against the platform's
    # own limits, because a tag the API rejects is a failed publish.
    if topic_tag is not None:
        tag = topic_tag.strip()
        if not tag:
            if settings.require_topic_tag:
                report.violations.append(
                    Finding(
                        "topic_tag_missing",
                        "The thread has no topic tag. Threads uses topic tags for discovery — one "
                        "per post, set through the topic_tag parameter — and a topic that has a "
                        "community also surfaces the post there. Pick the topic a reader would "
                        "search for this conversation (not the product name), show it on the "
                        "preview, and pass it to threads_publish.",
                        detail={"require_topic_tag": True},
                    )
                )
        else:
            problem = topic_tag_problem(tag)
            if problem:
                report.violations.append(
                    Finding(
                        "topic_tag_invalid",
                        problem,
                        detail={"topic_tag": tag},
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

    for phrase in funnel_phrases:
        needle = phrase.lower()
        for index, text in enumerate(lowered_posts):
            if needle in text:
                report.warnings.append(
                    Finding(
                        "funnel_phrase",
                        f'"{phrase}" talks the reader toward the link instead of giving them a '
                        "reason to click. Say what they get — a detail, a boundary, a buying "
                        "consideration — and let the link post follow it.",
                        post_index=index,
                        detail={"phrase": phrase},
                    )
                )
                break

    for phrase in seller_viewpoint_phrases:
        needle = phrase.lower()
        for index, text in enumerate(lowered_posts):
            if needle in text:
                report.warnings.append(
                    Finding(
                        "seller_viewpoint",
                        f'"{phrase}" writes from the seller\'s seat. The Description orients the '
                        "research, it never writes the copy: its claims are leads to verify with "
                        "independent sources or to leave out — not to repeat, rephrase, or "
                        "attribute.",
                        post_index=index,
                        detail={"phrase": phrase},
                    )
                )
                break

    # ---- structural soft signals -----------------------------------------
    # Cheap counters for patterns that read as templated: narrated reasoning,
    # enumerated posts, announced structure, spec dumping. Each one is a prompt
    # to look again, never a verdict. A threshold of 0 disables the signal.
    raw_texts = [str(post.get("text") or "") for post in posts]

    if settings.signposting_warning_threshold > 0:
        hits = _phrase_hits(raw_texts, signposting_phrases)
        if len(hits) >= settings.signposting_warning_threshold:
            report.warnings.append(
                Finding(
                    "excessive_signposting",
                    f"{len(hits)} signposting phrase(s) announce what the thread is about to "
                    "do instead of doing it. Soft signal, not a block — cut the ones that add "
                    "nothing.",
                    detail={"count": len(hits), "matches": hits[:8]},
                )
            )

    if settings.transition_warning_threshold > 0:
        hits = _sentence_opener_hits(raw_texts, transition_words)
        if len(hits) >= settings.transition_warning_threshold:
            report.warnings.append(
                Finding(
                    "repeated_transition_density",
                    f"{len(hits)} sentence-opening transition(s) narrate the reasoning instead "
                    "of carrying meaning. Soft signal, not a block — a transition is worth "
                    "keeping only when it contributes something.",
                    detail={"count": len(hits), "matches": hits[:8]},
                )
            )

    if settings.enumeration_warning_threshold > 0:
        hits = _enumeration_hits(raw_texts, enumeration_words)
        if len(hits) >= settings.enumeration_warning_threshold:
            report.warnings.append(
                Finding(
                    "excessive_enumeration",
                    f"{len(hits)} enumeration marker(s) turn the thread into a list. Soft "
                    "signal, not a block — check whether the list is doing work the sentences "
                    "should be doing.",
                    detail={"count": len(hits), "matches": hits[:8]},
                )
            )

    if settings.spec_token_warning_threshold > 0:
        hits = _spec_token_hits(raw_texts)
        if len(hits) >= settings.spec_token_warning_threshold:
            report.warnings.append(
                Finding(
                    "product_detail_density",
                    f"{len(hits)} specification token(s) in one thread. Soft signal, not a "
                    "block — select the details the angle needs instead of listing what the "
                    "research happened to contain.",
                    detail={"count": len(hits), "matches": hits[:8]},
                )
            )
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


def _phrase_hits(texts: Sequence[str], phrases: Iterable[str]) -> list[str]:
    """Phrases that appear anywhere in the thread, counted once each."""
    hits: list[str] = []
    lowered = [text.lower() for text in texts]
    for phrase in phrases:
        needle = phrase.lower()
        if any(needle in text for text in lowered):
            hits.append(phrase)
    return hits


def _sentence_opener_hits(texts: Sequence[str], words: Iterable[str]) -> list[str]:
    """Words that open a sentence — so "jadi" inside "menjadi" does not count."""
    hits: list[str] = []
    for word in words:
        pattern = re.compile(
            r"(?:^|[.!?]\s+|\n)\s*" + re.escape(word) + r"\b", re.IGNORECASE
        )
        for text in texts:
            hits.extend([word] * len(pattern.findall(text)))
    return hits


def _enumeration_hits(texts: Sequence[str], words: Iterable[str]) -> list[str]:
    """Enumeration markers, matched only when a comma or colon follows them."""
    escaped = [re.escape(word) for word in words]
    if not escaped:
        return []
    pattern = re.compile(r"\b(?:" + "|".join(escaped) + r")\s*[,:]", re.IGNORECASE)
    hits: list[str] = []
    for text in texts:
        hits.extend(match.group(0) for match in pattern.finditer(text))
    return hits


def _spec_token_hits(texts: Sequence[str]) -> list[str]:
    """Number-plus-unit tokens — the cheapest proxy for spec dumping."""
    hits: list[str] = []
    for text in texts:
        hits.extend(match.group(0).strip() for match in _SPEC_TOKEN_RE.finditer(text))
    return hits
