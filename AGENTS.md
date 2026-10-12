# AGENTS.md: ListenLoom Meeting Hub

Instructions for **any** coding agent (Claude Code, Codex, Cursor, Copilot, Gemini CLI, Aider, …) and
for humans. This file is the source of truth for how to work in this repo. Tool-specific files
(`CLAUDE.md`, etc.) only add to it.

## 1. What this repo is

The **hub** of a three-repo system. It is an MCP server that stores meeting transcripts, extracts
summaries, action items and user stories with Gemini, answers questions with vector search, and
sends action items to Jira.

```
poc_slack (Slack bot) ──MCP──┐
streamlit_app.py      ──MCP──┼──► poc_mcp (THIS REPO) ──► MongoDB Atlas | in-memory
any MCP client        ──MCP──┘          └──HTTP POST /tasks──► poc_jira (Jira Task Service) ──► Jira Cloud
```

| Repo | Local path (sibling folders) | Role |
|---|---|---|
| `poc_mcp` | `../poc_mcp` | MCP hub (this repo). **Owns the integration contract.** |
| `poc_slack` | `../poc_slack` | Slack bot; MCP client |
| `poc_jira` | `../poc_jira/jira_task_creator` | Jira Task Service; called by the hub over HTTP |

Read next, as needed:
- `docs/ARCHITECTURE.md`: layers, data model, request flows, how to extend.
- `docs/INTEGRATION.md`: **the cross-repo contract** (tool signatures, HTTP API, shared schemas,
  ports, env wiring).
- `docs/STATUS.md`: current state, known issues, backlog, decision log, **handoff log**.

## 2. Commands

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+. Run everything from the repo root.

| Task | Command |
|---|---|
| Install / update env | `uv sync` |
| Run MCP server | `uv run meeting-hub` (serves `http://127.0.0.1:8001/mcp`) |
| Run without a database | `STORE_BACKEND=memory uv run meeting-hub` |
| Web UI | `uv run streamlit run streamlit_app.py` |
| Seed sample meetings | `uv run python scripts/seed_meetings.py` (server must be running) |
| Tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| All pre-commit hooks | `uv run pre-commit run --all-files` |
| Whole stack in Docker | `docker compose -f deploy/docker-compose.yml up --build` |

**Before you say a change is done:** `uv run ruff format . && uv run ruff check . && uv run pytest`
must all pass.

## 3. Repo map

```
src/meeting_hub/
  server.py       MCP tool definitions only (thin). create_server(service), build_service(settings), main()
  service.py      MeetingService: all business logic. Must NOT import mcp.
  store.py        MeetingStore protocol + MongoStore (Atlas Vector Search) + InMemoryStore
  llm.py          LLM protocol + GeminiLLM (embeddings, structured extraction, answers)
  chunking.py     transcript → utterances → ~800-char chunks (pure functions)
  jira_client.py  JiraServiceClient (httpx) → poc_jira POST /tasks
  client.py       tiny MCP client (Streamlit + seed script)
  models.py       Pydantic models. ActionItem / JiraSyncResult are part of the cross-repo contract
  config.py       Settings (pydantic-settings). The ONLY place env vars are read
streamlit_app.py  UI; talks to the server through MCP only
scripts/          seed_meetings.py, create_vector_index.py
tests/            conftest.py (FakeLLM, fixtures), unit + in-memory MCP end-to-end tests
deploy/           docker-compose.yml for the whole three-repo stack
```

## 4. Rules

**Architecture**
- Keep the layering: `server.py` → `service.py` → (`store.py`, `llm.py`, `jira_client.py`).
  New logic goes in `service.py`; MCP tools only parse input, call the service, and map expected
  errors to `ToolError`.
- Depend on protocols (`MeetingStore`, `LLM`), not concrete classes, so tests can use fakes.
- Never swallow errors or return fake "fallback" results. Raise a clear exception. Expected failures
  become readable MCP tool errors.
- Read configuration only through `config.Settings`. Never call `os.getenv` elsewhere.
- Use `logging`, never `print` (scripts excepted).

**Contract (cross-repo)**
- Tool names, parameters and return shapes, `ActionItem`, and the `/tasks` payload are a **public
  contract** used by `poc_slack` and `poc_jira`. Changing them is a breaking change. You must
  1. update `docs/INTEGRATION.md`,
  2. add a `CHANGELOG.md` entry under **Changed/Removed** marked **BREAKING**,
  3. update or flag the consumer repos (add an item to `docs/STATUS.md` → Backlog if you can't).
- Adding a new tool or optional parameter is not breaking; still document it in `INTEGRATION.md`.

**Data**
- Embedding model and dimensions (`gemini-embedding-001`, 768) must match the Atlas index. Changing
  either means recreating the index and re-ingesting. Record it in the decision log.

**Tests**
- No network in tests: no real Gemini, MongoDB, Jira or HTTP. Use `FakeLLM`, `InMemoryStore`, and
  `httpx.MockTransport`.
- Every bug fix comes with a test that fails without the fix.
- MCP-level behaviour is tested via `mcp.shared.memory.create_connected_server_and_client_session`.

**Security**
- Never commit `.env`, tokens, keys, or connection strings. `.env.example` holds names only.
  `gitleaks` runs in pre-commit and CI.
- Never paste secrets into docs, logs, tests or commit messages.

**Style**
- Python 3.12+, type hints everywhere, Pydantic v2 models for data crossing a boundary.
- Ruff (lint + format, line length 100) is the style authority. Match the surrounding code's comment
  density. Comments explain *why*, not *what*.

## 5. Workflow

- **Branches:** `feat/…`, `fix/…`, `docs/…`, `chore/…`, `refactor/…`, `ci/…` from `main`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org), e.g.
  `feat(server): add list_speakers tool`, `fix(store): filter vector search by meeting`.
- **PRs:** fill in `.github/PULL_REQUEST_TEMPLATE.md`. CI (lint, format, tests on 3.12 and 3.13,
  secret scan) must be green.
- **Changelog:** add user-visible changes under `## [Unreleased]` in `CHANGELOG.md`.
- **Versioning:** SemVer in `pyproject.toml`. Bump the version when releasing, not per PR.

## 6. Handoff protocol (multi-agent)

Several different agents and people work on these repos. To keep context from getting lost:

1. **Start of session:** read `docs/STATUS.md` (Known issues, Backlog, latest Handoff entries).
2. **During:** if you make a design decision someone could reasonably question, add a row to the
   Decision log in `docs/STATUS.md`.
3. **End of session:** add a dated entry at the top of the Handoff log in `docs/STATUS.md`:
   what changed, what you verified (and how), what is unfinished, what the next agent should do.
   Update the Health table and Backlog to match reality.
4. Be honest about verification: "tests pass" ≠ "verified live against Gemini/Atlas/Jira".

## 7. Gotchas

- **Windows:** never create a top-level folder named `MCP`/`Mcp`. The filesystem is case-insensitive,
  so tools like ruff then treat the `mcp` package as first-party (v1 had exactly this).
- `FastMCP` turns on DNS-rebinding protection when bound to `127.0.0.1`. In Docker it binds
  `0.0.0.0` (`MCP_HOST`) so other containers can reach `http://hub:8001/mcp`.
- FastMCP wraps non-object return values as `{"result": ...}`. `client.unwrap_result` handles it.
- MongoDB returns tz-aware datetimes only because the client uses `tz_aware=True`. Keep it.
