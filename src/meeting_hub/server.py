import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from meeting_hub.config import Settings, get_settings
from meeting_hub.jira_client import JiraServiceClient, JiraServiceError
from meeting_hub.llm import GeminiLLM, LLMError
from meeting_hub.models import Answer, JiraSyncResult, MeetingRecord, SearchHit
from meeting_hub.service import MeetingNotFoundError, MeetingService
from meeting_hub.store import InMemoryStore, MeetingStore, MongoStore

logger = logging.getLogger(__name__)

INSTRUCTIONS = """ListenLoom meeting hub. Stores meeting transcripts with an AI summary, action items
and user stories, and answers questions about them. Use `ask_meetings` for questions, `search_meetings`
for raw excerpts, `get_latest_meeting` / `list_meetings` to browse, and `create_jira_tasks` only when
the user explicitly asks to create Jira tickets."""

# Errors that should reach the MCP client as a readable tool error rather than a stack trace.
_EXPECTED_ERRORS = (ValueError, MeetingNotFoundError, LLMError, JiraServiceError, RuntimeError)


def create_server(service: MeetingService, *, host: str = "127.0.0.1", port: int = 8001) -> FastMCP:
    mcp = FastMCP("ListenLoom Meeting Hub", instructions=INSTRUCTIONS, host=host, port=port)

    @mcp.tool()
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

    @mcp.tool()
    async def list_meetings(limit: int = 10) -> list[MeetingRecord]:
        """List stored meetings, newest first, with their summaries and action items."""
        return await service.list_meetings(limit)

    @mcp.tool()
    async def get_meeting(meeting_id: str, include_transcript: bool = False) -> MeetingRecord:
        """Get one meeting by id, optionally including the full transcript."""
        try:
            return await service.get_meeting(meeting_id, include_transcript)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def get_latest_meeting() -> MeetingRecord:
        """Get the most recent meeting's summary, action items and user stories."""
        try:
            return await service.latest_meeting()
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def search_meetings(
        query: str, limit: int = 5, meeting_id: str | None = None
    ) -> list[SearchHit]:
        """Semantic search over meeting transcripts. Returns the most relevant excerpts with
        similarity scores. Pass `meeting_id` to search within a single meeting."""
        try:
            return await service.search(query, limit, meeting_id)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def ask_meetings(question: str, limit: int = 5, meeting_id: str | None = None) -> Answer:
        """Answer a natural-language question from the meeting transcripts, citing the excerpts
        used."""
        try:
            return await service.ask(question, limit, meeting_id)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def create_jira_tasks(
        meeting_id: str | None = None, dry_run: bool = False
    ) -> JiraSyncResult:
        """Create or update Jira tasks for a meeting's action items (defaults to the latest
        meeting). Re-running is safe: tasks already created for the same action item are updated,
        not duplicated. Use `dry_run=true` to preview without touching Jira."""
        try:
            return await service.send_action_items_to_jira(meeting_id, dry_run)
        except _EXPECTED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    return mcp


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
        )
    llm = GeminiLLM(
        settings.google_api_key.get_secret_value(),
        model=settings.gemini_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
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
    return MeetingService(store, llm, jira)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    server = create_server(build_service(settings), host=settings.mcp_host, port=settings.mcp_port)
    logger.info(
        "Starting MCP server on http://%s:%d/mcp (store=%s)",
        settings.mcp_host,
        settings.mcp_port,
        settings.store_backend,
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
