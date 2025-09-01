from database.models.meeting_chunk_model import MeetingChunk
from services.embedding_service import EmbeddingService
from typing import List, Dict, Any, Optional
import os

class MongoDBService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.vector_index_name = os.getenv("VECTOR_INDEX_NAME")
        self.collection_name = os.getenv("COLLECTION_NAME")
        print(f"MongoDBService initialized, targeting collection '{self.collection_name}' with vector index '{self.vector_index_name}'")

    async def find_chunks_by_semantic_search(self, query_text: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Performs a semantic search on meeting chunks using Atlas Vector Search.
        """
        print(f"Generating embedding for query: '{query_text}'")
        query_embedding = await self.embedding_service.get_embedding(query_text)
        print(f"Query embedding generated (first 5 dims): {query_embedding[:5]}...")

        pipeline = [
            {
                "$vectorSearch": {
                    "queryVector": query_embedding,
                    "path": "embedding",
                    "numCandidates": 100,
                    "limit": limit,
                    "index": self.vector_index_name,
                }
            },
            {"$project": {"_id": 0, "meeting_id": 1, "text_content": 1, "speaker": 1, "score": {"$meta": "vectorSearchScore"}}}
        ]

        print("Executing vector search pipeline...")
        
        try:
            # Get database and collection directly (fixed approach)
            from database.connection import get_database
            db = get_database()
            collection = db[self.collection_name]
            
            # Execute aggregation with proper cursor handling
            results = []
            async for doc in collection.aggregate(pipeline):
                results.append(doc)
            
            print(f"Vector search returned {len(results)} results.")
            return results
            
        except Exception as e:
            print(f"Error in vector search: {e}")
            
            # Fallback: Get all documents and do basic filtering
            print("Falling back to simple document retrieval...")
            try:
                all_chunks = await MeetingChunk.find_all().to_list()
                
                # Simple text matching as fallback
                filtered_chunks = []
                query_lower = query_text.lower()
                
                for chunk in all_chunks:
                    if any(word in chunk.text_content.lower() for word in query_lower.split()):
                        filtered_chunks.append({
                            "meeting_id": chunk.meeting_id,
                            "text_content": chunk.text_content,
                            "speaker": chunk.speaker,
                            "score": 0.5  # Default score
                        })
                
                # Limit results
                filtered_chunks = filtered_chunks[:limit]
                print(f"Fallback search returned {len(filtered_chunks)} results.")
                return filtered_chunks
                
            except Exception as fallback_error:
                print(f"Fallback search also failed: {fallback_error}")
                return []

    async def insert_meeting_chunk(self, chunk: Dict[str, Any]) -> MeetingChunk:
        """Inserts a single meeting chunk document into the database."""
        new_chunk = MeetingChunk(**chunk)
        await new_chunk.insert()
        print(f"Inserted chunk for meeting {new_chunk.meeting_id}")
        return new_chunk

    async def get_all_chunks(self) -> List[MeetingChunk]:
        """Retrieves all meeting chunks from the collection."""
        return await MeetingChunk.find_all().to_list()