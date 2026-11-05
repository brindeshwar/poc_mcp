"""Block Kit for Slackbot's MCP client (`_meta.slack.blocks` in tool results).

Slackbot renders these natively. Buttons whose action_id is `tool:<name>` call that tool back with
the JSON in `value` as arguments, which gives a preview → confirm flow for Jira without any Slack
app code. Other MCP clients ignore `_meta`.
"""

import json
from typing import Any

from meeting_hub.models import JiraSyncResult, MeetingRecord

SECTION_LIMIT = 2900
VALUE_LIMIT = 2000  # Slack's limit for a button's value


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _section(text: str) -> dict[str, Any]:
    if len(text) > SECTION_LIMIT:
        text = text[: SECTION_LIMIT - 1] + "…"
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _tool_button(label: str, tool: str, args: dict[str, Any], style: str | None = None) -> dict:
    value = json.dumps(args, separators=(",", ":"))
    if len(value) > VALUE_LIMIT:
        raise ValueError("tool button arguments exceed Slack's 2000-character limit")
    button: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": label},
        "action_id": f"tool:{tool}",
        "value": value,
    }
    if style:
        button["style"] = style
    return button


def meeting_blocks(meeting: MeetingRecord) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": meeting.title[:150]}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Held {meeting.held_at.date().isoformat()}"}],
        },
        _section(_escape(meeting.summary)),
    ]
    if meeting.action_items:
        lines = []
        for item in meeting.action_items:
            owner = item.assignee or "unassigned"
            due = f", due {item.due_date}" if item.due_date else ""
            lines.append(f"• {_escape(item.summary)} _({_escape(owner)}{due})_")
        blocks.append(_section("*Action items*\n" + "\n".join(lines)))
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    _tool_button(
                        "Preview Jira tasks",
                        "create_jira_tasks",
                        {"meeting_id": meeting.meeting_id, "dry_run": True},
                    )
                ],
            }
        )
    if meeting.user_stories:
        stories = "\n".join(f"• {_escape(s)}" for s in meeting.user_stories)
        blocks.append(_section("*User stories*\n" + stories))
    return blocks


STATUS_LABELS = {
    "created": "Created",
    "updated": "Updated",
    "would_create": "Would create",
    "would_update": "Would update",
    "failed": "Failed",
}


def jira_blocks(result: JiraSyncResult, meeting_id: str | None, dry_run: bool) -> list[dict]:
    lines = []
    for row in result.results:
        label = STATUS_LABELS.get(row.status, row.status)
        link = f" <{row.jira_url}|{row.jira_key}>" if row.jira_url else ""
        line = f"• *{label}*{link} {_escape(row.summary)}"
        if row.message:
            line += f"\n   _{_escape(row.message)}_"
        lines.append(line)
    blocks: list[dict[str, Any]] = [_section(f"*Jira:* {_escape(result.message)}")]
    if lines:
        blocks.append(_section("\n".join(lines)))
    # Confirmation step: only a preview with something to create gets the button. The real run's
    # result has no button, so clicking it "consumes" the action when Slackbot refreshes in place.
    if dry_run and meeting_id and any(r.status.startswith("would_") for r in result.results):
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    _tool_button(
                        "Create these tickets",
                        "create_jira_tasks",
                        {"meeting_id": meeting_id, "dry_run": False},
                        style="primary",
                    )
                ],
            }
        )
    return blocks
