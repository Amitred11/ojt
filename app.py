from quart import Quart, redirect, url_for
from config import Config
from routes.auth import auth_bp
from routes.tracker import tracker_bp
from routes.portfolio import portfolio_bp
from routes.leaderboard import leaderboard_bp

app = Quart(__name__)
app.config.from_object(Config)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(tracker_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(leaderboard_bp) 

@app.route("/")
async def home():
    return redirect(url_for("tracker.index"))

# Required for Vercel to detect the app
if __name__ == "__main__":
    app.run(debug=True)