from quart import Blueprint, render_template, session, redirect, url_for
from db import logs_col, profiles_col, users_col

leaderboard_bp = Blueprint('leaderboard', __name__)
REQUIRED_HOURS = 486

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))

    # 1. Aggregate Total Hours per User from Logs
    pipeline = [
        {
            "$group": {
                "_id": "$user_id",
                "total_hours": {"$sum": "$hours"}
            }
        },
        {"$sort": {"total_hours": -1}} # Sort Highest to Lowest
    ]
    
    leaders_raw = await logs_col.aggregate(pipeline).to_list(length=None)

    # 2. Enrich data with User Profile info (Names, Courses)
    leaderboard_data = []
    
    for rank, entry in enumerate(leaders_raw, 1):
        user_id = entry['_id']
        hours = entry['total_hours']
        
        # Get Profile details
        profile = await profiles_col.find_one({"user_id": user_id})
        
        # Fallback if profile not set up yet
        if not profile:
            user = await users_col.find_one({"_id": ObjectId(user_id)}) if 'ObjectId' in globals() else None
            display_name = "Unknown User"
            # Try to fetch username if we can (requires importing ObjectId)
            # For simplicity, we skip complex user lookup if profile is missing
        else:
            display_name = profile.get('full_name', 'Student')
            course = profile.get('course', 'BSIT')

        # Calculate Progress
        progress = min((hours / REQUIRED_HOURS) * 100, 100)
        
        leaderboard_data.append({
            "rank": rank,
            "name": display_name,
            "hours": round(hours, 2),
            "progress": int(progress),
            "is_current_user": user_id == session['user_id']
        })

    return await render_template("leaderboard.html", leaders=leaderboard_data)