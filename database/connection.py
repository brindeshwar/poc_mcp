import asyncio
import os
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Type
from beanie import Document

# Global variables to store the client and database
_client: AsyncIOMotorClient = None
_database = None

async def connect_db(document_models: List[Type[Document]]):
    """
    Connects to MongoDB using Beanie and initializes document models.
    """
    global _client, _database
    
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set.")
    
    mongo_db = os.getenv("MONGO_DB")
    if not mongo_db:
        raise ValueError("MONGO_DB environment variable not set.")
    
    try:
        # Create MongoDB client
        _client = AsyncIOMotorClient(mongo_uri)
        _database = _client[mongo_db]
        
        # Initialize Beanie with the database and document models
        await init_beanie(database=_database, document_models=document_models)
        
        print(f"Connected to MongoDB database: {mongo_db}")
        
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        raise

def get_database():
    """
    Returns the current database instance.
    """
    global _database
    if _database is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _database

def get_client():
    """
    Returns the current client instance.
    """
    global _client
    if _client is None:
        raise RuntimeError("Client not initialized. Call connect_db() first.")
    return _client