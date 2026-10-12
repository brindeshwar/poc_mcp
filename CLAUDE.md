# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- `AGENTS.md` (imported above) holds the shared rules. Put anything that applies to every agent there,
  not here. This file is only for Claude-specific workflow.
- Use plan mode for anything that touches the cross-repo contract (`docs/INTEGRATION.md`) or more
  than one repo. The sibling repos are at `../poc_slack` and `../poc_jira/jira_task_creator` and
  have their own `AGENTS.md`.
- Before finishing a task, run `uv run ruff format . && uv run ruff check . && uv run pytest` and
  report the actual result.
- At the end of a session, follow the handoff protocol in `AGENTS.md` §6: update `docs/STATUS.md`.
- Never run `create_jira_tasks` without `dry_run=true` against a real Jira, and never write to the
  user's Atlas database for testing. Use `STORE_BACKEND=memory`.
