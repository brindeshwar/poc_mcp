# Contributing

Thanks for helping! This repo is one of three that make up the ListenLoom system (meeting hub, Slack
bot, Jira Task Service). Coding agents should read [`AGENTS.md`](AGENTS.md) first. It has the same
rules in more detail.

## Set up

```bash
uv sync                      # creates .venv with runtime + dev dependencies
cp .env.example .env         # fill in what you need; never commit .env
uv run pre-commit install    # ruff, gitleaks, lockfile checks on every commit
```

## Make a change

1. Branch from `main`: `feat/<short-name>`, `fix/…`, `docs/…`, `refactor/…`, `chore/…`, `ci/…`.
2. Write the code and the tests. Tests must not touch the network (no real Gemini, MongoDB, Jira or
   Slack); use the fakes in `tests/conftest.py`.
3. Run the same checks as CI:
   ```bash
   uv run ruff format . && uv run ruff check . && uv run pytest
   ```
4. Commit with [Conventional Commits](https://www.conventionalcommits.org):
   `feat(server): add list_speakers tool`, `fix(chunking): keep long turns together`,
   `docs: explain Atlas index setup`. Mark breaking changes with `!` and a `BREAKING CHANGE:` footer.
5. Add a line under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md) for anything user-visible.
6. Update `docs/STATUS.md` (handoff log; also backlog and decision log if relevant).
7. Open a PR and fill in the template. `main` is protected: the PR needs all 5 CI checks green and
   up to date with `main`, and resolved conversations. Merge with **Rebase and merge** (the only method
   enabled), which keeps history linear and the individual Conventional Commits intact.

## Changes that affect other repos

Tool signatures, `ActionItem`, and the Jira `/tasks` payload are a shared contract, documented in
the hub's [`docs/INTEGRATION.md`](https://github.com/brindeshwar/poc_mcp/blob/main/docs/INTEGRATION.md).
If you change them, update that document and the consuming repos in the same piece of work, or open
linked issues for them.

## Dependencies

Add with `uv add <pkg>` (or `uv add --dev <pkg>`). This updates `pyproject.toml` and `uv.lock`;
commit both. Dependabot proposes weekly updates.

## Releasing

1. Move `[Unreleased]` entries in `CHANGELOG.md` under a new version heading with today's date.
2. Bump `version` in `pyproject.toml` (SemVer).
3. Commit `chore(release): vX.Y.Z`, tag `vX.Y.Z`, push the tag, and create a GitHub release from the
   changelog section.
