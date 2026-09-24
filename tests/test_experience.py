"""The experience flow — Step 1.5's answer and the provenance guardrails.

The mode is derived from the row's own ``Used``/``Testimonial`` cells, never
chosen by the model, so these tests lock three things: the derivation itself,
the checks that replace the blanket ban once a testimony exists, and the fact
that ``threads_publish`` applies the row's mode rather than anything a caller
says.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from types import ModuleType

import pytest
from test_tools_publish import FakeSheet, make_row

from atg_plugin import config, guardrails, sheets_client, threads_client, tools
from conftest import PLUGIN_DIR, happy_path_responses, scripted_transport

SCRIPTS = PLUGIN_DIR / "skills" / "affiliate-threads-generator" / "scripts"
AFFILIATE_URL = "https://shope.ee/abc123"
TOPIC_TAG = "power bank"

#: The human's own account — the only source a first-hand claim may draw on.
TESTIMONY = "Dipakai buat kerja tiap hari, nyaman, baterainya masih sisa 40 persen sore."

#: A draft whose first post is first-hand copy. It passes every other hard rule
#: on purpose, so each test is about the experience mode and nothing else.
FIRSTHAND_POSTS = [
    {"text": "Aku sudah coba produk ini dan cukup nyaman dipakai kerja."},
    {"text": "Masalahnya: kapasitas besar selalu berarti berat — 380g terasa di saku."},
    {"text": f"Detail lengkapnya ada di sini: {AFFILIATE_URL}"},
    {"text": f"Link afiliasi. {AFFILIATE_URL}"},
]


def _thread(text: str) -> list[dict]:
    return [{"text": text}, {"text": "b"}, {"text": "c"}]


class TestExperienceMode:
    def test_yes_with_a_testimony_is_firsthand(self) -> None:
        assert config.experience_mode("Yes", "dipakai") == config.FIRSTHAND_MODE

    def test_yes_without_a_testimony_is_none(self) -> None:
        assert config.experience_mode("Yes", "") == config.NONE_MODE

    def test_no_is_none_even_beside_leftover_text(self) -> None:
        assert config.experience_mode("No", "stale text") == config.NONE_MODE

    def test_blank_is_none(self) -> None:
        assert config.experience_mode("", "") == config.NONE_MODE

    def test_reading_tolerates_case_and_whitespace(self) -> None:
        assert config.experience_mode(" yes ", " dipakai ") == config.FIRSTHAND_MODE


class TestProvenanceGuardrails:
    """In ``firsthand`` mode the blanket ban is replaced, not relaxed: nothing
    may go beyond what the stored testimony says."""

    def codes(self, report: guardrails.GuardrailReport) -> set[str]:
        return {item.code for item in report.violations}

    def test_a_first_hand_claim_is_allowed_with_a_testimony(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            _thread("Aku sudah coba produk ini dan cukup nyaman."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial=TESTIMONY,
        )
        assert "fabricated_personal_experience" not in self.codes(report)

    def test_the_same_claim_still_blocks_without_an_answer(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(_thread("Aku sudah coba produk ini."), settings)
        assert "fabricated_personal_experience" in self.codes(report)

    def test_an_invented_frequency_is_refused(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            _thread("Aku pakai tiap minggu buat kerja, nyaman."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial=TESTIMONY,
        )
        assert "experience_detail_unsupported" in self.codes(report)

    def test_a_frequency_the_testimony_has_is_fine(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            _thread("Aku pakai tiap hari buat kerja, nyaman."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial=TESTIMONY,
        )
        assert "experience_detail_unsupported" not in self.codes(report)

    def test_naming_a_person_the_testimony_does_not_mention_is_refused(
        self, settings: config.Settings
    ) -> None:
        report = guardrails.validate_thread(
            _thread("Anakku cocok pakai produk ini."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial=TESTIMONY,
        )
        assert "experience_attribution_unsupported" in self.codes(report)

    def test_naming_a_person_the_testimony_describes_is_fine(
        self, settings: config.Settings
    ) -> None:
        report = guardrails.validate_thread(
            _thread("Anakku cocok pakai produk ini."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial="Yang pakai di rumah anak saya, katanya cocok.",
        )
        assert "experience_attribution_unsupported" not in self.codes(report)


class TestAmplifierLanguage:
    def test_guarantees_are_refused_without_an_answer(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(_thread("Dijamin baterainya awet."), settings)
        assert "amplifier_language" in {item.code for item in report.violations}

    def test_guarantees_are_refused_even_with_a_testimony(self, settings: config.Settings) -> None:
        report = guardrails.validate_thread(
            _thread("Dijamin baterainya awet."),
            settings,
            experience=config.FIRSTHAND_MODE,
            testimonial=TESTIMONY,
        )
        assert "amplifier_language" in {item.code for item in report.violations}


@pytest.fixture
def publish_env(monkeypatch: pytest.MonkeyPatch, ctx):  # noqa: ANN001, ANN201
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("THREADS_USER_ID", "user-1")

    def install(sheet: FakeSheet):  # noqa: ANN202
        monkeypatch.setattr(tools, "SheetClient", lambda settings, **kwargs: sheet)
        transport = scripted_transport(happy_path_responses(posts=4))

        def factory(access_token, user_id="", **kwargs):  # noqa: ANN001, ANN202
            return threads_client.ThreadsClient(
                access_token, user_id, transport=transport, sleep=lambda _s: None, max_retries=0
            )

        monkeypatch.setattr(tools, "ThreadsClient", factory)
        return sheet

    return install


def publish(args: dict) -> dict:
    return json.loads(tools.threads_publish({"topic_tag": TOPIC_TAG, **args}))


class TestPublishUsesTheRowsMode:
    def test_a_firsthand_row_publishes_first_hand_copy(self, publish_env) -> None:  # noqa: ANN001
        sheet = publish_env(FakeSheet([make_row(used="Yes", testimonial=TESTIMONY)]))
        result = publish({"product_id": "12", "posts": FIRSTHAND_POSTS, "confirm_publish": True})
        assert result["ok"] is True, result
        assert result["experience"] == "firsthand"
        assert len(sheet.writes) == 1

    def test_the_same_copy_is_refused_without_the_testimony(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row()]))
        result = publish({"product_id": "12", "posts": FIRSTHAND_POSTS, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "fabricated_personal_experience" in {item["code"] for item in result["violations"]}

    def test_an_added_detail_is_refused_even_with_the_testimony(self, publish_env) -> None:  # noqa: ANN001
        sheet = publish_env(FakeSheet([make_row(used="Yes", testimonial=TESTIMONY)]))
        posts = [
            dict(FIRSTHAND_POSTS[0], text="Aku sudah coba produk ini 3 bulan dan nyaman."),
            *FIRSTHAND_POSTS[1:],
        ]
        result = publish({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "experience_detail_unsupported" in {item["code"] for item in result["violations"]}
        assert sheet.writes == []

    def test_guarantee_language_is_refused_in_both_modes(self, publish_env) -> None:  # noqa: ANN001
        publish_env(FakeSheet([make_row(used="Yes", testimonial=TESTIMONY)]))
        posts = [
            dict(FIRSTHAND_POSTS[0], text="Aku sudah coba produk ini. Dijamin awet."),
            *FIRSTHAND_POSTS[1:],
        ]
        result = publish({"product_id": "12", "posts": posts, "confirm_publish": True})
        assert result["stage"] == "guardrails"
        assert "amplifier_language" in {item["code"] for item in result["violations"]}


class StubSheet:
    """Stands in for ``SheetClient`` inside a script: one row, one write op."""

    def __init__(self, row: sheets_client.Row | None, *, fail_write: bool = False) -> None:
        self.row = row
        self.fail_write = fail_write
        self.writes: list[dict] = []

    def __call__(self, settings, **kwargs):  # noqa: ANN001, ANN202 - the script constructs it
        return self

    def find_by_id(self, product_id: str) -> sheets_client.Row | None:
        if self.row is None or self.row.id != str(product_id).strip():
            return None
        return self.row

    def write_experience(self, row_number: int, *, used: str, testimonial: str) -> None:
        if self.fail_write:
            raise sheets_client.SheetError(
                "the Used/Testimonial columns are not configured", stage="sheets_setup"
            )
        self.writes.append({"row": row_number, "used": used, "testimonial": testimonial})


@pytest.fixture(scope="module")
def set_experience_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "atg_set_experience", SCRIPTS / "set_experience.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validate_thread_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "atg_validate_experience", SCRIPTS / "validate_thread.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, sheet: StubSheet, *argv: str
) -> tuple[int, dict]:
    monkeypatch.setattr(sheets_client, "SheetClient", sheet)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        exit_code = script.main(list(argv))
    text = out.getvalue().strip()
    return exit_code, (json.loads(text) if text.startswith("{") else {})


class TestSetExperienceScript:
    def test_a_no_answer_is_written_and_clears_stale_text(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = make_row(used="Yes", testimonial="an old account")
        sheet = StubSheet(row)
        exit_code, payload = run_script(
            set_experience_script, monkeypatch, sheet, "12", "--used", "no"
        )
        assert exit_code == 0
        assert payload["used"] == "No"
        assert payload["experience_mode"] == "none"
        assert sheet.writes == [{"row": row.row_number, "used": "No", "testimonial": ""}]

    def test_a_testimony_is_stored_verbatim(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(make_row())
        exit_code, payload = run_script(
            set_experience_script,
            monkeypatch,
            sheet,
            "12",
            "--used",
            "yes",
            "--testimonial",
            "  Dipakai tiap hari.  ",
        )
        assert exit_code == 0
        assert payload["experience_mode"] == "firsthand"
        assert sheet.writes[0]["testimonial"] == "Dipakai tiap hari."

    def test_yes_without_a_testimony_is_stored_with_a_note(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(make_row())
        exit_code, payload = run_script(
            set_experience_script, monkeypatch, sheet, "12", "--used", "yes"
        )
        assert exit_code == 0
        assert payload["experience_mode"] == "none"
        assert "note" in payload

    def test_no_cannot_carry_a_testimony(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(make_row())
        exit_code, _ = run_script(
            set_experience_script,
            monkeypatch,
            sheet,
            "12",
            "--used",
            "no",
            "--testimonial",
            "x",
        )
        assert exit_code == 4
        assert sheet.writes == []

    def test_an_unknown_id_is_refused(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(None)
        exit_code, _ = run_script(
            set_experience_script, monkeypatch, sheet, "99", "--used", "no"
        )
        assert exit_code == 4

    def test_a_dry_run_writes_nothing(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(make_row())
        exit_code, payload = run_script(
            set_experience_script, monkeypatch, sheet, "12", "--used", "no", "--dry-run"
        )
        assert exit_code == 0
        assert payload["status"] == "dry_run"
        assert sheet.writes == []

    def test_an_unconfigured_layout_reports_instead_of_writing(
        self, set_experience_script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sheet = StubSheet(make_row(), fail_write=True)
        exit_code, payload = run_script(
            set_experience_script, monkeypatch, sheet, "12", "--used", "no"
        )
        assert exit_code == 1
        assert payload["stage"] == "sheets_setup"


def lint(script: ModuleType, tmp_path, posts: list, *extra: str) -> tuple[int, dict]:
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"posts": posts}), encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        exit_code = script.main(
            ["--file", str(draft), "--affiliate-url", AFFILIATE_URL, "--topic-tag", TOPIC_TAG, *extra]
        )
    text = out.getvalue().strip()
    return exit_code, (json.loads(text) if text.startswith("{") else {})


class TestLintExperience:
    """The lint's promise is that a draft passing it passes the publish — so it
    has to follow the same row-derived mode, and refuse a firsthand claim that
    has no testimony behind it."""

    def test_default_none_refuses_a_first_hand_claim(
        self, validate_thread_script: ModuleType, tmp_path
    ) -> None:
        exit_code, payload = lint(validate_thread_script, tmp_path, FIRSTHAND_POSTS)
        assert exit_code == 1
        assert "fabricated_personal_experience" in {
            item["code"] for item in payload["violations"]
        }

    def test_firsthand_without_a_testimony_is_a_usage_error(
        self, validate_thread_script: ModuleType, tmp_path
    ) -> None:
        exit_code, _ = lint(
            validate_thread_script, tmp_path, FIRSTHAND_POSTS, "--experience", "firsthand"
        )
        assert exit_code == 2

    def test_explicit_firsthand_allows_the_claim(
        self, validate_thread_script: ModuleType, tmp_path
    ) -> None:
        exit_code, payload = lint(
            validate_thread_script,
            tmp_path,
            FIRSTHAND_POSTS,
            "--experience",
            "firsthand",
            "--testimonial",
            TESTIMONY,
        )
        assert exit_code == 0, payload

    def test_the_row_supplies_the_mode_and_the_testimony(
        self, validate_thread_script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(
            sheets_client, "SheetClient", StubSheet(make_row(used="Yes", testimonial=TESTIMONY))
        )
        exit_code, payload = lint(
            validate_thread_script, tmp_path, FIRSTHAND_POSTS, "--product-id", "12"
        )
        assert exit_code == 0, payload
        assert payload["experience"] == "firsthand"
