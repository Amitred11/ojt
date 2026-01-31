from quart import Blueprint, render_template, session, redirect, url_for
from db import logs_col, profiles_col
from bson import ObjectId

leaderboard_bp = Blueprint('leaderboard', __name__)
REQUIRED_HOURS = 486

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    curr_user_id = session['user_id']

    # This pipeline calculates the total for each user by:
    # 1. Checking if 'total_minutes' exists.
    # 2. If not, converting 'hours' to minutes (hours * 60).
    # 3. Summing them all together before joining with profiles.
    pipeline = [
        {
            "$project": {
                "user_id": 1,
                "log_minutes": {
                    "$cond": {
                        "if": { "$gt": ["$total_minutes", 0] },
                        "then": "$total_minutes",
                        "else": { "$multiply": [{ "$ifNull": ["$hours", 0] }, 60] }
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "grand_total_minutes": { "$sum": "$log_minutes" }
            }
        },
        {
            "$lookup": {
                "from": "profiles",
                "localField": "_id",
                "foreignField": "user_id",
                "as": "user_profile"
            }
        },
        {"$unwind": {"path": "$user_profile", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"grand_total_minutes": -1}}
    ]
    
    leaders_raw = await logs_col.aggregate(pipeline).to_list(length=None)
    leaderboard_data = []
    
    for rank, entry in enumerate(leaders_raw, 1):
        total_m = entry.get('grand_total_minutes', 0)
        
        # Convert total minutes back to hours for display (e.g., 114.88)
        hours_display = round(total_m / 60, 2)
        
        profile = entry.get('user_profile', {})
        display_name = profile.get('full_name', 'Anonymous Student')
        
        leaderboard_data.append({
            "rank": rank,
            "name": display_name,
            "hours": hours_display,
            "progress": min(int((total_m / (REQUIRED_HOURS * 60)) * 100), 100),
            "is_current_user": entry['_id'] == curr_user_id,
            "avatar_char": display_name[0].upper() if display_name else "?"
        })

    return await render_template("main/leaderboard.html", leaders=leaderboard_data)