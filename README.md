# ListenLoom Meeting Hub (MCP server)

[![CI](https://github.com/brindeshwar/poc_mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/brindeshwar/poc_mcp/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that is the hub for three connected projects. It
stores meeting transcripts, generates a summary, action items and user stories for each one, answers
questions with semantic search (RAG), and hands action items to Jira.

```
           ┌──────────────── Meeting hub (this repo, MCP over HTTP) ────────────────┐
Slack bot ─┤  ingest_meeting      list_meetings     get_meeting    get_latest_meeting │── MongoDB Atlas
Streamlit ─┤  search_meetings     ask_meetings      create_jira_tasks ────────────────┼─► Jira Task Service ─► Jira
Any MCP   ─┘                                                                          │   (poc_jira)
client     └──────────────────────────────────────────────────────────────────────────┘
```

- [poc_slack](https://github.com/brindeshwar/poc_slack): Slack bot. Slash commands and a Gemini agent
  that calls these tools.
- `poc_jira`: FastAPI service that creates or updates Jira tasks, without duplicates.
- `streamlit_app.py` (here): web UI. It is a real MCP client too, not a shortcut into the code.

Because it is plain MCP, you can also plug it into Claude Desktop, Claude Code or an IDE.

## Tools

| Tool | What it does |
|---|---|
| `ingest_meeting(title, transcript, held_at?)` | Chunks and embeds the transcript; extracts summary, action items (owner, due date resolved against the meeting date) and user stories |
| `list_meetings(limit)` / `get_meeting(id)` / `get_latest_meeting()` | Browse stored meetings |
| `search_meetings(query, limit, meeting_id?)` | Vector search, returns excerpts with scores |
| `ask_meetings(question, limit, meeting_id?)` | RAG answer with cited sources |
| `create_jira_tasks(meeting_id?, dry_run?)` | Sends a meeting's action items to the Jira service; safe to re-run |

Errors (bad input, unknown meeting, LLM or Jira failures) come back as readable MCP tool errors. Nothing
is silently swallowed or replaced with fallback results.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
cp .env.example .env            # set GOOGLE_API_KEY (+ MONGO_URI for Atlas)
uv sync
uv run meeting-hub              # MCP endpoint at http://127.0.0.1:8001/mcp
uv run python scripts/seed_meetings.py    # two sample meetings, through the MCP tools
uv run streamlit run streamlit_app.py     # web UI
```

**No Atlas account?** Set `STORE_BACKEND=memory` to keep everything in-process. Data is lost on
restart, but the whole stack works.

**Atlas setup (once):** create the vector index with `uv run python scripts/create_vector_index.py`,
then wait until Atlas shows it as READY. It indexes `embedding` (768-dim, cosine) and `meeting_id`
as a filter.

**Inspect with the MCP Inspector:** `npx @modelcontextprotocol/inspector`, then connect to
`http://127.0.0.1:8001/mcp` (Streamable HTTP).

## Tests

```bash
uv run pytest       # fake LLM + in-memory store; includes end-to-end MCP client/server tests
uv run ruff check .
```

## Design notes

- **Layers:** `server.py` (MCP tools only) → `service.py` (business logic, no MCP code) →
  `store.py` (`MongoStore` / `InMemoryStore`) and `llm.py` (`GeminiLLM`). Each layer has a small
  protocol, so tests swap in fakes.
- **One database connection** for the process, made lazily. v1 opened a new event loop and connection
  per query.
- **Insights are generated once at ingest** and stored, so Slack slash commands are instant and
  consistent with what gets sent to Jira.
- **Chunking** keeps speaker turns together (about 800 characters per chunk) and records which
  speakers appear in each chunk.

## Layout

```
src/meeting_hub/
  server.py      FastMCP server and tool definitions; `main()` entry point
  service.py     ingest / search / ask / Jira hand-off
  store.py       MongoDB Atlas + in-memory stores
  llm.py         Gemini embeddings, structured extraction, answers
  chunking.py    transcript parsing and chunking
  jira_client.py HTTP client for the Jira Task Service
  client.py      small MCP client used by Streamlit and the seed script
  models.py, config.py
streamlit_app.py
scripts/         seed_meetings.py, create_vector_index.py
```

## Docker

```bash
docker compose -f deploy/docker-compose.yml up --build                    # hub + Streamlit + Jira service
docker compose -f deploy/docker-compose.yml --profile slack up --build    # + Slack bot
```

The compose file expects `poc_slack` and `poc_jira` as sibling folders, each with its own `.env`.

## Documentation

| Doc | For |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules and commands for coding agents and contributors (`CLAUDE.md` imports it) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, data model, flows, how to extend |
| [`docs/INTEGRATION.md`](docs/INTEGRATION.md) | Cross-repo contract: tools, `/tasks` API, shared schemas, wiring |
| [`docs/STATUS.md`](docs/STATUS.md) | Current health, known issues, backlog, decisions, handoff log |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md) · [`CHANGELOG.md`](CHANGELOG.md) | Process |

## License

[MIT](LICENSE) © Brindeshwar Sharma
