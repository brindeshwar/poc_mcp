# listenloom-mcp-server/services/embedding_service.py
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import os
from typing import List
import asyncio

class EmbeddingService:
    def __init__(self):
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")
        self.embedding_model = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=google_api_key
        )
        print("EmbeddingService initialized with models/embedding-001")

    async def get_embedding(self, text: str) -> List[float]:
        """Generates a vector embedding for the given text."""
        try:
            # LangChain's embed_query is synchronous, so we run it in a thread pool
            # to avoid blocking the event loop in an async context.
            return await asyncio.to_thread(self.embedding_model.embed_query, text)
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise