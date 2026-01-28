from datetime import datetime, date
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)
REQUIRED_HOURS = 486

# --- HELPER FUNCTIONS ---

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        fmt = "%H:%M"
        t1 = datetime.strptime(t_in, fmt)
        t2 = datetime.strptime(t_out, fmt)
        diff_seconds = (t2 - t1).total_seconds()
        return int(diff_seconds // 60)
    except ValueError:
        return 0

def minutes_to_string(total_minutes):
    hours = total_minutes // 60
    mins = total_minutes % 60
    return f"{hours}h {mins}m"

# --- ROUTES ---

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']

    if request.method == "POST":
        form = await request.form
        log_date = form.get("log_date")
        am_in, am_out = form.get("am_in"), form.get("am_out")
        pm_in, pm_out = form.get("pm_in"), form.get("pm_out")
        
        day_minutes = get_minutes_diff(am_in, am_out) + get_minutes_diff(pm_in, pm_out)
        hours_decimal = round(day_minutes / 60, 2)

        await logs_col.update_one(
            {"log_date": log_date, "user_id": user_id},
            {"$set": {
                "am_in": am_in, "am_out": am_out, 
                "pm_in": pm_in, "pm_out": pm_out, 
                "hours": hours_decimal,
                "total_minutes": day_minutes
            }},
            upsert=True
        )
        return redirect(url_for("tracker.index"))

    # Fetch Logs
    cursor = logs_col.find({"user_id": user_id}).sort("log_date", -1)
    raw_logs = await cursor.to_list(length=None)
    
    # Process Logs & Group by Month
    # We use a standard dict because Python 3.7+ preserves insertion order (and logs are already sorted)
    grouped_logs = {} 
    grand_total_minutes = 0

    for log in raw_logs:
        try:
            # 1. Math Calculation
            am_mins = get_minutes_diff(log.get('am_in'), log.get('am_out'))
            pm_mins = get_minutes_diff(log.get('pm_in'), log.get('pm_out'))
            daily_minutes = am_mins + pm_mins
            grand_total_minutes += daily_minutes
            
            # 2. Formatting
            d = datetime.strptime(log['log_date'], '%Y-%m-%d')
            log['id'] = str(log['_id'])
            log['display_day'] = d.strftime('%d')
            log['display_weekday'] = d.strftime('%A')
            log['am_str'] = f"{log.get('am_in')} - {log.get('am_out')}" if log.get('am_in') else "-"
            log['pm_str'] = f"{log.get('pm_in')} - {log.get('pm_out')}" if log.get('pm_in') else "-"
            log['hours_str'] = minutes_to_string(daily_minutes)
            
            # 3. Grouping by "Month Year" (e.g., "January 2026")
            month_key = d.strftime('%B %Y')
            if month_key not in grouped_logs:
                grouped_logs[month_key] = []
            grouped_logs[month_key].append(log)
            
        except Exception as e:
            continue

    # Stats Calculation
    required_minutes = REQUIRED_HOURS * 60
    remaining_minutes = max(0, required_minutes - grand_total_minutes)
    progress_val = min((grand_total_minutes / required_minutes) * 100, 100) if required_minutes > 0 else 0

    return await render_template("index.html", 
                                 grouped_logs=grouped_logs, # Passing dictionary instead of flat list
                                 total_str=minutes_to_string(grand_total_minutes), 
                                 remaining_str=minutes_to_string(remaining_minutes),
                                 required_str=f"{REQUIRED_HOURS}h 0m",
                                 progress=progress_val, 
                                 today=date.today().isoformat())

@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session:
        await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))