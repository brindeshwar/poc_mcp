# Integration Contract

This document is the **single source of truth** for how the three repos talk to each other. It lives
in the hub because the hub sits in the middle. The other repos link here instead of copying it.

Contract version: **0.2** (matches hub `0.2.x`). Breaking changes bump this and must be listed in
every affected repo's `CHANGELOG.md`.

## Topology and defaults

| Component | Repo | Default address | Talks to |
|---|---|---|---|
| Meeting hub (MCP, Streamable HTTP) | `poc_mcp` | `http://127.0.0.1:8001/mcp` | MongoDB, Gemini, Jira service |
| Streamlit UI | `poc_mcp` | `http://127.0.0.1:8501` | hub (MCP) |
| Jira Task Service (HTTP/JSON) | `poc_jira` | `http://127.0.0.1:8000` | Jira Cloud, Gemini |
| Slack bot | `poc_slack` | Socket Mode (no port) or `:3000` in HTTP mode | Slack, hub (MCP), Gemini |

**Start order for local development:** Jira service → hub → Slack bot / Streamlit.

## Environment wiring

| Variable | Set in | Must equal |
|---|---|---|
| `JIRA_SERVICE_URL` | hub | Jira service base URL (e.g. `http://127.0.0.1:8000`) |
| `JIRA_SERVICE_API_KEY` | hub | `SERVICE_API_KEY` in the Jira service (both empty = no auth) |
| `MCP_SERVER_URL` | Slack bot, Streamlit | hub MCP endpoint, including `/mcp` |

## Shared schema: `ActionItem`

Defined in `poc_mcp/src/meeting_hub/models.py` and mirrored in
`poc_jira/src/jira_service/models.py`. Keep them identical.

```json
{
  "summary": "Write the rollback plan",      // required, 1-255 chars, imperative
  "description": "For the Atlas migration",  // optional
  "assignee": "Eve",                          // optional: name or email as spoken
  "due_date": "2025-07-08"                    // optional: YYYY-MM-DD; invalid values become null
}
```

## Hub → Jira service: `POST /tasks`

Headers: `Content-Type: application/json`, plus `X-API-Key: <key>` when configured.

Request (`SyncRequest`):
```json
{ "meeting_id": "a1b2…", "meeting_title": "Eng sync", "dry_run": false,
  "action_items": [ActionItem, …] }        // 1–50 items
```

Response `200` (`SyncResponse` / hub `JiraSyncResult`):
```json
{ "message": "1 created, 1 updated.",
  "results": [
    { "summary": "Write the rollback plan", "status": "created",
      "jira_key": "POC-12", "jira_url": "https://…/browse/POC-12",
      "message": null, "warnings": [] } ] }
```

`status` ∈ `created | updated | would_create | would_update | failed`. A per-item failure is reported
in `results` (with `message`) and does **not** fail the request.

Errors: `401` bad or missing API key · `422` validation error · `5xx` service failure. The hub turns
any non-2xx into a tool error that includes `detail`.

**Idempotency guarantee:** the same `(meeting_id, normalized summary)` always maps to the same Jira
issue (via label `ai-task-<sha1[:12]>`). Re-sending updates that issue and never clears fields that
were not provided.

Other Jira service endpoints (not used by the hub): `GET /health`,
`POST /tasks/from-transcript`, `POST /create-jira-tasks` (deprecated, plain text).

## Clients → hub: MCP tools

Transport: MCP Streamable HTTP at `MCP_SERVER_URL`. Structured results: object returns arrive as the
object; list returns arrive wrapped as `{"result": [...]}`. Errors arrive as `isError=true` with a
readable text message.

| Tool | Arguments | Returns |
|---|---|---|
| `ingest_meeting` | `title: str`, `transcript: str`, `held_at?: ISO str` | `MeetingRecord` (no transcript) |
| `list_meetings` | `limit=10` (1–20) | `MeetingRecord[]` newest first |
| `get_meeting` | `meeting_id: str`, `include_transcript=false` | `MeetingRecord` |
| `get_latest_meeting` | (none) | `MeetingRecord` (no transcript) |
| `search_meetings` | `query: str`, `limit=5`, `meeting_id?` | `SearchHit[]` |
| `ask_meetings` | `question: str`, `limit=5`, `meeting_id?` | `Answer` |
| `create_jira_tasks` | `meeting_id?` (default latest), `dry_run=false` | `JiraSyncResult` |

```text
MeetingRecord { meeting_id, title, held_at (ISO), summary, action_items: ActionItem[],
                user_stories: str[], ingested_at, transcript: str|null }
SearchHit     { meeting_id, meeting_title, chunk_index, text, speakers: str[], score: float }
Answer        { answer: str, sources: SearchHit[] }
JiraSyncResult{ message: str, results: [{summary, status, jira_key?, jira_url?, message?}] }
```

### Who uses what

| Tool | Slack bot | Streamlit |
|---|---|---|
| `get_latest_meeting` | `/lastmeetingsummary`, `/lastmeetingtodo`, `/lastmeetinguserstory`, agent | |
| `create_jira_tasks` | `/meetingtojira [preview]`, agent (only when explicitly asked) | Meetings tab buttons |
| `ask_meetings`, `search_meetings`, `list_meetings`, `get_meeting` | agent (picked dynamically) | Ask / Meetings tabs |
| `ingest_meeting` | agent | Add meeting tab, seed script |

The Slack agent discovers tools at runtime (`list_tools`), so **new tools appear in Slack
automatically**. Their docstrings are the descriptions Gemini reads, so write them for an LLM.

## Change procedure

1. Change the producer and its tests.
2. Update this file and bump the contract version if the change is breaking.
3. Update the consumers (or add a Backlog item in their `docs/STATUS.md`).
4. Add `CHANGELOG.md` entries in every touched repo.
