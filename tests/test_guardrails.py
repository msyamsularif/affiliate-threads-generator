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
        posts = [{"text": f"post {index}"} for index in range(12)]
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


class TestTagDisclosureStyle:
    """``disclosure_style: tag`` — a bare hashtag on the final post is the whole
    disclosure. The operator chooses this when a commission sentence reads as
    hard-sell; the commercial relationship still has to be visible, so the tag
    is required on the post carrying the link."""

    @pytest.fixture
    def tag_settings(self, settings: config.Settings) -> config.Settings:
        import dataclasses

        return dataclasses.replace(settings, disclosure_style="tag")

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.violations}

    def test_a_bare_tag_on_the_final_post_is_enough(self, tag_settings: config.Settings) -> None:
        posts = [
            {"text": "Kapasitas besar biasanya berarti berat."},
            {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
            {"text": "Untuk skenario seperti ini, satu kabel sudah cukup."},
            {"text": "https://shope.ee/abc123 #ad"},
        ]
        report = guardrails.validate_thread(posts, tag_settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in self.codes(report)
        assert not any("komisi" in str(post["text"]) for post in posts)

    def test_the_tag_must_be_on_the_final_post(self, tag_settings: config.Settings) -> None:
        posts = [
            {"text": "Post pembuka #ad"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(posts, tag_settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in self.codes(report)

    def test_a_sentence_marker_alone_does_not_satisfy_the_tag_style(
        self, tag_settings: config.Settings
    ) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi: https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(posts, tag_settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in self.codes(report)

    def test_an_unknown_hashtag_is_not_a_marker(self, tag_settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123 #promo"},
        ]
        report = guardrails.validate_thread(posts, tag_settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in self.codes(report)

    def test_a_tag_style_without_hashtag_markers_says_why(self, settings: config.Settings) -> None:
        import dataclasses

        broken = dataclasses.replace(
            settings, disclosure_style="tag", disclosure_markers=("komisi",)
        )
        posts = [{"text": "a"}, {"text": "b"}, {"text": "https://shope.ee/abc123 #ad"}]
        report = guardrails.validate_thread(posts, broken, affiliate_url="https://shope.ee/abc123")
        violation = next(item for item in report.violations if item.code == "missing_disclosure")
        assert "no hashtag marker" in violation.message

    def test_the_default_style_still_reads_any_marker_anywhere(
        self, settings: config.Settings
    ) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123 Link afiliasi."},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in self.codes(report)


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

    def test_ai_tic_phrases_are_no_longer_a_guardrail_concern(self, settings: config.Settings) -> None:
        """The generic AI-prose catalogue belongs to the external antislop skills.

        The code layer keeps only what is specific to affiliate product copy, so
        a phrase like this one must not be flagged here any more.
        """
        posts = [
            {"text": "Penting untuk dicatat bahwa ini bagus."},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "obvious_ai_phrase" not in {item.code for item in report.warnings}

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


class TestStructuralSignals:
    """Cheap structural counters. Warnings only — never proof of AI writing."""

    STRUCTURAL = {
        "excessive_signposting",
        "repeated_transition_density",
        "excessive_enumeration",
        "product_detail_density",
    }

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.warnings}

    def test_a_clean_thread_raises_none_of_them(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            build_good_thread(), settings, affiliate_url="https://shope.ee/abc123"
        )
        assert self.STRUCTURAL.isdisjoint(self.codes(report))

    def test_narrated_transitions_warn(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Jadi, kapasitas besar selalu berarti berat."},
            {"text": "Makanya, yang paling sering dipakai justru yang paling ringan."},
            {"text": "Kesimpulannya, ini bukan buat semua orang."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok
        assert "repeated_transition_density" in self.codes(report)

    def test_a_transition_inside_a_word_does_not_count(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Beratnya menjadi alasan utama orang melewatinya."},
            {"text": "Kapasitas menjadi alasan orang membelinya."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "repeated_transition_density" not in self.codes(report)

    def test_enumeration_markers_warn(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Dua catatan: Pertama, kapasitasnya besar. Kedua, beratnya ikut naik."},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_enumeration" in self.codes(report)

    def test_pertama_kali_is_not_an_enumeration_marker(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Pertama kali lihat, ukurannya terlihat kecil."},
            {"text": "Kedua kalinya, baru terasa bedanya."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_enumeration" not in self.codes(report)

    def test_signposting_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Mari kita bahas daya tahannya."},
            {"text": "Yang perlu kamu tahu soal kapasitasnya."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_signposting" in self.codes(report)

    def test_spec_density_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "20000mAh, 22.5W, 380g, 15cm, 6 jam, 2 liter."},
            {"text": "b"},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "product_detail_density" in self.codes(report)

    def test_a_threshold_of_zero_disables_the_signal(self, settings: config.Settings) -> None:
        import dataclasses

        relaxed = dataclasses.replace(settings, transition_warning_threshold=0)
        posts = [
            {"text": "Jadi, satu."},
            {"text": "Makanya, dua."},
            {"text": "Kesimpulannya, tiga."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, relaxed, affiliate_url="https://shope.ee/abc123"
        )
        assert "repeated_transition_density" not in self.codes(report)

    def test_structural_signals_never_block(self, settings: config.Settings) -> None:
        posts = [
            {
                "text": (
                    "Jadi, makanya, kesimpulannya. Pertama, kedua, ketiga: "
                    "20000mAh, 22.5W, 380g, 15cm, 6 jam, 2 liter."
                )
            },
            {"text": "Mari kita bahas. Yang perlu kamu tahu: ini panjang."},
            {"text": "#afiliasi https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok
        assert self.STRUCTURAL & self.codes(report)
