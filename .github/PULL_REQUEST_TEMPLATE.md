## What and why

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type

- [ ] feat
- [ ] fix
- [ ] refactor / chore
- [ ] docs
- [ ] ci

## Cross-repo contract

- [ ] This PR does **not** change tool names/arguments/results, `ActionItem`, or the `/tasks` payload
- [ ] It does, and I updated the integration contract, marked it BREAKING in `CHANGELOG.md` if needed,
      and updated or flagged the other repos

## How it was verified

<!-- Commands run and what you saw. Say explicitly if anything was only tested with fakes. -->

- [ ] `uv run ruff format . && uv run ruff check .`
- [ ] `uv run pytest`
- [ ] Manually / live (describe):

## Checklist

- [ ] Tests added or updated (bug fixes include a regression test)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (if user-visible)
- [ ] Docs updated (`README.md`, `docs/`, `AGENTS.md`) where behaviour or workflow changed
- [ ] `docs/STATUS.md` handoff entry added
- [ ] No secrets, `.env` files or tokens in the diff
