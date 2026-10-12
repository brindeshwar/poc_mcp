import asyncio
import logging
import math
from typing import Any, Protocol

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.operations import SearchIndexModel

from meeting_hub.models import Chunk, MeetingRecord

logger = logging.getLogger(__name__)


class MeetingStore(Protocol):
    async def save_meeting(self, meeting: MeetingRecord, chunks: list[Chunk]) -> None: ...

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None: ...

    async def list_meetings(self, limit: int) -> list[MeetingRecord]: ...

    async def vector_search(
        self, vector: list[float], limit: int, meeting_id: str | None = None
    ) -> list[tuple[Chunk, float]]: ...

    async def close(self) -> None: ...


class InMemoryStore:
    """Process-local store with brute-force cosine search. Good for demos and tests."""

    def __init__(self) -> None:
        self._meetings: dict[str, MeetingRecord] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    async def save_meeting(self, meeting: MeetingRecord, chunks: list[Chunk]) -> None:
        self._meetings[meeting.meeting_id] = meeting
        self._chunks[meeting.meeting_id] = chunks

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        return self._meetings.get(meeting_id)

    async def list_meetings(self, limit: int) -> list[MeetingRecord]:
        ordered = sorted(self._meetings.values(), key=lambda m: m.held_at, reverse=True)
        return ordered[:limit]

    async def vector_search(
        self, vector: list[float], limit: int, meeting_id: str | None = None
    ) -> list[tuple[Chunk, float]]:
        candidates = (
            self._chunks.get(meeting_id, [])
            if meeting_id
            else [c for chunks in self._chunks.values() for c in chunks]
        )
        scored = [(c, _cosine(vector, c.embedding)) for c in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    async def close(self) -> None:
        return None


class MongoStore:
    """MongoDB Atlas store. Chunks are searched with an Atlas Vector Search index."""

    def __init__(
        self,
        uri: str,
        db_name: str,
        *,
        meetings_collection: str,
        chunks_collection: str,
        vector_index_name: str,
    ) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri, tz_aware=True)
        db = self._client[db_name]
        self._meetings = db[meetings_collection]
        self._chunks = db[chunks_collection]
        self._vector_index = vector_index_name
        self._indexes_ready = False
        self._index_lock = asyncio.Lock()

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            await self._meetings.create_index("meeting_id", unique=True)
            await self._meetings.create_index([("held_at", DESCENDING)])
            await self._chunks.create_index([("meeting_id", ASCENDING), ("chunk_index", ASCENDING)])
            self._indexes_ready = True

    async def create_vector_index(self, dimensions: int) -> None:
        """Create the Atlas Vector Search index (one-time setup; Atlas builds it asynchronously)."""
        model = SearchIndexModel(
            name=self._vector_index,
            type="vectorSearch",
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": dimensions,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "meeting_id"},
                ]
            },
        )
        await self._chunks.create_search_index(model)

    async def save_meeting(self, meeting: MeetingRecord, chunks: list[Chunk]) -> None:
        await self._ensure_indexes()
        await self._meetings.replace_one(
            {"meeting_id": meeting.meeting_id}, meeting.model_dump(mode="python"), upsert=True
        )
        await self._chunks.delete_many({"meeting_id": meeting.meeting_id})
        if chunks:
            await self._chunks.insert_many([c.model_dump() for c in chunks])

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        doc = await self._meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
        return MeetingRecord.model_validate(doc) if doc else None

    async def list_meetings(self, limit: int) -> list[MeetingRecord]:
        cursor = self._meetings.find({}, {"_id": 0}).sort("held_at", DESCENDING).limit(limit)
        return [MeetingRecord.model_validate(doc) async for doc in cursor]

    async def vector_search(
        self, vector: list[float], limit: int, meeting_id: str | None = None
    ) -> list[tuple[Chunk, float]]:
        stage: dict[str, Any] = {
            "index": self._vector_index,
            "path": "embedding",
            "queryVector": vector,
            "numCandidates": max(limit * 20, 100),
            "limit": limit,
        }
        if meeting_id:
            stage["filter"] = {"meeting_id": meeting_id}
        pipeline = [
            {"$vectorSearch": stage},
            {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
        ]
        cursor = await self._chunks.aggregate(pipeline)
        results = []
        async for doc in cursor:
            score = doc.pop("score")
            results.append((Chunk.model_validate(doc), float(score)))
        return results

    async def close(self) -> None:
        await self._client.close()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
