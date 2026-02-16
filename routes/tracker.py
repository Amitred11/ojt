from datetime import datetime, date, timedelta, timezone
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)

# Constants
REQUIRED_HOURS = 486
DAILY_CAP_MINUTES = 480 
OT_START_TIME = "17:00"

# Philippine Holidays 2026
PH_HOLIDAYS = [
    "2026-01-01", "2026-02-17", "2026-04-02", "2026-04-03", "2026-04-09", 
    "2026-05-01", "2026-06-12", "2026-08-31", "2026-11-01", "2026-11-30", 
    "2026-12-08", "2026-12-25", "2026-12-30"
]

def minutes_to_string(total_minutes):
    if total_minutes < 0: total_minutes = 0
    h = int(total_minutes // 60)
    m = int(total_minutes % 60)
    return f"{h}h {m}m"

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

def calculate_finish_date(remaining_minutes, avg_daily_m):
    if remaining_minutes <= 0: return {"date": "Completed", "days_left": 0, "calendar_days": 0}
    
    proj_speed = DAILY_CAP_MINUTES
    
    work_days_left = remaining_minutes / proj_speed
    
    current_date = date.today()
    start_date = current_date
    temp_m = remaining_minutes
    
    max_loops = 1000
    loops = 0

    while temp_m > 0 and loops < max_loops:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5 and current_date.isoformat() not in PH_HOLIDAYS:
            temp_m -= proj_speed
        loops += 1
            
    return {
        "date": current_date.strftime("%b %d, %Y"),
        "days_left": work_days_left,
        "calendar_days": (current_date - start_date).days
    }

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    if 'allow_ot' not in session: session['allow_ot'] = True

    if request.method == "POST":
        form = await request.form
        if "toggle_ot_policy" in form:
            session['allow_ot'] = not session['allow_ot']
            return redirect(url_for("tracker.index"))
        
        log_id, log_date = form.get("log_id"), form.get("log_date")
        am_in, am_out = form.get("am_in", ""), form.get("am_out", "")
        pm_in, pm_out = form.get("pm_in", ""), form.get("pm_out", "")
        
        # --- CALCULATE MINUTES BEFORE SAVING ---
        am_m = get_minutes_diff(am_in, am_out)
        pm_m = get_minutes_diff(pm_in, pm_out)
        raw_ot = calculate_ot_minutes(pm_out)
        
        # Calculate totals
        total_raw_minutes = am_m + pm_m
        # Logic: (Total - OT) is capped at 8hrs, then add OT back
        reg_m = min(total_raw_minutes - raw_ot, DAILY_CAP_MINUTES)
        credited_minutes = reg_m + raw_ot # Always credit OT in DB, filter in UI
        
        log_data = {
            "user_id": user_id, 
            "log_date": log_date, 
            "am_in": am_in, "am_out": am_out, 
            "pm_in": pm_in, "pm_out": pm_out,
            # SAVE INTEGERS FOR LEADERBOARD ACCURACY
            "total_minutes": total_raw_minutes,
            "credited_minutes": credited_minutes,
            "ot_minutes": raw_ot
        }
        
        if log_id: await logs_col.update_one({"_id": ObjectId(log_id)}, {"$set": log_data})
        else: await logs_col.update_one({"log_date": log_date, "user_id": user_id}, {"$set": log_data}, upsert=True)
        return redirect(url_for("tracker.index"))

    raw_logs = await logs_col.find({"user_id": user_id}).sort("log_date", -1).to_list(None)
    allow_ot = session.get('allow_ot', True)
    
    total_credited_m, total_raw_m, total_ot_m, am_total_m, pm_total_m = 0, 0, 0, 0, 0
    processed_logs = []
    
    for rl in raw_logs:
        # Re-calculate for display integrity or use saved values
        am_m = get_minutes_diff(rl.get('am_in'), rl.get('am_out'))
        pm_m = get_minutes_diff(rl.get('pm_in'), rl.get('pm_out'))
        raw_ot = calculate_ot_minutes(rl.get('pm_out'))
        
        reg_m = min((am_m + pm_m) - raw_ot, DAILY_CAP_MINUTES)
        # Apply session policy
        credited = reg_m + (raw_ot if allow_ot else 0)
        
        total_raw_m += (am_m + pm_m)
        total_credited_m += credited
        total_ot_m += (raw_ot if allow_ot else 0)
        am_total_m += am_m
        pm_total_m += pm_m
        
        log_dt = datetime.strptime(rl['log_date'], '%Y-%m-%d')
        processed_logs.append({
            **rl, 'id': str(rl['_id']), 'credited_m': credited, 'total_m': am_m + pm_m,
            'display_day': log_dt.strftime('%d'), 'display_weekday': log_dt.strftime('%A'),
            'month_key': log_dt.strftime('%B %Y'),
            'raw_str': minutes_to_string(am_m + pm_m), 'credited_str': minutes_to_string(credited),
            'am_str': f"{rl.get('am_in')} - {rl.get('am_out')}" if rl.get('am_in') else "-",
            'pm_str': f"{rl.get('pm_in')} - {rl.get('pm_out')}" if rl.get('pm_in') else "-",
            'status_color': 'emerald' if raw_ot > 0 and allow_ot else 'slate'
        })

    log_count = len(processed_logs)
    avg_m = total_credited_m / log_count if log_count > 0 else 480
    recent_avg = sum(l['credited_m'] for l in processed_logs[:5]) / 5 if log_count >= 5 else avg_m
    pulse_trend = "up" if recent_avg >= avg_m else "down"
    
    milestones = [
        {"label": "The Start", "target": 1, "done": total_credited_m >= 60},
        {"label": "Quarter Way", "target": 121, "done": (total_credited_m/60) >= 121},
        {"label": "Halfway Hero", "target": 243, "done": (total_credited_m/60) >= 243},
        {"label": "Final Stretch", "target": 437, "done": (total_credited_m/60) >= 437},
    ]
    next_ms = next((m for m in milestones if not m['done']), milestones[-1])
    ms_progress = min(((total_credited_m/60) / next_ms['target']) * 100, 100) if next_ms['target'] > 0 else 100

    grouped = {}
    for l in processed_logs:
        if l['month_key'] not in grouped: grouped[l['month_key']] = {'logs': [], 'month_total_m': 0}
        grouped[l['month_key']]['logs'].append(l)
        grouped[l['month_key']]['month_total_m'] += l['credited_m']
    for k in grouped: grouped[k]['month_total_str'] = minutes_to_string(grouped[k]['month_total_m'])

    streak, check_d = 0, date.today()
    log_dates = sorted([datetime.strptime(l['log_date'], '%Y-%m-%d').date() for l in processed_logs], reverse=True)
    for ld in log_dates:
        if ld == check_d: streak += 1; check_d -= timedelta(days=1)
        elif ld < check_d: break

    return await render_template(
        "main/index.html", grouped_logs=grouped, total_str=minutes_to_string(total_credited_m),
        total_raw_str=minutes_to_string(total_raw_m), remaining_str=minutes_to_string(max(0, (REQUIRED_HOURS*60)-total_credited_m)),
        progress=min((total_credited_m/(REQUIRED_HOURS*60))*100, 100), today=date.today().isoformat(),
        avg_speed=round(avg_m/60, 1), finish_info=calculate_finish_date(max(0, (REQUIRED_HOURS*60)-total_credited_m), avg_m),
        streak=streak, milestones=milestones, am_perc=round((am_total_m/((am_total_m+pm_total_m) or 1))*100),
        pm_perc=round((pm_total_m/((am_total_m+pm_total_m) or 1))*100), allow_ot=allow_ot,
        ot_str=minutes_to_string(total_ot_m), productivity_idx=round((total_credited_m/(total_raw_m or 1))*100),
        next_ms=next_ms, ms_progress=ms_progress, pulse_trend=pulse_trend, log_count=log_count
    )

@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session: await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))