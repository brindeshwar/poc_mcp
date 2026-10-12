"""Load two sample meetings into a running hub through its MCP `ingest_meeting` tool.

Usage:  uv run python scripts/seed_meetings.py [--url http://127.0.0.1:8001/mcp]
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from meeting_hub.client import HubToolError, call_tool

MARKETING_SYNC = """\
Alice: Morning everyone. Today is the Q3 marketing strategy, mainly digital ad spend and the new social campaigns. We need to finalise the influencer budget.
Bob: I pulled last quarter's numbers. TikTok had excellent ROI, Instagram stories underperformed. I'd move about 20 percent of the Instagram budget to TikTok.
Charlie: For influencers, micro-influencers beat macro ones on engagement, especially for next month's product launch.
Alice: Agreed. Bob, please put together the budget reallocation proposal by Friday.
Bob: Will do.
Alice: Charlie, can you draft a shortlist of ten micro-influencers for the launch? Next Wednesday is fine.
Charlie: Sure.
Alice: And I'll get legal feedback on the new ad creatives by end of day tomorrow.
Bob: One more thing, customers keep asking for a way to save products they saw in an ad and buy them later.
"""

ENGINEERING_SYNC = """\
David: Welcome to the engineering sync. Main topic is the MongoDB Atlas migration and the microservices deployment schedule. We're targeting next sprint for phase one.
Eve: I'm worried about data integrity during the migration. We need a rollback plan and a full test run in staging before going live.
David: Fair. Eve, can you own the rollback plan? Let's have it by next Tuesday.
Eve: Yes.
Frank: The microservices split will help scalability, but the CI/CD pipelines have to be fully automated first. I'll automate the deployment pipeline for the orders service this sprint.
David: Great. Also, support says admins want an audit log of who changed what in the dashboard.
Frank: I'll write up a ticket for the audit log too.
"""


async def main(url: str) -> None:
    now = datetime.now(UTC)
    samples = [
        ("Q3 marketing strategy", MARKETING_SYNC, now - timedelta(days=3)),
        ("Engineering sync: Atlas migration", ENGINEERING_SYNC, now - timedelta(days=1)),
    ]
    for title, transcript, held_at in samples:
        meeting = await call_tool(
            url,
            "ingest_meeting",
            {"title": title, "transcript": transcript, "held_at": held_at.isoformat()},
        )
        print(f"Ingested '{title}' -> {meeting['meeting_id']}")
        for item in meeting["action_items"]:
            print(f"   - {item['summary']} ({item.get('assignee') or 'unassigned'})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001/mcp")
    try:
        asyncio.run(main(parser.parse_args().url))
    except HubToolError as exc:
        raise SystemExit(f"Seeding failed: {exc}") from None
