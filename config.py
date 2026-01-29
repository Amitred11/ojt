import os

class Config:
    # Remove the link from the second argument!
    # If the variable isn't found, it returns None (causing an error), which is safer than leaking data.
    MONGO_URI = os.environ.get("MONGO_URI") 
    
    DB_NAME = "OJT"
    SECRET_KEY = os.environ.get("SECRET_KEY", "local_secret_key")
    REGISTRATION_KEY = "2026"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024