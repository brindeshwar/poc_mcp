"""Streamlit UI for the meeting hub. It is a real MCP client: every action goes through the
server's MCP tools over HTTP, exactly like the Slack bot does.

Run:  uv run streamlit run streamlit_app.py
"""

import asyncio
import os
from datetime import date
from typing import Any

import streamlit as st

from meeting_hub.client import HubToolError, call_tool

SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

st.set_page_config(page_title="ListenLoom Meeting Hub", page_icon="🗣️", layout="wide")


def tool(name: str, **arguments: Any) -> Any:
    """Call an MCP tool; show a readable error and stop the script run if it fails."""
    try:
        return asyncio.run(call_tool(SERVER_URL, name, arguments))
    except HubToolError as exc:
        st.error(str(exc))
    except Exception as exc:  # connection refused, timeouts, ...
        st.error(f"Could not reach the MCP server at {SERVER_URL}: {exc}")
    st.stop()


def render_sources(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for hit in sources:
            st.markdown(f"**{hit['meeting_title']}** · score {hit['score']:.3f}")
            st.text(hit["text"])


def render_jira_results(result: dict[str, Any]) -> None:
    st.info(result["message"])
    for row in result["results"]:
        link = f" — [{row['jira_key']}]({row['jira_url']})" if row.get("jira_url") else ""
        st.markdown(f"- `{row['status']}` {row['summary']}{link}")


st.title("🗣️ ListenLoom Meeting Hub")
st.caption(f"Connected to MCP server: `{SERVER_URL}`")

ask_tab, meetings_tab, add_tab = st.tabs(["Ask", "Meetings", "Add meeting"])

with ask_tab:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_sources(message.get("sources", []))

    if question := st.chat_input("Ask about your meetings…"):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"), st.spinner("Searching meetings…"):
            answer = tool("ask_meetings", question=question, limit=5)
            st.markdown(answer["answer"])
            render_sources(answer["sources"])
        st.session_state.messages.append(
            {"role": "assistant", "content": answer["answer"], "sources": answer["sources"]}
        )

with meetings_tab:
    meetings = tool("list_meetings", limit=20)
    if not meetings:
        st.info("No meetings yet. Add one in the **Add meeting** tab or run the seed script.")
    for meeting in meetings:
        held = meeting["held_at"][:10]
        with st.expander(f"{held} · {meeting['title']}"):
            st.markdown(f"**Summary**\n\n{meeting['summary']}")
            if meeting["action_items"]:
                st.markdown("**Action items**")
                for item in meeting["action_items"]:
                    owner = item.get("assignee") or "unassigned"
                    due = f", due {item['due_date']}" if item.get("due_date") else ""
                    st.markdown(f"- {item['summary']} _({owner}{due})_")
            if meeting["user_stories"]:
                st.markdown("**User stories**")
                for story in meeting["user_stories"]:
                    st.markdown(f"- {story}")

            preview_col, send_col = st.columns(2)
            mid = meeting["meeting_id"]
            if preview_col.button("Preview Jira tasks", key=f"preview-{mid}"):
                render_jira_results(tool("create_jira_tasks", meeting_id=mid, dry_run=True))
            if send_col.button("Create Jira tasks", key=f"send-{mid}", type="primary"):
                render_jira_results(tool("create_jira_tasks", meeting_id=mid))

with add_tab, st.form("add-meeting", clear_on_submit=True):
    title = st.text_input("Title")
    held_on = st.date_input("Date", value=date.today())
    transcript = st.text_area(
        "Transcript", height=300, placeholder="Alice: Let's start…\nBob: I'll take that."
    )
    if st.form_submit_button("Save meeting", type="primary"):
        with st.spinner("Summarising and indexing…"):
            meeting = tool(
                "ingest_meeting",
                title=title,
                transcript=transcript,
                held_at=held_on.isoformat(),
            )
        st.success(
            f"Saved '{meeting['title']}' with {len(meeting['action_items'])} action item(s)."
        )
