import os
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

# Global client variable
motor_client = None

def get_db():
    """
    Returns the database instance.
    Uses a single connection pool for the whole app (Efficiency).
    """
    global motor_client
    
    if motor_client is None:
        if not Config.MONGO_URI:
            raise ValueError("No MONGO_URI found!")
        
        # maxPoolSize=100 allows 100 concurrent connections
        # minPoolSize=10 keeps connections ready so there's no startup lag
        motor_client = AsyncIOMotorClient(
            Config.MONGO_URI,
            maxPoolSize=100,
            minPoolSize=10
        )
    
    return motor_client[Config.DB_NAME]

# Initialize immediately for collections export
_db = get_db()
users_col = _db.users
logs_col = _db.logs
profiles_col = _db.profiles
weekly_logs_col = _db.weekly_logs
reflections_col = _db.reflections
dtr_uploads_col = _db.dtr_uploads

async def create_indexes():
    """Run this on startup to make searches instant"""
    await logs_col.create_index([("user_id", 1), ("log_date", -1)])
    await weekly_logs_col.create_index([("user_id", 1), ("week_end_date", -1)])
    await dtr_uploads_col.create_index([("user_id", 1), ("uploaded_at", -1)])
    print("⚡ Database Indexes Optimized")