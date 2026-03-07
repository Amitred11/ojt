from datetime import datetime, date, timedelta, timezone
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col, db, settings_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)

# Philippine Holidays 2026
PH_HOLIDAYS = [
    "2026-01-01", "2026-02-17", "2026-04-02", "2026-04-03", "2026-04-04", 
    "2026-04-09", "2026-05-01", "2026-06-12", "2026-08-31", "2026-11-01", 
    "2026-11-30", "2026-12-08", "2026-12-25", "2026-12-30"
]

async def get_user_settings(user_id):
    settings = await settings_col.find_one({"user_id": user_id})
    if not settings:
        return {
            "required_hours": 486,
            "strict_8h": False,
            "count_lunch": False,
            "allow_before_7am": False,
            "allow_after_5pm": True,
            "allow_weekend_duty": False, # Renamed for clarity
            "allow_holiday_duty": False
        }
    return settings

def minutes_to_string(total_minutes):
    if total_minutes < 0: total_minutes = 0
    h = int(total_minutes // 60)
    m = int(total_minutes % 60)
    return f"{h}h {m}m"

def normalize_time(t_str):
    """Ensures '8:00' becomes '08:00' for reliable comparison."""
    if not t_str or ":" not in t_str: return None
    try:
        parts = t_str.split(':')
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except: return None

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        # Normalize to HH:MM
        t1 = datetime.strptime(normalize_time(t_in), "%H:%M")
        t2 = datetime.strptime(normalize_time(t_out), "%H:%M")
        return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
    except: return 0

def calculate_ot_minutes(pm_out):
    if not pm_out: return 0
    try:
        out_time = datetime.strptime(pm_out, "%H:%M")
        threshold = datetime.strptime("17:00", "%H:%M")
        return int((out_time - threshold).total_seconds() // 60) if out_time > threshold else 0
    except: return 0

def calculate_finish_date(remaining_minutes, settings, actual_avg_m):
    if remaining_minutes <= 0: 
        return {"date": "Completed", "days_left": 0, "calendar_days": 0}
    
    # Projection Pace (minimum 8h if average is too low)
    proj_speed = actual_avg_m if actual_avg_m > 60 else 480 
    
    current_date = date.today()
    start_date = current_date
    temp_m = remaining_minutes
    
    max_loops = 2000 
    loops = 0
    
    while temp_m > 0 and loops < max_loops:
        current_date += timedelta(days=1)
        is_weekend = current_date.weekday() >= 5
        is_holiday = current_date.isoformat() in PH_HOLIDAYS
        
        # PERSISTENT PROJECTION LOGIC:
        # We ALWAYS skip weekends and holidays for future projection.
        # This keeps the ETA stable. The date only moves "closer" 
        # because weekend/holiday logs reduce the 'remaining_minutes' total.
        if not is_weekend and not is_holiday:
            temp_m -= proj_speed
            
        loops += 1
        
    return {
        "date": current_date.strftime("%b %d, %Y"),
        "days_left": remaining_minutes / proj_speed,
        "calendar_days": (current_date - start_date).days
    }

def get_day_type(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        if date_str in PH_HOLIDAYS: return "Holiday"
        if dt.weekday() >= 5: return "Weekend"
        return "Work Day"
    except: return "Unknown"

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    settings = await get_user_settings(user_id)
    
    if request.method == "POST":
        form = await request.form
        
        # 1. Update Configuration
        if "update_configs" in form:
            settings = {
                "user_id": user_id,
                "required_hours": int(form.get("required_hours", 486)),
                "strict_8h": "strict_8h" in form,
                "count_lunch": "count_lunch" in form,
                "allow_before_7am": "allow_before_7am" in form,
                "allow_after_5pm": "allow_after_5pm" in form,
                "allow_weekend_duty": "allow_weekend_duty" in form,
                "allow_holiday_duty": "allow_holiday_duty" in form
            }
            await settings_col.update_one({"user_id": user_id}, {"$set": settings}, upsert=True)
            # Do NOT return yet, let the code below recalculate everything with the new settings

        # 2. Add/Edit Log Entry
        elif "log_date" in form:
            log_id, log_date = form.get("log_id"), form.get("log_date")
            log_data = {
                "user_id": user_id, "log_date": log_date, 
                "am_in": form.get("am_in", ""), "am_out": form.get("am_out", ""), 
                "pm_in": form.get("pm_in", ""), "pm_out": form.get("pm_out", "")
            }
            if log_id: await logs_col.update_one({"_id": ObjectId(log_id)}, {"$set": log_data})
            else: await logs_col.update_one({"log_date": log_date, "user_id": user_id}, {"$set": log_data}, upsert=True)
            if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return redirect(url_for("tracker.index"))

    # 3. THE RECALCULATION ENGINE
    raw_logs = await logs_col.find({"user_id": user_id}).sort("log_date", -1).to_list(None)
    
    total_credited_m = 0
    total_raw_m = 0 # Kept for internal logic if needed, but not displayed
    total_ot_m = 0
    am_total_m = 0 
    pm_total_m = 0 
    processed_logs = []
    
    settings = await get_user_settings(user_id)
    weekends_allowed = settings.get('allow_weekend_duty', False)
    holidays_allowed = settings.get('allow_holiday_duty', False)

    for rl in raw_logs:
        log_dt = datetime.strptime(rl['log_date'], '%Y-%m-%d')
        is_holiday = rl['log_date'] in PH_HOLIDAYS
        is_weekend = datetime.strptime(rl['log_date'], '%Y-%m-%d').weekday() >= 5
        
        nai = normalize_time(rl.get('am_in'))
        nao = normalize_time(rl.get('am_out'))
        npi = normalize_time(rl.get('pm_in'))
        npo = normalize_time(rl.get('pm_out'))

        effective_ai = "08:00" if (not settings.get('allow_before_7am') and nai and nai < "08:00") else nai
        
        m_am = get_minutes_diff(effective_ai, nao)
        m_pm = get_minutes_diff(npi, npo)
        m_lunch = 60 if (settings.get('count_lunch') and nao and npi and "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15") else 0
        day_ot = calculate_ot_minutes(npo) if settings.get('allow_after_5pm') else 0
        
        day_total = m_am + m_pm + m_lunch
        if settings.get('strict_8h'): day_total = min(day_total, 480)
        else: day_total += day_ot

        if (is_weekend and not weekends_allowed) or (is_holiday and not holidays_allowed):
            day_total = 0
            day_ot = 0

        total_credited_m += day_total
        total_raw_m += (get_minutes_diff(nai, nao) + get_minutes_diff(npi, npo))
        total_ot_m += day_ot
        
        if day_total > 0:
            am_total_m += m_am
            pm_total_m += (m_pm + day_ot)
        
        processed_logs.append({
            **rl, 'id': str(rl['_id']), 'credited_m': day_total,
            'credited_str': minutes_to_string(day_total),
            'month_key': log_dt.strftime('%B %Y'),
            'display_day': log_dt.strftime('%d'),
            'display_weekday': log_dt.strftime('%A'),
            'am_str': f"{rl.get('am_in')} - {rl.get('am_out')}" if rl.get('am_in') else "-",
            'pm_str': f"{rl.get('pm_in')} - {rl.get('pm_out')}" if rl.get('pm_in') else "-"
        })
    
    today_iso = date.today().isoformat()
    today_log = next((l for l in processed_logs if l['log_date'] == today_iso), None)

    target_h = settings.get('required_hours', 486)
    target_m = target_h * 60
    rem_m = max(0, target_m - total_credited_m)
    
    worked_days = [l for l in processed_logs if l['credited_m'] > 0]
    avg_m = total_credited_m / len(worked_days) if worked_days else 480
    finish_info = calculate_finish_date(rem_m, settings, avg_m)
    
    cur_h = total_credited_m / 60
    milestones = [
        {"label": "The Start", "target": 1, "done": cur_h >= 1},
        {"label": "Quarter Way", "target": target_h * 0.25, "done": cur_h >= (target_h * 0.25)},
        {"label": "Halfway Hero", "target": target_h * 0.5, "done": cur_h >= (target_h * 0.5)},
        {"label": "Final Stretch", "target": target_h * 0.9, "done": cur_h >= (target_h * 0.9)},
    ]
    next_ms = next((m for m in milestones if not m['done']), milestones[-1])
    ms_p = min((cur_h / next_ms['target']) * 100, 100) if next_ms['target'] > 0 else 100

    grouped = {}
    for l in processed_logs:
        if l['month_key'] not in grouped: grouped[l['month_key']] = {'logs': [], 'month_total_m': 0}
        grouped[l['month_key']]['logs'].append(l); grouped[l['month_key']]['month_total_m'] += l['credited_m']
    for k in grouped: grouped[k]['month_total_str'] = minutes_to_string(grouped[k]['month_total_m'])

    return await render_template(
        "main/index.html", grouped_logs=grouped, settings=settings, 
        total_str=minutes_to_string(total_credited_m),
        ot_total_str=minutes_to_string(total_ot_m), # REPLACED Raw Total String
        remaining_str=minutes_to_string(rem_m),
        progress=min((total_credited_m/target_m)*100, 100), 
        today=today_iso,
        today_log=today_log,
        avg_speed=round(avg_m/60, 1), 
        finish_info=finish_info,
        milestones=milestones, 
        am_perc=round((am_total_m/((am_total_m+pm_total_m) or 1))*100),
        pm_perc=round((pm_total_m/((am_total_m+pm_total_m) or 1))*100),
        ot_str=minutes_to_string(total_ot_m),
        session_count=len(worked_days), # REPLACED Efficiency Index with Session Count
        next_ms=next_ms, ms_progress=ms_p, 
        pulse_trend="up", log_count=len(processed_logs),
        ph_holidays=PH_HOLIDAYS, today_type=get_day_type(date.today().isoformat())
    )

@tracker_bp.route("/punch", methods=["POST"])
async def punch():
    if 'user_id' not in session: return {"error": "Unauthorized"}, 401
    
    user_id = session['user_id']
    today_str = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M")
    
    # Find today's existing log
    log = await logs_col.find_one({"user_id": user_id, "log_date": today_str})
    
    if not log:
        # First punch of the day
        new_log = {
            "user_id": user_id,
            "log_date": today_str,
            "am_in": now_time, "am_out": "",
            "pm_in": "", "pm_out": ""
        }
        await logs_col.insert_one(new_log)
        return {"status": "success", "action": "AM IN", "time": now_time}

    # Sequential Logic: Fill the first empty slot
    field_to_update = ""
    action_name = ""
    
    if not log.get("am_in"): 
        field_to_update = "am_in"
        action_name = "AM IN"
    elif not log.get("am_out"): 
        field_to_update = "am_out"
        action_name = "AM OUT"
    elif not log.get("pm_in"): 
        field_to_update = "pm_in"
        action_name = "PM IN"
    elif not log.get("pm_out"): 
        field_to_update = "pm_out"
        action_name = "PM OUT"
    else:
        return {"status": "full", "message": "Day already completed"}

    await logs_col.update_one(
        {"_id": log["_id"]}, 
        {"$set": {field_to_update: now_time}}
    )
    
    return {"status": "success", "action": action_name, "time": now_time}
    
@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session: await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))