from quart import Blueprint, render_template, session, redirect, url_for, request # Added request
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
    # Get ranking mode from URL (default to 'official')
    ranking_mode = request.args.get('mode', 'official')

    # 1. Updated MongoDB Aggregation Pipeline
    pipeline = [
        {
            "$project": {
                "user_id": 1,
                "log_date": 1,
                "raw_minutes": {
                    "$cond": {
                        "if": { "$gt": ["$total_minutes", 0] },
                        "then": "$total_minutes",
                        "else": { "$multiply": [{ "$ifNull": ["$hours", 0] }, 60] }
                    }
                }
            }
        },
        {
            # FEATURE: Corrected Aggregation using $min [raw, 480]
            "$project": {
                "user_id": 1,
                "log_date": 1,
                "raw_minutes": 1,
                "capped_minutes": { "$min": ["$raw_minutes", 480] }
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "grand_total_raw": { "$sum": "$raw_minutes" },
                "grand_total_capped": { "$sum": "$capped_minutes" },
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
        # Sort based on the selected mode
        {"$sort": { ("grand_total_capped" if ranking_mode == 'official' else "grand_total_raw"): -1}}
    ]
    
    leaders_raw = await logs_col.aggregate(pipeline).to_list(length=None)
    
    leaderboard_data = []
    total_collective_minutes = 0
    finishers_count = 0
    prev_user_hours = None

    # 2. Process results
    for rank, entry in enumerate(leaders_raw, 1):
        raw_m = entry.get('grand_total_raw', 0)
        capped_m = entry.get('grand_total_capped', 0)
        
        # Decide which hours are primary vs secondary
        if ranking_mode == 'official':
            primary_h = round(capped_m / 60, 2)
            secondary_h = round(raw_m / 60, 2)
        else:
            primary_h = round(raw_m / 60, 2)
            secondary_h = round(capped_m / 60, 2)

        total_collective_minutes += capped_m # Global stats usually track official progress
        
        if primary_h >= REQUIRED_HOURS: 
            finishers_count += 1
        
        gap = 0
        if prev_user_hours is not None:
            gap = round(prev_user_hours - primary_h, 1)
        prev_user_hours = primary_h

        log_count = entry.get('log_count', 0)
        progress = min(int((capped_m / (REQUIRED_HOURS * 60)) * 100), 100)
        
        stats = {
            'rank': rank,
            'total_hours': primary_h,
            'log_count': log_count,
            'avg_daily': round(primary_h / log_count, 1) if log_count > 0 else 0,
            'progress': progress
        }
        
        achievements = get_achievements(stats)

        leaderboard_data.append({
            "rank": rank,
            "name": entry.get('user_profile', {}).get('full_name', 'Anonymous Student'),
            "hours": primary_h,
            "secondary_hours": secondary_h, # FEATURE: Double Hour Display
            "gap": gap,
            "achievements": achievements,
            "log_count": log_count,
            "progress": progress,
            "is_current_user": str(entry['_id']) == curr_user_id,
            "avatar_char": entry.get('user_profile', {}).get('full_name', '?')[0].upper() if entry.get('user_profile', {}).get('full_name') else "?"
        })

    # 3. Final Summary Stats
    total_students = len(leaderboard_data)
    class_goal_minutes = total_students * REQUIRED_HOURS * 60
    
    global_stats = {
        "total_hours": round(total_collective_minutes / 60, 1),
        "finishers": finishers_count,
        "total_students": total_students,
        "class_progress": min(int((total_collective_minutes / class_goal_minutes) * 100), 100) if class_goal_minutes > 0 else 0,
        "velocity": round((total_collective_minutes / 60) / total_students, 1) if total_students > 0 else 0,
        "ranking_mode": ranking_mode # Pass mode to template
    }

    return await render_template("main/leaderboard.html", leaders=leaderboard_data, stats=global_stats)