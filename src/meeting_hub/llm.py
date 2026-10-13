import asyncio
import logging
from datetime import date, timedelta
from typing import Literal, Protocol

from google import genai
from google.genai import types

from meeting_hub.models import MeetingInsights, SearchHit

logger = logging.getLogger(__name__)

_EMBED_BATCH = 100
_EMBED_CONCURRENCY = 4

ThinkingLevel = Literal["minimal", "low", "medium", "high"]


class LLMError(RuntimeError):
    """The language model call failed or returned something unusable."""


class LLM(Protocol):
    async def embed_documents(self, docs: list[tuple[str, str]]) -> list[list[float]]:
        """Embed (title, text) pairs for storage."""
        ...

    async def embed_query(self, query: str) -> list[float]: ...

    async def extract_insights(self, transcript: str, meeting_date: date) -> MeetingInsights: ...

    async def answer(self, question: str, hits: list[SearchHit]) -> str: ...


# gemini-embedding-2 has no `task_type`; the task is expressed as a text prefix instead.
def document_text(title: str, text: str) -> str:
    return f"title: {title or 'none'} | text: {text}"


def query_text(query: str) -> str:
    return f"task: search result | query: {query}"


INSIGHTS_PROMPT = """You turn meeting transcripts into structured notes.

The meeting took place on {meeting_date} ({weekday}). Resolve relative deadlines against that date:
"end of week" / "by Friday" means {friday}; "next week" means the week starting {next_monday}.
Only include a due date or assignee when the transcript actually states one; otherwise use null.
Action items must be concrete tasks someone committed to, not general discussion.
User stories should capture product needs that came up; return an empty list if there were none.
"""

ANSWER_PROMPT = """You answer questions about past meetings using only the excerpts provided.
If the excerpts do not contain the answer, say you could not find it in the meeting notes.
Mention which meeting (by title) an answer comes from. Be concise."""


class GeminiLLM:
    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        embedding_model: str,
        embedding_dimensions: int,
        extract_thinking: ThinkingLevel = "low",
        answer_thinking: ThinkingLevel = "minimal",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._embedding_model = embedding_model
        self._dimensions = embedding_dimensions
        self._extract_thinking = _thinking(extract_thinking)
        self._answer_thinking = _thinking(answer_thinking)
        self._embed_slots = asyncio.Semaphore(_EMBED_CONCURRENCY)

    async def embed_documents(self, docs: list[tuple[str, str]]) -> list[list[float]]:
        texts = [document_text(title, text) for title, text in docs]
        batches = [texts[i : i + _EMBED_BATCH] for i in range(0, len(texts), _EMBED_BATCH)]
        results = await asyncio.gather(*(self._embed_batch(b) for b in batches))
        return [vector for batch in results for vector in batch]

    async def embed_query(self, query: str) -> list[float]:
        [vector] = await self._embed_batch([query_text(query)])
        return vector

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with self._embed_slots:
            try:
                response = await self._client.aio.models.embed_content(
                    model=self._embedding_model,
                    contents=texts,
                    # gemini-embedding-2 normalizes truncated dimensions itself.
                    config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
                )
            except Exception as exc:
                raise LLMError(f"Embedding request failed: {exc}") from exc
        vectors = [list(e.values or []) for e in response.embeddings or []]
        if len(vectors) != len(texts):
            raise LLMError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
        return vectors

    async def extract_insights(self, transcript: str, meeting_date: date) -> MeetingInsights:
        friday = meeting_date + timedelta(days=(4 - meeting_date.weekday()) % 7)
        next_monday = meeting_date + timedelta(days=7 - meeting_date.weekday())
        system = INSIGHTS_PROMPT.format(
            meeting_date=meeting_date.isoformat(),
            weekday=meeting_date.strftime("%A"),
            friday=friday.isoformat(),
            next_monday=next_monday.isoformat(),
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=f"Transcript:\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    thinking_config=self._extract_thinking,
                    response_mime_type="application/json",
                    response_json_schema=MeetingInsights.model_json_schema(),
                ),
            )
            return MeetingInsights.model_validate_json(response.text or "")
        except Exception as exc:
            raise LLMError(f"Could not extract meeting insights: {exc}") from exc

    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        excerpts = "\n\n".join(
            f"[{i}] Meeting: {hit.meeting_title}\n{hit.text}" for i, hit in enumerate(hits, 1)
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=f"Excerpts:\n{excerpts}\n\nQuestion: {question}",
                config=types.GenerateContentConfig(
                    system_instruction=ANSWER_PROMPT,
                    temperature=0.2,
                    thinking_config=self._answer_thinking,
                ),
            )
        except Exception as exc:
            raise LLMError(f"Answer generation failed: {exc}") from exc
        if not response.text:
            raise LLMError("The model returned an empty answer")
        return response.text.strip()


def _thinking(level: ThinkingLevel) -> types.ThinkingConfig:
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel(level.upper()))
