import logging
import uuid
from datetime import UTC, datetime

from meeting_hub.chunking import chunk_transcript
from meeting_hub.jira_client import JiraServiceClient
from meeting_hub.llm import LLM
from meeting_hub.models import (
    Answer,
    Chunk,
    JiraSyncResult,
    MeetingRecord,
    SearchHit,
)
from meeting_hub.store import MeetingStore

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
MAX_TRANSCRIPT_CHARS = 200_000
NO_RESULTS_ANSWER = "I couldn't find anything about that in the stored meetings."


class MeetingNotFoundError(LookupError):
    pass


class MeetingService:
    """Business logic behind the MCP tools. Has no MCP-specific code so it is easy to test."""

    def __init__(
        self, store: MeetingStore, llm: LLM, jira: JiraServiceClient | None = None
    ) -> None:
        self._store = store
        self._llm = llm
        self._jira = jira

    async def ingest(
        self,
        title: str,
        transcript: str,
        held_at: datetime | None = None,
        meeting_id: str | None = None,
    ) -> MeetingRecord:
        title, transcript = title.strip(), transcript.strip()
        if not title:
            raise ValueError("Meeting title cannot be empty.")
        if not transcript:
            raise ValueError("Transcript cannot be empty.")
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            raise ValueError(f"Transcript is longer than {MAX_TRANSCRIPT_CHARS} characters.")

        held_at = held_at or datetime.now(UTC)
        if held_at.tzinfo is None:
            held_at = held_at.replace(tzinfo=UTC)
        meeting_id = meeting_id or uuid.uuid4().hex

        text_chunks = chunk_transcript(transcript)
        insights = await self._llm.extract_insights(transcript, held_at.date())
        vectors = await self._llm.embed([c.text for c in text_chunks], for_query=False)

        meeting = MeetingRecord(
            meeting_id=meeting_id,
            title=title,
            held_at=held_at,
            transcript=transcript,
            summary=insights.summary,
            action_items=insights.action_items,
            user_stories=insights.user_stories,
        )
        chunks = [
            Chunk(
                meeting_id=meeting_id,
                chunk_index=i,
                text=c.text,
                speakers=c.speakers,
                embedding=vector,
            )
            for i, (c, vector) in enumerate(zip(text_chunks, vectors, strict=True))
        ]
        await self._store.save_meeting(meeting, chunks)
        logger.info("Ingested meeting %s (%r) with %d chunks", meeting_id, title, len(chunks))
        return meeting

    async def list_meetings(self, limit: int = 10) -> list[MeetingRecord]:
        meetings = await self._store.list_meetings(_clamp(limit))
        return [m.model_copy(update={"transcript": None}) for m in meetings]

    async def get_meeting(self, meeting_id: str, include_transcript: bool = False) -> MeetingRecord:
        meeting = await self._store.get_meeting(meeting_id)
        if meeting is None:
            raise MeetingNotFoundError(f"No meeting with id '{meeting_id}'.")
        return meeting if include_transcript else meeting.model_copy(update={"transcript": None})

    async def latest_meeting(self) -> MeetingRecord:
        meetings = await self._store.list_meetings(1)
        if not meetings:
            raise MeetingNotFoundError("No meetings have been stored yet.")
        return meetings[0].model_copy(update={"transcript": None})

    async def search(
        self, query: str, limit: int = 5, meeting_id: str | None = None
    ) -> list[SearchHit]:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty.")
        [vector] = await self._llm.embed([query], for_query=True)
        matches = await self._store.vector_search(vector, _clamp(limit), meeting_id)

        titles: dict[str, str] = {}
        hits = []
        for chunk, score in matches:
            if chunk.meeting_id not in titles:
                meeting = await self._store.get_meeting(chunk.meeting_id)
                titles[chunk.meeting_id] = meeting.title if meeting else "Unknown meeting"
            hits.append(
                SearchHit(
                    meeting_id=chunk.meeting_id,
                    meeting_title=titles[chunk.meeting_id],
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    speakers=chunk.speakers,
                    score=round(score, 4),
                )
            )
        return hits

    async def ask(self, question: str, limit: int = 5, meeting_id: str | None = None) -> Answer:
        hits = await self.search(question, limit, meeting_id)
        if not hits:
            return Answer(answer=NO_RESULTS_ANSWER, sources=[])
        return Answer(answer=await self._llm.answer(question, hits), sources=hits)

    async def send_action_items_to_jira(
        self, meeting_id: str | None = None, dry_run: bool = False
    ) -> JiraSyncResult:
        if self._jira is None:
            raise RuntimeError("The Jira integration is not configured (set JIRA_SERVICE_URL).")
        meeting = await (self.get_meeting(meeting_id) if meeting_id else self.latest_meeting())
        if not meeting.action_items:
            return JiraSyncResult(
                message=f"'{meeting.title}' has no action items to send.", results=[]
            )
        return await self._jira.sync_action_items(
            meeting.action_items,
            meeting_id=meeting.meeting_id,
            meeting_title=meeting.title,
            dry_run=dry_run,
        )

    async def close(self) -> None:
        await self._store.close()
        if self._jira is not None:
            await self._jira.close()


def _clamp(limit: int) -> int:
    return max(1, min(limit, MAX_RESULTS))
