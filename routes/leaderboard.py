from quart import Blueprint, render_template, session, redirect, url_for
from db import logs_col, profiles_col
from bson import ObjectId

# 1. INITIALIZE THE BLUEPRINT FIRST (This fixes the NameError)
leaderboard_bp = Blueprint('leaderboard', __name__)

REQUIRED_HOURS = 486

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    curr_user_id = session['user_id']

    # Aggregation pipeline to calculate totals per user
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
    total_collective_minutes = 0
    finishers_count = 0

    for rank, entry in enumerate(leaders_raw, 1):
        total_m = entry.get('grand_total_minutes', 0)
        total_collective_minutes += total_m
        
        hours_display = round(total_m / 60, 2)
        if hours_display >= REQUIRED_HOURS: 
            finishers_count += 1
        
        profile = entry.get('user_profile', {})
        display_name = profile.get('full_name', 'Anonymous Student')
        
        leaderboard_data.append({
            "rank": rank,
            "name": display_name,
            "hours": hours_display,
            "progress": min(int((total_m / (REQUIRED_HOURS * 60)) * 100), 100),
            "is_current_user": str(entry['_id']) == str(curr_user_id),
            "avatar_char": display_name[0].upper() if display_name else "?"
        })

    # Stats for the top dashboard
    stats = {
        "total_hours": round(total_collective_minutes / 60, 1),
        "finishers": finishers_count,
        "total_students": len(leaderboard_data)
    }

    return await render_template("main/leaderboard.html", leaders=leaderboard_data, stats=stats)