import asyncio
import logging
import math
import re
from collections import Counter
from typing import Any, Literal, Protocol

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from meeting_hub.models import Chunk, MeetingRecord

logger = logging.getLogger(__name__)

SearchMode = Literal["hybrid", "vector"]
RRF_K = 60  # standard reciprocal-rank-fusion constant (also Atlas $rankFusion's default)


class MeetingStore(Protocol):
    async def save_meeting(self, meeting: MeetingRecord, chunks: list[Chunk]) -> None: ...

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None: ...

    async def list_meetings(self, limit: int | None) -> list[MeetingRecord]:
        """Newest first; `None` means all (used by re-embedding)."""
        ...

    async def search(
        self,
        query: str,
        vector: list[float],
        limit: int,
        meeting_id: str | None = None,
        mode: SearchMode = "hybrid",
    ) -> list[tuple[Chunk, float]]: ...

    async def close(self) -> None: ...


class InMemoryStore:
    """Process-local store for demos and tests. Hybrid search mirrors Atlas: reciprocal-rank
    fusion of a cosine ranking and a keyword ranking."""

    def __init__(self) -> None:
        self._meetings: dict[str, MeetingRecord] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    async def save_meeting(self, meeting: MeetingRecord, chunks: list[Chunk]) -> None:
        self._meetings[meeting.meeting_id] = meeting
        self._chunks[meeting.meeting_id] = chunks

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        return self._meetings.get(meeting_id)

    async def list_meetings(self, limit: int | None) -> list[MeetingRecord]:
        ordered = sorted(self._meetings.values(), key=lambda m: m.held_at, reverse=True)
        return ordered if limit is None else ordered[:limit]

    async def search(
        self,
        query: str,
        vector: list[float],
        limit: int,
        meeting_id: str | None = None,
        mode: SearchMode = "hybrid",
    ) -> list[tuple[Chunk, float]]:
        candidates = (
            self._chunks.get(meeting_id, [])
            if meeting_id
            else [c for chunks in self._chunks.values() for c in chunks]
        )
        by_vector = sorted(candidates, key=lambda c: _cosine(vector, c.embedding), reverse=True)
        if mode == "vector":
            return [(c, _cosine(vector, c.embedding)) for c in by_vector[:limit]]

        by_keyword = _keyword_ranking(query, candidates)
        fused: dict[int, float] = {}
        for ranking in (by_vector, by_keyword):
            for rank, chunk in enumerate(ranking, 1):
                fused[id(chunk)] = fused.get(id(chunk), 0.0) + 1 / (RRF_K + rank)
        lookup = {id(c): c for c in candidates}
        best = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [(lookup[key], score) for key, score in best]

    async def close(self) -> None:
        return None


class MongoStore:
    """MongoDB Atlas store. Hybrid search = $rankFusion over Atlas Vector Search and Atlas Search."""

    def __init__(
        self,
        uri: str,
        db_name: str,
        *,
        meetings_collection: str,
        chunks_collection: str,
        vector_index_name: str,
        text_index_name: str,
    ) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri, tz_aware=True)
        db = self._client[db_name]
        self._meetings = db[meetings_collection]
        self._chunks = db[chunks_collection]
        self._vector_index = vector_index_name
        self._text_index = text_index_name
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

    async def create_search_indexes(self, dimensions: int) -> list[str]:
        """Create the vector and full-text search indexes (one-time; Atlas builds them async)."""
        models = [
            SearchIndexModel(
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
            ),
            SearchIndexModel(
                name=self._text_index,
                type="search",
                definition={
                    "mappings": {
                        "dynamic": False,
                        "fields": {
                            "text": {"type": "string", "analyzer": "lucene.english"},
                            "meeting_title": {"type": "string"},
                            "meeting_id": {"type": "token"},
                        },
                    }
                },
            ),
        ]
        return await self._chunks.create_search_indexes(models)

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

    async def list_meetings(self, limit: int | None) -> list[MeetingRecord]:
        cursor = self._meetings.find({}, {"_id": 0}).sort("held_at", DESCENDING)
        if limit is not None:
            cursor = cursor.limit(limit)
        return [MeetingRecord.model_validate(doc) async for doc in cursor]

    async def search(
        self,
        query: str,
        vector: list[float],
        limit: int,
        meeting_id: str | None = None,
        mode: SearchMode = "hybrid",
    ) -> list[tuple[Chunk, float]]:
        # Each sub-pipeline over-fetches so fusion has enough overlap to work with.
        per_pipeline = limit * 4
        vector_stage: dict[str, Any] = {
            "index": self._vector_index,
            "path": "embedding",
            "queryVector": vector,
            "numCandidates": max(per_pipeline * 20, 100),
            "limit": per_pipeline if mode == "hybrid" else limit,
        }
        if meeting_id:
            vector_stage["filter"] = {"meeting_id": meeting_id}

        if mode == "vector":
            pipeline: list[dict[str, Any]] = [
                {"$vectorSearch": vector_stage},
                {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
            ]
        else:
            text_query: dict[str, Any] = {
                "must": [{"text": {"query": query, "path": "text", "fuzzy": {"maxEdits": 1}}}]
            }
            if meeting_id:
                text_query["filter"] = [{"equals": {"path": "meeting_id", "value": meeting_id}}]
            pipeline = [
                {
                    "$rankFusion": {
                        "input": {
                            "pipelines": {
                                "vector": [{"$vectorSearch": vector_stage}],
                                "text": [
                                    {
                                        "$search": {
                                            "index": self._text_index,
                                            "compound": text_query,
                                        }
                                    },
                                    {"$limit": per_pipeline},
                                ],
                            }
                        }
                    }
                },
                {"$limit": limit},
                {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "score"}}},
            ]

        try:
            cursor = await self._chunks.aggregate(pipeline)
            results = []
            async for doc in cursor:
                score = doc.pop("score")
                results.append((Chunk.model_validate(doc), float(score)))
        except OperationFailure as exc:
            raise RuntimeError(
                f"Search failed ({exc.details.get('errmsg', exc) if exc.details else exc}). "
                "Run scripts/create_search_indexes.py and wait until both indexes are READY, "
                "or set SEARCH_MODE=vector."
            ) from exc
        return results

    async def close(self) -> None:
        await self._client.close()


_WORD = re.compile(r"[a-z0-9]+")
# Lucene's English stopword list, as used by the Atlas Search `lucene.english` analyzer, so the
# in-memory keyword ranking matches what Atlas would do.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "if",
        "in",
        "into",
        "is",
        "it",
        "no",
        "not",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "will",
        "with",
    ]
)


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def _keyword_ranking(query: str, chunks: list[Chunk]) -> list[Chunk]:
    """Chunks containing query terms, ranked by IDF-weighted term frequency (a small BM25 cousin)."""
    terms = set(_tokens(query))
    if not terms or not chunks:
        return []
    counts = [Counter(_tokens(c.text)) for c in chunks]
    df = {t: sum(1 for c in counts if t in c) for t in terms}
    n = len(chunks)
    scored = []
    for chunk, count in zip(chunks, counts, strict=True):
        score = sum((1 + math.log(count[t])) * math.log(1 + n / df[t]) for t in terms if count[t])
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
