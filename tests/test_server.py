"""End-to-end tests through a real MCP client connected to the server in-process."""

import json

from mcp import Client

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
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert all(t.description for t in tools)


async def test_ingest_then_ask_over_mcp(service):
    server = create_server(service)
    async with Client(server) as client:
        ingested = await client.call_tool(
            "ingest_meeting",
            {"title": "Eng sync", "transcript": TRANSCRIPT, "held_at": "2025-07-02"},
        )
        assert not ingested.is_error
        meeting = unwrap_result(ingested)
        assert meeting["transcript"] is None

        listed = unwrap_result(await client.call_tool("list_meetings", {}))
        assert [m["meeting_id"] for m in listed] == [meeting["meeting_id"]]

        answer = unwrap_result(await client.call_tool("ask_meetings", {"question": "rollback?"}))
        assert answer["sources"][0]["meeting_title"] == "Eng sync"


async def test_errors_come_back_as_readable_tool_errors(service):
    server = create_server(service)
    async with Client(server) as client:
        latest = await client.call_tool("get_latest_meeting", {})
        bad_date = await client.call_tool(
            "ingest_meeting", {"title": "x", "transcript": "y", "held_at": "yesterday"}
        )
    assert latest.is_error and "No meetings" in latest.content[0].text
    assert bad_date.is_error and "Invalid isoformat" in bad_date.content[0].text


async def test_tools_carry_annotations(service):
    server = create_server(service)
    async with Client(server) as client:
        tools = {t.name: t.annotations for t in (await client.list_tools()).tools}
    read_only = {
        "list_meetings",
        "get_meeting",
        "get_latest_meeting",
        "search_meetings",
        "ask_meetings",
    }
    assert all(tools[name].read_only_hint for name in read_only)
    assert tools["ingest_meeting"].read_only_hint is False
    jira = tools["create_jira_tasks"]
    assert (jira.read_only_hint, jira.idempotent_hint, jira.open_world_hint) == (False, True, True)
    assert not any(a.destructive_hint for a in tools.values())


async def test_tools_have_human_readable_titles(service):
    async with Client(create_server(service)) as client:
        tools = (await client.list_tools()).tools
    assert all(t.title and t.title[0].isupper() for t in tools), [t.title for t in tools]


async def test_block_kit_tools_are_declared_for_slackbot(service):
    async with Client(create_server(service)) as client:
        meta = {t.name: (t.meta or {}) for t in (await client.list_tools()).tools}
    assert meta["get_latest_meeting"]["slack"]["supportsBlockKit"] is True
    assert meta["create_jira_tasks"]["slack"]["supportsBlockKit"] is True


async def test_latest_meeting_returns_structured_data_and_slack_blocks(service):
    await service.ingest("Eng sync", TRANSCRIPT)
    async with Client(create_server(service)) as client:
        result = await client.call_tool("get_latest_meeting", {})
    assert unwrap_result(result)["title"] == "Eng sync"  # other clients see the same data as before
    blocks = result.meta["slack"]["blocks"]
    button = next(b for b in blocks if b["type"] == "actions")["elements"][0]
    assert button["action_id"] == "tool:create_jira_tasks"
    assert json.loads(button["value"])["dry_run"] is True  # a preview first, never a write
