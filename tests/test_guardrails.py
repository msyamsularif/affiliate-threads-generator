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


class TestDisclosureIsASentence:
    """The disclosure is a sentence in the copy — never a hashtag.

    ``#ad`` at the end is not used: it reads as an unclear tag, and a hashtag
    anywhere in the copy is refused by ``hashtag_in_copy`` anyway, so a hashtag
    can never be what satisfies this rule."""

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.violations}

    def test_a_sentence_marker_satisfies_the_rule(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Kapasitas besar biasanya berarti berat."},
            {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
            {"text": "Untuk skenario seperti ini, satu kabel sudah cukup."},
            {"text": "https://shope.ee/abc123\n\nLink afiliasi."},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in self.codes(report)

    def test_a_hashtag_is_not_a_disclosure(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123 #ad"},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in self.codes(report)
        assert "hashtag_in_copy" in self.codes(report)

    def test_a_hashtag_shaped_marker_is_ignored(self) -> None:
        """A ``#...`` marker can never be satisfied — the hashtag rule refuses it
        — so it is not consulted, even when a configuration still names one."""
        import dataclasses

        configured = dataclasses.replace(
            config.Settings(require_topic_tag=False), disclosure_markers=("#iklan",)
        )
        posts = [{"text": "a"}, {"text": "b"}, {"text": "https://shope.ee/abc123 #iklan"}]
        report = guardrails.validate_thread(posts, configured, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" in self.codes(report)

    def test_any_configured_sentence_marker_works_wherever_it_sits(
        self, settings: config.Settings
    ) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123\n\nLink afiliasi."},
        ]
        report = guardrails.validate_thread(posts, settings, affiliate_url="https://shope.ee/abc123")
        assert "missing_disclosure" not in self.codes(report)


class TestAffiliateUrl:
    def test_missing_from_row_is_rejected(self, settings: config.Settings) -> None:
        posts = [{"text": "a"}, {"text": "b"}, {"text": "Link afiliasi."}]
        report = guardrails.validate_thread(posts, settings, affiliate_url="")
        assert "affiliate_url_missing_from_row" in {item.code for item in report.violations}

    def test_not_in_thread_is_rejected(self, settings: config.Settings) -> None:
        posts = [{"text": "a"}, {"text": "b"}, {"text": "Link afiliasi. https://other.example"}]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "affiliate_url_not_in_thread" in {item.code for item in report.violations}

    def test_matches_with_different_scheme_and_trailing_slash(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123/"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "repeated_transition_density" not in self.codes(report)

    def test_enumeration_markers_warn(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Dua catatan: Pertama, kapasitasnya besar. Kedua, beratnya ikut naik."},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_enumeration" in self.codes(report)

    def test_pertama_kali_is_not_an_enumeration_marker(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Pertama kali lihat, ukurannya terlihat kecil."},
            {"text": "Kedua kalinya, baru terasa bedanya."},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_enumeration" not in self.codes(report)

    def test_signposting_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Mari kita bahas daya tahannya."},
            {"text": "Yang perlu kamu tahu soal kapasitasnya."},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "excessive_signposting" in self.codes(report)

    def test_spec_density_warns(self, settings: config.Settings) -> None:
        posts = [
            {"text": "20000mAh, 22.5W, 380g, 15cm, 6 jam, 2 liter."},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
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
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok
        assert self.STRUCTURAL & self.codes(report)


class TestHashtags:
    """Threads is not Instagram: one tag per post becomes the topic tag, and
    that tag is set through its own argument. A hashtag trail in the copy cannot
    add reach, so it is a hard stop — except the configured disclosure markers."""

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.violations}

    def test_a_hashtag_trail_in_a_reply_is_refused(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123\n\n#rekomendasi #belanjaonline"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        violation = next(item for item in report.violations if item.code == "hashtag_in_copy")
        assert violation.post_index == 2
        assert violation.detail["tags"] == ["rekomendasi", "belanjaonline"]

    def test_a_sentence_marker_leaves_the_draft_clean(self, settings: config.Settings) -> None:
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok, [item.as_dict() for item in report.violations]

    def test_a_disclosure_hashtag_is_refused_like_any_other(
        self, settings: config.Settings
    ) -> None:
        """``#ad`` was once the tag-style disclosure; it is a plain hashtag now."""
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "https://shope.ee/abc123 #ad"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "hashtag_in_copy" in self.codes(report)

    def test_the_operator_allowlist_can_keep_a_tag(self, settings: config.Settings) -> None:
        import dataclasses

        allowed = dataclasses.replace(settings, allowed_hashtags=("#OOTD",))
        posts = [
            {"text": "a"},
            {"text": "b"},
            {"text": "Link afiliasi. https://shope.ee/abc123\n\n#ootd"},
        ]
        report = guardrails.validate_thread(
            posts, allowed, affiliate_url="https://shope.ee/abc123"
        )
        assert "hashtag_in_copy" not in self.codes(report)

        posts[-1]["text"] = "Link afiliasi. https://shope.ee/abc123\n\n#promo"
        report = guardrails.validate_thread(
            posts, allowed, affiliate_url="https://shope.ee/abc123"
        )
        assert "hashtag_in_copy" in self.codes(report)

    def test_a_url_fragment_is_not_a_hashtag(self) -> None:
        assert guardrails.extract_hashtags("baca di https://example.com/x/#bagian") == []

    def test_a_number_sign_is_not_a_hashtag(self) -> None:
        assert guardrails.extract_hashtags("#1 paling sering disebut, #2 jarang") == []

    def test_extract_hashtags_keeps_order_and_drops_duplicates(self) -> None:
        assert guardrails.extract_hashtags("#satu dua #dua tiga #satu") == ["satu", "dua"]


class TestFunnelLanguage:
    """Copy whose only job is to talk the reader toward the link. Warnings, not
    blocks: the honest fix is a rewrite, and the link still has to live where a
    reader can find it."""

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.warnings}

    def test_a_teaser_warns_without_blocking(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Kapasitas besar biasanya berarti berat."},
            {"text": "Kalau mau detail lengkapnya, klik link di bawah ya."},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok
        assert "funnel_phrase" in self.codes(report)

    def test_a_plain_contextual_line_does_not_warn(self, settings: config.Settings) -> None:
        posts = [
            {"text": "Kapasitas besar biasanya berarti berat."},
            {"text": "Detail produknya ada di sini, buat yang penasaran ukurannya."},
            {"text": "Link afiliasi. https://shope.ee/abc123"},
        ]
        report = guardrails.validate_thread(
            posts, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert "funnel_phrase" not in self.codes(report)


class TestTopicTag:
    """The topic tag is Threads' discovery mechanism — and how a post reaches a
    community when its topic has one — so the requirement and the platform's own
    limits live in code, not in a reminder to the model."""

    POSTS = [
        {"text": "Kapasitas besar biasanya berarti berat."},
        {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
        {"text": "Link afiliasi. https://shope.ee/abc123"},
    ]

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.violations}

    def validate(self, settings: config.Settings, topic_tag: str) -> guardrails.GuardrailReport:
        return guardrails.validate_thread(
            self.POSTS,
            settings,
            affiliate_url="https://shope.ee/abc123",
            topic_tag=topic_tag,
        )

    def test_the_default_is_to_require_one(self, settings: config.Settings) -> None:
        assert settings.require_topic_tag is True

    def test_a_missing_tag_is_refused(self, settings: config.Settings) -> None:
        assert "topic_tag_missing" in self.codes(self.validate(settings, ""))

    def test_the_requirement_can_be_turned_off(self, settings: config.Settings) -> None:
        import dataclasses

        relaxed = dataclasses.replace(settings, require_topic_tag=False)
        assert "topic_tag_missing" not in self.codes(self.validate(relaxed, ""))

    def test_not_checking_at_all_is_a_different_thing(self, settings: config.Settings) -> None:
        """``None`` means the caller has no tag to check — a link reply, or a test
        about the copy itself — not that the tag is missing."""
        report = guardrails.validate_thread(
            self.POSTS, settings, affiliate_url="https://shope.ee/abc123"
        )
        assert report.ok

    @pytest.mark.parametrize(
        "tag",
        [
            "#power bank",  # the displayed form, not the parameter's
            "x" * 51,
            "kopi. susu",
            "kopi & susu",
            "dua\nbaris",
        ],
    )
    def test_tags_the_api_would_reject(self, settings: config.Settings, tag: str) -> None:
        assert "topic_tag_invalid" in self.codes(self.validate(settings, tag))

    def test_a_valid_tag_passes(self, settings: config.Settings) -> None:
        report = self.validate(settings, "power bank")
        assert report.ok, [item.as_dict() for item in report.violations]

    def test_the_problem_helper_explains_itself(self) -> None:
        assert "leading" in guardrails.topic_tag_problem("#foto")
        assert guardrails.TOPIC_TAG_MAX_CHARS == 50
        assert guardrails.topic_tag_problem("foto") == ""
