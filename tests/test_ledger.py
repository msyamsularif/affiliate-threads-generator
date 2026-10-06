"""The publish ledger's contract.

The ledger is the only record of what actually went live, so the weekly metrics
fetch reads it for both the media ids and the content shape the writer settled
on. These tests pin that contract: attribution round-trips, and a record written
without it — including one already on disk from before the fields existed —
still loads.
"""

from __future__ import annotations

from atg_plugin import ledger, runtime


def _publish(**extra):  # noqa: ANN003, ANN202
    return ledger.record_published(
        "12",
        media_ids=["media-1"],
        permalink="https://www.threads.net/@you/post/media-1",
        posts_count=1,
        published_at="2026-10-06T03:00:00+00:00",
        **extra,
    )


class TestAttributionMetadata:
    def test_metadata_round_trips(self, ctx) -> None:  # noqa: ANN001
        _publish(
            angle_type="trade_off",
            topic="power bank capacity vs weight",
            hook_pattern="cost_statement",
            cta_shape="kalau penasaran",
            topic_tag="power bank",
        )

        record = ledger.get("12")
        assert record is not None
        assert record["angle_type"] == "trade_off"
        assert record["topic"] == "power bank capacity vs weight"
        assert record["hook_pattern"] == "cost_statement"
        assert record["cta_shape"] == "kalau penasaran"
        assert record["topic_tag"] == "power bank"
        assert ledger.records()[0]["angle_type"] == "trade_off"

    def test_a_record_written_without_metadata_reads_back_empty(self, ctx) -> None:  # noqa: ANN001
        _publish()

        record = ledger.get("12")
        assert record is not None
        assert record["angle_type"] == ""
        assert record["topic"] == ""
        assert record["hook_pattern"] == ""
        assert record["cta_shape"] == ""
        assert record["topic_tag"] == ""

    def test_a_pre_attribution_record_on_disk_still_loads(self, ctx) -> None:  # noqa: ANN001
        # Exactly what an older plugin wrote: no attribution keys at all.
        runtime.state_set(
            "publish_ledger",
            {
                "12": {
                    "product_id": "12",
                    "media_ids": ["media-1"],
                    "permalink": "https://www.threads.net/@you/post/media-1",
                    "posts_count": 1,
                    "published_at": "2026-09-23T03:00:00+00:00",
                    "publish_mode": "single",
                    "sheet_synced": True,
                }
            },
        )

        record = ledger.get("12")
        assert record is not None
        assert record.get("angle_type", "") == ""
        assert record["media_ids"] == ["media-1"]
