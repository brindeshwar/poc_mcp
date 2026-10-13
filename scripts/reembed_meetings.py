"""Rebuild chunks and embeddings for stored meetings from their transcripts.

Run this after changing GEMINI_EMBEDDING_MODEL or EMBEDDING_DIMENSIONS (e.g. upgrading from
gemini-embedding-001 to gemini-embedding-2, whose vectors are not compatible). Summaries, action
items and user stories are kept; only the search index data is rebuilt.

Usage:  uv run python scripts/reembed_meetings.py [--meeting-id ID]
"""

import argparse
import asyncio
import logging

from meeting_hub.config import get_settings
from meeting_hub.server import build_service


async def main(meeting_id: str | None) -> None:
    service = build_service(get_settings())
    try:
        count = await service.reembed(meeting_id)
        print(f"Re-embedded {count} meeting(s).")
    finally:
        await service.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting-id")
    asyncio.run(main(parser.parse_args().meeting_id))
