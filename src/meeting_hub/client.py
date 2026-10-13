"""Minimal MCP client used by the Streamlit UI and the seed script."""

import json
from typing import Any

from mcp import Client


class HubToolError(RuntimeError):
    pass


async def call_tool(server_url: str, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call one MCP tool over streamable HTTP and return its structured result."""
    async with Client(server_url) as client:
        result = await client.call_tool(name, arguments or {})
    if result.is_error:
        message = " ".join(getattr(c, "text", "") for c in result.content).strip()
        raise HubToolError(message or f"Tool '{name}' failed")
    return unwrap_result(result)


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
