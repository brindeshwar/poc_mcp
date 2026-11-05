"""Authentication for the MCP endpoint.

Two ways in, either of which is enough when configured:

- **Bearer token** (`MCP_AUTH_TOKEN`): for our own clients (Slack bot, Streamlit, scripts).
- **Slack request signature** (`SLACK_SIGNING_SECRET`): for Slackbot's MCP client using
  "Slack identity auth". Slack signs every request; we verify it exactly like Slack's Events API
  (`v0:{timestamp}:{body}` HMAC-SHA256), and reject requests older than five minutes.

With neither configured the endpoint is open, which is only appropriate on localhost.
"""

import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MAX_SIGNATURE_AGE = 60 * 5


def slack_signature(signing_secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()


def verify_slack_signature(
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: float | None = None,
) -> bool:
    if not timestamp or not signature:
        return False
    try:
        age = abs((now or time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > MAX_SIGNATURE_AGE:
        return False  # replay protection
    return hmac.compare_digest(slack_signature(signing_secret, timestamp, body), signature)


class HubAuthMiddleware:
    """ASGI middleware guarding every HTTP request to the MCP app."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str | None = None,
        slack_signing_secret: str | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.slack_signing_secret = slack_signing_secret

    @property
    def enabled(self) -> bool:
        return bool(self.token or self.slack_signing_secret)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        if self.token and _bearer_matches(headers.get("authorization"), self.token):
            await self.app(scope, receive, send)
            return

        if self.slack_signing_secret:
            # The signature covers the raw body, so read it now and replay it downstream.
            body, receive = await _buffer_body(receive)
            if verify_slack_signature(
                self.slack_signing_secret,
                headers.get("x-slack-request-timestamp"),
                headers.get("x-slack-signature"),
                body,
            ):
                await self.app(scope, receive, send)
                return

        logger.warning("Rejected unauthenticated %s %s", scope.get("method"), scope.get("path"))
        await _unauthorized(send)


def _bearer_matches(header: str | None, token: str) -> bool:
    if not header or not header.lower().startswith("bearer "):
        return False
    return secrets.compare_digest(header[7:].strip(), token)


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            break
    body = b"".join(chunks)
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()  # e.g. http.disconnect

    return body, replay


async def _unauthorized(send: Send) -> None:
    payload = json.dumps({"error": "unauthorized"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="meeting-hub"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
