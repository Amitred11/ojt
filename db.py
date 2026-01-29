from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client.get_database(Config.DB_NAME)

# Collections
users_col = db.users
logs_col = db.logs          # For the Tracker/DTR
journal_col = db.journal    # For Profile, Company, Reflections
journal_entries_col = db.journal_entries # For Daily/Weekly Work Logs
files_col = db.files        # For Appendices (Photos, Certs)