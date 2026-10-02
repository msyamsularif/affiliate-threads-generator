"""Threads client tests — the reply-chain and retry behaviour, without network."""

from __future__ import annotations

import pytest

from atg_plugin import threads_client
from conftest import happy_path_responses, scripted_transport


def make_client(transport, **kwargs):  # noqa: ANN001, ANN201
    defaults = {"sleep": lambda _seconds: None, "max_retries": 1, "user_id": "user-1"}
    defaults.update(kwargs)
    return threads_client.ThreadsClient("token", transport=transport, **defaults)


class TestNormalizePosts:
    def test_accepts_dicts(self) -> None:
        posts = threads_client.normalize_posts(
            [
                {"text": "a"},
                {"text": "b", "image_url": "https://i"},
                {"text": "c", "video_url": "https://v"},
            ]
        )
        assert posts == [
            {"text": "a", "image_url": "", "video_url": ""},
            {"text": "b", "image_url": "https://i", "video_url": ""},
            {"text": "c", "image_url": "", "video_url": "https://v"},
        ]

    def test_accepts_bare_strings(self) -> None:
        assert threads_client.normalize_posts(["a", "b"]) == [
            {"text": "a", "image_url": "", "video_url": ""},
            {"text": "b", "image_url": "", "video_url": ""},
        ]

    def test_ignores_unsupported_entries(self) -> None:
        assert threads_client.normalize_posts([1, None, {"text": "ok"}]) == [
            {"text": "ok", "image_url": "", "video_url": ""}
        ]

    def test_empty(self) -> None:
        assert threads_client.normalize_posts(None) == []


class TestPublishThread:
    def test_chains_each_post_as_a_reply_to_the_previous(self) -> None:
        transport = scripted_transport(happy_path_responses(posts=3))
        client = make_client(transport)

        result = client.publish_thread(
            [{"text": "one"}, {"text": "two"}, {"text": "three"}], container_wait_seconds=0
        )

        assert result.media_ids == ["media-1", "media-2", "media-3"]
        assert result.root_media_id == "media-1"
        assert result.permalink == "https://www.threads.net/@tester/post/media-1"
        assert result.username == "tester"

        create_calls = [
            call for call in transport.calls if call[0] == "POST" and call[1].endswith("/threads")
        ]
        assert len(create_calls) == 3
        # The root post has no reply_to_id; every later post replies to the previous media id.
        assert "reply_to_id" not in create_calls[0][2]
        assert create_calls[1][2]["reply_to_id"] == "media-1"
        assert create_calls[2][2]["reply_to_id"] == "media-2"

    def test_every_container_is_created_as_text_when_there_is_no_image(self) -> None:
        transport = scripted_transport(happy_path_responses(posts=1))
        make_client(transport).publish_thread([{"text": "one"}], container_wait_seconds=0)
        create = next(call for call in transport.calls if call[1].endswith("/threads"))
        assert create[2]["media_type"] == "TEXT"

    def test_an_image_post_becomes_an_image_container(self) -> None:
        transport = scripted_transport(happy_path_responses(posts=1))
        make_client(transport).publish_thread(
            [{"text": "one", "image_url": "https://cdn.example/i.jpg"}], container_wait_seconds=0
        )
        create = next(call for call in transport.calls if call[1].endswith("/threads"))
        assert create[2]["media_type"] == "IMAGE"
        assert create[2]["image_url"] == "https://cdn.example/i.jpg"

    def test_a_video_post_becomes_a_video_container(self) -> None:
        transport = scripted_transport(happy_path_responses(posts=1))
        make_client(transport).publish_thread(
            [{"text": "one", "video_url": "https://cdn.example/clip.mp4"}],
            container_wait_seconds=0,
        )
        create = next(call for call in transport.calls if call[1].endswith("/threads"))
        assert create[2]["media_type"] == "VIDEO"
        assert create[2]["video_url"] == "https://cdn.example/clip.mp4"
        assert "image_url" not in create[2]

    def test_a_video_container_is_polled_until_it_is_finished(self) -> None:
        transport = scripted_transport(
            [
                (200, {"id": "container-1"}),
                (200, {"id": "container-1", "status": "IN_PROGRESS"}),
                (200, {"id": "container-1", "status": "FINISHED"}),
                (200, {"id": "media-1"}),
                (200, {"permalink": "https://x/y", "username": "tester"}),
            ]
        )
        result = make_client(transport).publish_thread(
            [{"text": "one", "video_url": "https://cdn.example/clip.mp4"}],
            container_wait_seconds=0,
        )
        assert result.media_ids == ["media-1"]

    def test_a_video_container_that_is_still_processing_is_never_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(threads_client, "VIDEO_CONTAINER_TIMEOUT_SECONDS", 0.0)
        transport = scripted_transport(
            [(200, {"id": "container-1"}), (200, {"status": "IN_PROGRESS"})]
        )
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread(
                [{"text": "one", "video_url": "https://cdn.example/clip.mp4"}],
                container_wait_seconds=0,
            )
        assert excinfo.value.stage == "container_status"
        assert "still processing" in str(excinfo.value)
        assert not any(item[1].endswith("/threads_publish") for item in transport.calls)

    def test_a_post_with_both_media_kinds_is_refused_before_any_request(self) -> None:
        transport = scripted_transport([])
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread(
                [
                    {
                        "text": "one",
                        "image_url": "https://cdn.example/i.jpg",
                        "video_url": "https://cdn.example/clip.mp4",
                    }
                ],
                container_wait_seconds=0,
            )
        assert excinfo.value.stage == "create_container[1]"
        assert "both" in str(excinfo.value)
        assert transport.calls == []

    def test_topic_tag_is_applied_to_the_root_post_only(self) -> None:
        transport = scripted_transport(happy_path_responses(posts=2))
        make_client(transport).publish_thread(
            [{"text": "one"}, {"text": "two"}], topic_tag="powerbank", container_wait_seconds=0
        )
        creates = [call for call in transport.calls if call[1].endswith("/threads")]
        assert creates[0][2]["topic_tag"] == "powerbank"
        assert "topic_tag" not in creates[1][2]

    def test_no_link_attachment_is_sent(self) -> None:
        """Threads builds the preview card from the post text itself, and no API
        parameter removes it — so the client does not pretend otherwise. Sending
        `link_attachment` would also count as a second link against the limit."""
        transport = scripted_transport(happy_path_responses(posts=1))
        make_client(transport).publish_thread(
            [{"text": "detail: https://shope.ee/abc123"}], container_wait_seconds=0
        )
        create = next(call for call in transport.calls if call[1].endswith("/threads"))
        assert "link_attachment" not in create[2]

    def test_empty_post_list_is_rejected(self) -> None:
        client = make_client(scripted_transport([]))
        with pytest.raises(threads_client.ThreadsAPIError):
            client.publish_thread([], container_wait_seconds=0)

    def test_a_missing_permalink_does_not_fail_a_live_thread(self) -> None:
        responses = happy_path_responses(posts=1)
        responses[-1] = (200, {"id": "media-1", "username": "tester"})  # no permalink
        result = make_client(scripted_transport(responses)).publish_thread(
            [{"text": "one"}], container_wait_seconds=0
        )
        assert result.media_ids == ["media-1"]
        assert result.permalink == "https://www.threads.net/@tester/post/media-1"


class TestFailureHandling:
    def test_publish_returning_no_id_is_an_error(self) -> None:
        transport = scripted_transport(
            [(200, {"id": "container-1"}), (200, {"status": "FINISHED"}), (200, {})]
        )
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread([{"text": "one"}], container_wait_seconds=0)
        assert excinfo.value.stage == "publish_container"

    def test_container_creation_returning_no_id_is_an_error(self) -> None:
        transport = scripted_transport([(200, {})])
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread([{"text": "one"}], container_wait_seconds=0)
        assert excinfo.value.stage == "create_container[1]"

    def test_container_error_state_raises(self) -> None:
        transport = scripted_transport(
            [
                (200, {"id": "container-1"}),
                (200, {"status": "ERROR", "error_message": "unsupported image"}),
            ]
        )
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread(
                [{"text": "one", "image_url": "https://cdn.example/i.jpg"}], container_wait_seconds=0
            )
        assert "unsupported image" in str(excinfo.value)

    def test_transient_error_is_retried(self) -> None:
        transport = scripted_transport(
            [
                (500, {"error": {"code": 2, "message": "temporary"}}),
                (200, {"id": "container-1"}),
                (200, {"status": "FINISHED"}),
                (200, {"id": "media-1"}),
                (200, {"permalink": "https://x/y", "username": "tester"}),
            ]
        )
        result = make_client(transport).publish_thread([{"text": "one"}], container_wait_seconds=0)
        assert result.media_ids == ["media-1"]

    def test_client_error_is_not_retried(self) -> None:
        transport = scripted_transport(
            [(400, {"error": {"code": 100, "message": "invalid parameter"}})]
        )
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).publish_thread([{"text": "one"}], container_wait_seconds=0)
        assert excinfo.value.code == 100
        assert excinfo.value.retryable is False
        assert len(transport.calls) == 1

    def test_retries_are_bounded(self) -> None:
        transport = scripted_transport(
            [(500, {"error": {"code": 2, "message": "down"}}) for _ in range(5)]
        )
        with pytest.raises(threads_client.ThreadsAPIError):
            make_client(transport, max_retries=2).publish_thread(
                [{"text": "one"}], container_wait_seconds=0
            )
        assert len(transport.calls) == 3  # initial attempt + 2 retries

    def test_network_failure_is_reported_as_an_error(self) -> None:
        transport = scripted_transport([(0, {"error": {"code": -1, "message": "network error: dns"}})])
        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport, max_retries=0).publish_thread(
                [{"text": "one"}], container_wait_seconds=0
            )
        assert "network error" in str(excinfo.value)


class TestPublishReply:
    def test_a_video_link_reply_becomes_a_video_container(self) -> None:
        transport = scripted_transport(
            [
                (200, {"id": "container-1"}),
                (200, {"status": "FINISHED"}),
                (200, {"id": "media-1"}),
            ]
        )
        media_id = make_client(transport).publish_reply(
            text="detail: https://shope.ee/abc123",
            reply_to_id="media-0",
            video_url="https://cdn.example/clip.mp4",
            container_wait_seconds=0,
        )
        assert media_id == "media-1"
        create = next(call for call in transport.calls if call[1].endswith("/threads"))
        assert create[2]["media_type"] == "VIDEO"
        assert create[2]["video_url"] == "https://cdn.example/clip.mp4"
        assert create[2]["reply_to_id"] == "media-0"


class TestClientSetup:
    def test_empty_token_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            threads_client.ThreadsClient("")

    def test_user_id_is_resolved_from_me_when_absent(self) -> None:
        transport = scripted_transport(
            [
                (200, {"id": "resolved-user", "username": "tester"}),
                (200, {"id": "container-1"}),
                (200, {"status": "FINISHED"}),
                (200, {"id": "media-1"}),
                (200, {"permalink": "https://x/y", "username": "tester"}),
            ]
        )
        client = make_client(transport, user_id="")
        client.publish_thread([{"text": "one"}], container_wait_seconds=0)
        assert "/resolved-user/threads" in transport.calls[1][1]


class TestMediaInsights:
    def test_parses_lifetime_values(self) -> None:
        transport = scripted_transport(
            [
                (
                    200,
                    {
                        "data": [
                            {"name": "views", "values": [{"value": 120}]},
                            {"name": "likes", "values": [{"value": 7}]},
                        ]
                    },
                )
            ]
        )

        values = make_client(transport).get_media_insights("media-1")

        assert values == {"views": 120, "likes": 7}
        method, url, _data = transport.calls[0]
        assert method == "GET"
        assert "/media-1/insights" in url
        assert "metric=views%2Clikes%2Creplies%2Creposts%2Cquotes%2Cshares" in url

    def test_a_missing_metric_is_simply_absent(self) -> None:
        transport = scripted_transport(
            [(200, {"data": [{"name": "likes", "values": [{"value": 3}]}]})]
        )

        assert make_client(transport).get_media_insights("m") == {"likes": 3}

    def test_an_empty_payload_is_an_empty_map(self) -> None:
        transport = scripted_transport([(200, {})])

        assert make_client(transport).get_media_insights("m") == {}

    def test_a_non_numeric_point_is_skipped(self) -> None:
        transport = scripted_transport(
            [(200, {"data": [{"name": "views", "values": [{"value": "lots"}]}]})]
        )

        assert make_client(transport).get_media_insights("m") == {}

    def test_a_custom_metric_set_is_requested(self) -> None:
        transport = scripted_transport([(200, {"data": []})])

        make_client(transport).get_media_insights("m", metrics=("likes", "replies"))

        assert "metric=likes%2Creplies" in transport.calls[0][1]

    def test_an_api_error_raises(self) -> None:
        transport = scripted_transport(
            [(400, {"error": {"message": "bad metric", "code": 100}})]
        )

        with pytest.raises(threads_client.ThreadsAPIError) as excinfo:
            make_client(transport).get_media_insights("m")

        assert excinfo.value.status == 400


class TestUserInsights:
    def test_clicks_carries_the_window_and_the_user(self) -> None:
        transport = scripted_transport(
            [
                (
                    200,
                    {
                        "data": [
                            {
                                "name": "clicks",
                                "link_total_values": [
                                    {"value": 11, "link_url": "https://shope.ee/abc"}
                                ],
                            }
                        ]
                    },
                )
            ]
        )

        body = make_client(transport).get_user_insights("clicks", since=100, until=200)

        assert body["data"][0]["name"] == "clicks"
        method, url, _data = transport.calls[0]
        assert method == "GET"
        assert "/user-1/threads_insights" in url
        assert "metric=clicks" in url
        assert "since=100" in url
        assert "until=200" in url

    def test_the_window_is_omitted_when_unset(self) -> None:
        transport = scripted_transport([(200, {"data": []})])

        make_client(transport).get_user_insights("clicks")

        url = transport.calls[0][1]
        assert "since=" not in url
        assert "until=" not in url
