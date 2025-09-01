# listenloom-mcp-server/database/models/meeting_chunk_model.py
from beanie import Document
from typing import List, Optional
from datetime import datetime
import os

class MeetingChunk(Document):
    meeting_id: str # A way to group chunks by meeting
    start_time: float # Start time of the chunk within the meeting
    end_time: float   # End time of the chunk within the meeting
    text_content: str # The actual text content of this chunk (e.g., several 1-sec segments combined)
    embedding: Optional[List[float]] = None # The vector embedding of text_content
    speaker: Optional[str] = None # Speaker of the chunk
    timestamp: datetime = datetime.utcnow() # When this chunk was recorded/processed

    class Settings:
        name = os.getenv("COLLECTION_NAME", "meetings") # Default to 'meeting_chunks'
        # Beanie doesn't define the vector index itself, but it ensures the field exists.
        # The Atlas Vector Search index will be created manually in MongoDB Atlas.