"""Guardrail tests — the rules a model must not be trusted to self-police."""

from __future__ import annotations

import pytest

from atg_plugin import config, guardrails
from conftest import build_good_thread


class TestCharCount:
    def test_ascii_counts_one_per_character(self) -> None:
        assert guardrails.threads_char_count("hello world") == 11

    def test_emoji_counts_as_utf8_bytes(self) -> None:
        # A 4-byte emoji counts as 4, not 1.
        assert guardrails.threads_char_count("🔥") == 4

    def test_mixed_text_is_conservative(self) -> None:
        # 1 (a) + 4 (emoji) + 1 (b)
        assert guardrails.threads_char_count("a🔥b") == 6

    def test_empty(self) -> None:
        assert guardrails.threads_char_count("") == 0

    def test_limit_boundary_is_inclusive(self) -> None:
        text = "x" * 500
        assert guardrails.threads_char_count(text) == 500


class TestLinks:
    def test_counts_unique_links(self) -> None:
        text = "see https://a.example and https://b.example"
        assert guardrails.count_links(text) == 2

    def test_deduplicates_the_same_url(self) -> None:
        text = "https://a.example https://a.example"
        assert guardrails.count_links(text) == 1

    def test_ignores_trailing_punctuation(self) -> None:
        assert guardrails.extract_links("go to https://a.example.") == ["a.example"]

    def test_handles_www_prefix(self) -> None:
        assert guardrails.count_links("www.example.com/x") == 1

    def test_no_links(self) -> None:
        assert guardrails.count_links("no links here") == 0


class TestHardViolations:
    def test_good_draft_passes(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            build_good_thread(), settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok, [item.as_dict() for item in report.violations]

    def test_empty_thread_is_rejected(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread([], settings)
        assert [item.code for item in report.violations] == ["no_posts"]

    def test_too_few_posts(self, settings: config.Settings) -> None:
        posts = [{"text": "one"}, {"text": "two"}]
        report = guardrails.validate_thread(posts, settings)
        assert "too_few_posts" in {item.code for item in report.violations}

    def test_too_many_posts(self, settings: config.Settings) -> None:
        posts = [{"text": f"post {index}"} for index in range(8)]
        report = guardrails.validate_thread(posts, settings)
        assert "too_many_posts" in {item.code for item in report.violations}

    def test_post_too_long(self, settings: config.Settings) -> None:
        posts = [{"text": "x" * 600}, {"text": "b"}, {"text": "c"}]
        report = guardrails.validate_thread(posts, settings)
        violation = next(item for item in report.violations if item.code == "post_too_long")
        assert violation.post_index == 0
        assert violation.detail["count"] == 600

    def test_too_many_links_in_one_post(self, settings: config.Settings) -> None:
        text = " ".join(f"https://example{index}.com" for index in range(6))
        posts = [{"text": text}, {"text": "b"}, {"text": "c"}]
        report = guardrails.validate_thread(posts, settings)
        assert "too_many_links" in {item.code for item in report.violations}

    def test_empty_post(self, settings: config.Settings) -> None:
        posts = [{"text": "a"}, {"text": "   "}, {"text": "c"}]
        report = guardrails.validate_thread(posts, settings)
        assert "empty_post" in {item.code for item in report.violations}

    def test_non_https_image_url(self, settings: config.Settings) -> None:
        posts = [{"text": "a", "image_url": "http://insecure.example/i.jpg"}, {"text": "b"}, {"text": "c"}]
        report = guardrails.validate_thread(posts, settings)
        assert "bad_image_url" in {item.code for item in report.violations}


class TestPersonalExperienceGuardrail:
    @pytest.mark.parametrize(
        "text",
        [
            "Aku sudah coba produk ini selama seminggu.",
            "Saya pakai ini setiap hari dan hasilnya bagus.",
            "Menurut pengalaman saya, ini yang terbaik.",
            "I have personally tested this for a month.",
            "When I tried it, the battery lasted two days.",
            "In my experience, this is the best option.",
        ],
    )
    def test_blocked_phrases_are_hard_violations(
        self, settings: config.Settings, text: str
    ) -> None:
        posts = [{"text": text}, {"text": "b"}, {"text": "c"}]
        report = guardrails.validate_thread(posts, settings)
        assert "fabricated_personal_experience" in {item.code for item in report.violations}

    def test_hedged_observations_are_allowed(self, settings: config.Settings) -> None:
        posts = build_good_thread()
        posts[1]["text"] = (
            "Dari spesifikasi produknya, kapasitas besar selalu berarti berat. "
            "Berdasarkan review yang tersedia, 380g itu terasa di saku."
        )
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "fabricated_personal_experience" not in {item.code for item in report.violations}

    def test_broken_user_pattern_does_not_crash(self, settings: config.Settings) -> None:
        import dataclasses

        broken = dataclasses.replace(settings, blocked_phrases=("([unclosed",))
        report = guardrails.validate_thread([{"text": "a"}, {"text": "b"}, {"text": "c"}], broken)
        assert isinstance(report.violations, list)


class TestDisclosure:
    def test_missing_disclosure_is_rejected(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in {item.code for item in report.violations}

    def test_disclosure_marker_satisfies_the_rule(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi: https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in {item.code for item in report.violations}

    def test_requirement_can_be_disabled(self, settings: config.Settings) -> None:
        import dataclasses

        relaxed = dataclasses.replace(settings, require_disclosure=False)
        posts = [{"text": "a"}, {"text": "b"}, {"text": "https://shope.ee/abc123"}]
        report = guardrails.validate_thread(posts, relaxed, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in {item.code for item in report.violations}


class TestAffiliateUrl:
    def test_missing_from_row_is_rejected(self, settings: config.Settings) -> None:
        posts = [{"text": "a"}, {"text": "b"}, {"text": "#afiliasi"}]
        report = guardrails.validate_thread(posts, settings, affiliate_url="")
        assert "affiliate_url_missing_from_row" in {item.code for item in report.violations}

    def test_not_in_thread_is_rejected(self, settings: config.Settings) -> None:
        posts = [{"text": "a"}, {"text": "b"}, {"text": "#afiliasi https://other.example"}]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "affiliate_url_not_in_thread" in {item.code for item in report.violations}

    def test_matches_with_different_scheme_and_trailing_slash(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123/"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "affiliate_url_not_in_thread" not in {item.code for item in report.violations}


class TestSoftWarnings:
    def test_generic_phrase_warns_but_does_not_block(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Produk ini praktis dan nyaman digunakan."},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok
        assert "generic_phrase" in {item.code for item in report.warnings}

    def test_ai_tic_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Penting untuk dicatat bahwa ini bagus."},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "obvious_ai_phrase" in {item.code for item in report.warnings}

    def test_product_overexposure_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Powerbank Z adalah ..."},
            {"text": "Powerbank Z juga ..."},
            {"text": "Powerbank Z lagi ..."},
            {"text": "Powerbank Z terakhir ..."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts,
            settings,
            affiliate_url="https://shope.ee/abc123",
            product_name="Powerbank Z",
        )
        assert "product_overexposed" in {item.code for item in report.warnings}
