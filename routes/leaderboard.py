from quart import Blueprint, render_template, session, redirect, url_for, request
from db import logs_col, users_col, profiles_col # Added profiles_col to imports
from bson import ObjectId
from datetime import datetime
from utils.achievements import get_achievements

leaderboard_bp = Blueprint('leaderboard', __name__)

REQUIRED_HOURS = 486
DAILY_CAP_MINUTES = 480
OT_START_TIME = "17:00"

# --- HELPER FUNCTIONS ---
def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        t1 = datetime.strptime(t_in, "%H:%M")
        t2 = datetime.strptime(t_out, "%H:%M")
        return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
    except: return 0

def calculate_ot_minutes(pm_out):
    if not pm_out: return 0
    try:
        out_time = datetime.strptime(pm_out, "%H:%M")
        threshold = datetime.strptime(OT_START_TIME, "%H:%M")
        return int((out_time - threshold).total_seconds() // 60) if out_time > threshold else 0
    except: return 0

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    curr_user_id = str(session['user_id'])
    ranking_mode = request.args.get('mode', 'official')

    # 1. Fetch Data
    all_logs = await logs_col.find({}).to_list(None)
    all_profiles = await profiles_col.find({}).to_list(None)
    profile_map = {str(p['user_id']): p.get('full_name', 'Anonymous') for p in all_profiles}
    
    user_stats = {}

    # 2. Process Logs (Python Logic for 100% Accuracy)
    for log in all_logs:
        uid = str(log.get('user_id'))
        if uid not in user_stats:
            user_stats[uid] = {
                'raw_minutes': 0,
                'credited_minutes': 0,
                'log_count': 0
            }
        
        # Calculate exactly like Tracker
        am_m = get_minutes_diff(log.get('am_in'), log.get('am_out'))
        pm_m = get_minutes_diff(log.get('pm_in'), log.get('pm_out'))
        raw_ot = calculate_ot_minutes(log.get('pm_out'))
        
        total_raw = am_m + pm_m
        
        # LOGIC: (Total Raw - OT) capped at 8h, THEN add OT back
        reg_m = min(total_raw - raw_ot, DAILY_CAP_MINUTES)
        credited = reg_m + raw_ot 

        user_stats[uid]['raw_minutes'] += total_raw
        user_stats[uid]['credited_minutes'] += credited
        user_stats[uid]['log_count'] += 1

    leaderboard_data = []
    total_collective_minutes = 0
    finishers_count = 0

    # 3. Build List
    for uid, stats in user_stats.items():
        name = profile_map.get(uid, "Unknown Student")
        
        raw_h = stats['raw_minutes'] / 60
        credited_h = stats['credited_minutes'] / 60
        
        if ranking_mode == 'official':
            primary_h = round(credited_h, 2)
            secondary_h = round(raw_h, 2)
            sort_val = stats['credited_minutes']
        else:
            primary_h = round(raw_h, 2)
            secondary_h = round(credited_h, 2)
            sort_val = stats['raw_minutes']

        total_collective_minutes += stats['credited_minutes']
        if primary_h >= REQUIRED_HOURS: finishers_count += 1
        
        progress = min(int((stats['credited_minutes'] / (REQUIRED_HOURS * 60)) * 100), 100)
        
        # Calculate Average Daily here
        avg_daily = round(primary_h / stats['log_count'], 1) if stats['log_count'] > 0 else 0
        
        ach_stats = {
            'total_hours': primary_h,
            'log_count': stats['log_count'],
            'avg_daily': avg_daily,
            'progress': progress
        }

        leaderboard_data.append({
            "name": name,
            "hours": primary_h,
            "secondary_hours": secondary_h,
            "sort_val": sort_val,
            "log_count": stats['log_count'],
            "avg_daily": avg_daily,  # <--- FIXED: Added this missing variable
            "progress": progress,
            "achievements": get_achievements(ach_stats),
            "is_current_user": uid == curr_user_id,
            "avatar_char": name[0].upper() if name else "?"
        })

    # 4. Sort
    leaderboard_data.sort(key=lambda x: x['sort_val'], reverse=True)

    # 5. Add Ranks and Gap
    prev_hours = None
    final_data = []
    for i, d in enumerate(leaderboard_data, 1):
        d['rank'] = i
        d['gap'] = round(prev_hours - d['hours'], 1) if prev_hours else 0
        prev_hours = d['hours']
        final_data.append(d)

    # 6. Global Stats
    total_students = len(final_data)
    class_goal_minutes = total_students * REQUIRED_HOURS * 60
    
    global_stats = {
        "total_hours": round(total_collective_minutes / 60, 1),
        "finishers": finishers_count,
        "total_students": total_students,
        "class_progress": min(int((total_collective_minutes / class_goal_minutes) * 100), 100) if class_goal_minutes > 0 else 0,
        "velocity": round((total_collective_minutes / 60) / total_students, 1) if total_students > 0 else 0,
        "ranking_mode": ranking_mode
    }

    return await render_template("main/leaderboard.html", leaders=final_data, stats=global_stats)