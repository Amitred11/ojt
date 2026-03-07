from quart import Blueprint, render_template, session, redirect, url_for, request, jsonify
from db import logs_col, users_col, profiles_col, settings_col, notifications_col
from bson import ObjectId
from datetime import datetime, date, timedelta
from utils.achievements import get_achievements 

leaderboard_bp = Blueprint('leaderboard', __name__)

REQUIRED_HOURS = 486
PH_HOLIDAYS = [
    "2026-01-01", "2026-02-17", "2026-04-02", "2026-04-03", "2026-04-04", 
    "2026-04-09", "2026-05-01", "2026-06-12", "2026-08-31", "2026-11-01", 
    "2026-11-30", "2026-12-08", "2026-12-25", "2026-12-30"
]

def normalize_time(t_str):
    if not t_str or ":" not in t_str: return None
    try:
        parts = t_str.split(':')
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except: return None

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        t1 = datetime.strptime(normalize_time(t_in), "%H:%M")
        t2 = datetime.strptime(normalize_time(t_out), "%H:%M")
        return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
    except: return 0

def calculate_ot_minutes(pm_out):
    if not pm_out: return 0
    try:
        out_time = datetime.strptime(normalize_time(pm_out), "%H:%M")
        threshold = datetime.strptime("17:00", "%H:%M")
        return int((out_time - threshold).total_seconds() // 60) if out_time > threshold else 0
    except: return 0

def calculate_finish_date(remaining_minutes, avg_daily_m):
    if remaining_minutes <= 0: return "Completed"
    proj_speed = avg_daily_m if avg_daily_m > 60 else 480
    current_date = date.today()
    temp_m = remaining_minutes
    loops = 0
    while temp_m > 0 and loops < 1000:
        current_date += timedelta(days=1)
        is_weekend = current_date.weekday() >= 5
        is_holiday = current_date.isoformat() in PH_HOLIDAYS
        if not is_holiday and not is_weekend:
            temp_m -= proj_speed
        loops += 1
    return current_date.strftime("%b %d")

@leaderboard_bp.route("/leaderboard/social", methods=["POST"])
async def social_interaction():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = await request.get_json()
    sender_id = str(session['user_id'])
    target_uid = data.get('target_uid')
    action_type = data.get('type') # 'cheer' or 'nudge'

    if not target_uid or sender_id == target_uid:
        return jsonify({"status": "error", "message": "Invalid target"}), 400

    # Get sender name for the notification
    sender_profile = await profiles_col.find_one({"user_id": ObjectId(sender_id)})
    sender_name = sender_profile.get('full_name', 'Someone') if sender_profile else "Someone"

    # Save interaction
    await notifications_col.insert_one({
        "sender_id": sender_id,
        "sender_name": sender_name,
        "target_uid": target_uid,
        "type": action_type,
        "created_at": datetime.utcnow(),
        "is_read": False
    })

    return jsonify({"status": "success", "type": action_type})

@leaderboard_bp.route("/leaderboard")
async def index():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    curr_user_id = str(session['user_id'])
    all_logs = await logs_col.find({}).to_list(None)
    all_profiles = await profiles_col.find({}).to_list(None)
    all_settings = await settings_col.find({}).to_list(None)
    
    profile_map = {str(p['user_id']): p.get('full_name', 'Anonymous') for p in all_profiles}
    settings_map = {str(s['user_id']): s for s in all_settings}
    
    user_stats = {}
    for log in all_logs:
        uid = str(log.get('user_id'))
        if uid not in user_stats:
            user_stats[uid] = {'credited_minutes': 0, 'log_count': 0}
        
        u_set = settings_map.get(uid, {"strict_8h": False, "count_lunch": False, "allow_before_7am": False, "allow_after_5pm": True, "include_weekends_eta": False})
        log_date = log.get('log_date', "")
        is_weekend = False
        try: is_weekend = datetime.strptime(log_date, '%Y-%m-%d').weekday() >= 5
        except: pass

        nai, nao, npi, npo = normalize_time(log.get('am_in')), normalize_time(log.get('am_out')), normalize_time(log.get('pm_in')), normalize_time(log.get('pm_out'))
        eff_ai = "08:00" if (not u_set.get('allow_before_7am') and nai and nai < "08:00") else nai
        
        m_am = get_minutes_diff(eff_ai, nao)
        m_pm = get_minutes_diff(npi, npo)
        m_lunch = 60 if (u_set.get('count_lunch') and nao and npi and "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15") else 0
        day_ot = calculate_ot_minutes(npo) if u_set.get('allow_after_5pm') else 0
        
        day_credited = m_am + m_pm + m_lunch
        if u_set.get('strict_8h'): day_credited = min(day_credited, 480)
        else: day_credited += day_ot
            
        if is_weekend and not u_set.get('include_weekends_eta'): day_credited = 0
        user_stats[uid]['credited_minutes'] += day_credited
        if day_credited > 0: user_stats[uid]['log_count'] += 1

    leaderboard_data = []
    total_collective_minutes = 0
    finishers_count = 0
    curr_user_final_hours = 0

    for uid, stats in user_stats.items():
        name = profile_map.get(uid, "Unknown Student")
        credited_h = stats['credited_minutes'] / 60
        total_collective_minutes += stats['credited_minutes']
        if credited_h >= REQUIRED_HOURS: finishers_count += 1
        if uid == curr_user_id: curr_user_final_hours = credited_h
        
        progress = min(int((stats['credited_minutes'] / (REQUIRED_HOURS * 60)) * 100), 100)
        avg_daily = round(credited_h / stats['log_count'], 1) if stats['log_count'] > 0 else 0
        rem_m = max(0, (REQUIRED_HOURS * 60) - stats['credited_minutes'])
        avg_m = stats['credited_minutes'] / stats['log_count'] if stats['log_count'] > 0 else 480
        est_finish = calculate_finish_date(rem_m, avg_m)

        leaderboard_data.append({
            "uid": uid, "name": name, "hours": round(credited_h, 2),
            "sort_val": stats['credited_minutes'], "log_count": stats['log_count'], 
            "avg_daily": avg_daily, "progress": progress, "is_current_user": uid == curr_user_id, 
            "avatar_char": name[0].upper() if name else "?", "est_finish": est_finish
        })

    leaderboard_data.sort(key=lambda x: x['sort_val'], reverse=True)
    prev_hours, final_data = None, []
    for i, d in enumerate(leaderboard_data, 1):
        d['rank'] = i
        d['achievements'] = get_achievements({'rank': i, 'total_hours': d['hours'], 'log_count': d['log_count'], 'avg_daily': d['avg_daily'], 'progress': d['progress']})
        d['gap'] = round(prev_hours - d['hours'], 1) if prev_hours is not None else 0
        prev_hours = d['hours']
        final_data.append(d)

    total_students = len(final_data)
    class_goal_minutes = total_students * REQUIRED_HOURS * 60
    
    global_stats = {
        "total_hours": round(total_collective_minutes / 60, 1),
        "finishers": finishers_count, "total_students": total_students,
        "class_progress": min(int((total_collective_minutes / class_goal_minutes) * 100), 100) if class_goal_minutes > 0 else 0,
        "velocity": round((total_collective_minutes / 60) / total_students, 1) if total_students > 0 else 0,
        "user_hours": round(curr_user_final_hours, 1)
    }

    return await render_template("main/leaderboard.html", leaders=final_data, stats=global_stats)