"""Cell-level write safety for ``SheetClient``.

A write may only ever touch the columns it was asked to write. The regression
pinned here: ``write_fields`` used to collapse its fields into one A1 span and
fill every column in between with an empty string, so a publish (``threads_url``
at F, ``status`` at I) cleared ``Used`` (G) and ``Testimonial`` (H) on its way.

The injected runner applies each update positionally from the range's first
cell — the same trick the integration test's fake ``google_api.py`` uses — so a
reintroduced span write would visibly wipe the simulated row and fail loudly.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from atg_plugin import config, sheets_client

#: One full data row: F and I are what a publish writes; G and H hold the
#: human's experience answer and must survive every other write.
ROW = (
    "7",
    "Wireless Earbuds X",
    "TWS, BT 5.3, IPX4",
    "https://shope.ee/bbb",
    "Audio",
    "",
    "Yes",
    "Dipakai sebulan buat kerja, baterainya masih penuh.",
    "Ready To Generate",
)

URL = "https://www.threads.net/@tester/post/x"


def start_column(a1_range: str) -> str:
    """The column of an A1 range's first cell (``Sheet1!F6:I6`` -> ``F``)."""
    cell = a1_range.split("!", 1)[1].split(":", 1)[0]
    return "".join(char for char in cell if char.isalpha())


class SheetSim:
    """An injected runner that applies each update to a simulated 9-cell row.

    The payload is written positionally from the range's start column, exactly
    like the fake ``google_api.py`` in the integration tests, and every call is
    recorded as ``(a1_range, payload_row)``.
    """

    def __init__(self, row: Sequence[str] = ROW) -> None:
        self.row = list(row)
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, argv: Sequence[str]) -> tuple[int, str, str]:
        a1_range = argv[5]
        payload = json.loads(argv[7])[0]
        self.calls.append((a1_range, payload))
        start = config.column_index(start_column(a1_range))
        for offset, value in enumerate(payload):
            self.row[start - 1 + offset] = value
        return 0, "{}", ""


def build_client(settings: config.Settings, sim: SheetSim) -> sheets_client.SheetClient:
    return sheets_client.SheetClient(settings, runner=sim, google_api_path="/dev/null")


class TestPublishWrite:
    def test_a_publish_writes_only_the_threads_url_and_status(self, settings) -> None:
        sim = SheetSim()

        build_client(settings, sim).write_publish_result(6, threads_url=URL, status="Done")

        # Two single-column updates — never one F:I span with blanks in between.
        assert sim.calls == [
            ("Sheet1!F6:F6", [URL]),
            ("Sheet1!I6:I6", ["Done"]),
        ]
        # The whole row after the write: G and H keep the human's answer.
        assert sim.row == [
            "7",
            "Wireless Earbuds X",
            "TWS, BT 5.3, IPX4",
            "https://shope.ee/bbb",
            "Audio",
            URL,
            "Yes",
            "Dipakai sebulan buat kerja, baterainya masih penuh.",
            "Done",
        ]


class TestStatusWrite:
    def test_a_status_write_touches_only_the_status_cell(self, settings) -> None:
        sim = SheetSim()

        build_client(settings, sim).write_status(6, "Hold")

        assert sim.calls == [("Sheet1!I6:I6", ["Hold"])]
        assert sim.row[6] == "Yes"
        assert sim.row[7] == ROW[7]


class TestExperienceWrite:
    def test_used_no_still_clears_the_testimony(self, settings) -> None:
        """The deliberate clearing: an unused product keeps no old account."""
        sim = SheetSim()

        build_client(settings, sim).write_experience(6, used="No", testimonial="")

        # Both cells are written explicitly, so the testimony is emptied.
        assert sim.calls == [("Sheet1!G6:H6", ["No", ""])]
        assert sim.row[6] == "No"
        assert sim.row[7] == ""
        assert sim.row[:6] == list(ROW[:6])
        assert sim.row[8] == ROW[8]

    def test_used_yes_stores_the_testimony_verbatim(self, settings) -> None:
        sim = SheetSim()
        testimony = "Dipakai 3 bulan, pas buat kerja."

        build_client(settings, sim).write_experience(6, used="Yes", testimonial=testimony)

        assert sim.calls == [("Sheet1!G6:H6", ["Yes", testimony])]
        assert sim.row[6] == "Yes"
        assert sim.row[7] == testimony


class TestWriteFields:
    def test_non_contiguous_fields_are_written_as_separate_runs(self, settings) -> None:
        sim = SheetSim()

        build_client(settings, sim).write_fields(6, {"id": "8", "status": "In Progress"})

        assert sim.calls == [
            ("Sheet1!A6:A6", ["8"]),
            ("Sheet1!I6:I6", ["In Progress"]),
        ]
        assert sim.row[6] == "Yes"
        assert sim.row[7] == ROW[7]

    def test_unknown_fields_write_nothing(self, settings) -> None:
        sim = SheetSim()

        build_client(settings, sim).write_fields(6, {"not_a_column": "x"})

        assert sim.calls == []
        assert sim.row == list(ROW)


class MetricsSim:
    """A runner that simulates a whole plugin-owned tab.

    ``append_rows`` first reads the tab's column A to find the last filled row,
    then writes the block as one update. This fake implements both halves so the
    read-then-write behaves like the real Sheets API, and records every call as
    ``(a1_range, payload_or_None)``.
    """

    def __init__(self, rows: Sequence[Sequence[str]] | None = None) -> None:
        self.rows: list[list[str]] = [list(row) for row in (rows or [])]
        self.calls: list[tuple[str, list[list[str]] | None]] = []

    def _slice(self, a1_range: str) -> list[list[str]]:
        cells = a1_range.split("!", 1)[1]
        first, _, last = cells.partition(":")
        first_col = "".join(char for char in first if char.isalpha())
        last_col = "".join(char for char in (last or first) if char.isalpha())
        start = config.column_index(first_col) - 1
        end = config.column_index(last_col)
        return [list(row[start:end]) for row in self.rows]

    def __call__(self, argv: Sequence[str]) -> tuple[int, str, str]:
        action, a1_range = argv[3], argv[5]
        if action == "get":
            self.calls.append((a1_range, None))
            return 0, json.dumps(self._slice(a1_range)), ""
        payload = json.loads(argv[7])
        self.calls.append((a1_range, payload))
        cells = a1_range.split("!", 1)[1]
        first = cells.split(":", 1)[0]
        start_row = int("".join(char for char in first if char.isdigit()))
        start_col = config.column_index("".join(char for char in first if char.isalpha()))
        for offset, row in enumerate(payload):
            index = start_row - 1 + offset
            while len(self.rows) <= index:
                self.rows.append([])
            target = self.rows[index]
            while len(target) < start_col - 1 + len(row):
                target.append("")
            for col_offset, value in enumerate(row):
                target[start_col - 1 + col_offset] = value
        return 0, "{}", ""


HEADER = (
    "Product ID",
    "Media ID",
    "Checked At",
    "Views",
    "Likes",
    "Replies",
    "Reposts",
    "Quotes",
    "Shares",
    "Link Clicks",
)

#: The 14-column header the weekly job writes once attribution exists.
NEW_HEADER = HEADER + ("Angle Type", "Hook Pattern", "CTA Shape", "Topic")


def metrics_row(product_id: str = "12") -> list[str]:
    return [product_id, "media-1", "2026-10-06T03:00:00+00:00", "10", "1", "", "", "", "", "3"]


class TestMetricsRead:
    def test_read_range_returns_the_slice_as_strings(self, settings) -> None:
        sim = MetricsSim([["a", 1], ["b", 2]])
        assert build_client(settings, sim).read_range("Metrics!A1:B2") == [["a", "1"], ["b", "2"]]


class TestMetricsAppend:
    def test_the_first_write_creates_the_header_and_the_row(self, settings) -> None:
        sim = MetricsSim()

        first = build_client(settings, sim).append_rows("Metrics", [metrics_row()], header=HEADER)

        assert first == 1
        assert sim.calls[0] == ("Metrics!A1:A", None)
        assert sim.calls[1][0] == "Metrics!A1:J2"
        payload = sim.calls[1][1]
        assert payload is not None
        assert payload[0] == list(HEADER)
        assert payload[1][0] == "12"
        assert sim.rows[0] == list(HEADER)
        assert sim.rows[1][9] == "3"

    def test_a_later_write_lands_below_the_last_filled_row(self, settings) -> None:
        sim = MetricsSim([HEADER, metrics_row("11")])

        first = build_client(settings, sim).append_rows("Metrics", [metrics_row("12")], header=HEADER)

        assert first == 3
        assert sim.calls[1][0] == "Metrics!A3:J3"
        assert sim.rows[2][0] == "12"

    def test_no_rows_writes_nothing(self, settings) -> None:
        sim = MetricsSim()

        assert build_client(settings, sim).append_rows("Metrics", []) == 0
        assert sim.calls == []

    def test_a_missing_tab_fails_with_the_create_hint(self, settings) -> None:
        def failing_runner(argv: Sequence[str]) -> tuple[int, str, str]:
            return 1, "", "Unable to parse range: Metrics!A1:A"

        client = build_client(settings, failing_runner)

        with pytest.raises(sheets_client.SheetError) as excinfo:
            client.append_rows("Metrics", [metrics_row()])
        assert "Metrics" in str(excinfo.value)
        assert "create" in (excinfo.value.hint or "").lower()


class TestMetricsWriteRow:
    """``write_row`` is how the weekly job upgrades an older Metrics header."""

    def test_it_writes_exactly_the_row_range(self, settings) -> None:
        sim = MetricsSim([["Product ID", "Media ID"]])

        build_client(settings, sim).write_row("Metrics", 1, NEW_HEADER)

        assert sim.calls == [("Metrics!A1:N1", [list(NEW_HEADER)])]
        assert sim.rows[0] == list(NEW_HEADER)

    def test_empty_values_write_nothing(self, settings) -> None:
        sim = MetricsSim()

        build_client(settings, sim).write_row("Metrics", 1, [])

        assert sim.calls == []
