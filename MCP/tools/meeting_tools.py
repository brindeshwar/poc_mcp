# listenloom-mcp-server/MCP/tools/meeting_tools.py

import sys
import os

# Modern MCP approach using FastMCP
from mcp.server.fastmcp import FastMCP

from services.mongodb_service import MongoDBService
from services.embedding_service import EmbeddingService
from database.connection import connect_db
from database.models.meeting_chunk_model import MeetingChunk
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document as LCDocument
from langchain_core.prompts import PromptTemplate
import asyncio

# --- Initialize Services ONCE (Global instances for the MCP server) ---
embedding_service_instance = EmbeddingService()
mongodb_service_instance = MongoDBService(embedding_service_instance)

# --- Create FastMCP Server ---
app = FastMCP("ListenLoom MCP Server")

# --- Input/Output Schemas for the Tool ---
class MeetingSearchInput(BaseModel):
    query_text: str = Field(..., description="The natural language query for finding relevant meeting discussions.")
    limit: int = Field(3, description="Maximum number of relevant meeting chunks to retrieve.")

class RetrievedChunk(BaseModel):
    meeting_id: str
    text_content: str
    speaker: Optional[str] = None
    score: float

class MeetingSearchResult(BaseModel):
    answer: str = Field(..., description="The AI-generated answer based on the retrieved meeting context.")
    retrieved_chunks: List[RetrievedChunk] = Field(..., description="List of meeting chunks used to generate the answer.")

# --- MCP Tool Implementation ---
@app.tool()
async def get_meeting_by_semantic_search(query_text: str, limit: int = 3) -> dict:
    """
    Retrieves relevant meeting chunks using semantic search and generates an answer using an LLM.
    
    Args:
        query_text: The natural language query for finding relevant meeting discussions
        limit: Maximum number of relevant meeting chunks to retrieve (default: 3)
    
    Returns:
        Dictionary with answer and retrieved_chunks
    """
    print(f"MCP Tool called with query: '{query_text}'")

    # Use your existing MongoDBService (preserving your architecture)
    retrieved_docs_raw = await mongodb_service_instance.find_chunks_by_semantic_search(
        query_text=query_text,
        limit=limit
    )

    if not retrieved_docs_raw:
        print("No relevant chunks found.")
        return {
            "answer": "I could not find any relevant information in the meeting transcripts for your query.",
            "retrieved_chunks": []
        }

    retrieved_chunks_models = [RetrievedChunk(**doc) for doc in retrieved_docs_raw]

    context_string = "\n---\n".join([
        f"Meeting ID: {chunk.meeting_id}\nSpeaker: {chunk.speaker if chunk.speaker else 'Unknown'}\nContent: {chunk.text_content}"
        for chunk in retrieved_chunks_models
    ])
    print(f"Context provided to LLM:\n{context_string}")

    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))
        
        # Modern approach: Create a simple prompt and invoke directly
        from langchain_core.prompts import PromptTemplate
        
        # Create context from documents
        context = "\n\n".join([doc['text_content'] for doc in retrieved_docs_raw])
        
        # Simple prompt template
        prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template="""Based on the following meeting transcript context, please answer the question.

Context:
{context}

Question: {question}

Answer:"""
        )
        
        # Create the prompt and invoke
        prompt = prompt_template.format(context=context, question=query_text)
        response = await llm.ainvoke(prompt)
        generated_answer = response.content if hasattr(response, 'content') else str(response)
        
        print(f"Generated answer: {generated_answer}")

        return {
            "answer": generated_answer,
            "retrieved_chunks": [chunk.dict() for chunk in retrieved_chunks_models]
        }

    except Exception as e:
        print(f"Error during LLM generation: {e}")
        return {
            "answer": f"An error occurred while generating the answer: {str(e)}",
            "retrieved_chunks": [chunk.dict() for chunk in retrieved_chunks_models]
        }

# --- Synchronous Wrapper for Streamlit (calls the MCP tool) ---
def get_meeting_by_semantic_search_sync(query_text: str, limit: int = 3) -> dict:
    """
    Synchronous wrapper that calls the proper MCP tool.
    This preserves your MongoDBService architecture without re-initialization.
    """
    try:
        import asyncio
        import concurrent.futures
        
        def run_in_new_thread():
            # Create a new event loop in a separate thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                # Initialize database connection once in this thread
                new_loop.run_until_complete(connect_db(document_models=[MeetingChunk]))
                
                # Call the proper MCP tool function
                return new_loop.run_until_complete(
                    get_meeting_by_semantic_search(query_text=query_text, limit=limit)
                )
            finally:
                new_loop.close()
        
        # Run in thread to avoid event loop conflicts with Streamlit
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_thread)
            result = future.result(timeout=30)  # 30 second timeout
            
            # Convert dict result to MeetingSearchResult for compatibility
            retrieved_chunks = [RetrievedChunk(**chunk) for chunk in result.get("retrieved_chunks", [])]
            return MeetingSearchResult(
                answer=result.get("answer", ""),
                retrieved_chunks=retrieved_chunks
            )
                
    except Exception as e:
        print(f"Error in sync wrapper: {e}")
        return MeetingSearchResult(
            answer=f"An error occurred while searching: {str(e)}",
            retrieved_chunks=[]
        )

# --- Database Initialization Function ---
async def initialize_database():
    """Initialize database connection"""
    print("Initializing database connection...")
    await connect_db(document_models=[MeetingChunk])
    print("MongoDB connection established.")

# Note: FastMCP handles initialization differently - database will be connected
# when the sync wrapper is called, ensuring connection is available when needed