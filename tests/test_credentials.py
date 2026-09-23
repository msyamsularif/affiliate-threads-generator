"""Credential handling — declaration and hygiene.

Two families of check, both pinning down the same promise: this repository
contains credential *names*, never credential *values*.

1. **Declaration.** The plugin declares the names through Hermes' own mechanisms
   (`optional_env` in the manifest, `required_environment_variables` in the skill
   frontmatter) so Hermes owns the prompt, the storage and the injection. The
   declarations in the two files must agree, or a variable reaches the plugin but
   not the skill's scripts (which run as sanitized children).

2. **Hygiene.** Nothing vendor-shaped is committed anywhere.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from atg_plugin import hooks, runtime
from conftest import PLUGIN_DIR

yaml = pytest.importorskip("yaml", reason="pip install pyyaml to run credential checks")

REPO_ROOT = PLUGIN_DIR.parents[1]
MANIFEST_PATH = PLUGIN_DIR / "plugin.yaml"
SKILL_PATH = PLUGIN_DIR / "skills" / "affiliate-threads-generator" / "SKILL.md"

#: The plugin cannot do its job without these. They gate loading, and Hermes
#: prompts for them during `hermes plugins install` / `hermes plugins enable`.
REQUIRED_ENV_VARS = {"THREADS_ACCESS_TOKEN", "AFFILIATE_SHEET_ID"}

#: A working default, or resolved automatically at first use. Declared so they
#: appear in the config UI, but they never block a load.
OPTIONAL_ENV_VARS = {"THREADS_USER_ID", "AFFILIATE_SHEET_TAB"}

#: The union is what the skill must declare: its declaration is what forwards the
#: names into the sanitized `terminal` / `execute_code` children the scripts run
#: in, so an unlisted name reaches the plugin and not the scripts.
EXPECTED_ENV_VARS = REQUIRED_ENV_VARS | OPTIONAL_ENV_VARS

#: Vendor-prefixed credential shapes. Deliberately specific: a loose
#: "high-entropy string" heuristic would flag commit SHAs and content hashes in
#: documentation, and a test that cries wolf gets disabled.
SECRET_SHAPES: tuple[tuple[str, str], ...] = (
    (r"\bTHQW[A-Za-z0-9]{10,}", "Meta Threads user token"),
    (r"\bEAAG[A-Za-z0-9]{20,}", "Facebook / Meta access token"),
    (r"\bsk-proj-[A-Za-z0-9_-]{20,}", "OpenAI project key"),
    (r"\bsk-[A-Za-z0-9]{20,}", "OpenAI-style secret key"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bghp_[A-Za-z0-9]{30,}", "GitHub personal access token"),
    (r"\bAIza[0-9A-Za-z_-]{30,}", "Google API key"),
    (r"\bya29\.[0-9A-Za-z_-]{20,}", "Google OAuth refresh token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"\bbws_[A-Za-z0-9._-]{20,}", "Bitwarden access token"),
    (r"\bops_[A-Za-z0-9]{40,}", "1Password service-account token"),
)

SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".sh", ".toml", ".json", ".txt", ".example", ""}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv", "node_modules"}
SKIP_NAMES = {".env", "uv.lock", "poetry.lock"}

#: Assembled at runtime so this file does not itself trip the scan below.
FAKE_TOKEN = "THQW" + "x" * 24


def iter_repo_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        files.append(path)
    return files


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def skill_frontmatter() -> dict:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1])


# --------------------------------------------------------------------------- #
# Declaration — the manifest
# --------------------------------------------------------------------------- #

class TestManifestDeclaration:
    def test_requires_env_drives_the_install_prompt(self, manifest: dict) -> None:
        """`requires_env` is the only field Hermes prompts for at install time.

        Hermes reads `requires_env` regardless of kind — it is what every shipped
        platform plugin uses, and it is how a new user is walked through setup
        instead of being told to go and edit a file.
        """
        assert {entry["name"] for entry in manifest["requires_env"]} == REQUIRED_ENV_VARS

    def test_optional_env_never_gates(self, manifest: dict) -> None:
        assert {entry["name"] for entry in manifest["optional_env"]} == OPTIONAL_ENV_VARS

    def test_the_two_lists_do_not_overlap(self, manifest: dict) -> None:
        """A name in both lists would still gate, so the prompt would be a lie:
        the user answers it and the plugin stays disabled."""
        required = {entry["name"] for entry in manifest["requires_env"]}
        optional = {entry["name"] for entry in manifest["optional_env"]}
        assert not (required & optional)

    def test_together_they_cover_every_variable_the_plugin_reads(self, manifest: dict) -> None:
        declared = {
            entry["name"]
            for entry in [*manifest["requires_env"], *manifest["optional_env"]]
        }
        assert declared == EXPECTED_ENV_VARS

    def test_every_entry_is_a_rich_dict(self, manifest: dict) -> None:
        """A bare name gives the install prompt and the config UI nothing to show."""
        for entry in [*manifest["requires_env"], *manifest["optional_env"]]:
            assert isinstance(entry, dict), entry
            assert entry.get("name"), entry
            assert entry.get("description"), entry
            assert entry.get("prompt"), entry

    def test_the_threads_token_is_masked_in_both_code_paths(self, manifest: dict) -> None:
        """Two keys because Hermes has two separate readers.

        ``hermes_cli/plugins_cmd.py`` builds the install prompt from `secret`;
        ``hermes_cli/config.py`` builds the config-UI entry from `password`.
        Setting only one leaks the value unmasked on the other surface.
        """
        entry = next(e for e in manifest["requires_env"] if e["name"] == "THREADS_ACCESS_TOKEN")
        assert entry["secret"] is True
        assert entry["password"] is True

    def test_non_secrets_are_not_masked(self, manifest: dict) -> None:
        for entry in [*manifest["requires_env"], *manifest["optional_env"]]:
            if entry["name"] == "THREADS_ACCESS_TOKEN":
                continue
            assert entry.get("password") is not True, entry
            assert entry.get("secret") is not True, entry

    def test_the_token_entry_points_at_the_console(self, manifest: dict) -> None:
        entry = next(e for e in manifest["requires_env"] if e["name"] == "THREADS_ACCESS_TOKEN")
        assert entry.get("url", "").startswith("https://")

    def test_config_schema_secret_carries_an_env_name_and_no_value(self, manifest: dict) -> None:
        for key, spec in manifest["config_schema"].items():
            if spec.get("type") != "secret":
                continue
            assert spec.get("env"), f"{key} is a secret but names no env var"
            assert "default" not in spec or spec["default"] in ("", None), (
                f"{key} declares a default value — secrets are supplied, not shipped"
            )


# --------------------------------------------------------------------------- #
# Declaration — the skill
# --------------------------------------------------------------------------- #

class TestSkillDeclaration:
    def test_declares_the_same_names_as_the_manifest(
        self, manifest: dict, skill_frontmatter: dict
    ) -> None:
        """Mismatch here is a silent, confusing failure.

        The skill's declaration is what forwards the variable into the `terminal`
        and `execute_code` children the skill's scripts run in. A name the
        manifest declares but the skill does not reaches the plugin and not the
        scripts.
        """
        manifest_names = {
            entry["name"]
            for entry in [*manifest["requires_env"], *manifest["optional_env"]]
        }
        skill_names = {
            entry["name"] for entry in skill_frontmatter["required_environment_variables"]
        }
        assert skill_names == manifest_names

    def test_every_entry_explains_itself(self, skill_frontmatter: dict) -> None:
        for entry in skill_frontmatter["required_environment_variables"]:
            assert entry.get("name"), entry
            assert entry.get("prompt"), entry
            assert entry.get("help"), entry
            assert entry.get("required_for"), entry

    def test_declares_the_google_credential_files(self, skill_frontmatter: dict) -> None:
        """This skill borrows google-workspace's OAuth artifacts.

        Declaring them lets Hermes report "setup needed" before the first Sheet
        call and mount them correctly on remote backends.
        """
        paths = {entry["path"] for entry in skill_frontmatter["required_credential_files"]}
        assert paths == {"google_token.json", "google_client_secret.json"}

    def test_credential_file_paths_are_relative(self, skill_frontmatter: dict) -> None:
        for entry in skill_frontmatter["required_credential_files"]:
            assert not entry["path"].startswith("/"), entry


# --------------------------------------------------------------------------- #
# Hygiene — nothing secret-shaped is committed
# --------------------------------------------------------------------------- #

class TestRepositoryHygiene:
    @pytest.mark.parametrize(("pattern", "label"), SECRET_SHAPES)
    def test_no_vendor_shaped_secret_anywhere(self, pattern: str, label: str) -> None:
        compiled = re.compile(pattern)
        offenders: list[str] = []
        for path in iter_repo_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):  # pragma: no cover - defensive
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
        assert not offenders, f"possible {label} committed at: {offenders}"

    def test_env_example_contains_no_values(self) -> None:
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            assert "=" in stripped, f".env.example:{number} is not a KEY=VALUE line"
            key, _, value = stripped.partition("=")
            assert value.strip() == "", (
                f".env.example:{number} gives {key.strip()} a value. "
                "Names only — Hermes owns the values."
            )

    def test_env_is_gitignored(self) -> None:
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert ".env" in [line.strip() for line in ignored]

    def test_docs_never_ask_for_a_token_in_chat(self) -> None:
        """A token pasted into Telegram lands in the conversation history and the
        session database. Setup guidance must never invite that."""
        pattern = re.compile(r"(paste|kirim|send)\s+(it|the token|your token)\s+(to|ke)\s+", re.I)
        for path in (REPO_ROOT / "docs").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert not pattern.search(text), f"{path.name} asks for a secret in-band"


# --------------------------------------------------------------------------- #
# Runtime — a credential is never written anywhere durable
# --------------------------------------------------------------------------- #

class TestCredentialsAreNeverPersisted:
    def test_the_audit_trail_does_not_record_the_token(
        self, monkeypatch: pytest.MonkeyPatch, ctx
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", FAKE_TOKEN)
        hooks.on_post_tool_call(
            tool_name="threads_publish",
            args={"product_id": "12", "posts": [{"text": "a"}]},
            result=json.dumps({"ok": True, "status": "published", "threads_url": "https://x/y"}),
        )
        audit = runtime.state_get("publish_audit", default=[])
        assert FAKE_TOKEN not in json.dumps(audit)

    def test_check_reports_configured_without_the_value(
        self, monkeypatch: pytest.MonkeyPatch, ctx
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", FAKE_TOKEN)
        from atg_plugin import tools

        payload = json.loads(tools.threads_check({"include_sheet": False, "include_token": False}))
        assert payload["settings"]["threads_credentials_configured"] is True
        assert FAKE_TOKEN not in json.dumps(payload)

    def test_public_summary_never_includes_the_value(
        self, monkeypatch: pytest.MonkeyPatch, ctx
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", FAKE_TOKEN)
        from atg_plugin import config

        assert FAKE_TOKEN not in json.dumps(config.resolve().public_summary())
