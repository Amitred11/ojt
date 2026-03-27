from quart import Quart, redirect, url_for, render_template, session, request
from config import Config
import asyncio
import os

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

@app.context_processor
def override_url_for():
    # We pass the function itself to the template context
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    """
    Standard url_for wrapper that adds a version query string (?v=...) 
    based on the file's last modified timestamp.
    """
    if endpoint == 'static':
        filename = values.get('filename')
        if filename:
            # Construct path: root/static/filename
            file_path = os.path.join(app.root_path, 'static', filename)
            if os.path.exists(file_path):
                # Add a version timestamp (v=123456789)
                values['v'] = int(os.path.getmtime(file_path))
    
    # Use Quart's built-in url_for to generate the final string
    return url_for(endpoint, **values)

@app.before_request
async def check_maintenance_mode():
    # Allow admin to always access, and allow login/logout/admin pages
    if request.endpoint in ['auth.login', 'auth.logout', 'init_db'] or \
       request.path.startswith('/admin') or \
       request.path.startswith('/static'):
        return

    from db import settings_col
    config = await settings_col.find_one({"type": "global_config"})
    if config and config.get('maintenance_mode'):
        return await render_template('main/errors.html', 
            code="FIXING", 
            message="The system is currently undergoing a core update. Please standby.")

@app.context_processor
async def inject_global_settings():
    from db import settings_col
    config = await settings_col.find_one({"type": "global_config"})
    return {
        "system_broadcast": config.get('system_broadcast'),
        "maintenance_mode": config.get('maintenance_mode', False) if config else False
    }

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)