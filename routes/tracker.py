from datetime import datetime, date
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import logs_col
from bson.objectid import ObjectId

tracker_bp = Blueprint('tracker', __name__)
REQUIRED_HOURS = 486

# --- HELPER FUNCTIONS ---
def calculate_session(t_in, t_out):
    """Returns decimal hours for storage (e.g., 1.5)"""
    if not t_in or not t_out: return 0.0
    try:
        fmt = "%H:%M"
        tdelta = datetime.strptime(t_out, fmt) - datetime.strptime(t_in, fmt)
        return tdelta.total_seconds() / 3600
    except ValueError: return 0.0

def format_hm(decimal_hours):
    """Converts 4.5 -> '4h 30m'"""
    if not decimal_hours: return "0h 0m"
    hours = int(decimal_hours)
    minutes = int(round((decimal_hours - hours) * 60))
    return f"{hours}h {minutes}m"

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
        
        # Calculate decimal for math/storage
        total_decimal = round(calculate_session(am_in, am_out) + calculate_session(pm_in, pm_out), 2)

        await logs_col.update_one(
            {"log_date": log_date, "user_id": user_id},
            {"$set": {
                "am_in": am_in, "am_out": am_out, 
                "pm_in": pm_in, "pm_out": pm_out, 
                "hours": total_decimal
            }},
            upsert=True
        )
        return redirect(url_for("tracker.index"))

    # Fetch Logs
    cursor = logs_col.find({"user_id": user_id}).sort("log_date", -1)
    raw_logs = await cursor.to_list(length=None)
    
    # Calculate Total (Decimal)
    pipeline = [{"$match": {"user_id": user_id}}, {"$group": {"_id": None, "total": {"$sum": "$hours"}}}]
    agg = await logs_col.aggregate(pipeline).to_list(length=1)
    
    total_val = round(agg[0]['total'], 2) if agg else 0.0
    remaining_val = max(0, REQUIRED_HOURS - total_val)
    progress_val = min((total_val / REQUIRED_HOURS) * 100, 100)

    # Process logs for display
    processed_logs = []
    for log in raw_logs:
        try:
            d = datetime.strptime(log['log_date'], '%Y-%m-%d')
            log['id'] = str(log['_id'])
            log['display_day'] = d.strftime('%d')
            log['display_month'] = d.strftime('%b')
            log['display_weekday'] = d.strftime('%A')
            log['am_str'] = f"{log.get('am_in')} - {log.get('am_out')}" if log.get('am_in') else "-"
            log['pm_str'] = f"{log.get('pm_in')} - {log.get('pm_out')}" if log.get('pm_in') else "-"
            
            # Convert stored decimal to "Xh Ym" string
            log['hours_str'] = format_hm(log.get('hours', 0))
            
            processed_logs.append(log)
        except: continue

    return await render_template("index.html", 
                                 logs=processed_logs, 
                                 
                                 # Pass formatted strings for display
                                 total_str=format_hm(total_val), 
                                 remaining_str=format_hm(remaining_val),
                                 required_str=format_hm(REQUIRED_HOURS),
                                 
                                 # Pass raw values for logic/progress bar
                                 progress=progress_val, 
                                 today=date.today().isoformat())

@tracker_bp.route("/delete_log/<log_id>")
async def delete_log(log_id):
    if 'user_id' in session:
        await logs_col.delete_one({"_id": ObjectId(log_id), "user_id": session['user_id']})
    return redirect(url_for("tracker.index"))