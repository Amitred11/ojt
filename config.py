import os

class Config:
    # 1. MongoDB URI
    # Default is None to force an error if missing (better than connecting to localhost in production)
    MONGO_URI = os.environ.get("MONGO_URI")
    
    # 2. Database Name
    # Ensure this matches the specific database inside your Cluster
    DB_NAME = "OJT" 
    
    # 3. Security
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key_change_this_in_prod")
    
    # 4. Upload Limits
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB Limit
    SEND_FILE_MAX_AGE_DEFAULT = 31536000 
    
    # Optimize JSON responses
    JSON_SORT_KEYS = False