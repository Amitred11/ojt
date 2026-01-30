import os
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

# 1. Initialize Client
# We use the URI from Config. If it fails, check your .env or Vercel settings.
if not Config.MONGO_URI:
    raise ValueError("No MONGO_URI found! Set it in your .env file or Vercel Environment Variables.")

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client[Config.DB_NAME]

# 2. Export Collections (For auth.py, tracker.py, leaderboard.py)
users_col = db.users
logs_col = db.logs
profiles_col = db.profiles

# These are needed for portfolio.py if we were to use direct access, 
# but portfolio uses get_db(), which we define below.
weekly_logs_col = db.weekly_logs
reflections_col = db.reflections
dtr_uploads_col = db.dtr_uploads

# 3. Export Helper Function (For portfolio.py)
def get_db():
    """Returns the database instance for routes that use the get_db pattern."""
    return db