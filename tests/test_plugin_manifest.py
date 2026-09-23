"""Manifest / registration integrity.

These are the checks ``hermes plugins doctor`` performs — declared tools and hooks
must match what ``register(ctx)`` actually registers, and the bundled skill must be
loadable. Catching drift here is much cheaper than catching it at load time.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import PLUGIN_DIR

yaml = pytest.importorskip("yaml", reason="pip install pyyaml to run manifest checks")

MANIFEST_PATH = PLUGIN_DIR / "plugin.yaml"
SKILL_DIR = PLUGIN_DIR / "skills" / "affiliate-threads-generator"

#: Types the manifest v2 reference documents for `config_schema` entries.
VALID_SCHEMA_TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "secret",
    "string",
    "boolean",
    "integer",
    "number",
    "array",
    "object",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


class RecordingContext:
    """A ``PluginContext`` that records what the plugin registers."""

    def __init__(self) -> None:
        self.tools: list[dict] = []
        self.hooks: list[tuple[str, object]] = []
        self.skills: list[tuple[str, Path]] = []
        self.settings: dict = {}

    def get_config(self, key: str, default=None):  # noqa: ANN001, ANN201
        return self.settings.get(key, default)

    def set_config(self, key: str, value) -> None:  # noqa: ANN001
        self.settings[key] = value

    def register_tool(self, **kwargs) -> None:  # noqa: ANN003
        self.tools.append(kwargs)

    def register_hook(self, event: str, callback) -> None:  # noqa: ANN001
        self.hooks.append((event, callback))

    def register_skill(self, name: str, path) -> None:  # noqa: ANN001
        self.skills.append((name, Path(path)))


@pytest.fixture
def registered() -> RecordingContext:
    plugin = importlib.import_module("atg_plugin")
    context = RecordingContext()
    plugin.register(context)
    return context


class TestManifest:
    def test_parses_as_mapping(self, manifest: dict) -> None:
        assert isinstance(manifest, dict)

    def test_declares_v2_and_identifies_itself(self, manifest: dict) -> None:
        assert manifest["manifest_version"] == 2
        assert manifest["api_version"] == 1
        assert manifest["name"] == "affiliate-threads-generator"
        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
        assert manifest["license"] == "MIT"
        assert manifest["description"]

    def test_declares_env_for_the_install_prompt(self, manifest: dict) -> None:
        # `requires_env` is what makes `hermes plugins install` / `enable` collect
        # the credentials, instead of leaving a new user to go and edit a file.
        # `optional_env` covers the two with working defaults, so they never gate.
        assert manifest["requires_env"]
        assert manifest["optional_env"]

    def test_every_config_schema_entry_uses_a_known_type(self, manifest: dict) -> None:
        for key, spec in manifest["config_schema"].items():
            assert "type" in spec, key
            assert spec["type"] in VALID_SCHEMA_TYPES, f"{key}: {spec['type']}"

    def test_secret_settings_declare_an_env_var(self, manifest: dict) -> None:
        for key, spec in manifest["config_schema"].items():
            if spec["type"] == "secret":
                assert spec.get("env"), f"{key} is a secret but has no env name"

    def test_choices_settings_have_a_default_inside_the_choices(self, manifest: dict) -> None:
        for key, spec in manifest["config_schema"].items():
            if "choices" in spec:
                assert spec.get("default") in spec["choices"], key


class TestRegistration:
    def test_declared_tools_match_registered_tools(self, manifest: dict, registered) -> None:  # noqa: ANN001
        declared = sorted(manifest["provides_tools"])
        actual = sorted(tool["name"] for tool in registered.tools)
        assert declared == actual

    def test_declared_hooks_match_registered_hooks(self, manifest: dict, registered) -> None:  # noqa: ANN001
        declared = sorted(set(manifest["provides_hooks"]))
        actual = sorted({event for event, _ in registered.hooks})
        assert declared == actual

    def test_every_tool_has_a_schema_and_a_handler(self, registered) -> None:  # noqa: ANN001
        for tool in registered.tools:
            assert tool["schema"]["name"] == tool["name"]
            assert tool["schema"]["description"]
            assert tool["schema"]["parameters"]["type"] == "object"
            assert callable(tool["handler"])
            assert tool["toolset"] == "affiliate_threads"

    def test_schemas_are_json_serialisable(self, registered) -> None:  # noqa: ANN001
        for tool in registered.tools:
            assert json.dumps(tool["schema"])

    def test_handlers_accept_args_and_kwargs(self, registered) -> None:  # noqa: ANN001
        import inspect

        for tool in registered.tools:
            params = inspect.signature(tool["handler"]).parameters
            assert len(params) >= 1
            assert any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())

    def test_hook_callbacks_accept_kwargs(self, registered) -> None:  # noqa: ANN001
        import inspect

        for event, callback in registered.hooks:
            params = inspect.signature(callback).parameters
            assert any(
                param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
            ), f"{event} callback should accept **kwargs"

    def test_publish_tool_is_registered(self, registered) -> None:  # noqa: ANN001
        names = {tool["name"] for tool in registered.tools}
        assert "threads_publish" in names

    def test_register_binds_the_host_context(self, registered) -> None:  # noqa: ANN001
        from atg_plugin import runtime

        assert runtime.has_context() is True


class TestBundledSkill:
    def test_skill_directory_is_registered(self, registered) -> None:  # noqa: ANN001
        assert registered.skills
        names = {name for name, _ in registered.skills}
        assert "affiliate-threads-generator" in names

    def test_skill_file_exists(self) -> None:
        assert (SKILL_DIR / "SKILL.md").is_file()

    def test_frontmatter_is_valid(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        _, frontmatter, body = text.split("---\n", 2)
        meta = yaml.safe_load(frontmatter)

        assert meta["name"] == "affiliate-threads-generator"
        assert len(meta["description"]) > 80
        assert meta["version"]
        assert meta["license"] == "MIT"
        assert body.strip()

    def test_frontmatter_description_states_when_to_use_it(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---\n", 2)[1]
        meta = yaml.safe_load(frontmatter)
        lowered = meta["description"].lower()
        assert "use for" in lowered or "use it" in lowered or "use when" in lowered

    def test_blueprint_schedule_matches_the_specification(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---\n", 2)[1])
        blueprint = meta["metadata"]["hermes"]["blueprint"]

        # Monday, Wednesday, Friday, Sunday at 08:00 (0 = Sunday).
        assert blueprint["schedule"] == "0 8 * * 0,1,3,5"
        assert blueprint["prompt"]

    def test_every_referenced_file_exists(self) -> None:
        """The skill's progressive disclosure only works if the files are real."""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        referenced = set(re.findall(r"`(references/[\w./-]+\.md)`", text))
        assert referenced, "the skill should point at its reference files"
        for relative in sorted(referenced):
            assert (SKILL_DIR / relative).is_file(), f"missing {relative}"

    @pytest.mark.parametrize(
        "script",
        [
            "_bridge.py",
            "doctor.py",
            "select_candidate.py",
            "set_status.py",
            "threads_token.py",
            "validate_thread.py",
        ],
    )
    def test_scripts_exist_and_are_syntactically_valid(self, script: str) -> None:
        import ast

        path = SKILL_DIR / "scripts" / script
        assert path.is_file(), f"missing scripts/{script}"
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_scripts_have_a_shebang(self) -> None:
        for path in (SKILL_DIR / "scripts").glob("*.py"):
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
            assert first_line.startswith("#!"), f"{path.name} has no shebang"

    def test_guardrails_are_documented_in_the_skill(self) -> None:
        """The writer must be told the rules the tool will enforce."""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
        assert "disclosure" in text
        assert "personal experience" in text
        assert "threads_publish" in text


class TestRepositoryLayout:
    def test_docs_exist(self) -> None:
        docs = PLUGIN_DIR.parents[1] / "docs"
        for name in (
            "installation.md",
            "configuration.md",
            "threads-app-setup.md",
            "google-sheets-setup.md",
            "cron-setup.md",
            "operations-runbook.md",
            "credentials.md",
        ):
            assert (docs / name).is_file(), f"missing docs/{name}"

    def test_install_script_is_executable_content(self) -> None:
        script = PLUGIN_DIR.parents[1] / "install.sh"
        assert script.is_file()
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")

    def test_install_script_runs_clean(self, tmp_path: Path) -> None:
        """Run the installer for real, into a throwaway HERMES_HOME.

        The next-steps block is an *unquoted* heredoc, so a stray backtick is
        executed as a command rather than printed: bash reports "command not
        found" on stderr and silently drops the word from the output. That got
        shipped once. Asserting empty stderr is what catches it.
        """
        script = PLUGIN_DIR.parents[1] / "install.sh"
        home = tmp_path / "hermes"
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            env={**os.environ, "HERMES_HOME": str(home)},
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stderr == "", f"install.sh wrote to stderr:\n{result.stderr}"

        # The text the heredoc is supposed to print must survive intact.
        assert "requires_env" in result.stdout
        assert "optional_env" in result.stdout

        # And it must have actually installed both halves under the current name.
        plugin_dir = home / "plugins" / PLUGIN_DIR.name
        skill_dir = home / "skills" / PLUGIN_DIR.name
        assert (plugin_dir / "plugin.yaml").is_file()
        assert (skill_dir / "SKILL.md").is_file()
        assert "affiliate-threads-generator" in (plugin_dir / "plugin.yaml").read_text(
            encoding="utf-8"
        )

    def test_the_two_directories_share_the_plugin_name(self) -> None:
        """The bundled skill directory must match the plugin, or install.sh
        copies from a path that does not exist."""
        skills = PLUGIN_DIR / "skills"
        assert [child.name for child in skills.iterdir() if child.is_dir()] == [PLUGIN_DIR.name]
