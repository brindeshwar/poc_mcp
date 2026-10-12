"""One-time setup: create the Atlas Vector Search index used by `search_meetings`.

Usage:  uv run python scripts/create_vector_index.py
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
    )
    try:
        await store.create_vector_index(settings.embedding_dimensions)
        print(
            f"Requested index '{settings.vector_index_name}' on "
            f"{settings.mongo_db}.{settings.chunks_collection}. Atlas builds it in the background; "
            "it is usable once its status is READY in the Atlas UI."
        )
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
