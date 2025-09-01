import streamlit as st
import json
import os
import asyncio
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(__file__))

# Import MCP components directly - USE YOUR SYNC WRAPPER
from MCP.tools.meeting_tools import get_meeting_by_semantic_search_sync
from database.connection import connect_db
from database.models.meeting_chunk_model import MeetingChunk

st.set_page_config(page_title="ListenLoom MCP Chat POC", layout="wide")

st.title("🗣️ ListenLoom MCP Chat POC (Historical Meetings)")
st.markdown("Ask questions about your recorded meetings using natural language. This app uses the ListenLoom MCP Server functions directly.")

# Initialize database connection (cached to avoid reconnecting)
@st.cache_resource
def init_database():
    """Initialize database connection synchronously"""
    try:
        # Create a dedicated event loop for database initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(connect_db(document_models=[MeetingChunk]))
            return True
        finally:
            # Don't close the loop here as it might be needed later
            pass
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return False

# Initialize DB
if not init_database():
    st.stop()

# --- Chat History Management ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "retrieved_chunks" in message and message["retrieved_chunks"]:
            with st.expander("Retrieved Context"):
                for chunk in message["retrieved_chunks"]:
                    st.write(f"**Meeting ID:** {chunk.get('meeting_id', 'N/A')}")
                    st.write(f"**Speaker:** {chunk.get('speaker', 'N/A')}")
                    st.markdown(f"**Content:** {chunk.get('text_content', 'N/A')}")
                    st.markdown(f"**Score:** {chunk.get('score', 'N/A'):.4f}")
                    st.markdown("---")

# --- User Input and MCP Tool Call ---
if prompt := st.chat_input("Ask a question about your meetings..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Call your sync wrapper function (preserves your MongoDBService architecture!)
                result = get_meeting_by_semantic_search_sync(query_text=prompt, limit=5)
                
                if result and result.answer:
                    answer = result.answer
                    retrieved_chunks = [chunk.model_dump() for chunk in result.retrieved_chunks]

                    st.markdown(answer)
                    if retrieved_chunks:
                        with st.expander("Retrieved Context"):
                            for chunk in retrieved_chunks:
                                st.write(f"**Meeting ID:** {chunk.get('meeting_id', 'N/A')}")
                                st.write(f"**Speaker:** {chunk.get('speaker', 'N/A')}")
                                st.markdown(f"**Content:** {chunk.get('text_content', 'N/A')}")
                                st.markdown(f"**Score:** {chunk.get('score', 'N/A'):.4f}")
                                st.markdown("---")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "retrieved_chunks": retrieved_chunks
                    })
                else:
                    error_msg = "Failed to get results from the search tool."
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

            except Exception as e:
                error_msg = f"An error occurred: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                # Optional: Show detailed error for debugging
                with st.expander("Debug Info"):
                    st.exception(e)