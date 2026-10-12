import logging
from datetime import date, timedelta
from typing import Protocol

from google import genai
from google.genai import types

from meeting_hub.models import MeetingInsights, SearchHit

logger = logging.getLogger(__name__)

_EMBED_BATCH = 100


class LLMError(RuntimeError):
    """The language model call failed or returned something unusable."""


class LLM(Protocol):
    async def embed(self, texts: list[str], *, for_query: bool) -> list[list[float]]: ...

    async def extract_insights(self, transcript: str, meeting_date: date) -> MeetingInsights: ...

    async def answer(self, question: str, hits: list[SearchHit]) -> str: ...


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
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._embedding_model = embedding_model
        self._dimensions = embedding_dimensions

    async def embed(self, texts: list[str], *, for_query: bool) -> list[list[float]]:
        task = "RETRIEVAL_QUERY" if for_query else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), _EMBED_BATCH):
                response = await self._client.aio.models.embed_content(
                    model=self._embedding_model,
                    contents=texts[start : start + _EMBED_BATCH],
                    config=types.EmbedContentConfig(
                        task_type=task, output_dimensionality=self._dimensions
                    ),
                )
                vectors.extend(list(e.values or []) for e in response.embeddings or [])
        except Exception as exc:
            raise LLMError(f"Embedding request failed: {exc}") from exc
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
                    system_instruction=ANSWER_PROMPT, temperature=0.2
                ),
            )
        except Exception as exc:
            raise LLMError(f"Answer generation failed: {exc}") from exc
        if not response.text:
            raise LLMError("The model returned an empty answer")
        return response.text.strip()
