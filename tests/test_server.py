"""End-to-end tests through a real MCP client session (in-memory transport)."""

from mcp.shared.memory import create_connected_server_and_client_session

from meeting_hub.client import unwrap_result
from meeting_hub.server import create_server

TRANSCRIPT = "Eve: We need a rollback plan for the migration.\nDavid: Eve owns it."

EXPECTED_TOOLS = {
    "ingest_meeting",
    "list_meetings",
    "get_meeting",
    "get_latest_meeting",
    "search_meetings",
    "ask_meetings",
    "create_jira_tasks",
}


async def test_tools_are_listed_with_descriptions(service):
    server = create_server(service)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert all(t.description for t in tools)


async def test_ingest_then_ask_over_mcp(service):
    server = create_server(service)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        ingested = await client.call_tool(
            "ingest_meeting",
            {"title": "Eng sync", "transcript": TRANSCRIPT, "held_at": "2025-07-02"},
        )
        assert not ingested.isError
        meeting = unwrap_result(ingested)
        assert meeting["transcript"] is None

        listed = unwrap_result(await client.call_tool("list_meetings", {}))
        assert [m["meeting_id"] for m in listed] == [meeting["meeting_id"]]

        answer = unwrap_result(await client.call_tool("ask_meetings", {"question": "rollback?"}))
        assert answer["sources"][0]["meeting_title"] == "Eng sync"


async def test_errors_come_back_as_readable_tool_errors(service):
    server = create_server(service)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        latest = await client.call_tool("get_latest_meeting", {})
        bad_date = await client.call_tool(
            "ingest_meeting", {"title": "x", "transcript": "y", "held_at": "yesterday"}
        )
    assert latest.isError and "No meetings" in latest.content[0].text
    assert bad_date.isError and "Invalid isoformat" in bad_date.content[0].text
