# listenloom-mcp-server/scripts/populate_sample_data.py
import asyncio
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.embedding_service import EmbeddingService
from services.mongodb_service import MongoDBService
from database.connection import connect_db
from database.models.meeting_chunk_model import MeetingChunk
from datetime import datetime
from uuid import uuid4

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

async def populate_data():
    """
    Connects to DB, initializes services, generates embeddings for sample data,
    and inserts them into the collection.
    """
    try:
        await connect_db(document_models=[MeetingChunk])
        
        embedding_service = EmbeddingService()
        mongodb_service = MongoDBService(embedding_service)

        print("\n--- Generating and inserting sample data ---")

        sample_meeting_id_1 = str(uuid4())
        sample_meeting_id_2 = str(uuid4())

        sample_chunks = [
            # Meeting 1
            {
                "meeting_id": sample_meeting_id_1,
                "start_time": 0.0,
                "end_time": 15.0,
                "speaker": "Alice",
                "text_content": "Good morning everyone. Today we are discussing the Q3 marketing strategy, particularly focusing on our digital ad spend and new social media campaigns. We need to finalize the budget for the influencer outreach.",
            },
            {
                "meeting_id": sample_meeting_id_1,
                "start_time": 15.1,
                "end_time": 30.0,
                "speaker": "Bob",
                "text_content": "I've prepared a detailed report on the past quarter's performance. Our TikTok campaign showed excellent ROI, but Instagram stories were underperforming. We might need to reallocate funds there.",
            },
            {
                "meeting_id": sample_meeting_id_1,
                "start_time": 30.1,
                "end_time": 45.0,
                "speaker": "Charlie",
                "text_content": "Regarding the influencer budget, I think we should prioritize micro-influencers over macro ones for better engagement, especially for the new product launch next month. It aligns with our agile marketing approach.",
            },
            {
                "meeting_id": sample_meeting_id_1,
                "start_time": 45.1,
                "end_time": 60.0,
                "speaker": "Alice",
                "text_content": "Great points. Let's make sure the new product launch strategy is integrated into these discussions. We also need to get feedback from legal on the ad creatives by end of day.",
            },
            # Meeting 2
            {
                "meeting_id": sample_meeting_id_2,
                "start_time": 0.0,
                "end_time": 10.0,
                "speaker": "David",
                "text_content": "Welcome to the engineering sync. Our main topic today is the database migration to MongoDB Atlas and the new microservices architecture deployment schedule. We're targeting next sprint for the first phase.",
            },
            {
                "meeting_id": sample_meeting_id_2,
                "start_time": 10.1,
                "end_time": 25.0,
                "speaker": "Eve",
                "text_content": "I'm concerned about the data integrity during the MongoDB migration. We need a robust rollback plan and extensive testing in the staging environment before going live.",
            },
            {
                "meeting_id": sample_meeting_id_2,
                "start_time": 25.1,
                "end_time": 40.0,
                "speaker": "Frank",
                "text_content": "The new microservices architecture will significantly improve our scalability and fault tolerance. We just need to ensure the CI/CD pipelines are fully automated for seamless deployments.",
            },
        ]

        # Generate embeddings and insert
        for i, chunk in enumerate(sample_chunks):
            print(f"Processing chunk {i+1}/{len(sample_chunks)}: '{chunk['text_content'][:50]}...'")
            chunk["embedding"] = await embedding_service.get_embedding(chunk["text_content"])
            chunk["timestamp"] = datetime.utcnow()
            await mongodb_service.insert_meeting_chunk(chunk)

        print("\n--- Sample data insertion complete ---")
        total_chunks = await mongodb_service.get_all_chunks()
        print(f"Total chunks in database: {len(total_chunks)}")

    except Exception as e:
        print(f"An error occurred during data population: {e}")

if __name__ == "__main__":
    asyncio.run(populate_data())