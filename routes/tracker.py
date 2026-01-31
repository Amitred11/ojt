from datetime import datetime, date
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)
REQUIRED_HOURS = 486

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        t1 = datetime.strptime(t_in, "%H:%M")
        t2 = datetime.strptime(t_out, "%H:%M")
        return int((t2 - t1).total_seconds() // 60)
    except: return 0

def minutes_to_string(total_minutes):
    return f"{total_minutes // 60}h {total_minutes % 60}m"

@tracker_bp.route("/tracker", methods=["GET", "POST"])
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']

    if request.method == "POST":
        form = await request.form
        log_id = form.get("log_id") # Added for editing
        log_date = form.get("log_date")
        am_in, am_out = form.get("am_in"), form.get("am_out")
        pm_in, pm_out = form.get("pm_in"), form.get("pm_out")
        
        m = get_minutes_diff(am_in, am_out) + get_minutes_diff(pm_in, pm_out)
        
        log_data = {
            "user_id": user_id,
            "log_date": log_date,
            "am_in": am_in, "am_out": am_out,
            "pm_in": pm_in, "pm_out": pm_out,
            "hours": round(m/60, 2), 
            "total_minutes": m
        }

        if log_id: # Update existing
            await logs_col.update_one({"_id": ObjectId(log_id), "user_id": user_id}, {"$set": log_data})
        else: # Create new or upsert by date
            await logs_col.update_one(
                {"log_date": log_date, "user_id": user_id},
                {"$set": log_data},
                upsert=True
            )
        return redirect(url_for("tracker.index"))

    raw_logs = await logs_col.find({"user_id": user_id}).sort("log_date", -1).to_list(None)
    grouped_logs, total_m = {}, 0

    for log in raw_logs:
        m = log.get('total_minutes')
        
        # 2. If it's an old log, re-calculate from raw time strings to avoid rounding errors
        if m is None:
            am_m = get_minutes_diff(log.get('am_in'), log.get('am_out'))
            pm_m = get_minutes_diff(log.get('pm_in'), log.get('pm_out'))
            m = am_m + pm_m
            
            # 3. Last resort fallback (only if time strings are missing)
            if m == 0 and log.get('hours', 0) > 0:
                m = int(round(log.get('hours') * 60))

        total_m += m
        d = datetime.strptime(log['log_date'], '%Y-%m-%d')
        
        month_key = d.strftime('%B %Y')
        if month_key not in grouped_logs:
            grouped_logs[month_key] = {'logs': [], 'month_total_m': 0}
        
        log.update({
            'id': str(log['_id']), 
            'display_day': d.strftime('%d'), 
            'display_weekday': d.strftime('%A'),
            'am_str': f"{log.get('am_in')} - {log.get('am_out')}" if log.get('am_in') else "-",
            'pm_str': f"{log.get('pm_in')} - {log.get('pm_out')}" if log.get('pm_in') else "-",
            'hours_str': minutes_to_string(m)
        })
        
        grouped_logs[month_key]['logs'].append(log)
        grouped_logs[month_key]['month_total_m'] += m

    # Convert monthly totals to strings
    for key in grouped_logs:
        grouped_logs[key]['month_total_str'] = minutes_to_string(grouped_logs[key]['month_total_m'])

    prog = min((total_m / (REQUIRED_HOURS * 60)) * 100, 100)
    return await render_template("main/index.html", grouped_logs=grouped_logs, 
                                 total_str=minutes_to_string(total_m), 
                                 remaining_str=minutes_to_string(max(0, (REQUIRED_HOURS*60)-total_m)),
                                 required_str=f"{REQUIRED_HOURS}h 0m", progress=prog, today=date.today().isoformat())

@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session:
        await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))