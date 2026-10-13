"""One-time setup: create the Atlas Vector Search and Atlas Search (full-text) indexes.

Hybrid search (SEARCH_MODE=hybrid, the default) needs both; SEARCH_MODE=vector needs only the first.

Usage:  uv run python scripts/create_search_indexes.py
"""

import asyncio

from meeting_hub.config import get_settings
from meeting_hub.store import MongoStore


async def main() -> None:
    settings = get_settings()
    if settings.mongo_uri is None:
        raise SystemExit("MONGO_URI is not set")
    store = MongoStore(
        settings.mongo_uri.get_secret_value(),
        settings.mongo_db,
        meetings_collection=settings.meetings_collection,
        chunks_collection=settings.chunks_collection,
        vector_index_name=settings.vector_index_name,
        text_index_name=settings.text_index_name,
    )
    try:
        names = await store.create_search_indexes(settings.embedding_dimensions)
        print(
            f"Requested indexes {names} on {settings.mongo_db}.{settings.chunks_collection}. "
            "Atlas builds them in the background; they are usable once their status is READY."
        )
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
