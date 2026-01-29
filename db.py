from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client.get_database(Config.DB_NAME)

# Collections
users_col = db.users
logs_col = db.logs          # Used for Section 6 (DTR) and Section 4 (Time)
journal_col = db.journal    # Stores Sections 1, 2, 3, 5 (Profile, Company, Reflections)
journal_entries_col = db.journal_entries # Stores Section 4 (Detailed Daily/Weekly Narratives)
files_col = db.files        # Stores Section 6 (Appendices/Photos)