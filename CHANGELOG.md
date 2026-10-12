# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-13

Full rewrite. The hub is now the integration point for the Slack bot and the Jira Task Service.

### Added
- MCP tools over Streamable HTTP: `ingest_meeting`, `list_meetings`, `get_meeting`,
  `get_latest_meeting`, `search_meetings`, `ask_meetings`, `create_jira_tasks`.
- Summary, action items (owner, due date resolved against the meeting date) and user stories
  extracted once at ingest and stored.
- `create_jira_tasks` hands action items to the Jira Task Service, with a dry-run option.
- `STORE_BACKEND=memory` to run without MongoDB.
- `scripts/create_vector_index.py` and `scripts/seed_meetings.py`.
- Test suite (unit plus in-memory MCP end-to-end), CI, pre-commit with gitleaks, Dependabot,
  Docker image and a compose file for the whole stack, and contributor and agent documentation.

### Changed
- **BREAKING:** the v1 tool `get_meeting_by_semantic_search` is replaced by `search_meetings` and
  `ask_meetings`.
- **BREAKING:** new collections (`meeting_records`, `meeting_chunks`) and embedding model
  (`gemini-embedding-001`, 768 dims). Recreate the vector index and re-ingest.
- Streamlit UI is now a real MCP client (v1 imported server code directly).
- One database connection per process (v1 created an event loop and connection per query).
- `google-genai` and pymongo's async API replace LangChain, motor and beanie.

### Fixed
- The MCP server never connected to the database when run standalone, so every search returned
  nothing.
- Vector-search errors were hidden by a keyword fallback with a fake score.
- Retrieved speaker and meeting context was built but never sent to the LLM.
- `timestamp` defaulted to the import time for every document.

### Removed
- Unpinned `requirements.txt` and the `mcp==0.1.0` pin; dependencies are now managed with uv
  (`pyproject.toml` + `uv.lock`).

## [0.1.0] - 2025-07-25

- Initial internship proof of concept.

[Unreleased]: https://github.com/brindeshwar/poc_mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/brindeshwar/poc_mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/brindeshwar/poc_mcp/releases/tag/v0.1.0
