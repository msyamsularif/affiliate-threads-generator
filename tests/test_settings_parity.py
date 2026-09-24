"""The standalone scripts must enforce the operator's settings, not the defaults.

``validate_thread.py`` promises that a draft passing here passes
``threads_publish``. That promise is only worth anything if both read the same
guardrails — so a customised ``plugins.entries.<id>.settings.*`` block has to
reach the scripts too, which run with no Hermes context at all.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import textwrap
from pathlib import Path
from types import ModuleType

import pytest
from test_tools_publish import FakeSheet, make_row

from atg_plugin import config, config_file, runtime, threads_client, tools
from conftest import PLUGIN_DIR, happy_path_responses, scripted_transport

SCRIPTS = PLUGIN_DIR / "skills" / "affiliate-threads-generator" / "scripts"
AFFILIATE_URL = "https://shope.ee/abc123"

#: The topic tag these tests supply unless they are specifically about the tag.
DEFAULT_TOPIC_TAG = "power bank"

#: A realistic operator configuration. Every value differs from the default so a
#: script that ignored the file would fail these tests loudly.
CONFIG_YAML = textwrap.dedent(
    """\
    # ~/.hermes/config.yaml
    plugins:
      entries:
        affiliate-threads-generator:
          enabled: true
          settings:
            sheet_tab: "Candidates"
            require_affiliate_url: true
            disclosure_markers:
              - "#iklan"
              - "link afiliasi"
            blocked_phrases:
              - '\\bproduk ini wajib punya\\b'
            max_posts: 4
            columns:
              status: "H"
              threads_url: "G"
        some-other-plugin:
          enabled: true
          settings:
            unrelated: 1
    """
)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Write the operator's config.yaml into this test's ``$HERMES_HOME``."""
    home = tmp_path / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.yaml"
    path.write_text(CONFIG_YAML, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    runtime.reset_for_tests()
    return path


@pytest.fixture(scope="module")
def validate_thread_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "atg_validate_thread", SCRIPTS / "validate_thread.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publish_env(monkeypatch: pytest.MonkeyPatch, ctx):  # noqa: ANN001, ANN201
    """A fake Sheet plus a fake Threads API, wired into the tools module."""

    def install(sheet: FakeSheet):  # noqa: ANN202
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("THREADS_USER_ID", "user-1")
        monkeypatch.setattr(tools, "SheetClient", lambda settings, **kwargs: sheet)
        transport = scripted_transport(happy_path_responses(posts=4))

        def factory(access_token, user_id="", **kwargs):  # noqa: ANN001, ANN202
            return threads_client.ThreadsClient(
                access_token, user_id, transport=transport, sleep=lambda _s: None, max_retries=0
            )

        monkeypatch.setattr(tools, "ThreadsClient", factory)
        return sheet

    return install


def lint(
    script: ModuleType, tmp_path: Path, posts: list, *extra: str
) -> tuple[int, dict, str]:
    """Run ``validate_thread.py`` in-process against a draft file.

    A topic tag is supplied by default, because the publish tool requires one and
    this helper exists to prove the two agree. The topic-tag tests pass their own
    value — an empty one included, which is the refusal they are checking.
    """
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"posts": posts}), encoding="utf-8")
    argv = ["--file", str(draft), "--affiliate-url", AFFILIATE_URL]
    if "--topic-tag" not in extra:
        argv += ["--topic-tag", DEFAULT_TOPIC_TAG]
    argv += list(extra)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        exit_code = script.main(argv)
    payload = json.loads(out.getvalue()) if out.getvalue().strip().startswith("{") else {}
    return exit_code, payload, err.getvalue()


class TestConfigFile:
    def test_settings_reach_config_resolve(self, configured: Path) -> None:  # noqa: ARG002
        resolved = config.resolve()
        assert resolved.sheet_tab == "Candidates"
        assert resolved.disclosure_markers == ("#iklan", "link afiliasi")
        assert resolved.blocked_phrases == (r"\bproduk ini wajib punya\b",)
        assert resolved.max_posts == 4
        assert resolved.columns["status"] == "H"
        assert resolved.columns["threads_url"] == "G"
        # Fields the operator did not set keep their defaults.
        assert resolved.columns["id"] == "A"

    def test_the_host_context_still_wins(self, configured: Path, ctx) -> None:  # noqa: ANN001, ARG002
        ctx.settings["sheet_tab"] = "FromHost"
        assert config.resolve().sheet_tab == "FromHost"

    def test_settings_win_over_the_generic_environment_variable(
        self, configured: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same precedence as inside Hermes: the plugin's own setting first."""
        monkeypatch.setenv("SHEET_TAB", "FromEnv")
        assert config.resolve().sheet_tab == "Candidates"

    def test_no_config_file_means_defaults(self, tmp_path: Path) -> None:
        assert runtime.settings_source()["source"] == "defaults"
        assert config.resolve().max_posts == config.Settings().max_posts
        assert runtime.settings_note() == ""

    def test_a_missing_plugin_entry_is_not_an_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        home = tmp_path / "hermes-home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("plugins:\n  entries:\n", encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))
        runtime.reset_for_tests()
        assert config.resolve().max_posts == config.Settings().max_posts
        assert runtime.settings_note() == ""

    def test_the_reader_caches_until_the_file_changes(self, configured: Path) -> None:
        assert config.resolve().max_posts == 4
        configured.write_text(CONFIG_YAML.replace("max_posts: 4", "max_posts: 12"), encoding="utf-8")
        assert config.resolve().max_posts == 12

    def test_a_broken_file_is_reported_not_half_applied(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes-home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            "plugins:\n  entries: [unclosed\n", encoding="utf-8"
        )
        monkeypatch.setenv("HERMES_HOME", str(home))
        runtime.reset_for_tests()

        result = config_file.load("affiliate-threads-generator")
        assert result.found is True
        assert result.settings == {}
        assert result.warning
        assert config.resolve().max_posts == config.Settings().max_posts

    def test_the_scripts_print_that_warning(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "hermes-home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("plugins: {}\n", encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))
        runtime.reset_for_tests()
        monkeypatch.setattr(
            runtime.config_file,
            "load",
            lambda plugin_id, path=None: config_file.ConfigFile(  # noqa: ARG005
                found=True,
                path=path or runtime.config_file.config_path(),
                settings={},
                warning="config.yaml: the settings block could not be read",
            ),
        )
        assert "could not be read" in runtime.settings_note()
        assert runtime.settings_source()["source"] == "defaults"
        assert config.resolve().max_posts == config.Settings().max_posts


class TestFallbackParserAgreesWithPyYaml:
    """The fallback is what runs on a host without PyYAML. If it read the file
    differently, the scripts would enforce different rules than the tool — the
    exact bug this module exists to close."""

    def test_realistic_configuration_matches(self) -> None:
        yaml = pytest.importorskip("yaml")
        expected, warning = config_file._dig(
            yaml.safe_load(CONFIG_YAML), "affiliate-threads-generator"
        )
        actual, fallback_warning = config_file._fallback_settings(
            CONFIG_YAML, "affiliate-threads-generator"
        )
        assert warning == "" and fallback_warning == ""
        assert actual == expected
        assert actual["blocked_phrases"] == [r"\bproduk ini wajib punya\b"]
        assert actual["disclosure_markers"] == ["#iklan", "link afiliasi"]

    def test_comments_and_quotes_are_handled(self) -> None:
        text = textwrap.dedent(
            """\
            plugins:
              entries:
                affiliate-threads-generator:
                  settings:
                    # leading comment
                    sheet_tab: 'Tab #1'   # trailing comment
                    eligible_status: Ready To Generate
                    require_disclosure: yes
                    min_posts: 3
            """
        )
        settings, warning = config_file._fallback_settings(text, "affiliate-threads-generator")
        assert warning == ""
        assert settings["sheet_tab"] == "Tab #1"
        assert settings["eligible_status"] == "Ready To Generate"
        assert settings["require_disclosure"] is True
        assert settings["min_posts"] == 3

    def test_a_flow_mapping_is_refused_rather_than_guessed(self) -> None:
        text = textwrap.dedent(
            """\
            plugins:
              entries:
                affiliate-threads-generator:
                  settings:
                    columns: {id: "A"}
            """
        )
        settings, warning = config_file._fallback_settings(text, "affiliate-threads-generator")
        assert settings == {}
        assert "line 5" in warning

    def test_a_nested_list_item_is_refused_rather_than_guessed(self) -> None:
        text = textwrap.dedent(
            """\
            plugins:
              entries:
                affiliate-threads-generator:
                  settings:
                    blocked_phrases:
                      - key: value
            """
        )
        settings, warning = config_file._fallback_settings(text, "affiliate-threads-generator")
        assert settings == {}
        assert "line 6" in warning

    def test_a_missing_file_is_reported_as_absent(self) -> None:
        result = config_file.load("affiliate-threads-generator", path=Path("/nonexistent/config.yaml"))
        assert result.found is False
        assert result.settings == {}
        assert result.warning == ""


class TestLintMatchesPublish:
    """The promise: copy that passes the lint passes the publish guardrails."""

    DRAFT_OK = [
        {"text": "Kapasitas besar biasanya berarti berat."},
        {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
        {"text": "Untuk skenario seperti ini, satu kabel saja sudah cukup."},
        {"text": f"#iklan {AFFILIATE_URL}"},
    ]

    DRAFT_TOO_LONG = [
        {"text": "a"},
        {"text": "b"},
        {"text": "c"},
        {"text": "d"},
        {"text": f"#iklan {AFFILIATE_URL}"},
    ]

    def test_the_lint_uses_the_customised_limits(
        self, configured: Path, validate_thread_script: ModuleType, tmp_path: Path  # noqa: ARG002
    ) -> None:
        exit_code, payload, _ = lint(validate_thread_script, tmp_path, self.DRAFT_TOO_LONG)
        assert exit_code == 1
        assert payload["limits"]["max_posts"] == 4
        assert "too_many_posts" in {item["code"] for item in payload["violations"]}

    def test_a_draft_outside_the_operator_markers_is_refused(
        self, configured: Path, validate_thread_script: ModuleType, tmp_path: Path  # noqa: ARG002
    ) -> None:
        posts = [*self.DRAFT_OK[:3], {"text": f"#afiliasi {AFFILIATE_URL}"}]
        exit_code, payload, _ = lint(validate_thread_script, tmp_path, posts)
        assert exit_code == 1
        assert "missing_disclosure" in {item["code"] for item in payload["violations"]}

    def test_the_operator_marker_and_limits_pass_the_lint(
        self, configured: Path, validate_thread_script: ModuleType, tmp_path: Path  # noqa: ARG002
    ) -> None:
        exit_code, payload, _ = lint(validate_thread_script, tmp_path, self.DRAFT_OK)
        assert exit_code == 0, payload
        assert payload["violations"] == []

    def test_publish_agrees_that_the_draft_passes(self, configured: Path, publish_env) -> None:  # noqa: ANN001, ARG002
        sheet = publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": self.DRAFT_OK,
                    "topic_tag": DEFAULT_TOPIC_TAG,
                    "confirm_publish": True,
                }
            )
        )
        assert result["ok"] is True, result
        assert sheet.writes and sheet.writes[0]["status"] == "Done"

    def test_publish_refuses_what_the_lint_refused(self, configured: Path, publish_env) -> None:  # noqa: ANN001, ARG002
        sheet = publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": self.DRAFT_TOO_LONG,
                    "topic_tag": DEFAULT_TOPIC_TAG,
                    "confirm_publish": True,
                }
            )
        )
        assert result["stage"] == "guardrails"
        assert "too_many_posts" in {item["code"] for item in result["violations"]}
        assert sheet.writes == []

    def test_publish_refuses_a_marker_the_lint_refused(self, configured: Path, publish_env) -> None:  # noqa: ANN001, ARG002
        posts = [*self.DRAFT_OK[:3], {"text": f"#afiliasi {AFFILIATE_URL}"}]
        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": posts,
                    "topic_tag": DEFAULT_TOPIC_TAG,
                    "confirm_publish": True,
                }
            )
        )
        assert result["stage"] == "guardrails"
        assert "missing_disclosure" in {item["code"] for item in result["violations"]}

    def test_the_customised_blocked_phrase_is_enforced_by_both(
        self, configured: Path, validate_thread_script: ModuleType, tmp_path: Path, publish_env  # noqa: ANN001, ARG002
    ) -> None:
        posts = [{"text": "Produk ini wajib punya menurut penjualnya."}, *self.DRAFT_OK[1:]]
        exit_code, payload, _ = lint(validate_thread_script, tmp_path, posts)
        assert exit_code == 1
        assert "fabricated_personal_experience" in {item["code"] for item in payload["violations"]}

        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": posts,
                    "topic_tag": DEFAULT_TOPIC_TAG,
                    "confirm_publish": True,
                }
            )
        )
        assert "fabricated_personal_experience" in {item["code"] for item in result["violations"]}


TWO_STAGE_CONFIG = textwrap.dedent(
    """\
    plugins:
      entries:
        affiliate-threads-generator:
          settings:
            publish_mode: "two_stage"
            disclosure_markers:
              - "#iklan"
              - "link afiliasi"
    """
)


class TestTwoStageParity:
    """Under the deferred-link mode the lint has to agree with the tool about
    which half of the publish each rule belongs to."""

    THREAD = [
        {"text": "Kapasitas besar biasanya berarti berat."},
        {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
        {"text": "Untuk skenario seperti ini, satu kabel sudah cukup."},
    ]
    REPLY = [{"text": f"Detail lengkapnya di sini: {AFFILIATE_URL} #iklan"}]

    @pytest.fixture
    def two_stage_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        home = tmp_path / "hermes-home"
        home.mkdir(parents=True, exist_ok=True)
        path = home / "config.yaml"
        path.write_text(TWO_STAGE_CONFIG, encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))
        runtime.reset_for_tests()
        return path

    def test_the_thread_body_defers_the_link_and_the_disclosure(
        self, two_stage_config: Path, validate_thread_script: ModuleType, tmp_path: Path, publish_env  # noqa: ANN001, ARG002
    ) -> None:
        exit_code, payload, _ = lint(validate_thread_script, tmp_path, self.THREAD)
        assert exit_code == 0, payload
        assert payload["stage"] == "thread"
        assert payload["deferred"] == ["affiliate_url", "disclosure"]

        # …and the tool publishes the same copy as stage one rather than refusing it.
        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": self.THREAD,
                    "topic_tag": DEFAULT_TOPIC_TAG,
                    "confirm_publish": True,
                }
            )
        )
        assert result["ok"] is True, result
        assert result["status"] == "published_awaiting_link"

    def test_the_link_reply_lints_as_one_post_that_carries_the_link(
        self, two_stage_config: Path, validate_thread_script: ModuleType, tmp_path: Path  # noqa: ARG002
    ) -> None:
        exit_code, payload, _ = lint(
            validate_thread_script, tmp_path, self.REPLY, "--stage", "link"
        )
        assert exit_code == 0, payload
        assert payload["stage"] == "link"
        assert payload["limits"]["max_posts"] == 1

    def test_a_multi_post_link_stage_draft_is_refused_by_both(
        self, two_stage_config: Path, validate_thread_script: ModuleType, tmp_path: Path, publish_env  # noqa: ANN001, ARG002
    ) -> None:
        exit_code, payload, _ = lint(
            validate_thread_script, tmp_path, self.THREAD, "--stage", "link"
        )
        assert exit_code == 1
        assert "too_many_posts" in {item["code"] for item in payload["violations"]}

        # The row is parked where a thread's link reply belongs, and the tool
        # refuses the same many-post draft the lint did.
        publish_env(FakeSheet([make_row(status="Link Pending", affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": self.THREAD,
                    "stage": "link",
                    "confirm_publish": True,
                }
            )
        )
        assert result["stage"] == "input"
        assert "exactly one post" in result["error"]

    def test_auto_follows_the_rows_own_status(self, two_stage_config: Path, validate_thread_script: ModuleType) -> None:  # noqa: ARG002
        from types import SimpleNamespace

        settings = config.resolve()
        assert settings.two_stage is True
        pending = SimpleNamespace(status="Link Pending")
        fresh = SimpleNamespace(status="Ready To Generate")
        assert validate_thread_script._stage_for(pending, settings) == "link"
        assert validate_thread_script._stage_for(fresh, settings) == "thread"
        assert validate_thread_script._stage_for(None, settings) == "thread"


TOPIC_TAG_OPTIONAL_CONFIG = textwrap.dedent(
    """\
    plugins:
      entries:
        affiliate-threads-generator:
          settings:
            require_topic_tag: false
            disclosure_markers:
              - "#iklan"
              - "link afiliasi"
    """
)


class TestTopicTagParity:
    """The topic tag is one requirement read from one setting by both the lint
    and the tool. A tag the API would reject is refused before anything is sent,
    and the operator can turn the whole requirement off."""

    POSTS = [
        {"text": "Kapasitas besar biasanya berarti berat."},
        {"text": "Yang sering disebut di review: kabel USB-C ikut di dalamnya."},
        {"text": "Untuk skenario seperti ini, satu kabel saja sudah cukup."},
        {"text": f"#iklan {AFFILIATE_URL}"},
    ]

    @pytest.fixture
    def optional_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        home = tmp_path / "hermes-home"
        home.mkdir(parents=True, exist_ok=True)
        path = home / "config.yaml"
        path.write_text(TOPIC_TAG_OPTIONAL_CONFIG, encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(home))
        runtime.reset_for_tests()
        return path

    def codes(self, violations: list) -> set[str]:
        return {item["code"] for item in violations}

    def test_the_default_refuses_a_missing_tag_in_both(
        self,
        configured: Path,  # noqa: ARG002
        validate_thread_script: ModuleType,
        tmp_path: Path,
        publish_env,  # noqa: ANN001
    ) -> None:
        exit_code, payload, _ = lint(
            validate_thread_script, tmp_path, self.POSTS, "--topic-tag", ""
        )
        assert exit_code == 1
        assert "topic_tag_missing" in self.codes(payload["violations"])

        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {"product_id": "12", "posts": self.POSTS, "confirm_publish": True}
            )
        )
        assert result["stage"] == "guardrails"
        assert "topic_tag_missing" in self.codes(result["violations"])

    def test_the_requirement_can_be_turned_off_for_both(
        self,
        optional_config: Path,  # noqa: ARG002
        validate_thread_script: ModuleType,
        tmp_path: Path,
        publish_env,  # noqa: ANN001
    ) -> None:
        exit_code, payload, _ = lint(
            validate_thread_script, tmp_path, self.POSTS, "--topic-tag", ""
        )
        assert exit_code == 0, payload

        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {"product_id": "12", "posts": self.POSTS, "confirm_publish": True}
            )
        )
        assert result["ok"] is True, result

    def test_a_tag_the_api_rejects_is_refused_by_both(
        self,
        configured: Path,  # noqa: ARG002
        validate_thread_script: ModuleType,
        tmp_path: Path,
        publish_env,  # noqa: ANN001
    ) -> None:
        exit_code, payload, _ = lint(
            validate_thread_script, tmp_path, self.POSTS, "--topic-tag", "#kabel usb"
        )
        assert exit_code == 1
        assert "topic_tag_invalid" in self.codes(payload["violations"])

        publish_env(FakeSheet([make_row(affiliate_url=AFFILIATE_URL)]))
        result = json.loads(
            tools.threads_publish(
                {
                    "product_id": "12",
                    "posts": self.POSTS,
                    "topic_tag": "#kabel usb",
                    "confirm_publish": True,
                }
            )
        )
        assert result["stage"] == "guardrails"
        assert "topic_tag_invalid" in self.codes(result["violations"])
