import os
from quart import Quart, redirect, url_for
from config import Config

# Get the absolute path to this file's directory
base_dir = os.path.dirname(os.path.abspath(__file__))

# Initialize app with explicit paths
app = Quart(__name__, 
            template_folder=os.path.join(base_dir, 'templates'),
            static_folder=os.path.join(base_dir, 'static'))

app.config.from_object(Config)

# Import Blueprints AFTER app initialization to avoid circular imports
from routes.auth import auth_bp
from routes.tracker import tracker_bp
from routes.portfolio import portfolio_bp
from routes.leaderboard import leaderboard_bp
from db import create_indexes

app.register_blueprint(auth_bp)
app.register_blueprint(tracker_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(leaderboard_bp)

@app.before_request
async def startup():
    if not hasattr(app, 'indexes_created'):
        try:
            await create_indexes()
            app.indexes_created = True
        except Exception as e:
            print(f"Index creation failed: {e}")

@app.route("/")
async def home():
    return redirect(url_for("tracker.index"))