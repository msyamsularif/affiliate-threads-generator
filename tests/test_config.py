"""Config resolution, column maths and A1 range building."""

from __future__ import annotations

import pytest

from atg_plugin import config


class TestColumnMaths:
    @pytest.mark.parametrize(
        ("letter", "index"),
        [("A", 1), ("B", 2), ("G", 7), ("Z", 26), ("AA", 27), ("AB", 28)],
    )
    def test_column_index(self, letter: str, index: int) -> None:
        assert config.column_index(letter) == index

    @pytest.mark.parametrize("letter", ["", "1", "A1", "!!", "A B"])
    def test_column_index_rejects_junk(self, letter: str) -> None:
        with pytest.raises(ValueError):
            config.column_index(letter)

    @pytest.mark.parametrize("index", [1, 2, 7, 26, 27, 28])
    def test_column_letter_round_trips(self, index: int) -> None:
        assert config.column_index(config.column_letter(index)) == index

    def test_column_letter_rejects_zero(self) -> None:
        with pytest.raises(ValueError):
            config.column_letter(0)


class TestRanges:
    def test_full_range_spans_every_column(self, settings: config.Settings) -> None:
        assert settings.full_range == "Sheet1!A1:I"

    def test_full_range_respects_a_custom_tab(self, settings: config.Settings) -> None:
        import dataclasses

        assert dataclasses.replace(settings, sheet_tab="Candidates").full_range == "Candidates!A1:I"

    def test_row_range_covers_the_requested_fields(self, settings: config.Settings) -> None:
        assert settings.row_range(14, "threads_url", "status") == "Sheet1!F14:I14"

    def test_row_range_with_no_fields_covers_everything(self, settings: config.Settings) -> None:
        assert settings.row_range(3) == "Sheet1!A3:I3"

    def test_cell_range(self, settings: config.Settings) -> None:
        assert settings.cell_range(14, "status") == "Sheet1!I14"

    def test_a_custom_column_map_is_honoured(self, settings: config.Settings) -> None:
        import dataclasses

        custom = dataclasses.replace(
            settings, columns={**config.COLUMNS, "status": "I", "threads_url": "H"}
        )
        assert custom.cell_range(4, "status") == "Sheet1!I4"
        assert custom.row_range(4, "threads_url", "status") == "Sheet1!H4:I4"
        assert custom.full_range == "Sheet1!A1:I"


class TestColumnMap:
    def test_defaults_when_unset(self, ctx) -> None:  # noqa: ANN001
        assert config.resolve().columns == config.COLUMNS

    def test_accepts_a_json_string(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = '{"status": "Z"}'
        assert config.resolve().columns["status"] == "Z"

    def test_unnamed_fields_keep_their_defaults(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = {"status": "Z"}
        resolved = config.resolve()
        assert resolved.columns["id"] == "A"
        assert resolved.columns["status"] == "Z"

    def test_lowercase_letters_are_normalised(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = {"status": "z"}
        assert config.resolve().columns["status"] == "Z"

    def test_a_layout_using_h_loses_the_experience_columns_instead_of_the_map(
        self, ctx
    ) -> None:  # noqa: ANN001
        # The operator's table predates Used/Testimonial and puts a field in H.
        # Keeping their layout matters more than the new feature: writing to a
        # letter they never gave us would corrupt their sheet.
        ctx.settings["columns"] = {"status": "H", "threads_url": "G"}
        resolved = config.resolve()
        assert resolved.columns["status"] == "H"
        assert resolved.columns["threads_url"] == "G"
        assert "used" not in resolved.columns
        assert "testimonial" not in resolved.columns
        assert resolved.experience_configured is False
        assert resolved.experience_questions_enabled is False

    def test_a_layout_can_name_the_experience_columns(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = {"status": "H", "used": "I", "testimonial": "J"}
        resolved = config.resolve()
        assert resolved.columns["status"] == "H"
        assert resolved.columns["testimonial"] == "J"
        assert resolved.experience_configured is True

    def test_a_duplicate_column_discards_the_whole_map(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = {"status": "A", "threads_url": "A"}
        assert config.resolve().columns == config.COLUMNS

    @pytest.mark.parametrize("junk", ["not json", "[]", "", {"status": "not-a-column"}, None])
    def test_junk_falls_back_to_the_documented_layout(self, ctx, junk: object) -> None:  # noqa: ANN001
        ctx.settings["columns"] = junk
        assert config.resolve().columns == config.COLUMNS

    def test_unknown_field_names_are_ignored(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["columns"] = {"nonsense": "Z"}
        assert config.resolve().columns == config.COLUMNS


class TestResolve:
    def test_defaults_when_nothing_is_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AFFILIATE_SHEET_ID", raising=False)
        resolved = config.resolve()
        assert resolved.spreadsheet_id == ""
        assert resolved.sheet_tab == config.DEFAULT_TAB
        assert resolved.eligible_status == "Ready To Generate"
        assert resolved.done_status == "Done"
        assert resolved.min_posts == 3
        assert resolved.max_posts == 10
        assert resolved.max_chars_per_post == 500
        assert resolved.credentials_configured is False

    def test_plugin_settings_win_over_env(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["sheet_tab"] = "FromSettings"
        assert config.resolve().sheet_tab == "FromSettings"

    def test_env_fallback_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFFILIATE_SHEET_ID", "env-sheet")
        monkeypatch.setenv("AFFILIATE_SHEET_TAB", "EnvTab")
        resolved = config.resolve()
        assert resolved.spreadsheet_id == "env-sheet"
        assert resolved.sheet_tab == "EnvTab"

    def test_token_comes_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "abc")
        resolved = config.resolve()
        assert resolved.threads_access_token == "abc"
        assert resolved.credentials_configured is True

    def test_overrides_win_over_everything(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["sheet_tab"] = "FromSettings"
        resolved = config.resolve({"sheet_tab": "Override"})
        assert resolved.sheet_tab == "Override"

    def test_blank_overrides_are_ignored(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["sheet_tab"] = "FromSettings"
        assert config.resolve({"sheet_tab": ""}).sheet_tab == "FromSettings"

    def test_unknown_override_keys_are_ignored(self, ctx) -> None:  # noqa: ANN001
        resolved = config.resolve({"not_a_setting": "x"})
        assert not hasattr(resolved, "not_a_setting")

    def test_boolean_coercion(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["require_topic_tag"] = "false"
        assert config.resolve().require_topic_tag is False
        ctx.settings["require_topic_tag"] = "yes"
        assert config.resolve().require_topic_tag is True

    def test_list_setting_accepts_json(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["allowed_hashtags"] = '["ootd", "finds"]'
        assert config.resolve().allowed_hashtags == ("ootd", "finds")

    def test_list_setting_accepts_comma_separated_text(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["allowed_hashtags"] = "ootd, finds"
        assert config.resolve().allowed_hashtags == ("ootd", "finds")

    def test_publish_mode_defaults_to_single(self, ctx) -> None:  # noqa: ANN001
        resolved = config.resolve()
        assert resolved.publish_mode == "single"
        assert resolved.two_stage is False

    def test_publish_mode_accepts_two_stage(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["publish_mode"] = "Two_Stage"
        resolved = config.resolve()
        assert resolved.publish_mode == "two_stage"
        assert resolved.two_stage is True

    def test_an_unknown_publish_mode_falls_back_to_single(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["publish_mode"] = "batched"
        assert config.resolve().publish_mode == "single"

    def test_the_link_pending_status_defaults(self, ctx) -> None:  # noqa: ANN001
        assert config.resolve().link_pending_status == "Link Pending"

    def test_a_link_pending_status_may_be_customised(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["link_pending_status"] = "Nunggu Link"
        assert config.resolve().link_pending_status == "Nunggu Link"

    @pytest.mark.parametrize("status", ["Ready To Generate", "Done", "Hold", "", "   "])
    def test_a_colliding_link_pending_status_is_replaced(self, ctx, status: str) -> None:  # noqa: ANN001
        """A collision would either publish the row twice or read as a hold."""
        ctx.settings["link_pending_status"] = status
        resolved = config.resolve()
        assert resolved.link_pending_status == "Link Pending"
        assert resolved.link_pending_status not in {
            resolved.eligible_status,
            resolved.done_status,
            resolved.hold_status,
            resolved.cancel_status,
            resolved.in_progress_status,
        }

    def test_a_double_collision_still_produces_a_distinct_status(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["eligible_status"] = "Link Pending"
        resolved = config.resolve()
        assert resolved.link_pending_status != resolved.eligible_status
        assert resolved.link_pending_status != resolved.done_status

    def test_min_posts_cannot_exceed_max_posts(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["min_posts"] = 9
        ctx.settings["max_posts"] = 4
        resolved = config.resolve()
        assert resolved.min_posts <= resolved.max_posts

    def test_zero_max_posts_is_clamped(self, ctx) -> None:  # noqa: ANN001
        ctx.settings["max_posts"] = 0
        assert config.resolve().max_posts >= 1

    def test_public_summary_never_leaks_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "super-secret-token")
        summary = config.resolve().public_summary()
        assert "super-secret-token" not in str(summary)
        assert summary["threads_credentials_configured"] is True
