# Project Status: Meeting Hub

> Living document. **Every agent or person updates this at the end of a work session** (see
> `AGENTS.md` §6). Newest handoff entry goes on top. Keep it honest and short.

## Health

| Check | State | As of |
|---|---|---|
| Unit + MCP end-to-end tests | ✅ 24 passing | 2026-10-13 |
| Lint / format (ruff) | ✅ clean | 2026-10-13 |
| MCP server over HTTP (memory store) | ✅ verified live | 2026-10-13 |
| Slack bot ↔ hub MCP connection | ✅ verified live | 2026-10-13 |
| Gemini (ingest / ask) live | ⛔ not verified: `GOOGLE_API_KEY` in local `.env` is invalid | 2026-10-13 |
| MongoDB Atlas live | ⛔ not verified: needs new vector index + re-seed | 2026-10-13 |
| Docker image | ⚠️ not built locally (Docker daemon not running); `deploy/docker-compose.yml` config validates; CI `docker` job builds it | 2026-10-13 |

## Current version

`0.2.0` (unreleased; on branch `refactor/v2-connected-system`). See `CHANGELOG.md`.

## Known issues / blockers

1. **Gemini key invalid.** Get a new key from Google AI Studio and put it in `.env`.
2. **Atlas data is from v1** (old `embedding-001` vectors, different collections). Run
   `scripts/create_vector_index.py`, wait for READY, then `scripts/seed_meetings.py`. Old collections
   can be dropped manually.

## Backlog (prioritized)

| # | Item | Notes |
|---|---|---|
| 1 | Live end-to-end run with a valid Gemini key | ingest → ask → `create_jira_tasks` dry run |
| 2 | Auth for the MCP endpoint | today anyone who can reach the port can call tools; add a bearer token or bind only to localhost |
| 3 | Pagination / date filters for `list_meetings` | |
| 4 | Speaker filter in `search_meetings` | `speakers` is already stored per chunk |
| 5 | Delete-meeting tool | needs a confirmation pattern for agents |
| 6 | Atlas integration test job (optional, manual) | against a throwaway cluster, behind a CI secret |

## Decision log

| Date | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 2026-10-13 | Hub is the integration point; Slack and Streamlit are MCP clients | one data owner; new tools reach all clients automatically | Slack importing hub code directly (v1 Streamlit did this) |
| 2026-10-13 | Jira stays a separate HTTP service called by the hub | keeps poc_jira independently usable and testable | merging Jira logic into the hub |
| 2026-10-13 | `google-genai` SDK directly, no LangChain | fewer layers; native structured output and function calling | LangChain (v1) |
| 2026-10-13 | pymongo async API instead of motor + beanie | motor is deprecated; beanie added little | keep motor/beanie |
| 2026-10-13 | Generate insights once at ingest and store them | slash commands are instant and match what goes to Jira | generate on every request |
| 2026-10-13 | `gemini-embedding-001` at 768 dims | keeps v1's index dimension; `embedding-001` is retired | 3072 dims (bigger index, little gain here) |
| 2026-10-13 | No silent fallbacks; errors become MCP tool errors | v1's keyword fallback hid broken config | |
| 2026-10-13 | `InMemoryStore` as a real backend (`STORE_BACKEND=memory`) | demo without Atlas; reference implementation for tests | test-only fake |

## Handoff log

### 2026-10-13: Claude (Opus 5.5) · v2 rebuild + project infrastructure
**Changed**
- Removed the v1 code (`MCP/`, `database/`, `services/`, `requirements.txt`). Rewrote the POC into `src/meeting_hub` (layered: server → service → store/llm/jira_client).
- 7 MCP tools over Streamable HTTP; Streamlit rewritten as a real MCP client; seed and index scripts.
- Added project infrastructure: `AGENTS.md`/`CLAUDE.md`, `docs/`, CI, pre-commit with gitleaks,
  Dependabot, issue and PR templates, CONTRIBUTING, SECURITY, CHANGELOG, LICENSE (MIT),
  Dockerfile, and `deploy/docker-compose.yml` for the three-repo stack.
- `ActionItem.summary` is now capped at 255 chars to match the Jira service's limit (contract bug
  found while writing `INTEGRATION.md`).

**Verified:** pytest (24), ruff, live MCP over HTTP with the memory store, pre-commit (all hooks incl. gitleaks),
Slack bot client against the live hub, error paths (no meetings, Jira unconfigured, hub down).

**Not verified:** anything needing Gemini (key invalid) or Atlas; Docker image build (daemon was off).

**Next agent:** Backlog #1 once the user provides a key.
