from quart import Blueprint, render_template, session, redirect, url_for
from db import logs_col
from bson import ObjectId
from datetime import datetime
from utils.achievements import get_achievements

leaderboard_bp = Blueprint('leaderboard', __name__)

REQUIRED_HOURS = 486

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    curr_user_id = str(session['user_id'])

    # 1. MongoDB Aggregation Pipeline
    pipeline = [
        {
            "$project": {
                "user_id": 1,
                "log_date": 1,
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
                "grand_total_minutes": { "$sum": "$log_minutes" },
                "log_count": { "$sum": 1 },
                "last_active": { "$max": "$log_date" }
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
    prev_user_hours = None

    # 2. Process results
    for rank, entry in enumerate(leaders_raw, 1):
        total_m = entry.get('grand_total_minutes', 0)
        total_collective_minutes += total_m 
        
        hours_display = round(total_m / 60, 2)
        
        if hours_display >= REQUIRED_HOURS: 
            finishers_count += 1
        
        gap = 0
        if prev_user_hours is not None:
            gap = round(prev_user_hours - hours_display, 1)
        prev_user_hours = hours_display

        log_count = entry.get('log_count', 0)
        progress = min(int((total_m / (REQUIRED_HOURS * 60)) * 100), 100)
        
        stats = {
            'rank': rank,
            'total_hours': hours_display,
            'log_count': log_count,
            'avg_daily': round(hours_display / log_count, 1) if log_count > 0 else 0,
            'progress': progress
        }
        
        achievements = get_achievements(stats)

        leaderboard_data.append({
            "rank": rank,
            "name": entry.get('user_profile', {}).get('full_name', 'Anonymous Student'),
            "hours": hours_display,
            "gap": gap,
            "achievements": achievements,
            "log_count": log_count,
            "progress": progress,
            "is_current_user": str(entry['_id']) == curr_user_id,
            "avatar_char": entry.get('user_profile', {}).get('full_name', '?')[0].upper() if entry.get('user_profile', {}).get('full_name') else "?"
        })

    # 3. Final Summary Stats for the whole class
    total_students = len(leaderboard_data)
    class_goal_minutes = total_students * REQUIRED_HOURS * 60
    
    global_stats = {
        "total_hours": round(total_collective_minutes / 60, 1),
        "finishers": finishers_count,
        "total_students": total_students,
        "class_progress": min(int((total_collective_minutes / class_goal_minutes) * 100), 100) if class_goal_minutes > 0 else 0,
        "velocity": round((total_collective_minutes / 60) / total_students, 1) if total_students > 0 else 0
    }

    return await render_template("main/leaderboard.html", leaders=leaderboard_data, stats=global_stats)