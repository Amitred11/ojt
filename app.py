from quart import Quart, redirect, url_for
from config import Config
import asyncio

# Import Blueprints
from routes.auth import auth_bp
from routes.tracker import tracker_bp
from routes.portfolio import portfolio_bp
from routes.leaderboard import leaderboard_bp

# Import DB Init
from db import create_indexes

app = Quart(__name__)
app.config.from_object(Config)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(tracker_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(leaderboard_bp)

# OPTIMIZED STARTUP: Don't block the user
@app.before_request
async def startup():
    if not hasattr(app, 'indexes_created'):
        # We use a Task so it runs in the background 
        # without making the user wait for the DB
        asyncio.create_task(create_indexes())
        app.indexes_created = True

@app.route("/")
async def home():
    return redirect(url_for("tracker.index"))

# Manual trigger if you ever need to force index creation
@app.route("/admin/init-db")
async def init_db():
    await create_indexes()
    return "Database Optimized!"

if __name__ == "__main__":
    app.run(port=5000, debug=True)