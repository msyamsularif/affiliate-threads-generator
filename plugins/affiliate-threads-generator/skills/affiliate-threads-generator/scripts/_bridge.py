#!/usr/bin/env python3
"""Bridge between this skill's scripts and the plugin's Python modules.

The scripts and the `threads_publish` tool must agree exactly — a draft that
passes `validate_thread.py` and then fails at publish time would be a bug. Rather
than duplicating the rules, the scripts import the plugin's own modules.

Locating the plugin:

1. ``$HERMES_HOME/plugins/affiliate-threads-generator``
2. ``~/.hermes/plugins/affiliate-threads-generator``
3. two directories up from this file (the bundled-in-plugin layout)

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

    # Layout-relative fallbacks. Both are checked; anything that does not contain
    # the plugin's modules is discarded by find_plugin_dir().
    #
    #   bundled:   <plugin>/skills/<skill>/scripts/_bridge.py   -> parents[3]
    #   installed: <hermes>/skills/<skill>/scripts/_bridge.py   -> parents[2]/plugins/<plugin>
    here = Path(__file__).resolve()
    parents = here.parents
    if len(parents) > 3:
        dirs.append(parents[3])
    if len(parents) > 2:
        dirs.append(parents[2] / "plugins" / PLUGIN_DIRNAME)
        dirs.append(parents[2])

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

    directory = find_plugin_dir()
    if directory is None:
        searched = "\n".join(f"  - {path}" for path in candidate_dirs())
        raise RuntimeError(
            "the affiliate-threads-generator plugin could not be found. Searched:\n"
            f"{searched}\n"
            "Install it with ./install.sh from the repository root."
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
