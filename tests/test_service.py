from datetime import UTC, datetime

import httpx
import pytest

from meeting_hub.jira_client import JiraServiceClient, JiraServiceError
from meeting_hub.models import ActionItem
from meeting_hub.service import NO_RESULTS_ANSWER, MeetingNotFoundError, MeetingService
from meeting_hub.store import InMemoryStore

MIGRATION = (
    "Eve: We need a rollback plan for the database migration.\nDavid: Agreed, staging first."
)
MARKETING = "Alice: TikTok campaigns had great ROI.\nBob: Instagram stories underperformed."


async def test_ingest_stores_insights_and_uses_meeting_date(service, llm):
    held = datetime(2025, 7, 2, 10, tzinfo=UTC)
    meeting = await service.ingest("Eng sync", MIGRATION, held_at=held)

    assert meeting.action_items[0].summary == "Write the rollback plan"
    assert llm.insight_dates == [held.date()]
    stored = await service.get_meeting(meeting.meeting_id, include_transcript=True)
    assert stored.transcript == MIGRATION


async def test_ingest_rejects_empty_input(service):
    with pytest.raises(ValueError, match="Transcript"):
        await service.ingest("Title", "   ")
    with pytest.raises(ValueError, match="title"):
        await service.ingest(" ", MIGRATION)


async def test_naive_datetimes_are_treated_as_utc(service):
    meeting = await service.ingest("Eng sync", MIGRATION, held_at=datetime(2025, 7, 2, 10))
    assert meeting.held_at.tzinfo is UTC


async def test_search_ranks_relevant_meeting_first(service):
    await service.ingest("Marketing", MARKETING)
    eng = await service.ingest("Eng sync", MIGRATION)

    hits = await service.search("rollback plan for the migration", limit=2)

    assert hits[0].meeting_id == eng.meeting_id
    assert hits[0].meeting_title == "Eng sync"
    assert hits[0].score > hits[1].score


async def test_search_can_be_scoped_to_one_meeting(service):
    mkt = await service.ingest("Marketing", MARKETING)
    await service.ingest("Eng sync", MIGRATION)

    hits = await service.search("rollback migration", meeting_id=mkt.meeting_id)

    assert {h.meeting_id for h in hits} == {mkt.meeting_id}


async def test_ask_without_any_meetings_does_not_call_llm(service, llm):
    answer = await service.ask("What did we decide?")
    assert answer.answer == NO_RESULTS_ANSWER
    assert llm.answer_calls == []


async def test_ask_passes_hits_to_llm(service, llm):
    await service.ingest("Eng sync", MIGRATION)
    answer = await service.ask("Who owns the rollback plan?")
    assert answer.answer == "Answer based on 1 excerpt(s)."
    assert answer.sources and llm.answer_calls[0][1] == answer.sources


async def test_latest_meeting_is_by_held_at_not_insert_order(service):
    await service.ingest("Newer", MARKETING, held_at=datetime(2025, 7, 10, tzinfo=UTC))
    await service.ingest("Older", MIGRATION, held_at=datetime(2025, 7, 1, tzinfo=UTC))
    latest = await service.latest_meeting()
    assert latest.title == "Newer"
    assert latest.transcript is None


async def test_latest_meeting_when_empty(service):
    with pytest.raises(MeetingNotFoundError):
        await service.latest_meeting()


async def test_jira_without_configuration_fails_clearly(service):
    await service.ingest("Eng sync", MIGRATION)
    with pytest.raises(RuntimeError, match="not configured"):
        await service.send_action_items_to_jira()


def _jira_service(llm, handler) -> MeetingService:
    client = JiraServiceClient(
        "http://jira.test", api_key="secret", transport=httpx.MockTransport(handler)
    )
    return MeetingService(InMemoryStore(), llm, client)


async def test_jira_sync_sends_action_items_with_api_key(llm):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("X-API-Key")
        seen["body"] = request.read()
        return httpx.Response(
            201,
            json={
                "message": "1 created",
                "results": [{"summary": "Write the rollback plan", "status": "created"}],
            },
        )

    service = _jira_service(llm, handler)
    meeting = await service.ingest("Eng sync", MIGRATION)
    result = await service.send_action_items_to_jira(dry_run=True)

    assert result.results[0].status == "created"
    assert seen["key"] == "secret"
    assert meeting.meeting_id.encode() in seen["body"]
    assert b'"dry_run":true' in seen["body"]


async def test_jira_errors_are_surfaced(llm):
    service = _jira_service(llm, lambda r: httpx.Response(401, json={"detail": "Invalid API key"}))
    await service.ingest("Eng sync", MIGRATION)
    with pytest.raises(JiraServiceError, match="401: Invalid API key"):
        await service.send_action_items_to_jira()


async def test_meeting_without_action_items_skips_jira(llm):
    def fail(_request):
        raise AssertionError("Jira should not be called")

    service = _jira_service(llm, fail)

    async def no_items(transcript, meeting_date):
        insights = await type(llm).extract_insights(llm, transcript, meeting_date)
        return insights.model_copy(update={"action_items": []})

    llm.extract_insights = no_items
    await service.ingest("Chit-chat", MARKETING)
    result = await service.send_action_items_to_jira()
    assert result.results == []


def test_invalid_due_dates_are_dropped():
    assert ActionItem(summary="x", due_date="next Friday").due_date is None
    assert ActionItem(summary="x", due_date="2025-07-04").due_date == "2025-07-04"


def test_long_action_item_summaries_fit_jira_limit():
    item = ActionItem(summary="word " * 100)
    assert len(item.summary) == 255
    assert item.summary.endswith("…")
