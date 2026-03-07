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

# Serverless approach: 
# Instead of before_serving, we run this once at the module level 
# OR call it inside a route with a check.
@app.before_request
async def startup():
    # This is a simple way to ensure indexes are created once per cold start
    if not hasattr(app, 'indexes_created'):
        await create_indexes()
        app.indexes_created = True

@app.route("/")
async def home():
    return redirect(url_for("tracker.index"))

# IMPORTANT: Do not use app.run() for Vercel. 
# Vercel handles the execution.

if __name__ == "__main__":
    # debug=True for auto-reload and error messages
    # host='0.0.0.0' allows access from other devices in your network
    app.run(port=5000, debug=True)