from datetime import datetime, date, timedelta, timezone
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col, db, settings_col, notifications_col, users_col
from bson.objectid import ObjectId
import hashlib

tracker_bp = Blueprint('tracker', __name__)

# Philippine Holidays 2026
PH_HOLIDAYS = [
    "2026-01-01", "2026-02-17", "2026-04-02", "2026-04-03", "2026-04-04", 
    "2026-04-09", "2026-05-01", "2026-06-12", "2026-08-31", "2026-11-01", 
    "2026-11-30", "2026-12-08", "2026-12-25", "2026-12-30"
]

def get_ph_now():
    """Returns the current datetime in Philippine Time (UTC+8)"""
    return datetime.now(timezone.utc) + timedelta(hours=8)

async def get_user_settings(user_id):
    settings = await settings_col.find_one({"user_id": user_id})
    if not settings:
        return {
            "required_hours": 486,
            "strict_8h": False,
            "is_10h_mode": False,
            "count_lunch": False,
            "allow_before_7am": False,
            "allow_after_5pm": True,
            "allow_weekend_duty": False,
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
        t1 = datetime.strptime(normalize_time(t_in), "%H:%M")
        t2 = datetime.strptime(normalize_time(t_out), "%H:%M")
        return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
    except: return 0

def calculate_ot_minutes(pm_in, pm_out):
    if not pm_in or not pm_out: return 0
    try:
        if get_minutes_diff(pm_in, pm_out) <= 0: return 0
        in_time = datetime.strptime(normalize_time(pm_in), "%H:%M")
        out_time = datetime.strptime(normalize_time(pm_out), "%H:%M")
        threshold = datetime.strptime("17:00", "%H:%M")
        if out_time <= threshold: return 0
        actual_ot_start = max(in_time, threshold)
        return int((out_time - actual_ot_start).total_seconds() // 60)
    except: return 0

def calculate_finish_date(remaining_minutes, settings, actual_avg_m):
    if remaining_minutes <= 0: 
        return {"date": "Completed", "days_left": 0, "calendar_days": 0}
    
    transition_date = date(2026, 3, 16)
    current_date = date.today()
    start_date = current_date
    temp_m = remaining_minutes
    
    max_loops = 2000 
    loops = 0
    work_days_left = 0
    
    while temp_m > 0 and loops < max_loops:
        current_date += timedelta(days=1)
        weekday = current_date.weekday()
        is_holiday = current_date.isoformat() in PH_HOLIDAYS
        
        if settings.get('is_10h_mode') and current_date >= transition_date:
            is_work_day = weekday <= 3 
            default_pace = 600         
        else:
            is_work_day = weekday <= 4 
            default_pace = 480         

        proj_speed = actual_avg_m if actual_avg_m > default_pace else default_pace 
        
        if is_work_day and not is_holiday:
            temp_m -= proj_speed
            work_days_left += 1
        loops += 1
        
    return {
        "date": current_date.strftime("%b %d, %Y"),
        "days_left": work_days_left,
        "calendar_days": (current_date - start_date).days
    }

def get_day_type(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        if date_str in PH_HOLIDAYS: return "Holiday"
        if dt.weekday() >= 5: return "Weekend"
        return "Work Day"
    except: return "Unknown"

@tracker_bp.route("/notifications/mark-read", methods=["POST"])
async def mark_notifications_read():
    if 'user_id' not in session: return {"error": "Unauthorized"}, 401
    user_id = str(session['user_id'])
    await notifications_col.update_many(
        {"target_uid": user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"status": "success"}

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    user = await users_col.find_one({"_id": ObjectId(user_id)})
    from db import db # ensure db is imported
    p = await db.profiles.find_one({"user_id": str(user_id)}) or {}
    settings = await get_user_settings(user_id)
    transition_date = date(2026, 3, 16)
    
    unread_count = await notifications_col.count_documents({
        "target_uid": str(user_id),
        "is_read": False
    })

    notifications = await notifications_col.find({
        "target_uid": str(user_id) 
    }).sort("created_at", -1).limit(10).to_list(None)

    for hype in notifications:
        hype['ph_time'] = hype['created_at'] + timedelta(hours=8)

    if request.method == "POST":
        form = await request.form
        if "update_configs" in form:
            settings = {
                "user_id": user_id,
                "required_hours": int(form.get("required_hours", 486)),
                "strict_8h": "strict_8h" in form,
                "is_10h_mode": "is_10h_mode" in form,
                "count_lunch": "count_lunch" in form,
                "allow_before_7am": "allow_before_7am" in form,
                "allow_after_5pm": "allow_after_5pm" in form,
                "allow_weekend_duty": "allow_weekend_duty" in form,
                "allow_holiday_duty": "allow_holiday_duty" in form
            }
            await settings_col.update_one({"user_id": user_id}, {"$set": settings}, upsert=True)

        elif "log_date" in form:
            log_id, log_date = form.get("log_id"), form.get("log_date")
            manual_credit = form.get("manual_credit", "")
            log_data = {
                "user_id": user_id, "log_date": log_date, 
                "am_in": form.get("am_in", ""), "am_out": form.get("am_out", ""), 
                "pm_in": form.get("pm_in", ""), "pm_out": form.get("pm_out", ""),
                "manual_credit": float(manual_credit) if manual_credit else None
            }
            if log_id: await logs_col.update_one({"_id": ObjectId(log_id)}, {"$set": log_data})
            else: await logs_col.update_one({"log_date": log_date, "user_id": user_id}, {"$set": log_data}, upsert=True)
            if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return redirect(url_for("tracker.index"))

    raw_logs = await logs_col.find({"user_id": user_id}).sort("log_date", -1).to_list(None)
    
    total_credited_m = 0
    total_ot_m = 0
    am_total_m = 0 
    pm_total_m = 0 
    processed_logs = []
    
    weekends_allowed = settings.get('allow_weekend_duty', False)
    holidays_allowed = settings.get('allow_holiday_duty', False)
    is_10h_mode = settings.get('is_10h_mode', False)

    for rl in raw_logs:
        log_dt = datetime.strptime(rl['log_date'], '%Y-%m-%d')
        log_date_obj = log_dt.date()
        is_holiday = rl['log_date'] in PH_HOLIDAYS
        is_weekend = log_dt.weekday() >= 5
        manual_val = rl.get('manual_credit')
        
        if manual_val is not None:
            day_total = int(manual_val * 60)
            day_ot = 0 
            m_am, m_pm = day_total, 0
        else:
            nai = normalize_time(rl.get('am_in'))
            nao = normalize_time(rl.get('am_out'))
            npi = normalize_time(rl.get('pm_in'))
            npo = normalize_time(rl.get('pm_out'))

            # --- IMPROVED CALCULATION ENGINE ---
            effective_start = "07:00" if (is_10h_mode and log_date_obj >= transition_date) else "08:00"
            
            # If AM In is empty, it's an absent period
            if not nai:
                m_am = 0
            else:
                # Apply the "Allow before 7/8AM" rule
                if not settings.get('allow_before_7am') and nai < effective_start:
                    nai = effective_start
                m_am = get_minutes_diff(nai, nao)

            # If PM In is empty, it's an absent period
            if not npi:
                m_pm = 0
            else:
                m_pm = get_minutes_diff(npi, npo)

            # Lunch Logic
            m_lunch = 60 if (settings.get('count_lunch') and nao and npi and "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15") else 0
            
            day_total = m_am + m_pm + m_lunch
            day_ot = calculate_ot_minutes(npi, npo) if settings.get('allow_after_5pm') else 0
            
            # Apply Caps based on Mode
            if is_10h_mode:
                if log_date_obj < transition_date:
                    day_total = min(day_total, 480) # 8h cap before March 16
                else:
                    day_total = min(day_total, 600) # 10h cap after March 16
                day_ot = 0 # No extra OT credit in compressed mode
            elif settings.get('strict_8h'): 
                day_total = min(day_total, 480)
                day_ot = 0

        if (is_weekend and not weekends_allowed) or (is_holiday and not holidays_allowed):
            day_total, day_ot, m_am, m_pm = 0, 0, 0, 0

        total_credited_m += day_total
        total_ot_m += day_ot
        if day_total > 0:
            am_total_m += m_am
            pm_total_m += m_pm
        
        processed_logs.append({
            **rl, 'id': str(rl['_id']), 
            'credited_m': day_total,
            'credited_str': minutes_to_string(day_total),
            'manual_credit': manual_val,
            'month_key': log_dt.strftime('%B %Y'),
            'display_day': log_dt.strftime('%d'),
            'display_weekday': log_dt.strftime('%A'),
            'am_str': f"{rl.get('am_in')} - {rl.get('am_out')}" if rl.get('am_in') else "-",
            'pm_str': f"{rl.get('pm_in')} - {rl.get('pm_out')}" if rl.get('pm_in') else "-"
        })
    
    ph_now = get_ph_now()
    today_iso = ph_now.date().isoformat()
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

    uid_string = str(user_id)
    user_hash = hashlib.sha256(uid_string.encode()).hexdigest()
    perm_nums = "".join([c for c in user_hash if c.isdigit()])[:4].zfill(4)
    perm_lets = "".join([c for c in user_hash if c.isalpha()])[:4].upper()
    cert_id = f"{perm_nums}-{perm_lets}"
    clean_hours = minutes_to_string(total_credited_m).split(' ')[0]

    return await render_template(
        "main/index.html", grouped_logs=grouped, settings=settings, 
        p=p,
        user=user,
        total_str=minutes_to_string(total_credited_m),
        ot_total_str=minutes_to_string(total_ot_m),
        remaining_str=minutes_to_string(rem_m),
        progress=min((total_credited_m/target_m)*100, 100), 
        today=today_iso,
        notifications=notifications,
        unread_count=unread_count,
        today_log=today_log,
        avg_speed=round(avg_m/60, 1), 
        finish_info=finish_info,
        milestones=milestones, 
        am_perc=round((am_total_m/((am_total_m+pm_total_m) or 1))*100),
        pm_perc=round((pm_total_m/((am_total_m+pm_total_m) or 1))*100),
        ot_str=minutes_to_string(total_ot_m),
        session_count=len(worked_days),
        next_ms=next_ms, ms_progress=ms_p, 
        pulse_trend="up", log_count=len(processed_logs),
        ph_holidays=PH_HOLIDAYS, today_type=get_day_type(today_iso),
        cert_id=cert_id
    )

@tracker_bp.route("/punch", methods=["POST"])
async def punch():
    if 'user_id' not in session: return {"error": "Unauthorized"}, 401
    user_id = session['user_id']
    ph_now = get_ph_now()
    today_str = ph_now.strftime("%Y-%m-%d")
    now_time = ph_now.strftime("%H:%M")
    log = await logs_col.find_one({"user_id": user_id, "log_date": today_str})
    if not log:
        new_log = {"user_id": user_id, "log_date": today_str, "am_in": now_time, "am_out": "", "pm_in": "", "pm_out": ""}
        await logs_col.insert_one(new_log)
        return {"status": "success", "action": "AM IN", "time": now_time}
    field_to_update = ""
    action_name = ""
    if not log.get("am_in"): field_to_update, action_name = "am_in", "AM IN"
    elif not log.get("am_out"): field_to_update, action_name = "am_out", "AM OUT"
    elif not log.get("pm_in"): field_to_update, action_name = "pm_in", "PM IN"
    elif not log.get("pm_out"): field_to_update, action_name = "pm_out", "PM OUT"
    else: return {"status": "full", "message": "Day already completed"}
    await logs_col.update_one({"_id": log["_id"]}, {"$set": {field_to_update: now_time}})
    return {"status": "success", "action": action_name, "time": now_time}
    
@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session: await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))