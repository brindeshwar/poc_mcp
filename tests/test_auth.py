import json
import time

import httpx
import pytest

from meeting_hub.auth import HubAuthMiddleware, slack_signature, verify_slack_signature
from meeting_hub.config import Settings
from meeting_hub.server import build_app, create_server

SECRET = "slack-signing-secret"
BODY = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'


async def echo_app(scope, receive, send):
    """Downstream app: proves the body still arrives intact after the middleware read it."""
    message = await receive()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": message.get("body", b"")})


def client(**kwargs) -> httpx.AsyncClient:
    app = HubAuthMiddleware(echo_app, **kwargs)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub")


def signed(body: bytes, secret: str = SECRET, ts: int | None = None) -> dict[str, str]:
    stamp = str(ts if ts is not None else int(time.time()))
    return {
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": slack_signature(secret, stamp, body),
    }


async def test_open_when_nothing_is_configured():
    async with client() as c:
        assert (await c.post("/mcp", content=BODY)).status_code == 200


async def test_bearer_token():
    async with client(token="t0k3n") as c:
        assert (await c.post("/mcp", content=BODY)).status_code == 401
        assert (
            await c.post("/mcp", content=BODY, headers={"Authorization": "Bearer nope"})
        ).status_code == 401
        ok = await c.post("/mcp", content=BODY, headers={"Authorization": "Bearer t0k3n"})
    assert ok.status_code == 200 and ok.content == BODY


async def test_valid_slack_signature_passes_and_body_is_replayed():
    async with client(slack_signing_secret=SECRET) as c:
        response = await c.post("/mcp", content=BODY, headers=signed(BODY))
    assert response.status_code == 200
    assert response.content == BODY


async def test_tampered_body_wrong_secret_and_old_requests_are_rejected():
    async with client(slack_signing_secret=SECRET) as c:
        tampered = await c.post("/mcp", content=BODY + b" ", headers=signed(BODY))
        wrong_secret = await c.post("/mcp", content=BODY, headers=signed(BODY, secret="other"))
        replayed = await c.post(
            "/mcp", content=BODY, headers=signed(BODY, ts=int(time.time()) - 600)
        )
    assert {tampered.status_code, wrong_secret.status_code, replayed.status_code} == {401}
    assert replayed.json() == {"error": "unauthorized"}


async def test_either_method_is_enough_when_both_are_configured():
    async with client(token="t0k3n", slack_signing_secret=SECRET) as c:
        by_token = await c.post("/mcp", content=BODY, headers={"Authorization": "Bearer t0k3n"})
        by_slack = await c.post("/mcp", content=BODY, headers=signed(BODY))
    assert by_token.status_code == by_slack.status_code == 200


def test_signature_helper_matches_slacks_documented_example():
    # Example from Slack's "Verifying requests from Slack" guide.
    secret = "8f742231b10e8888abcd99yyyzzz85a5"  # gitleaks:allow (public example from Slack docs)
    body = (
        b"token=xyzz0WbapA4vBCDEFasx0q6G&team_id=T1DC2JH3J&team_domain=testteamnow&channel_id=G8PSS9T3V"
        b"&channel_name=foobar&user_id=U2CERLKJA&user_name=roadrunner&command=%2Fwebhook-collect&text="
        b"&response_url=https%3A%2F%2Fhooks.slack.com%2Fcommands%2FT1DC2JH3J%2F397700885554%2F96rGlfmibIGlgcZRskXaIFfN"
        b"&trigger_id=398738663015.47445629121.803a0bc887a14d10d2c447fce8b6703c"
    )
    expected = "v0=a2114d57b48eac39b9ad189dd8316235a7b4a8d21a10bd27519666489c69b503"
    assert verify_slack_signature(secret, "1531420618", expected, body, now=1531420618)
    assert not verify_slack_signature(secret, "1531420618", expected, body, now=1531420618 + 3600)
    assert not verify_slack_signature(secret, None, expected, body)


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, google_api_key="k", store_backend="memory", **overrides)


async def test_full_app_requires_auth_and_accepts_a_public_host(service):
    app = build_app(
        settings(mcp_auth_token="t0k3n", mcp_allowed_hosts="abc123.ngrok-free.app"),
        create_server(service),
    )
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    from asgi_lifespan import LifespanManager  # noqa: PLC0415

    async with LifespanManager(app.app) as manager:
        app.app = manager.app
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://abc123.ngrok-free.app"
        ) as c:
            denied = await c.post("/mcp", content=json.dumps(init), headers=headers)
            allowed = await c.post(
                "/mcp",
                content=json.dumps(init),
                headers={**headers, "Authorization": "Bearer t0k3n"},
            )
    assert denied.status_code == 401
    assert allowed.status_code == 200, allowed.text


def test_allowed_hosts_parse_from_comma_separated_env():
    assert settings(mcp_allowed_hosts="a.example.com, b.example.com").mcp_allowed_hosts == [
        "a.example.com",
        "b.example.com",
    ]


@pytest.mark.parametrize("value", ["", None])
def test_no_allowed_hosts_by_default(value):
    kwargs = {} if value is None else {"mcp_allowed_hosts": value}
    assert settings(**kwargs).mcp_allowed_hosts == []
