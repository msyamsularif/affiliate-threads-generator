"""Meta Threads Graph API client — standard library only.

Publishing a thread is a chain of container creations and publishes:

    for each post, in order:
        container_id = POST /{user}/threads   (media_type, text, reply_to_id)
        wait until the container is FINISHED
        media_id     = POST /{user}/threads_publish (creation_id)
        reply_to_id  = media_id              <- the next post replies to this one

Nothing in here is model-facing. It runs the same way every time, which is the
whole reason publishing is a Tool and not a Skill instruction.

Only ``urllib`` is used, so a dependency conflict in the host environment can
never take publishing offline. Tests inject a ``transport`` callable.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.threads.net/v1.0"

#: Threads error codes that are worth one more attempt.
RETRYABLE_CODES = {-1, 1, 2, 4, 17, 32, 613}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

Transport = Callable[..., "tuple[int, dict[str, Any]]"]
"""``(method, url, form_data) -> (status, parsed_json)``.

Kept deliberately loose: this alias is evaluated at import time, and the skill's
scripts run under whatever ``python3`` the host provides — on macOS that is often
3.9, where ``dict[str, str] | None`` raises at runtime. Annotations elsewhere in
the plugin are safe because they are never evaluated.
"""


class ThreadsAPIError(RuntimeError):
    """A failure that came back from, or on the way to, the Threads API."""

    def __init__(
        self,
        message: str,
        *,
        stage: str = "",
        status: int | None = None,
        code: int | None = None,
        subcode: int | None = None,
        retryable: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.status = status
        self.code = code
        self.subcode = subcode
        self.retryable = retryable
        self.payload = payload or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage or None,
            "status": self.status,
            "code": self.code,
            "subcode": self.subcode,
            "message": self.message,
        }


@dataclass
class PublishResult:
    media_ids: list[str] = field(default_factory=list)
    permalink: str = ""
    username: str = ""
    container_ids: list[str] = field(default_factory=list)

    @property
    def root_media_id(self) -> str:
        return self.media_ids[0] if self.media_ids else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "media_ids": self.media_ids,
            "root_media_id": self.root_media_id,
            "permalink": self.permalink,
            "username": self.username,
            "posts_published": len(self.media_ids),
        }


def _default_transport(
    method: str,
    url: str,
    data: dict[str, str] | None,
    *,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    body = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, _loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, _loads(raw)
    except urllib.error.URLError as exc:
        return 0, {"error": {"message": f"network error: {exc.reason}", "code": -1}}


def _loads(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": {"message": raw[:500]}}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


class ThreadsClient:
    """Thin, deterministic wrapper over the endpoints publishing needs."""

    def __init__(
        self,
        access_token: str,
        user_id: str = "",
        *,
        base_url: str = GRAPH_BASE,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
        transport: Transport | None = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.user_id = str(user_id or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._transport = transport or (
            lambda method, url, data: _default_transport(method, url, data, timeout=timeout)
        )

    # ------------------------------------------------------------------ #
    # transport
    # ------------------------------------------------------------------ #

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        stage: str = "",
        authenticated: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, str] = {}
        for source in (params, data):
            if source:
                for key, value in source.items():
                    if value is None or value == "":
                        continue
                    payload[key] = str(value)
        if authenticated:
            payload["access_token"] = self.access_token

        url = f"{self.base_url}{path}"
        if method.upper() == "GET" and payload:
            url = f"{url}?{urllib.parse.urlencode(payload)}"

        last_error: ThreadsAPIError | None = None
        for attempt in range(self.max_retries + 1):
            status, body = self._transport(
                method.upper(), url, None if method.upper() == "GET" else payload
            )
            error = body.get("error") if isinstance(body, dict) else None

            if status and 200 <= status < 300 and not error:
                return body

            last_error = self._to_error(body, status=status, stage=stage)
            if not last_error.retryable or attempt >= self.max_retries:
                raise last_error
            delay = self.backoff_seconds * (attempt + 1)
            logger.warning(
                "threads %s %s failed (%s); retrying in %.1fs",
                method,
                path,
                last_error.message,
                delay,
            )
            self._sleep(delay)

        raise last_error or ThreadsAPIError("unknown transport failure", stage=stage)

    @staticmethod
    def _to_error(
        body: dict[str, Any], *, status: int, stage: str
    ) -> ThreadsAPIError:
        error = (body or {}).get("error") or {}
        if not isinstance(error, dict):
            error = {"message": str(error)}
        message = str(error.get("message") or f"HTTP {status} with no error body")
        code = error.get("code")
        subcode = error.get("error_subcode")
        retryable = status in RETRYABLE_STATUS or (
            isinstance(code, int) and code in RETRYABLE_CODES
        )
        return ThreadsAPIError(
            message,
            stage=stage,
            status=status or None,
            code=code if isinstance(code, int) else None,
            subcode=subcode if isinstance(subcode, int) else None,
            retryable=retryable,
            payload=body if isinstance(body, dict) else {},
        )

    def _user_path(self, suffix: str) -> str:
        if not self.user_id:
            self.user_id = str(self.get_me().get("id") or "")
        if not self.user_id:
            raise ThreadsAPIError("could not resolve the Threads user id", stage="identity")
        return f"/{self.user_id}{suffix}"

    # ------------------------------------------------------------------ #
    # identity / health
    # ------------------------------------------------------------------ #

    def get_me(self) -> dict[str, Any]:
        return self._call(
            "GET", "/me", params={"fields": "id,username,threads_profile_picture_url"}, stage="identity"
        )

    def debug_token(self) -> dict[str, Any]:
        """Validity and expiry for the current token (``threads_basic`` scope)."""
        data = self._call(
            "GET",
            "/debug_token",
            params={"input_token": self.access_token},
            stage="token",
        )
        return data.get("data") if isinstance(data.get("data"), dict) else data

    # ------------------------------------------------------------------ #
    # containers
    # ------------------------------------------------------------------ #

    def create_container(
        self,
        *,
        text: str,
        media_type: str = "TEXT",
        image_url: str = "",
        reply_to_id: str = "",
        topic_tag: str = "",
        stage: str = "create_container",
    ) -> str:
        # The API also takes a `link_attachment` URL, and it is deliberately not
        # sent: Threads already builds the preview card from the first URL in a
        # text-only post, and passing the parameter would only count a second
        # link against the per-post limit *and* point the card somewhere the
        # copy does not. There is no parameter that removes the card — see
        # references/publish-contract.md.
        data: dict[str, Any] = {"media_type": media_type.upper(), "text": text}
        if image_url:
            data["image_url"] = image_url
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        if topic_tag:
            data["topic_tag"] = topic_tag

        body = self._call("POST", self._user_path("/threads"), data=data, stage=stage)
        container_id = str(body.get("id") or "")
        if not container_id:
            raise ThreadsAPIError(
                "the API accepted the request but returned no container id",
                stage=stage,
                payload=body,
            )
        return container_id

    def container_status(self, container_id: str) -> dict[str, Any]:
        return self._call(
            "GET",
            f"/{container_id}",
            params={"fields": "id,status,error_message"},
            stage="container_status",
        )

    def wait_for_container(
        self,
        container_id: str,
        *,
        timeout: float = 60.0,
        interval: float = 2.0,
    ) -> str:
        """Block until the container reports ``FINISHED``.

        Text containers are ready almost immediately; media containers can take
        longer, which is why the Threads docs suggest a delay before publishing.
        An unknown status is not treated as a failure — the caller's
        ``container_wait_seconds`` pause covers that case.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        last_status = ""
        while True:
            try:
                body = self.container_status(container_id)
            except ThreadsAPIError as exc:
                logger.debug("container status unavailable for %s: %s", container_id, exc)
                return last_status
            last_status = str(body.get("status") or "")
            if last_status in {"FINISHED", "PUBLISHED"}:
                return last_status
            if last_status in {"ERROR", "EXPIRED"}:
                raise ThreadsAPIError(
                    str(body.get("error_message") or f"container ended in state {last_status}"),
                    stage="container_status",
                )
            if time.monotonic() >= deadline:
                return last_status
            self._sleep(interval)

    def publish_container(self, creation_id: str) -> str:
        body = self._call(
            "POST",
            self._user_path("/threads_publish"),
            data={"creation_id": creation_id},
            stage="publish_container",
        )
        media_id = str(body.get("id") or "")
        if not media_id:
            raise ThreadsAPIError(
                "publish returned no media id — the container may not have finished processing",
                stage="publish_container",
                payload=body,
            )
        return media_id

    def publish_reply(
        self,
        *,
        text: str,
        reply_to_id: str,
        image_url: str = "",
        container_wait_seconds: float = 5.0,
        stage: str = "create_container[reply]",
    ) -> str:
        """Publish one post as a reply to an existing media object.

        This is the second half of a deferred-link publish: the thread is already
        live, and this attaches a post to it — the reply that carries the
        affiliate URL and the disclosure.
        """
        if not reply_to_id:
            raise ThreadsAPIError(
                "a reply needs the media id it replies to", stage="preflight"
            )
        container_id = self.create_container(
            text=text,
            media_type="IMAGE" if image_url else "TEXT",
            image_url=image_url,
            reply_to_id=reply_to_id,
            stage=stage,
        )
        if container_wait_seconds > 0:
            self._sleep(container_wait_seconds)
        self.wait_for_container(container_id)
        return self.publish_container(container_id)

    def get_media(self, media_id: str, fields: str = "id,permalink,username") -> dict[str, Any]:
        return self._call("GET", f"/{media_id}", params={"fields": fields}, stage="media")

    # ------------------------------------------------------------------ #
    # the whole thread
    # ------------------------------------------------------------------ #

    def publish_thread(
        self,
        posts: Sequence[dict[str, Any]],
        *,
        topic_tag: str = "",
        container_wait_seconds: float = 5.0,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> PublishResult:
        """Publish ``posts`` as one reply-chained thread. Raises on any failure."""
        if not posts:
            raise ThreadsAPIError("no posts to publish", stage="preflight")

        result = PublishResult()
        reply_to_id = ""

        for index, post in enumerate(posts):
            text = str(post.get("text") or "")
            image_url = str(post.get("image_url") or "").strip()

            container_id = self.create_container(
                text=text,
                media_type="IMAGE" if image_url else "TEXT",
                image_url=image_url,
                reply_to_id=reply_to_id,
                topic_tag=topic_tag if index == 0 else "",
                stage=f"create_container[{index + 1}]",
            )
            result.container_ids.append(container_id)

            if container_wait_seconds > 0:
                self._sleep(container_wait_seconds)
            self.wait_for_container(container_id)

            media_id = self.publish_container(container_id)
            result.media_ids.append(media_id)
            reply_to_id = media_id

            if on_progress:
                on_progress(index + 1, media_id)
            logger.info("published post %d/%d as media %s", index + 1, len(posts), media_id)

        try:
            media = self.get_media(result.root_media_id)
            result.permalink = str(media.get("permalink") or "")
            result.username = str(media.get("username") or "")
        except ThreadsAPIError as exc:
            # The thread is live; a missing permalink is not worth failing over.
            logger.warning("published, but the permalink lookup failed: %s", exc)

        if not result.permalink and result.username:
            result.permalink = f"https://www.threads.net/@{result.username}/post/{result.root_media_id}"

        return result


def normalize_posts(raw: Iterable[Any]) -> list[dict[str, str]]:
    """Coerce the model-supplied ``posts`` argument into ``[{text, image_url}]``."""
    posts: list[dict[str, str]] = []
    for item in raw or []:
        if isinstance(item, str):
            posts.append({"text": item, "image_url": ""})
        elif isinstance(item, dict):
            posts.append(
                {
                    "text": str(item.get("text") or ""),
                    "image_url": str(item.get("image_url") or "").strip(),
                }
            )
    return posts
