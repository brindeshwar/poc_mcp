import asyncio
import hashlib
import re
from datetime import date

import pytest

from meeting_hub.models import ActionItem, MeetingInsights, SearchHit
from meeting_hub.service import MeetingService
from meeting_hub.store import InMemoryStore

DIMENSIONS = 64


def bag_of_words_vector(text: str) -> list[float]:
    """Deterministic stand-in for an embedding: texts sharing words get similar vectors."""
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"[a-z]+", text.lower()):
        if len(word) > 3:
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
    return vector


class FakeLLM:
    def __init__(self) -> None:
        self.answer_calls: list[tuple[str, list[SearchHit]]] = []
        self.insight_dates: list[date] = []
        self.events: list[str] = []  # call order, to check what runs concurrently
        self.embedded_docs: list[tuple[str, str]] = []

    async def embed_documents(self, docs: list[tuple[str, str]]) -> list[list[float]]:
        self.events.append("embed:start")
        await asyncio.sleep(0)  # yield, so a concurrent extraction can start
        self.embedded_docs.extend(docs)
        self.events.append("embed:end")
        return [bag_of_words_vector(text) for _, text in docs]

    async def embed_query(self, query: str) -> list[float]:
        return bag_of_words_vector(query)

    async def extract_insights(self, transcript: str, meeting_date: date) -> MeetingInsights:
        self.events.append("extract:start")
        await asyncio.sleep(0)
        self.events.append("extract:end")
        self.insight_dates.append(meeting_date)
        return MeetingInsights(
            summary=f"Summary of: {transcript[:30]}",
            action_items=[ActionItem(summary="Write the rollback plan", assignee="Eve")],
            user_stories=["As an admin, I want an audit log so that I can trace changes."],
        )

    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        self.answer_calls.append((question, hits))
        return f"Answer based on {len(hits)} excerpt(s)."


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(llm: FakeLLM) -> MeetingService:
    return MeetingService(InMemoryStore(), llm)
