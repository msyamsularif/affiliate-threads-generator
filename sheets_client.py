"""Google Sheets access, reusing Hermes' bundled ``google-workspace`` skill.

The plugin deliberately does not ship its own Google OAuth handling. Hermes
already has an authenticated ``google_api.py`` that the ``google-workspace``
skill uses, so this module shells out to it:

    google_api.py sheets get    <spreadsheet_id> "<tab>!A1:G"
    google_api.py sheets update <spreadsheet_id> "<tab>!F2:G2" --values '[[...]]'

That keeps one credential store, one refresh path, and no second Google client
in the process. If ``google_api.py`` cannot be located, the caller gets an
actionable error instead of a stack trace.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings, column_index, column_letter, experience_mode

logger = logging.getLogger(__name__)

Runner = Callable[[Sequence[str]], "tuple[int, str, str]"]


class SheetError(RuntimeError):
    """A failure reading from or writing to the business-data Sheet."""

    def __init__(self, message: str, *, stage: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.hint = hint

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": self.message}
        if self.stage:
            payload["stage"] = self.stage
        if self.hint:
            payload["hint"] = self.hint
        return payload


@dataclass
class Row:
    """One candidate row, addressed by its 1-based sheet row number."""

    row_number: int
    values: dict[str, str] = field(default_factory=dict)

    def get(self, field_name: str, default: str = "") -> str:
        return self.values.get(field_name, default) or default

    @property
    def id(self) -> str:
        return self.get("id")

    @property
    def product(self) -> str:
        return self.get("product")

    @property
    def description(self) -> str:
        return self.get("description")

    @property
    def affiliate_url(self) -> str:
        return self.get("affiliate_url")

    @property
    def category(self) -> str:
        return self.get("category")

    @property
    def threads_url(self) -> str:
        return self.get("threads_url")

    @property
    def status(self) -> str:
        return self.get("status")

    @property
    def used(self) -> str:
        """The row's experience answer: ``Yes`` / ``No`` / blank (not answered)."""
        return self.get("used")

    @property
    def testimonial(self) -> str:
        """The human's own account of using the product, stored verbatim."""
        return self.get("testimonial")

    def experience_mode(self) -> str:
        """The guardrail mode this row resolves to (see ``config.experience_mode``)."""
        return experience_mode(self.used, self.testimonial)

    def as_dict(self, *, include_description: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "row": self.row_number,
            "id": self.id,
            "product": self.product,
            "category": self.category,
            "status": self.status,
            "affiliate_url": self.affiliate_url,
            "threads_url": self.threads_url,
            "used": self.used,
            "experience_mode": self.experience_mode(),
        }
        if include_description:
            payload["description"] = self.description
            payload["testimonial"] = self.testimonial
        return payload


def _default_runner(argv: Sequence[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(  # noqa: S603 - argv is built here, never a shell string
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except OSError as exc:
        return 126, "", str(exc)
    return completed.returncode, completed.stdout, completed.stderr


def discover_google_api(explicit: str = "") -> Path | None:
    """Locate the bundled google-workspace skill's ``google_api.py``."""
    candidates: list[Path] = []

    if explicit:
        candidates.append(Path(explicit).expanduser())

    env_path = os.environ.get("HERMES_GAPI_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    homes: list[Path] = []
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        homes.append(Path(hermes_home).expanduser())
    homes.append(Path.home() / ".hermes")

    for home in homes:
        skills_root = home / "skills"
        if not skills_root.is_dir():
            continue
        candidates.append(skills_root / "productivity" / "google-workspace" / "scripts" / "google_api.py")
        with contextlib.suppress(OSError):  # pragma: no cover - defensive
            candidates.extend(sorted(skills_root.glob("**/google-workspace/scripts/google_api.py")))

    on_path = shutil.which("google_api.py")
    if on_path:
        candidates.append(Path(on_path))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


class SheetClient:
    """Read and write the candidate table through the bundled Google CLI."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: Runner | None = None,
        google_api_path: Path | str | None = None,
    ) -> None:
        self.settings = settings
        self._runner = runner or _default_runner
        if google_api_path is not None:
            self._google_api: Path | None = Path(google_api_path)
        else:
            self._google_api = discover_google_api(settings.google_api_path)

    # ------------------------------------------------------------------ #
    # plumbing
    # ------------------------------------------------------------------ #

    @property
    def google_api(self) -> Path:
        if self._google_api is None:
            raise SheetError(
                "the bundled google-workspace skill's google_api.py could not be found",
                stage="sheets_setup",
                hint=(
                    "Install/authorize the google-workspace skill, or point "
                    "HERMES_GAPI_PATH / the google_api_path setting at the script."
                ),
            )
        return self._google_api

    @property
    def spreadsheet_id(self) -> str:
        if not self.settings.spreadsheet_id:
            raise SheetError(
                "no spreadsheet configured",
                stage="sheets_setup",
                hint=(
                    'Set it with `hermes config set AFFILIATE_SHEET_ID "<id>"` — the id from '
                    "the sheet's URL — or load the skill in the local CLI and let Hermes "
                    "prompt for it. See docs/credentials.md."
                ),
            )
        return self.settings.spreadsheet_id

    def _argv(self, *args: str) -> list[str]:
        template = shlex.split(self.settings.google_api_command or "{python} {script}")
        head = [
            part.format(python=sys.executable, script=str(self.google_api))
            for part in template
        ]
        return [*head, *args]

    def _run_json(self, *args: str, stage: str) -> Any:  # noqa: ANN401
        argv = self._argv(*args)
        exit_code, stdout, stderr = self._runner(argv)
        if exit_code != 0:
            detail = (stderr or stdout or "").strip()[:800]
            hint = ""
            if "NOT_AUTHENTICATED" in detail:
                hint = "Run the google-workspace setup again (the OAuth token is missing or revoked)."
            elif "REFRESH_FAILED" in detail:
                hint = "The Google refresh token was rejected — re-authorize google-workspace."
            elif "Insufficient Permission" in detail:
                hint = "Re-authorize google-workspace including the Sheets scope."
            raise SheetError(
                f"google_api.py exited {exit_code}: {detail or 'no output'}",
                stage=stage,
                hint=hint,
            )
        text = (stdout or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SheetError(
                f"google_api.py returned output that is not JSON: {text[:400]}",
                stage=stage,
            ) from exc

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    def read_rows(self) -> list[Row]:
        data = self._run_json("sheets", "get", self.spreadsheet_id, self.settings.full_range, stage="sheets_read")
        return parse_rows(data, settings=self.settings)

    def find_by_id(self, product_id: str) -> Row | None:
        needle = str(product_id).strip()
        for row in self.read_rows():
            if row.id.strip() == needle:
                return row
        return None

    def require_row(self, product_id: str) -> Row:
        row = self.find_by_id(product_id)
        if row is None:
            raise SheetError(
                f"no row with ID {product_id!r} in {self.settings.sheet_tab}",
                stage="sheets_read",
                hint="Check the Product ID shown in the preview against the sheet's ID column.",
            )
        return row

    def next_eligible(self) -> Row | None:
        """Lowest numeric ID among rows whose Status is exactly the eligible one."""
        eligible = [row for row in self.read_rows() if row.status.strip() == self.settings.eligible_status]
        if not eligible:
            return None
        return min(eligible, key=_sort_key)

    def read_range(self, a1: str) -> list[list[str]]:
        """Read an explicit A1 range (tab included) as strings. Empty → ``[]``.

        Unlike ``read_rows`` this maps nothing — it is how the plugin-owned
        Metrics tab is read, by this client and by ``doctor.py``.
        """
        data = self._run_json("sheets", "get", self.spreadsheet_id, a1, stage="sheets_read")
        values = _extract_values(data)
        return [
            [str(cell) for cell in row]
            for row in values
            if isinstance(row, (list, tuple))
        ]

    # ------------------------------------------------------------------ #
    # writes
    # ------------------------------------------------------------------ #

    def write_fields(self, row_number: int, values: dict[str, str]) -> None:
        """Write one or more named columns on ``row_number``.

        Only the named columns are written. The fields are grouped into
        contiguous runs and each run goes out as its own ``sheets update``, so
        a column the caller did not name is never filled: a publish writes
        ``threads_url`` and ``status`` (F and I) without touching the
        ``Used``/``Testimonial`` cells (G and H) between them.
        """
        columns = self.settings.columns
        requested = sorted(
            ((column_index(columns[name]), name) for name in values if name in columns),
            key=lambda item: item[0],
        )
        if not requested:
            return

        runs: list[list[str]] = []
        previous = -2  # sentinel: any column index differs from previous + 1
        for index, name in requested:
            if index != previous + 1:
                runs.append([])
            runs[-1].append(name)
            previous = index

        for run in runs:
            cells = [values[name] for name in run]
            self._run_json(
                "sheets",
                "update",
                self.spreadsheet_id,
                self.settings.row_range(row_number, *run),
                "--values",
                json.dumps([cells], ensure_ascii=False),
                stage="sheets_write",
            )

    def write_publish_result(self, row_number: int, *, threads_url: str, status: str) -> None:
        self.write_fields(row_number, {"threads_url": threads_url, "status": status})

    def write_status(self, row_number: int, status: str) -> None:
        self.write_fields(row_number, {"status": status})

    def write_experience(self, row_number: int, *, used: str, testimonial: str) -> None:
        """Record the row's experience answer — only the ``Used``/``Testimonial`` cells.

        ``Used=No`` clears the testimony: an answer that the product was never
        used must not leave an old account sitting beside it.
        """
        if not self.settings.experience_configured:
            raise SheetError(
                "the Used/Testimonial columns are not configured, so the answer cannot be stored",
                stage="sheets_setup",
                hint=(
                    "Add `used` and `testimonial` to the columns setting (or use the default "
                    'layout), then try again. Until then every row validates in "none" mode.'
                ),
            )
        self.write_fields(row_number, {"used": used, "testimonial": testimonial})

    # ------------------------------------------------------------------ #
    # the plugin-owned Metrics tab
    # ------------------------------------------------------------------ #

    def append_rows(
        self,
        tab: str,
        rows: Sequence[Sequence[str]],
        *,
        header: Sequence[str] = (),
    ) -> int:
        """Append rows below the last filled row of ``tab``; return the first row written.

        The Metrics tab is plugin-owned and this is its only writer — one weekly
        run, no concurrency — so a read-then-write is safe. The header goes in
        when the tab is empty; the whole block (header included) is one
        contiguous ``sheets update``, so nothing outside the written range is
        ever touched.
        """
        if not rows:
            return 0

        try:
            existing = self.read_range(f"{tab}!A1:A")
        except SheetError as exc:
            raise SheetError(
                f"could not read the {tab!r} tab: {exc.message}",
                stage=exc.stage,
                hint=exc.hint
                or (
                    f"Check that a tab named {tab!r} exists in the spreadsheet — create it "
                    "if not; see docs/google-sheets-setup.md."
                ),
            ) from exc

        filled = sum(1 for row in existing if any(str(cell).strip() for cell in row))
        block: list[list[str]] = []
        if filled == 0 and header:
            block.append([str(cell) for cell in header])
        block.extend([str(cell) for cell in row] for row in rows)

        first_row = filled + 1
        last_row = first_row + len(block) - 1
        width = max(len(row) for row in block)
        padded = [row + [""] * (width - len(row)) for row in block]
        self._run_json(
            "sheets",
            "update",
            self.spreadsheet_id,
            f"{tab}!A{first_row}:{column_letter(width)}{last_row}",
            "--values",
            json.dumps(padded, ensure_ascii=False),
            stage="sheets_write",
        )
        return first_row

    def write_row(self, tab: str, row_number: int, values: Sequence[str]) -> None:
        """Write one row of a plugin-owned tab, and only that row.

        Used to rewrite the Metrics tab's header when it predates the current
        column set — ``append_rows`` writes a header only into an empty tab, so
        an existing header would otherwise stay stale and new rows would land
        under the wrong labels. The range is derived from the values' own
        width, so nothing outside the written cells is touched.
        """
        if not values:
            return
        self._run_json(
            "sheets",
            "update",
            self.spreadsheet_id,
            f"{tab}!A{row_number}:{column_letter(len(values))}{row_number}",
            "--values",
            json.dumps([[str(value) for value in values]], ensure_ascii=False),
            stage="sheets_write",
        )


def _sort_key(row: Row) -> tuple[int, float | str, int]:
    """Stable ordering: numeric IDs first (ascending), then everything else."""
    raw = row.id.strip()
    try:
        return (0, float(raw), row.row_number)
    except ValueError:
        return (1, raw.casefold(), row.row_number)


def parse_rows(data: Any, *, settings: Settings) -> list[Row]:  # noqa: ANN401
    """Turn a ``sheets get`` payload into ``Row`` objects.

    Accepts either the bare 2D array the skill prints or a ``{"values": [...]}``
    envelope. A header row is detected by its ID cell so a sheet without headers
    still works.
    """
    values = _extract_values(data)
    if not values:
        return []

    header_present = str(values[0][0] if values[0] else "").strip().upper() in {
        "ID",
        "PRODUCT ID",
    }
    body = values[1:] if header_present else values
    first_row_number = 2 if header_present else 1

    columns = settings.columns
    ordered_fields = sorted(columns.items(), key=lambda item: column_index(item[1]))

    rows: list[Row] = []
    for offset, cells in enumerate(body):
        cells = list(cells) if isinstance(cells, (list, tuple)) else [cells]
        if not any(str(cell).strip() for cell in cells):
            continue
        mapped: dict[str, str] = {}
        for name, letter in ordered_fields:
            index = column_index(letter) - 1
            mapped[name] = str(cells[index]).strip() if index < len(cells) else ""
        rows.append(Row(row_number=first_row_number + offset, values=mapped))
    return rows


def _extract_values(data: Any) -> list[list[Any]]:  # noqa: ANN401
    if data is None:
        return []
    if isinstance(data, dict):
        for key in ("values", "data", "rows", "result"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return candidate
        return []
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "values" in data[0]:
            return [row.get("values") or [] for row in data]
        return data
    return []
