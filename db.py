from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client.get_database(Config.DB_NAME)

# Collections
users_col = db.users
logs_col = db.logs
reports_col = db.reports