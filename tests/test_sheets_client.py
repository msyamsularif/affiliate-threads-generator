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
