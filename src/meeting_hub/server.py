import json
import logging
from datetime import datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from meeting_hub.auth import HubAuthMiddleware
from meeting_hub.config import Settings, get_settings
from meeting_hub.jira_client import JiraServiceClient, JiraServiceError
from meeting_hub.llm import GeminiLLM, LLMError
from meeting_hub.models import Answer, JiraSyncResult, MeetingRecord, SearchHit
from meeting_hub.service import MeetingNotFoundError, MeetingService
from meeting_hub.slack_blocks import jira_blocks, meeting_blocks
from meeting_hub.store import InMemoryStore, MeetingStore, MongoStore

logger = logging.getLogger(__name__)

INSTRUCTIONS = """ListenLoom meeting hub. Stores meeting transcripts with an AI summary, action items
and user stories, and answers questions about them. Use `ask_meetings` for questions, `search_meetings`
for raw excerpts, `get_latest_meeting` / `list_meetings` to browse, and `create_jira_tasks` only when
the user explicitly asks to create Jira tickets."""

# Hints for MCP hosts (e.g. whether to ask the user before calling). Nothing here deletes data.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
INGEST = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
JIRA_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)

# Tools that also return Block Kit for Slackbot's MCP client (in `_meta.slack.blocks`).
BLOCK_KIT = {"slack": {"supportsBlockKit": True}}

# Errors that should reach the MCP client as a readable tool error rather than a stack trace.
_EXPECTED_ERRORS = (ValueError, MeetingNotFoundError, LLMError, JiraServiceError, RuntimeError)


def create_server(service: MeetingService) -> MCPServer:
    mcp = MCPServer("ListenLoom Meeting Hub", instructions=INSTRUCTIONS)

    @mcp.tool(title="Add a meeting", annotations=INGEST)
    async def ingest_meeting(
        title: str, transcript: str, held_at: str | None = None
    ) -> MeetingRecord:
        """Store a meeting transcript. Generates a summary, action items and user stories and
        indexes the transcript for search. `held_at` is an ISO date/time (defaults to now).
        Transcript lines may be prefixed with 'Speaker: '."""
        try:
            when = datetime.fromisoformat(held_at) if held_at else None
            meeting = await service.ingest(title, transcript, held_at=when)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc
        return meeting.model_copy(update={"transcript": None})

    @mcp.tool(title="List meetings", annotations=READ_ONLY)
    async def list_meetings(limit: int = 10) -> list[MeetingRecord]:
        """List stored meetings, newest first, with their summaries and action items."""
        return await service.list_meetings(limit)

    @mcp.tool(title="Get a meeting", annotations=READ_ONLY)
    async def get_meeting(meeting_id: str, include_transcript: bool = False) -> MeetingRecord:
        """Get one meeting by id, optionally including the full transcript."""
        try:
            return await service.get_meeting(meeting_id, include_transcript)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Latest meeting", annotations=READ_ONLY, meta=BLOCK_KIT)
    async def get_latest_meeting() -> Annotated[CallToolResult, MeetingRecord]:
        """Get the most recent meeting's summary, action items and user stories."""
        try:
            meeting = await service.latest_meeting()
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc
        return _with_blocks(meeting, meeting_blocks(meeting))

    @mcp.tool(title="Search meetings", annotations=READ_ONLY)
    async def search_meetings(
        query: str, limit: int = 5, meeting_id: str | None = None
    ) -> list[SearchHit]:
        """Hybrid (semantic + keyword) search over meeting transcripts. Returns the most relevant
        excerpts with relevance scores (rank-fusion scores in hybrid mode). Pass `meeting_id` to
        search within a single meeting."""
        try:
            return await service.search(query, limit, meeting_id)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Ask about meetings", annotations=READ_ONLY)
    async def ask_meetings(question: str, limit: int = 5, meeting_id: str | None = None) -> Answer:
        """Answer a natural-language question from the meeting transcripts, citing the excerpts
        used."""
        try:
            return await service.ask(question, limit, meeting_id)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Create Jira tasks", annotations=JIRA_WRITE, meta=BLOCK_KIT)
    async def create_jira_tasks(
        meeting_id: str | None = None, dry_run: bool = False
    ) -> Annotated[CallToolResult, JiraSyncResult]:
        """Create or update Jira tasks for a meeting's action items (defaults to the latest
        meeting). Re-running is safe: tasks already created for the same action item are updated,
        not duplicated. Use `dry_run=true` to preview without touching Jira."""
        try:
            if meeting_id is None:
                meeting_id = (await service.latest_meeting()).meeting_id
            result = await service.send_action_items_to_jira(meeting_id, dry_run)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc
        return _with_blocks(result, jira_blocks(result, meeting_id, dry_run))

    return mcp


def _with_blocks(model: BaseModel, blocks: list[dict]) -> CallToolResult:
    """Structured result for every client, plus Block Kit that only Slackbot renders."""
    data = model.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
        meta={"slack": {"blocks": blocks}},
    )


def build_service(settings: Settings) -> MeetingService:
    store: MeetingStore
    if settings.store_backend == "memory":
        store = InMemoryStore()
    else:
        assert settings.mongo_uri is not None  # enforced by Settings
        store = MongoStore(
            settings.mongo_uri.get_secret_value(),
            settings.mongo_db,
            meetings_collection=settings.meetings_collection,
            chunks_collection=settings.chunks_collection,
            vector_index_name=settings.vector_index_name,
            text_index_name=settings.text_index_name,
        )
    llm = GeminiLLM(
        settings.google_api_key.get_secret_value(),
        model=settings.gemini_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        extract_thinking=settings.gemini_thinking_extract,
        answer_thinking=settings.gemini_thinking_answer,
    )
    jira = (
        JiraServiceClient(
            settings.jira_service_url,
            api_key=(
                settings.jira_service_api_key.get_secret_value()
                if settings.jira_service_api_key
                else None
            ),
        )
        if settings.jira_service_url
        else None
    )
    return MeetingService(store, llm, jira, search_mode=settings.search_mode)


def build_app(settings: Settings, server: MCPServer):
    """The ASGI app: MCP over Streamable HTTP at /mcp, behind token / Slack-signature auth."""
    security = None
    if settings.mcp_allowed_hosts:
        # A public hostname (e.g. an ngrok URL for Slackbot) must be allowed explicitly, or the
        # DNS-rebinding protection rejects it with 421.
        hosts = settings.mcp_allowed_hosts
        security = TransportSecuritySettings(
            allowed_hosts=[*hosts, *(f"{h}:*" for h in hosts), "127.0.0.1:*", "localhost:*"],
            allowed_origins=[f"https://{h}" for h in hosts],
        )
    app = server.streamable_http_app(host=settings.mcp_host, transport_security=security)
    return HubAuthMiddleware(
        app,
        token=settings.mcp_auth_token.get_secret_value() if settings.mcp_auth_token else None,
        slack_signing_secret=(
            settings.slack_signing_secret.get_secret_value()
            if settings.slack_signing_secret
            else None
        ),
    )


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    app = build_app(settings, create_server(build_service(settings)))
    auth = [
        name
        for name, on in (
            ("token", settings.mcp_auth_token),
            ("slack-signature", settings.slack_signing_secret),
        )
        if on
    ]
    logger.info(
        "Starting MCP server on http://%s:%d/mcp (store=%s, auth=%s)",
        settings.mcp_host,
        settings.mcp_port,
        settings.store_backend,
        "+".join(auth) or "NONE (localhost only!)",
    )
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
