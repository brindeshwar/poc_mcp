from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_validator


class ActionItem(BaseModel):
    """One follow-up task from a meeting. Shared contract with the Jira service."""

    summary: str = Field(description="Short imperative title, e.g. 'Draft the Q3 budget slides'.")
    description: str | None = Field(None, description="Extra detail from the discussion.")
    assignee: str | None = Field(None, description="Name or email of the owner, if one was named.")
    due_date: str | None = Field(None, description="Due date as YYYY-MM-DD, if one was stated.")

    @field_validator("summary")
    @classmethod
    def _fit_jira_summary(cls, value: str) -> str:
        # Jira summaries max out at 255 characters; the Jira service rejects longer ones.
        value = " ".join(value.split())
        return value if len(value) <= 255 else value[:254] + "…"

    @field_validator("due_date")
    @classmethod
    def _iso_date_or_none(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None


class MeetingInsights(BaseModel):
    """What the LLM extracts from a transcript at ingest time."""

    summary: str = Field(description="3-5 sentence summary of decisions and key points.")
    action_items: list[ActionItem] = Field(default_factory=list)
    user_stories: list[str] = Field(
        default_factory=list,
        description="User stories in 'As a <role>, I want <goal> so that <benefit>' form.",
    )


class MeetingRecord(BaseModel):
    meeting_id: str
    title: str
    held_at: datetime
    summary: str
    action_items: list[ActionItem]
    user_stories: list[str]
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transcript: str | None = None


class Chunk(BaseModel):
    meeting_id: str
    # Denormalized so search results need no per-hit meeting lookup.
    meeting_title: str = ""
    chunk_index: int
    text: str
    speakers: list[str]
    embedding: list[float] = Field(default_factory=list, repr=False)


class SearchHit(BaseModel):
    meeting_id: str
    meeting_title: str
    chunk_index: int
    text: str
    speakers: list[str]
    score: float


class Answer(BaseModel):
    answer: str
    sources: list[SearchHit]


class JiraTaskResult(BaseModel):
    summary: str
    status: str
    jira_key: str | None = None
    jira_url: str | None = None
    message: str | None = None


class JiraSyncResult(BaseModel):
    message: str
    results: list[JiraTaskResult]
