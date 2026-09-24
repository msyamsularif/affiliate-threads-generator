#!/usr/bin/env python3
"""Bridge between this skill's scripts and the plugin's Python modules.

The scripts and the `threads_publish` tool must agree exactly — a draft that
passes `validate_thread.py` and then fails at publish time would be a bug. Rather
than duplicating the rules, the scripts import the plugin's own modules.

That includes the operator's settings: the plugin reads
``plugins.entries.<id>.settings.*`` from Hermes' ``config.yaml`` itself when it
runs outside Hermes, so a customised guardrail is enforced here too. If that
read fails, ``settings_note()`` says so and the caller prints it — a lint that
ran with different rules must never look like a clean bill of health.

Locating the plugin:

1. ``$HERMES_HOME/plugins/affiliate-threads-generator``
2. ``~/.hermes/plugins/affiliate-threads-generator``
3. three directories up from this file — which is the plugin directory in both
   layouts the skill ever lives in, the repository
   (``<repo>/skills/<skill>/scripts/``) and the plugin as Hermes installs it
   (``<hermes>/plugins/<plugin>/skills/<skill>/scripts/``)

The modules use relative imports, so the plugin directory is registered in
``sys.modules`` as a package first.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

PACKAGE_NAME = "atg_plugin"
PLUGIN_DIRNAME = "affiliate-threads-generator"

_cached: types.ModuleType | None = None


def candidate_dirs() -> list[Path]:
    dirs: list[Path] = []

    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        dirs.append(Path(hermes_home).expanduser() / "plugins" / PLUGIN_DIRNAME)
    dirs.append(Path.home() / ".hermes" / "plugins" / PLUGIN_DIRNAME)

    # Layout-relative fallback. Three directories up is the plugin directory in
    # both layouts, so one candidate covers them:
    #
    #   in-repo:   <repo>/skills/<skill>/scripts/_bridge.py
    #   installed: <hermes>/plugins/<plugin>/skills/<skill>/scripts/_bridge.py
    here = Path(__file__).resolve()
    parents = here.parents
    if len(parents) > 3:
        dirs.append(parents[3])

    # De-duplicate while preserving order (the "first match wins" contract).
    seen: set[Path] = set()
    unique: list[Path] = []
    for directory in dirs:
        if directory not in seen:
            seen.add(directory)
            unique.append(directory)
    return unique


def find_plugin_dir() -> Path | None:
    for directory in candidate_dirs():
        if (directory / "guardrails.py").is_file() and (directory / "config.py").is_file():
            return directory
    return None


def plugin_package() -> types.ModuleType:
    """Import the plugin directory as a package and return it."""
    global _cached
    if _cached is not None:
        return _cached

    # A host process — the test suite, a REPL, another script — may already
    # have registered the plugin under this name. Reuse it instead of replacing
    # it: replacing drops whatever that package carried (``register``, bound
    # state) and the next importer would silently get a different module object.
    registered = sys.modules.get(PACKAGE_NAME)
    if registered is not None and getattr(registered, "__path__", None):
        _cached = registered
        return registered

    directory = find_plugin_dir()
    if directory is None:
        searched = "\n".join(f"  - {path}" for path in candidate_dirs())
        raise RuntimeError(
            "the affiliate-threads-generator plugin could not be found. Searched:\n"
            f"{searched}\n"
            "Install it with: hermes plugins install msyamsularif/affiliate-threads-generator --enable"
        )

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(directory)]  # type: ignore[attr-defined]
    package.__file__ = str(directory / "__init__.py")
    sys.modules[PACKAGE_NAME] = package
    _cached = package
    return package


def load(module_name: str):
    """Import ``atg_plugin.<module_name>`` and return the module."""
    plugin_package()
    return __import__(f"{PACKAGE_NAME}.{module_name}", fromlist=[module_name])


def plugin_path() -> Path:
    return Path(plugin_package().__path__[0])  # type: ignore[attr-defined]


def settings_note() -> str:
    """A one-line warning when the plugin's own settings could not be read.

    The scripts enforce the same rules as ``threads_publish`` by importing the
    plugin's modules, and those read ``plugins.entries.<id>.settings.*`` from
    Hermes' ``config.yaml`` when there is no host context. That read can fail
    (no PyYAML, a construct the fallback parser refuses). When it does, the
    defaults are in effect — which is exactly the divergence the scripts must
    not be quiet about.
    """
    try:
        return str(load("runtime").settings_note() or "")
    except Exception:  # noqa: BLE001 - a missing plugin is reported elsewhere
        return ""
