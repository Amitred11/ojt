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
db = get_db()

users_col = db.users
logs_col = db.logs
profiles_col = db.profiles
weekly_logs_col = db.weekly_logs
reflections_col = db.reflections
dtr_uploads_col = db.dtr_uploads
settings_col = db.settings


async def create_indexes():
    """Run this on startup to make searches instant"""
    await logs_col.create_index([("user_id", 1), ("log_date", -1)])
    await weekly_logs_col.create_index([("user_id", 1), ("week_end_date", -1)])
    await dtr_uploads_col.create_index([("user_id", 1), ("uploaded_at", -1)])
    await settings_col.create_index("user_id", unique=True)
    print("⚡ Database Indexes Optimized")