from quart import Quart, redirect, url_for, render_template # Add render_template
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

# --- CUSTOM ERROR HANDLERS ---

@app.route("/offline")
async def offline():
    return await render_template('main/errors.html', 
        code="OFFLINE", 
        message="Connection lost. Your training progress is paused until you're back online.")

@app.errorhandler(404)
async def error_404(e):
    return await render_template('main/errors.html', 
        code=404, 
        message="The page you are looking for has been moved to another dimension or never existed."), 404

@app.errorhandler(429)
async def error_429(e):
    return await render_template('main/errors.html', 
        code=429, 
        message="Slow down, Trainee! You're sending requests too fast. Please wait a moment."), 429

@app.errorhandler(400)
async def error_400(e):
    return await render_template('main/errors.html', 
        code=400, 
        message="The server couldn't understand that request. Try clearing your cache or logging in again."), 400

@app.errorhandler(500)
async def error_500(e):
    return await render_template('main/errors.html', 
        code=500, 
        message="Our systems hit a snag. We've notified the admins to check the logs."), 500

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(tracker_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(leaderboard_bp)

# OPTIMIZED STARTUP: Don't block the user
@app.before_request
async def startup():
    if not hasattr(app, 'indexes_created'):
        # asyncio.create_task runs this in the background 
        # so the website loads IMMEDIATELY without waiting for the DB
        asyncio.create_task(create_indexes()) 
        app.indexes_created = True

@app.route("/")
async def home():
    from quart import session
    # If logged in, go to tracker. If not, go straight to login.
    # This avoids the middle "302" redirect.
    if 'user_id' in session:
        return redirect(url_for("tracker.index"))
    return redirect(url_for("auth.login"))

# Manual trigger if you ever need to force index creation
@app.route("/admin/init-db")
async def init_db():
    await create_indexes()
    return "Database Optimized!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)