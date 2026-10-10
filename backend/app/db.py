import os
from pymongo import MongoClient

_client = None

def get_db():
    """Returns the skyledger database, or None if MONGO_URI isn't set."""
    global _client
    uri = os.getenv("MONGO_URI")
    if not uri:
        return None
    if _client is None:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client["skyledger"]
