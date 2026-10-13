from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: SecretStr
    gemini_model: str = "gemini-3.5-flash-lite"
    # Extraction resolves relative dates, so it gets a little reasoning; answers are grounded
    # summaries of retrieved text and don't need it.
    gemini_thinking_extract: Literal["minimal", "low", "medium", "high"] = "low"
    gemini_thinking_answer: Literal["minimal", "low", "medium", "high"] = "minimal"
    gemini_embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = 768

    # "hybrid" fuses vector and full-text search (catches names, acronyms, ticket IDs);
    # "vector" is semantic only and needs no Atlas Search text index.
    search_mode: Literal["hybrid", "vector"] = "hybrid"

    # "memory" keeps everything in-process (handy for demos); "mongo" uses MongoDB Atlas.
    store_backend: Literal["mongo", "memory"] = "mongo"
    mongo_uri: SecretStr | None = None
    mongo_db: str = "listenloom"
    meetings_collection: str = "meeting_records"
    chunks_collection: str = "meeting_chunks"
    vector_index_name: str = "meeting_chunks_vector_index"
    text_index_name: str = "meeting_chunks_text_index"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001

    # The Jira task service (poc_jira). Leave unset to disable the Jira tool.
    jira_service_url: str | None = "http://127.0.0.1:8000"
    jira_service_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _mongo_needs_uri(self) -> "Settings":
        if self.store_backend == "mongo" and self.mongo_uri is None:
            raise ValueError("MONGO_URI is required when STORE_BACKEND=mongo")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
