from quart import Quart, redirect, url_for
from config import Config

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

@app.before_serving
async def startup():
    await create_indexes()

@app.route("/")
async def home():
    return redirect(url_for("tracker.index"))

if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)