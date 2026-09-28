"""The content regression corpus.

``before/``
    Drafts that pass every hard guardrail but read as templated — the patterns
    the editorial layer exists to catch. They are here to prove the soft signals
    fire on them, and that nothing else did. A fixture may carry a ``recent``
    array (newest first) so the cross-thread repetition signals have something
    to compare against.

``expected/``
    The style target. It must stay clean: no violations and no structural
    warnings — the in-thread diversity signals included. If a guardrail change
    starts flagging one, the change is wrong, not the fixture. Some of them are
    written to pass in ``firsthand`` mode too (``experience`` + ``testimonial``).

``blocked/``
    Drafts a hard rule must refuse, each naming the violation code it exists
    for. Fake personal experience and guarantee language are the deterministic
    half of the acceptance list; the evidence review itself is judgement, and no
    fixture can pin judgement.

These tests do not generate anything. They pin the deterministic half of the
anti-slop and anti-template work, which is all a test can honestly pin — the
prose quality itself is the antislop audit's job, not a unit test's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atg_plugin import config, guardrails

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "content"

#: The warning codes for structural slop and anti-template diversity.
#: `generic_phrase` is deliberately not here: it is a separate, older signal.
STRUCTURAL_CODES = {
    # signposting, transition density, enumeration, spec density
    "excessive_signposting",
    "repeated_transition_density",
    "excessive_enumeration",
    "product_detail_density",
    # anti-template diversity — in-thread
    "uniform_post_length",
    "uniform_sentence_count",
    "opening_similarity",
    "explanation_density",
    # anti-template diversity — cross-thread (needs the fixture's `recent`)
    "product_entry_repetition",
    "cta_shape_repetition",
    "question_hook_repetition",
}

BEFORE_FIXTURES = sorted((FIXTURES / "before").glob("*.json"))
EXPECTED_FIXTURES = sorted((FIXTURES / "expected").glob("*.json"))
BLOCKED_FIXTURES = sorted((FIXTURES / "blocked").glob("*.json"))


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(fixture: dict, settings: config.Settings) -> guardrails.GuardrailReport:
    return guardrails.validate_thread(
        fixture["posts"],
        settings,
        affiliate_url=fixture.get("affiliate_url", ""),
        product_name=fixture.get("product_name", ""),
        experience=fixture.get("experience", config.NONE_MODE),
        testimonial=fixture.get("testimonial", ""),
        recent=fixture.get("recent", []),
    )


class TestCorpus:
    def test_all_three_sides_of_the_corpus_exist(self) -> None:
        assert BEFORE_FIXTURES, "the before/ corpus is empty"
        assert EXPECTED_FIXTURES, "the expected/ corpus is empty"
        assert BLOCKED_FIXTURES, "the blocked/ corpus is empty"

    @pytest.mark.parametrize("path", BEFORE_FIXTURES, ids=lambda path: path.stem)
    def test_before_drafts_are_legal_but_flagged(
        self, settings: config.Settings, path: Path
    ) -> None:
        """These pass the hard guardrails — that is the whole point.

        If one of them started failing, the guardrails changed behaviour rather
        than gaining a signal, and the editorial layer is no longer the only
        thing standing between this draft and a preview.
        """
        report = validate(load_fixture(path), settings)
        assert report.ok, [item.as_dict() for item in report.violations]
        assert STRUCTURAL_CODES & {item.code for item in report.warnings}, [
            item.as_dict() for item in report.warnings
        ]

    @pytest.mark.parametrize("path", EXPECTED_FIXTURES, ids=lambda path: path.stem)
    def test_expected_drafts_stay_clean(self, settings: config.Settings, path: Path) -> None:
        report = validate(load_fixture(path), settings)
        assert report.ok, [item.as_dict() for item in report.violations]
        assert not STRUCTURAL_CODES & {item.code for item in report.warnings}, [
            item.as_dict() for item in report.warnings
        ]

    @pytest.mark.parametrize("path", BLOCKED_FIXTURES, ids=lambda path: path.stem)
    def test_blocked_drafts_are_refused(self, settings: config.Settings, path: Path) -> None:
        """A hard rule still refuses them — the acceptance list's
        "fake personal experience → blocked" and "unsupported guarantees →
        blocked", pinned as codes rather than as judgement."""
        fixture = load_fixture(path)
        expected = set(fixture["expect_violations"])
        report = validate(fixture, settings)
        codes = {item.code for item in report.violations}
        assert expected <= codes, [item.as_dict() for item in report.violations]
