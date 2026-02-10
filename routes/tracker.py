from datetime import datetime, date, timedelta, timezone
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)
REQUIRED_HOURS = 486
DAILY_CAP_MINUTES = 480 # 8 Hours

# Philippine Holidays 2026
PH_HOLIDAYS = [
    "2026-01-01", "2026-02-17",
    "2026-04-02", "2026-04-03", "2026-04-09", 
    "2026-05-01", "2026-06-12", "2026-08-31", 
    "2026-11-01", "2026-11-30", "2026-12-08", 
    "2026-12-25", "2026-12-30"
]

def minutes_to_string(total_minutes):
    if total_minutes < 0: total_minutes = 0
    h = int(total_minutes // 60)
    m = int(total_minutes % 60)
    return f"{h}h {m}m"

def calculate_finish_date(remaining_minutes, avg_daily_credited_minutes):
    if remaining_minutes <= 0:
        return {"date": "Completed", "days_left": 0}
    
    # Use credited average speed, but cap at 8h for projection 
    # (prevents over-optimistic dates if someone works 10h/day)
    projection_speed = min(avg_daily_credited_minutes, DAILY_CAP_MINUTES)
    if projection_speed <= 0: projection_speed = DAILY_CAP_MINUTES
    
    real_days_left = remaining_minutes / projection_speed
    
    tz_ph = timezone(timedelta(hours=8))
    now_ph = datetime.now(tz_ph)
    current_date = now_ph.date()
    
    if now_ph.hour >= 18:
        current_date += timedelta(days=1)
        
    temp_minutes = remaining_minutes
    max_iterations = 1000 
    
    while temp_minutes > 0 and max_iterations > 0:
        is_weekend = current_date.weekday() >= 5 
        is_holiday = current_date.isoformat() in PH_HOLIDAYS
        
        if not is_weekend and not is_holiday:
            temp_minutes -= projection_speed
        
        if temp_minutes > 0:
            current_date += timedelta(days=1)
            max_iterations -= 1
            
    return {
        "date": current_date.strftime("%b %d, %Y"),
        "days_left": real_days_left
    }

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        t1 = datetime.strptime(t_in, "%H:%M")
        t2 = datetime.strptime(t_out, "%H:%M")
        return int((t2 - t1).total_seconds() // 60)
    except: return 0

def process_log_entry(log):
    m = log.get('total_minutes')
    if m is None:
        am_m = get_minutes_diff(log.get('am_in'), log.get('am_out'))
        pm_m = get_minutes_diff(log.get('pm_in'), log.get('pm_out'))
        m = am_m + pm_m
    
    # Calculate Credited Minutes (Cap at 8 hours)
    credited_m = min(m, DAILY_CAP_MINUTES)
    
    log_date = datetime.strptime(log['log_date'], '%Y-%m-%d')
    return {
        **log,
        'id': str(log['_id']),
        'total_minutes': m,
        'credited_minutes': credited_m,
        'display_day': log_date.strftime('%d'),
        'display_weekday': log_date.strftime('%A'),
        'month_key': log_date.strftime('%B %Y'),
        'am_str': f"{log.get('am_in')} - {log.get('am_out')}" if log.get('am_in') else "-",
        'pm_str': f"{log.get('pm_in')} - {log.get('pm_out')}" if log.get('pm_in') else "-",
        'hours_str': minutes_to_string(m),
        'is_overtime': m > DAILY_CAP_MINUTES
    }

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']

    if request.method == "POST":
        form = await request.form
        log_id = form.get("log_id")
        log_date = form.get("log_date")
        am_in, am_out = form.get("am_in", ""), form.get("am_out", "")
        pm_in, pm_out = form.get("pm_in", ""), form.get("pm_out", "")
        
        m = get_minutes_diff(am_in, am_out) + get_minutes_diff(pm_in, pm_out)
        log_data = {
            "user_id": user_id, "log_date": log_date, 
            "am_in": am_in, "am_out": am_out, 
            "pm_in": pm_in, "pm_out": pm_out, 
            "hours": round(m/60, 2), "total_minutes": m
        }

        if log_id:
            await logs_col.update_one({"_id": ObjectId(log_id)}, {"$set": log_data})
        else:
            await logs_col.update_one({"log_date": log_date, "user_id": user_id}, {"$set": log_data}, upsert=True)
        return redirect(url_for("tracker.index"))

    raw_logs = await logs_col.find({"user_id": user_id}).sort("log_date", -1).to_list(None)
    
    total_credited_m = 0
    total_raw_m = 0
    grouped_logs = {}
    
    for raw_log in raw_logs:
        log = process_log_entry(raw_log)
        total_raw_m += log['total_minutes']
        total_credited_m += log['credited_minutes']
        
        m_key = log['month_key']
        if m_key not in grouped_logs:
            grouped_logs[m_key] = {'logs': [], 'month_total_m': 0}
        
        grouped_logs[m_key]['logs'].append(log)
        grouped_logs[m_key]['month_total_m'] += log['total_minutes']

    for key in grouped_logs:
        grouped_logs[key]['month_total_str'] = minutes_to_string(grouped_logs[key]['month_total_m'])

    log_count = len(raw_logs)
    # Average is based on Credited time only
    avg_daily_m = total_credited_m / log_count if log_count > 0 else 480 
    
    remaining_m = max(0, (REQUIRED_HOURS * 60) - total_credited_m)
    progress = min((total_credited_m / (REQUIRED_HOURS * 60)) * 100, 100)
    
    finish_info = calculate_finish_date(remaining_m, avg_daily_m)

    current_streak = 0
    today_date = date.today()
    sorted_dates = sorted([datetime.strptime(l['log_date'], '%Y-%m-%d').date() for l in raw_logs], reverse=True)
    
    check_date = today_date
    for log_d in sorted_dates:
        if log_d == check_date:
            current_streak += 1
            check_date -= timedelta(days=1)
        elif log_d > check_date:
            continue
        else:
            break

    # 2. Milestone Progressions
    milestones = [
        {"label": "The Start", "target": 1, "done": total_credited_m >= 60},
        {"label": "Quarter Way", "target": REQUIRED_HOURS * 0.25, "done": (total_credited_m / 60) >= (REQUIRED_HOURS * 0.25)},
        {"label": "Halfway Hero", "target": REQUIRED_HOURS * 0.5, "done": (total_credited_m / 60) >= (REQUIRED_HOURS * 0.5)},
        {"label": "Final Stretch", "target": REQUIRED_HOURS * 0.9, "done": (total_credited_m / 60) >= (REQUIRED_HOURS * 0.9)},
    ]

    # 3. Time Distribution (AM vs PM)
    am_total = sum(get_minutes_diff(l.get('am_in'), l.get('am_out')) for l in raw_logs)
    pm_total = sum(get_minutes_diff(l.get('pm_in'), l.get('pm_out')) for l in raw_logs)
    total_m_calc = (am_total + pm_total) or 1
    am_perc = (am_total / total_m_calc) * 100
    pm_perc = (pm_total / total_m_calc) * 100
    
    return await render_template(
        "main/index.html", 
        grouped_logs=grouped_logs, 
        total_str=minutes_to_string(total_credited_m), # Main display is credited
        total_raw_str=minutes_to_string(total_raw_m),  # New variable for whole count
        remaining_str=minutes_to_string(remaining_m),
        required_str=f"{REQUIRED_HOURS}h 0m", 
        progress=progress, 
        today=date.today().isoformat(),
        avg_speed=round(avg_daily_m / 60, 2),
        finish_info=finish_info,
        streak=current_streak,
        milestones=milestones,
        am_perc=round(am_perc),
        pm_perc=round(pm_perc),
        log_count=log_count
    )

@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session:
        await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))