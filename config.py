import os

class Config:
    # Use Environment Variable in Vercel, or fallback to the provided link
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://amadoreleoncio:d60N5tmrtcA1cdZh@pf.okaqzml.mongodb.net/OJT?retryWrites=true&w=majority&appName=PF")
    DB_NAME = "OJT"
    SECRET_KEY = os.environ.get("SECRET_KEY", "ojt_secret_key_change_me")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB Max Upload