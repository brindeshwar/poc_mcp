# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private
[security advisory form](../../security/advisories/new) or email the maintainer. You'll get a
response within a few days.

## Supported versions

Only the latest release on `main` receives fixes.

## Handling secrets

This project uses API keys and tokens (Google Gemini, MongoDB Atlas, Jira, Slack).

- Secrets live only in a local `.env` (gitignored) or in your deployment's secret store.
  `.env.example` lists variable **names** only.
- `gitleaks` runs as a pre-commit hook and in CI to block committed secrets.
- If a secret is ever committed, even in a commit that was later reverted, treat it as leaked:
  **rotate it first**, then clean the history (`git filter-repo`) if needed. Deleting the file in a
  new commit does not remove it from history.
- Never paste secrets into issues, PRs, logs, test fixtures or agent prompts.

## Service-specific notes

- **MCP endpoint auth:** set `MCP_AUTH_TOKEN` (bearer token for our clients) and/or `SLACK_SIGNING_SECRET`
  (Slack-signed requests from Slackbot's MCP client) before the hub is reachable from anywhere but
  localhost. With neither set the endpoint is open, and it binds to `127.0.0.1` by default. Slack signatures
  older than 5 minutes are rejected (replay protection), and comparisons are constant-time.
- `_meta.slack` caller identity in requests is ordinary JSON. Trust it only on requests whose Slack
  signature verified.
- Calls from the hub to the Jira Task Service can be protected with a shared key
  (`JIRA_SERVICE_API_KEY` ↔ `SERVICE_API_KEY`). Set it whenever the two run on separate hosts.
