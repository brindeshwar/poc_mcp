# Architecture: Meeting Hub

## Context

The hub is the only component that owns meeting data. Every client (the Slack bot, the Streamlit UI,
or any MCP host) reaches meetings through its MCP tools. Jira writes are delegated to the Jira Task
Service. See `INTEGRATION.md` for the exact contracts.

## Layers

```
            ┌──────────────────────────────── server.py ───────────────────────────────┐
 MCP ──────►│ MCPServer tools: validate/parse input → call service → map errors to ToolError│
            └─────────────────────────────────────┬─────────────────────────────────────┘
                                                  ▼
            ┌──────────────────────────────── service.py ──────────────────────────────┐
            │ MeetingService: ingest · list/get/latest · search · ask · send_to_jira    │
            └──────────┬────────────────────────┬─────────────────────────┬────────────┘
                       ▼                        ▼                         ▼
              store.py (MeetingStore)     llm.py (LLM)           jira_client.py
              ├─ MongoStore (Atlas)       └─ GeminiLLM           └─ JiraServiceClient (httpx)
              └─ InMemoryStore
```

- `server.py` has no business logic, and `service.py` has no MCP imports. This keeps the logic
  testable with plain `pytest` and reusable from other front ends.
- `MeetingStore` and `LLM` are `typing.Protocol`s. Tests use `InMemoryStore` and `FakeLLM`.
- `build_service(settings)` is the single composition root. The service object lives for the whole
  process (one Mongo client, one Gemini client, one httpx client).

## Data model

**`meeting_records`** (one document per meeting, `MeetingRecord`)

| Field | Type | Notes |
|---|---|---|
| `meeting_id` | str | uuid4 hex, unique index |
| `title` | str | |
| `held_at` | datetime (UTC) | indexed desc; "latest meeting" = max `held_at` |
| `transcript` | str | omitted from tool responses unless `include_transcript=true` |
| `summary` | str | generated at ingest |
| `action_items` | `ActionItem[]` | generated at ingest; shared contract with Jira |
| `user_stories` | str[] | generated at ingest |
| `ingested_at` | datetime | |

**`meeting_chunks`** (searchable pieces, `Chunk`)

| Field | Type | Notes |
|---|---|---|
| `meeting_id` | str | filter field in both search indexes |
| `meeting_title` | str | denormalized, so results need no meeting lookup |
| `chunk_index` | int | |
| `text` | str | ~800 chars of `Speaker: text` lines |
| `speakers` | str[] | speakers appearing in the chunk |
| `embedding` | float[768] | `gemini-embedding-2` of `"title: <meeting title> \| text: <chunk>"` |

Two Atlas indexes, both created by `scripts/create_search_indexes.py`:
- **Vector Search** `meeting_chunks_vector_index`: `embedding` (768, cosine) plus `meeting_id` (filter).
- **Atlas Search** `meeting_chunks_text_index`: `text` (`lucene.english`), `meeting_title`, and
  `meeting_id` (token, for filtering).

## Flows

**Ingest** (`ingest_meeting`)
1. Validate title and transcript (non-empty, ≤ 200k chars). A naive `held_at` is treated as UTC.
2. `chunk_transcript` → utterances grouped into ~800-char chunks, never splitting a turn unless it is
   oversized.
3. **Concurrently** (`asyncio.gather`):
   - `LLM.extract_insights(transcript, held_at.date())` → summary, action items, user stories. Relative
     deadlines are resolved against the **meeting date**, not today.
   - `LLM.embed_documents([(title, chunk), …])` in batches of 100, up to 4 batches in flight.
4. `store.save_meeting` upserts the record and replaces its chunks (re-ingesting is idempotent per id).

**Search / Ask** (`search_meetings`, `ask_meetings`): embed the question as
`"task: search result | query: …"` → **hybrid search** (optionally filtered by meeting) → if no hits, return a fixed "couldn't find" answer *without*
calling the LLM; otherwise generate a grounded answer and return it with its sources.

**Jira hand-off** (`create_jira_tasks`): pick a meeting (given or latest). If it has no action items,
return early. Otherwise `POST /tasks` to the Jira service with the stored action items, `meeting_id`,
`meeting_title` and `dry_run`. The Jira service guarantees idempotency, so the hub keeps no ticket
state.

## Hybrid search

Embeddings are good at meaning but weak on exact tokens: names, acronyms, ticket keys like `POC-12`.
`SEARCH_MODE=hybrid` (the default) runs both and fuses them with reciprocal-rank fusion:

```
$rankFusion
  vector: $vectorSearch (limit × 4 candidates)
  text:   $search { text: query, fuzzy maxEdits 1, filter meeting_id } + $limit (limit × 4)
→ $limit · project score = {$meta: "score"}
```

Scores in hybrid mode are fused-rank scores (about 0.016–0.033), not cosine similarities. Compare them
only within one result list. `InMemoryStore` implements the same fusion (cosine ranking plus an
IDF-weighted keyword ranking with Lucene's English stopwords), so tests exercise real behaviour. A
missing text index raises a clear error telling you to run `create_search_indexes.py` or switch to
`SEARCH_MODE=vector`.

## Models

| Task | Model | Thinking |
|---|---|---|
| Insight extraction (structured output) | `gemini-3.5-flash-lite` | `low`: resolves relative dates |
| Answers (grounded in retrieved excerpts) | `gemini-3.5-flash-lite` | `minimal` |
| Embeddings | `gemini-embedding-2`, 768 dims (auto-normalized) | n/a |

`gemini-embedding-2` takes no `task_type`. The task is a text prefix (`llm.document_text` /
`llm.query_text`). Its vectors are **not compatible** with `gemini-embedding-001`. After changing
the embedding model or dimensions, run `scripts/reembed_meetings.py`, which rebuilds chunks from
stored transcripts without re-running extraction.

## Error handling

| Failure | Raised as | Client sees |
|---|---|---|
| Bad input | `ValueError` | MCP tool error with the message |
| Unknown meeting / no meetings | `MeetingNotFoundError` | tool error |
| Gemini failure | `LLMError` | tool error ("Could not extract…", "Embedding request failed…") |
| Jira service down / 4xx / 5xx | `JiraServiceError` | tool error including the service's `detail` |
| Jira not configured | `RuntimeError` | tool error |

Nothing is silently replaced by a fallback. v1 fell back to keyword matching with a fake score, and
that hid broken configuration.

## Extending

**Add a tool:** add a method to `MeetingService` (with tests in `tests/test_service.py`). Then add
a thin `@mcp.tool()` in `create_server` with a clear docstring (it becomes the tool description
that LLMs read). Add it to `EXPECTED_TOOLS` in `tests/test_server.py` and document it in
`INTEGRATION.md`.

**Swap the LLM provider:** implement the `LLM` protocol in `llm.py` and select it in `build_service`.
Keep embedding dimensions consistent with the index.

**Swap the database:** implement `MeetingStore`. `InMemoryStore` is the reference behaviour.

## Configuration

All settings live in `config.Settings`. See `.env.example` for the full list. Key ones:
`GOOGLE_API_KEY`, `STORE_BACKEND` (`mongo`|`memory`), `MONGO_URI`, `MCP_HOST`/`MCP_PORT`,
`JIRA_SERVICE_URL` (empty disables Jira), `JIRA_SERVICE_API_KEY`.
