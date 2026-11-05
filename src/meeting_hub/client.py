"""Minimal MCP client used by the Streamlit UI and the seed script."""

import json
from typing import Any

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError


class HubToolError(RuntimeError):
    pass


def connect(server_url: str, token: str | None = None) -> Client:
    """An MCP client for the hub. Sends `Authorization: Bearer <token>` when the hub requires it."""
    if not token:
        return Client(server_url)
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    return Client(streamable_http_client(server_url, http_client=http))


async def call_tool(
    server_url: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    token: str | None = None,
) -> Any:
    """Call one MCP tool over streamable HTTP and return its structured result."""
    try:
        async with connect(server_url, token) as client:
            result = await client.call_tool(name, arguments or {})
    except Exception as exc:
        inner = _single(exc)
        # The SDK reports an HTTP error on the session (e.g. 401) only as this generic MCPError.
        if isinstance(inner, MCPError) and "error response" in str(inner):
            raise HubToolError(
                "The meeting hub refused the session (HTTP error, usually 401 Unauthorized). "
                "If the hub sets MCP_AUTH_TOKEN, pass the same token."
            ) from inner
        raise inner from None
    if result.is_error:
        message = " ".join(getattr(c, "text", "") for c in result.content).strip()
        raise HubToolError(message or f"Tool '{name}' failed")
    return unwrap_result(result)


def _single(exc: BaseException) -> BaseException:
    """anyio task groups wrap a lone failure in an ExceptionGroup; unwrap it."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def unwrap_result(result: Any) -> Any:
    """MCPServer wraps non-object return values (e.g. lists) as {"result": ...}."""
    structured = result.structured_content
    if structured is None:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        try:
            return json.loads(text)
        except ValueError:
            return text
    if set(structured) == {"result"}:
        return structured["result"]
    return structured
