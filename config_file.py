"""Read the plugin's own settings out of ``$HERMES_HOME/config.yaml``.

Inside Hermes, the host resolves
``plugins.entries.<plugin-id>.settings.<key>`` and hands the values to the
plugin through ``ctx.get_config``. The skill's scripts run *outside* Hermes —
there is no ``ctx``, so nothing was reading that file for them and every
operator-set guardrail silently fell back to its default. A draft that passed
``validate_thread.py`` could then be refused at publish time, which defeats the
one promise the lint makes.

This module closes that gap by reading the same file, at the same path.

Two parsers, in order:

1. **PyYAML**, when it is importable. Hermes itself parses the file with it, so
   this is the exact reading the host makes.
2. A **narrow fallback** for hosts where PyYAML is absent (the skill's scripts
   run under whatever ``python3`` is on PATH). It understands the shape plugin
   settings actually take — nested mappings of scalars, inline ``[a, b]`` lists
   and ``- item`` blocks — and deliberately refuses anything else.

The fallback never guesses. A construct it does not understand inside the
settings block yields *no settings* plus a warning naming the line, so a script
can say so instead of quietly enforcing different rules than the tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Path of the settings block inside Hermes' ``config.yaml``.
SETTINGS_PATH: tuple[str, ...] = ("plugins", "entries")


@dataclass
class ConfigFile:
    """What could be read, and what could not."""

    path: Path
    found: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    warning: str = ""

    @property
    def readable(self) -> bool:
        return self.found and not self.warning


def config_path() -> Path:
    """``$HERMES_HOME/config.yaml``, else ``~/.hermes/config.yaml``."""
    root = os.environ.get("HERMES_HOME", "").strip()
    base = Path(root).expanduser() if root else Path.home() / ".hermes"
    return base / "config.yaml"


# --------------------------------------------------------------------------- #
# Scalars
# --------------------------------------------------------------------------- #

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"", "~", "null", "none"}


class _Unsupported(Exception):
    """A line the fallback will not guess at. Carries the line number."""

    def __init__(self, line_number: int, reason: str) -> None:
        super().__init__(f"line {line_number}: {reason}")
        self.line_number = line_number
        self.reason = reason


def _strip_plain_comment(text: str) -> str:
    """Drop a trailing ``# comment`` from an unquoted scalar."""
    marker = text.find(" #")
    if marker != -1:
        return text[:marker].rstrip()
    if text.startswith("#"):
        return ""
    return text.rstrip()


def _unquote(text: str, line_number: int = 0) -> tuple[str, str]:
    """Read a quoted scalar. Returns ``(value, remainder)``; raises if unterminated."""
    quote = text[0]
    out: list[str] = []
    index = 1
    while index < len(text):
        char = text[index]
        if quote == '"' and char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(following, "\\" + following))
            index += 2
            continue
        if char == quote:
            if quote == "'" and index + 1 < len(text) and text[index + 1] == "'":
                out.append("'")
                index += 2
                continue
            return "".join(out), text[index + 1 :]
        out.append(char)
        index += 1
    raise _Unsupported(line_number, "unterminated quoted value")


def _split_inline_list(text: str, line_number: int) -> list[Any]:
    """``[a, "b, c"]`` -> ``["a", "b, c"]``; raises on nesting or braces."""
    if not text.endswith("]"):
        raise _Unsupported(line_number, "unterminated inline list")
    body = text[1:-1].strip()
    if not body:
        return []
    items: list[Any] = []
    current = ""
    quote = ""
    for char in body:
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            current += char
            continue
        if char in "[{":
            raise _Unsupported(line_number, "nested collections inside an inline list")
        if char == ",":
            items.append(_scalar(current.strip(), line_number))
            current = ""
            continue
        current += char
    if quote:
        raise _Unsupported(line_number, "unterminated quoted value")
    items.append(_scalar(current.strip(), line_number))
    return items


def _scalar(text: str, line_number: int = 0) -> Any:  # noqa: ANN401 - YAML scalars are heterogeneous by nature
    """A scalar value: quoted string, inline list, bool, null, number, or string."""
    if text == "":
        return None
    if text[0] in "\"'":
        value, rest = _unquote(text, line_number)
        rest = _strip_plain_comment(rest.strip())
        if rest:
            raise _Unsupported(line_number, f"unexpected text after a quoted value: {rest!r}")
        return value
    if text.startswith("["):
        return _split_inline_list(text, line_number)
    if text.startswith("{") or text[0] in "&*!|>%@`":
        raise _Unsupported(line_number, f"unsupported value syntax: {text[:20]!r}")

    plain = _strip_plain_comment(text)
    lowered = plain.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    if lowered in _NULL:
        return None
    try:
        return int(plain)
    except ValueError:
        pass
    try:
        return float(plain)
    except ValueError:
        return plain


# --------------------------------------------------------------------------- #
# The narrow fallback parser
# --------------------------------------------------------------------------- #

def _records(text: str) -> list[tuple[int, int, str]]:
    """``(line_number, indent, content)`` for every meaningful line."""
    out: list[tuple[int, int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rest = raw.lstrip(" ")
        if rest.startswith("\t"):
            # YAML forbids tabs as indentation, so PyYAML would refuse the file
            # too — but say so rather than mis-indent the block.
            raise _Unsupported(number, "tab used for indentation")
        out.append((number, len(raw) - len(rest), rest.rstrip()))
    return out


def _split_key(content: str, line_number: int) -> tuple[str, str]:
    """``"max_posts: 10"`` -> ``("max_posts", "10")``; ``"key:"`` -> ``("key", "")``."""
    if content.startswith("- "):
        raise _Unsupported(line_number, "a list item where a mapping key was expected")
    if content[0] in "\"'":
        raise _Unsupported(line_number, "a quoted mapping key")
    index = content.find(":")
    if index <= 0:
        raise _Unsupported(line_number, f"not a `key: value` pair: {content[:30]!r}")
    key = content[:index].strip()
    if not key or " " in key:
        raise _Unsupported(line_number, f"unsupported key: {key!r}")
    return key, content[index + 1 :].strip()


def _block_end(records: list[tuple[int, int, str]], start: int, indent: int) -> int:
    """Index just past the last record indented deeper than ``indent``."""
    index = start
    while index < len(records) and records[index][1] > indent:
        index += 1
    return index


def _find_key(
    records: list[tuple[int, int, str]], start: int, end: int, indent: int, key: str
) -> int | None:
    """Index of the direct child ``key:`` inside ``records[start:end]``."""
    index = start
    while index < end:
        line_number, line_indent, content = records[index]
        if line_indent < indent:
            return None
        if line_indent == indent:
            candidate, _ = _split_key(content, line_number)
            if candidate == key:
                return index
        index += 1
    return None


def _parse_block(
    records: list[tuple[int, int, str]], start: int, parent_indent: int
) -> tuple[Any, int]:
    """Parse a mapping or a sequence of scalars indented deeper than ``parent_indent``."""
    if start >= len(records) or records[start][1] <= parent_indent:
        return {}, start

    block_indent = records[start][1]
    if records[start][2].startswith("-"):
        items: list[Any] = []
        index = start
        while index < len(records) and records[index][1] == block_indent:
            line_number, _, content = records[index]
            if not content.startswith("- "):
                break
            item = content[2:].strip()
            if item[:1] not in "\"'[{" and (": " in item or item.endswith(":")):
                raise _Unsupported(line_number, "a mapping inside a list item")
            items.append(_scalar(item, line_number))
            index += 1
        if index < len(records) and records[index][1] > block_indent:
            raise _Unsupported(records[index][0], "a nested block inside a list item")
        return items, index

    mapping: dict[str, Any] = {}
    index = start
    while index < len(records) and records[index][1] == block_indent:
        line_number, _, content = records[index]
        key, rest = _split_key(content, line_number)
        if key in mapping:
            raise _Unsupported(line_number, f"duplicate key {key!r}")
        if rest:
            mapping[key] = _scalar(rest, line_number)
            index += 1
            continue
        child, index = _parse_block(records, index + 1, block_indent)
        mapping[key] = child
    if index < len(records) and records[index][1] > block_indent:
        raise _Unsupported(records[index][0], "inconsistent indentation")
    return mapping, index


def _fallback_settings(text: str, plugin_id: str) -> tuple[dict[str, Any], str]:
    """Settings from the fallback parser, plus a warning when it had to stop."""
    try:
        records = _records(text)
        if not records:
            return {}, ""
        top = min(indent for _, indent, _ in records)
        plugins = _find_key(records, 0, len(records), top, "plugins")
        if plugins is None:
            return {}, ""
        end = _block_end(records, plugins + 1, top)
        child = records[plugins + 1][1] if plugins + 1 < end else None
        entries = (
            _find_key(records, plugins + 1, end, child, "entries") if child is not None else None
        )
        if entries is None:
            return {}, ""
        entry_end = _block_end(records, entries + 1, child)
        entry_indent = records[entries + 1][1] if entries + 1 < entry_end else None
        plugin = (
            _find_key(records, entries + 1, entry_end, entry_indent, plugin_id)
            if entry_indent is not None
            else None
        )
        if plugin is None:
            return {}, ""
        plugin_end = _block_end(records, plugin + 1, entry_indent)
        settings_indent = records[plugin + 1][1] if plugin + 1 < plugin_end else None
        settings = (
            _find_key(records, plugin + 1, plugin_end, settings_indent, "settings")
            if settings_indent is not None
            else None
        )
        if settings is None:
            return {}, ""
        block, index = _parse_block(records, settings + 1, settings_indent)
        if index != plugin_end:
            line_number = records[index][0] if index < len(records) else 0
            raise _Unsupported(line_number, "trailing content the fallback parser skipped")
    except _Unsupported as exc:
        return {}, (
            f"config.yaml: the settings block could not be read without PyYAML "
            f"({exc.reason} at line {exc.line_number}); the defaults and the "
            "environment are in effect instead"
        )
    if not isinstance(block, dict):
        return {}, "config.yaml: plugins.entries.<plugin>.settings is not a mapping"
    return block, ""


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def _yaml(data_text: str) -> tuple[dict[str, Any] | None, str]:
    """Parse with PyYAML. Returns ``(data, warning)``; ``data is None`` on failure."""
    try:
        import yaml
    except ImportError:
        return None, "unavailable"
    try:
        data = yaml.safe_load(data_text)
    except yaml.YAMLError as exc:  # pragma: no cover - depends on the host file
        first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return None, f"config.yaml could not be parsed: {first}"
    if data is None:
        return {}, ""
    if not isinstance(data, dict):
        return None, "the top level of config.yaml is not a mapping"
    return data, ""


def _dig(data: dict[str, Any], plugin_id: str) -> tuple[dict[str, Any], str]:
    node: Any = data
    for key in (*SETTINGS_PATH, plugin_id, "settings"):
        if not isinstance(node, dict):
            return {}, f"config.yaml: {key!r} is not a mapping, so plugin settings could not be read"
        node = node.get(key)
        if node is None:
            return {}, ""
    if not isinstance(node, dict):
        return {}, "config.yaml: plugins.entries.<plugin>.settings is not a mapping"
    return {str(key): value for key, value in node.items()}, ""


def load(plugin_id: str, path: Path | None = None) -> ConfigFile:
    """Read ``plugins.entries.<plugin_id>.settings`` from the Hermes config file."""
    target = path or config_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ConfigFile(path=target, found=False)
    except OSError as exc:
        return ConfigFile(path=target, found=True, warning=f"config.yaml is unreadable: {exc}")

    data, warning = _yaml(text)
    if data is None and warning == "unavailable":
        settings, warning = _fallback_settings(text, plugin_id)
        return ConfigFile(path=target, found=True, settings=settings, warning=warning)
    if data is None:
        return ConfigFile(path=target, found=True, warning=warning)

    settings, warning = _dig(data, plugin_id)
    return ConfigFile(path=target, found=True, settings=settings, warning=warning)
