# Project Status: Meeting Hub

> Living document. **Every agent or person updates this at the end of a work session** (see
> `AGENTS.md` §6). Newest handoff entry goes on top. Keep it honest and short.

## Health

| Check | State | As of |
|---|---|---|
| Unit + MCP end-to-end tests | ✅ 32 passing (incl. hybrid search, concurrency, no-N+1, re-embed, annotations) | 2026-10-13 |
| Lint / format (ruff) | ✅ clean | 2026-10-13 |
| MCP server over HTTP (memory store) | ✅ verified live | 2026-10-13 |
| Slack bot ↔ hub MCP connection | ✅ verified live | 2026-10-13 |
| Gemini (ingest / ask) live | ⛔ not verified: `GOOGLE_API_KEY` in local `.env` is invalid | 2026-10-13 |
| MongoDB Atlas live | ⛔ not verified: needs new vector index + re-seed | 2026-10-13 |
| Docker image | ✅ builds in CI (`Docker build` job, required check) | 2026-10-13 |

## Current version

`0.2.0`, released 2026-10-13 (tag `v0.2.0`, GitHub release). See `CHANGELOG.md`.

## Known issues / blockers

1. **Gemini key invalid.** Get a new key from Google AI Studio and put it in `.env`.
2. **Atlas data is from v1** (old `embedding-001` vectors, different collections). Run
   `scripts/create_search_indexes.py`, wait for both indexes to be READY, then `scripts/seed_meetings.py`
   (or `scripts/reembed_meetings.py` for meetings already stored by v0.2). Old collections
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
| 2026-10-13 | `gemini-embedding-001` at 768 dims (superseded below) | keeps v1's index dimension; `embedding-001` is retired | 3072 dims (bigger index, little gain here) |
| 2026-10-13 | v0.3: `gemini-3.5-flash-lite` for all generation; thinking `low` (extract) / `minimal` (answer) | 2.5 models closed to new projects; Flash-Lite is the fast, cheap stable tier and our tasks are grounded/structured | 3.8 Flash (≈5× the price, little gain for extraction) |
| 2026-10-13 | v0.3: `gemini-embedding-2` at 768 dims, task as text prefix | successor to 001 (shutdown 2028); same index size; auto-normalized | 3072 dims |
| 2026-10-13 | v0.3: hybrid search via `$rankFusion` (GA) | embeddings miss IDs, names and acronyms; RRF needs no score tuning | `$scoreFusion` (needs weight tuning), vector-only |
| 2026-10-13 | v0.3: denormalize `meeting_title` into chunks | removes N+1 lookups per search; it also gives the embedding its `title:` context | `$lookup` per query |
| 2026-10-13 | No silent fallbacks; errors become MCP tool errors | v1's keyword fallback hid broken config | |
| 2026-10-13 | `InMemoryStore` as a real backend (`STORE_BACKEND=memory`) | demo without Atlas; reference implementation for tests | test-only fake |
| 2026-10-13 | Protect `main`: PR + 5 required checks, linear history, rebase-only merges, 0 approvals | keeps `main` always green; linear history keeps the Conventional Commits readable; solo maintainer can't self-approve | squash merges (loses commit granularity); required approvals (blocks a solo maintainer) |

## Handoff log

### 2026-10-13: Claude (Opus 5.5) · v0.3.0 modernisation
**Changed:** models → `gemini-3.5-flash-lite` (per-task thinking levels) and `gemini-embedding-2`
(task prefixes; no `task_type`). Hybrid search (`$rankFusion` of vector + Atlas Search, mirrored in
`InMemoryStore` with Lucene English stopwords). Ingest runs extraction and embedding concurrently
(embedding batches 4-way parallel). `meeting_title` is denormalized into chunks (no N+1 per search).
`reembed` service method + script. MCP tool annotations. `create_search_indexes.py` replaces
`create_vector_index.py`. Python 3.14 in CI/Docker.

**Verified:** 32 tests, including a pair showing vector-only search *misses* an exact ticket key that
hybrid search surfaces; ruff; live HTTP: annotations visible to an `mcp.Client`.

**Not verified:** Atlas `$rankFusion` and the text index against a real cluster, and real Gemini 3.5 /
Embedding 2 calls (no valid key).

**Next agent:** with a key and Atlas: `create_search_indexes.py` → `seed_meetings.py` → `ask_meetings`
→ compare `SEARCH_MODE=hybrid` vs `vector` on a name/ID query.

### 2026-10-13: Claude (Opus 5.5) · dependency upgrades (Dependabot triage)
**Changed:** migrated to `mcp` 2.3 (`MCPServer`, `mcp.Client`, in-process `Client(server)` tests) and `google-genai` 2.x. CI actions moved to their Node 24 majors.

**Verified:** release notes reviewed for every major bump; pytest (24) on mcp 2.3; live HTTP smoke test (hub ↔ hub client and Slack client); google-genai 2.29 API surface checked against every call we make.

**Next agent:** Dependabot's superseded PRs close automatically after merge. Future major bumps need the
same review (CI alone isn't enough where tests use fakes, e.g. Gemini).

### 2026-10-13: Claude (Opus 5.5) · v0.2.0 released, branch protection
**Changed:** merged the v2 PR (rebase), tagged `v0.1.0` (original POC) and `v0.2.0`, and published the
GitHub release. Protected `main`: PR required, 5 required checks (lint, tests 3.12/3.13, secret scan,
Docker build) that must be up to date, linear history, conversation resolution, no force-push or
deletion, enforced for admins. 0 approvals required (solo maintainer; GitHub forbids self-approval).
Rebase merge is the only merge method; merged branches are auto-deleted.

**Verified:** CI green on the PR and on `main` after merge; protection settings read back from the
GitHub API.

**Next agent:** unchanged. Live verification is blocked on a valid Gemini key (and Jira site / Slack
token rotation; see Known issues). All changes now go through a PR.

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
