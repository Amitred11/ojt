from quart import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from db import users_col, get_db, settings_col
from bson import ObjectId
from datetime import datetime
import time 
import json
import io
import zipfile

auth_bp = Blueprint('auth', __name__)

# Constants
ADMIN_ID = "6979fc7f59b791fd5fcbf90f"
APP_START_TIME = time.time()

# Helper to check if user is the specific admin
def is_admin():
    return session.get('user_id') == ADMIN_ID

# --- HELPER UTILITIES (Synced with Tracker) ---
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

# --- THE OFFICIAL CALCULATION ENGINE (Synced with Tracker) ---
def calculate_user_official_minutes(logs, settings):
    total_credited_m = 0
    
    # Default rules if user hasn't touched settings
    strict_8h = settings.get('strict_8h', False)
    count_lunch = settings.get('count_lunch', False)
    allow_early = settings.get('allow_before_7am', False)
    allow_ot = settings.get('allow_after_5pm', True)
    weekends_allowed = settings.get('include_weekends_eta', False)

    for log in logs:
        # Check for weekend
        log_date = log.get('log_date', "")
        is_weekend = False
        try:
            is_weekend = datetime.strptime(log_date, '%Y-%m-%d').weekday() >= 5
        except: pass

        # Normalization
        nai, nao, npi, npo = normalize_time(log.get('am_in')), normalize_time(log.get('am_out')), \
                             normalize_time(log.get('pm_in')), normalize_time(log.get('pm_out'))

        # Early start clipping (8 AM rule)
        eff_ai = "08:00" if (not allow_early and nai and nai < "08:00") else nai
        
        m_am = get_minutes_diff(eff_ai, nao)
        m_pm = get_minutes_diff(npi, npo)
        
        # Lunch logic
        m_lunch = 0
        if count_lunch and nao and npi:
            if "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15":
                m_lunch = 60
        
        # OT logic
        day_ot = calculate_ot_minutes(npo) if allow_ot else 0
        
        # Summation
        day_total = m_am + m_pm + m_lunch
        if strict_8h:
            day_total = min(day_total, 480)
        else:
            day_total += day_ot

        # Weekend override
        if is_weekend and not weekends_allowed:
            day_total = 0

        total_credited_m += day_total
        
    return total_credited_m

@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    if 'user_id' in session:
        return redirect(url_for('tracker.index'))

    if request.method == "POST":
        form = await request.form
        username = form.get("username").lower().strip()
        password = form.get("password")
        user = await users_col.find_one({"username": username})

        if user and check_password_hash(user['password'], password):
            # CHECK STATUS (Only allow login if approved or if it's the specific admin)
            user_id_str = str(user['_id'])
            if user.get('status') == 'pending' and user_id_str != ADMIN_ID:
                await flash("Your account is awaiting Admin approval.", "info")
                return redirect(url_for('auth.login'))
            
            session['user_id'] = user_id_str
            session['username'] = user['username']
            session['is_admin'] = (user_id_str == ADMIN_ID) 
            
            await flash(f"Access Granted. Welcome, {user['username']}.", "success")
            return redirect(url_for('tracker.index'))
        
        await flash("Invalid credentials or unauthorized access.", "error")
    return await render_template("auth/login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
async def register():
    # Check if registration is locked
    config = await settings_col.find_one({"type": "global_config"})
    reg_open = config.get('registration_open', True) if config else True
    
    if not reg_open:
        await flash("Registration Protocol is currently LOCKED.", "error")
        return redirect(url_for('auth.login'))
    if request.method == "POST":
        form = await request.form
        username = form.get("username").lower().strip()
        password = form.get("password")
        # Note: security_code is ignored in the logic but kept in the design
        
        existing_user = await users_col.find_one({"username": username})
        if existing_user:
            await flash("Identity already exists in database.", "error")
            return redirect(url_for('auth.register'))

        hashed_pw = generate_password_hash(password)
        
        # All new registrations are 'pending'
        await users_col.insert_one({
            "username": username, 
            "password": hashed_pw,
            "status": "pending" 
        })
        
        await flash("Request sent! Please wait for Admin approval.", "success")
        return redirect(url_for('auth.login'))

    return await render_template("auth/register.html")

import re # Add this import at the top of your file

@auth_bp.route("/admin/toggle-reg", methods=["POST"])
async def toggle_registration():
    if not is_admin(): return {"status": "unauthorized"}, 403
    
    config = await settings_col.find_one({"type": "global_config"})
    current_status = config.get('registration_open', True) if config else True
    new_status = not current_status
    
    await settings_col.update_one(
        {"type": "global_config"},
        {"$set": {"registration_open": new_status}},
        upsert=True
    )
    return {"status": "success", "is_open": new_status}

@auth_bp.route("/fix-account", methods=["GET", "POST"])
async def fix_account():
    if request.method == "POST":
        form = await request.form
        input_username = form.get("username").strip()
        password = form.get("password")

        # Use a case-insensitive regex search
        # This will find "RinYuRin" even if you type "rinyurin"
        user = await users_col.find_one({
            "username": {"$regex": f"^{re.escape(input_username)}$", "$options": "i"}
        })

        if user:
            # Check if the plain text password matches
            if str(user.get('password')) == str(password):
                hashed_pw = generate_password_hash(password)
                
                # Update the account: 
                # 1. New hashed password
                # 2. Set status to approved
                # 3. Convert username to lowercase to follow your 'new' system format
                await users_col.update_one(
                    {"_id": user['_id']},
                    {
                        "$set": {
                            "username": user['username'].lower(), # Normalizes to "rinyurin"
                            "password": hashed_pw,
                            "status": "approved"
                        }
                    }
                )
                
                await flash(f"Account '{user['username']}' is now fixed and approved!", "success")
                return redirect(url_for('auth.login'))
            else:
                await flash("Password does not match the old records.", "error")
        else:
            await flash(f"User '{input_username}' not found even with case-insensitive search.", "error")
            
    return await render_template("auth/migration_tool.html")

@auth_bp.route("/logout")
async def logout():
    session.clear() # This wipes the user's session data
    await flash("Signed out successfully.", "info")
    return redirect(url_for('auth.login'))

# --- ADMIN PANEL ROUTES ---

@auth_bp.route("/admin/users")
async def manage_users():
    if not is_admin():
        await flash("Access Denied.", "error")
        return redirect(url_for('tracker.index'))

    # REMOVED: global_config and reg_open logic here
    
    users_cursor = users_col.find().sort("username", 1)
    all_users = await users_cursor.to_list(length=500)
    
    # Pre-fetch all settings to reduce database queries
    all_settings_list = await settings_col.find({"user_id": {"$exists": True}}).to_list(length=500)
    settings_map = {str(s['user_id']): s for s in all_settings_list}
    
    pending = []
    active = []
    
    for u in all_users:
        uid_str = str(u['_id'])
        u['id_str'] = uid_str
        user_logs = await get_db().logs.find({"user_id": uid_str}).to_list(None)
        user_settings = settings_map.get(uid_str, {})
        
        total_minutes = calculate_user_official_minutes(user_logs, user_settings)
        u['total_hours'] = round(total_minutes / 60, 1)
        u['goal_hours'] = user_settings.get('required_hours', 486)
        
        if u.get('status') == 'pending':
            pending.append(u)
        else:
            active.append(u)
            
    return await render_template(
        "auth/admin_users.html", 
        pending=pending, 
        active=active, 
        admin_id=ADMIN_ID
        # REMOVED: reg_open=reg_open
    )

@auth_bp.route("/admin/approve/<user_id>")
async def approve_user(user_id):
    if not is_admin(): return "Unauthorized", 403
    await users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"status": "approved"}})
    await flash("User Approved.", "success")
    return redirect(url_for('auth.manage_users'))

@auth_bp.route("/admin/delete/<user_id>")
async def delete_user(user_id):
    if not is_admin(): return "Unauthorized", 403
    
    # Prevent the admin from deleting themselves
    if user_id == ADMIN_ID:
        await flash("Cannot delete the master admin account.", "error")
        return redirect(url_for('auth.manage_users'))

    await users_col.delete_one({"_id": ObjectId(user_id)})
    await flash("User Removed.", "error")
    return redirect(url_for('auth.manage_users'))

# --- FORGOT PASSWORD SYSTEM ---

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
async def forgot_password():
    if request.method == "POST":
        form = await request.form
        username = form.get("username").lower().strip()
        user = await users_col.find_one({"username": username})

        if user:
            session['reset_user'] = username
            return redirect(url_for('auth.verify_recovery'))
        
        await flash("Identity not found in records.", "error")
    return await render_template("auth/forgot_password.html")

@auth_bp.route("/verify-recovery", methods=["GET", "POST"])
async def verify_recovery():
    username = session.get('reset_user')
    if not username:
        return redirect(url_for('auth.forgot_password'))

    user = await users_col.find_one({"username": username})
    
    # In your registration, you should add a 'security_answer' field.
    # If they don't have one (old accounts), we use a default or redirect to fix-account.
    if not user.get('security_answer'):
        await flash("No recovery method set for this account. Use Migration Tool.", "info")
        return redirect(url_for('auth.fix_account'))

    if request.method == "POST":
        form = await request.form
        answer = form.get("answer").lower().strip()
        new_password = form.get("password")

        # Check if the recovery answer matches (stored as a hash for security)
        if check_password_hash(user['security_answer'], answer):
            new_hashed_pw = generate_password_hash(new_password)
            await users_col.update_one(
                {"_id": user['_id']},
                {"$set": {"password": new_hashed_pw}}
            )
            session.pop('reset_user', None)
            await flash("Security Override Successful. Password Updated.", "success")
            return redirect(url_for('auth.login'))
        else:
            await flash("Recovery answer is incorrect.", "error")

    return await render_template("auth/verify_recovery.html", question=user.get('security_question', "What is your secret recovery key?"))

# --- SYSTEM LOGGING HELPER ---
async def log_event(message, level="info", user=None):
    """Logs a system event to MongoDB for the Admin Dashboard"""
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "level": level,
        "user": user or "System",
        "created_at": datetime.utcnow()
    }
    await get_db().system_logs.insert_one(log_entry)

# --- SYSTEM DIAGNOSTICS ROUTES ---

@auth_bp.route("/admin/system", methods=["GET", "POST"])
async def system_diagnostics():
    if not is_admin(): return redirect(url_for('tracker.index'))
    
    db = get_db()

    if request.method == "POST":
        form = await request.form
        broadcast_msg = form.get("broadcast_msg", "").strip()
        
        # Save to database
        await settings_col.update_one(
            {"type": "global_config"},
            {"$set": {"system_broadcast": broadcast_msg}},
            upsert=True
        )
        await flash("Broadcast Signal Dispatched.", "success")
        return redirect(url_for('auth.system_diagnostics'))

    # GET logic starts here
    stats = await db.command("dbStats")
    used_mb = round(stats.get('dataSize', 0) / (1024 * 1024), 2)
    
    config = await settings_col.find_one({"type": "global_config"}) or {}
    
    db_stats = {
        "used_mb": used_mb,
        "limit_mb": 512,
        "percent": round((used_mb / 512) * 100, 1),
        "uptime": f"{int((time.time() - APP_START_TIME)//3600)}h {int(((time.time() - APP_START_TIME)%3600)//60)}m",
        "broadcast": config.get('system_broadcast', ""),
        "maintenance_mode": config.get('maintenance_mode', False),
        "reg_open": config.get('registration_open', True),
        "collections": [
            {"name": "Personnel", "count": await users_col.count_documents({})},
            {"name": "Time Logs", "count": await db.logs.count_documents({})},
            {"name": "Security Logs", "count": await db.system_logs.count_documents({})}
        ]
    }

    logs = await db.system_logs.find().sort("created_at", -1).limit(100).to_list(100)
    logs.reverse()

    return await render_template("auth/admin_system.html", db_stats=db_stats, logs=logs)

@auth_bp.route("/admin/system/clear-logs", methods=["POST"])
async def clear_logs():
    if not is_admin(): return "Unauthorized", 403
    await get_db().system_logs.delete_many({})
    await log_event("System log history purged by Administrator", level="warn")
    await flash("Log history cleared.", "success")
    return redirect(url_for('auth.system_diagnostics'))

@auth_bp.route("/admin/system/toggle-<feature>", methods=["POST"])
async def toggle_system_feature(feature):
    if not is_admin(): return {"status": "unauthorized"}, 403
    
    config = await settings_col.find_one({"type": "global_config"}) or {}
    # Handles both 'maintenance_mode' and 'registration_open'
    field = "maintenance_mode" if feature == "maintenance" else "registration_open"
    current = config.get(field, False)
    
    await settings_col.update_one(
        {"type": "global_config"},
        {"$set": {field: not current}},
        upsert=True
    )
    await log_event(f"SYSTEM OVERRIDE: {field} set to {not current}", level="error")
    return {"status": "success", "new_state": not current}

@auth_bp.route("/admin/system/export-backup")
async def export_db():
    if not is_admin(): return "Unauthorized", 403
    
    db = get_db()
    data = {
        "users": await db.users.find().to_list(None),
        "logs": await db.logs.find().to_list(None),
        "settings": await db.settings.find().to_list(None)
    }
    
    # Convert ObjectIDs to strings for JSON
    def clean(obj):
        if isinstance(obj, list): return [clean(i) for i in obj]
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, ObjectId): return str(obj)
        return obj

    json_data = json.dumps(clean(data), indent=4)
    return await send_file(
        io.BytesIO(json_data.encode()),
        mimetype="application/json",
        attachment_filename=f"GATEKEEPER_BACKUP_{datetime.now().strftime('%Y%m%d')}.json",
        as_attachment=True
    )

@auth_bp.route("/admin/system/archive-session", methods=["POST"])
async def archive_session():
    if not is_admin(): return "Unauthorized", 403
    
    db = get_db()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    archive_tag = f"Archive_{timestamp}"

    # 1. Fetch all current (non-archived) logs
    current_logs = await db.logs.find({"is_archived": {"$ne": True}}).to_list(None)
    
    if not current_logs:
        await flash("No active logs found to archive.", "info")
        return redirect(url_for('auth.system_diagnostics'))

    # 2. Mark them as archived in the DB (keeps them for Global Leaderboards)
    # We add an 'is_archived' flag so the 'Active' leaderboard can ignore them
    await db.logs.update_many(
        {"is_archived": {"$ne": True}},
        {"$set": {"is_archived": True, "archive_date": timestamp}}
    )

    # 3. Create a ZIP file in memory containing the logs as JSON
    def clean_obj(obj):
        if isinstance(obj, list): return [clean_obj(i) for i in obj]
        if isinstance(obj, dict): return {k: clean_obj(v) for k, v in obj.items()}
        if isinstance(obj, ObjectId): return str(obj)
        return obj

    json_data = json.dumps(clean_obj(current_logs), indent=4)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr(f"logs_snapshot_{timestamp}.json", json_data)
        # You can add more files to the zip here (e.g. user list)
        
    zip_buffer.seek(0)

    await log_event(f"System Archived: Session {archive_tag} locked.", level="warn")
    
    return await send_file(
        zip_buffer,
        mimetype="application/zip",
        attachment_filename=f"SYSTEM_ARCHIVE_{timestamp}.zip",
        as_attachment=True
    )

@auth_bp.route("/admin/system/rollback-archive", methods=["POST"])
async def rollback_archive():
    if not is_admin(): return "Unauthorized", 403
    
    db = get_db()
    
    # 1. Find the most recent archive_date used in the system
    latest_log = await db.logs.find_one(
        {"is_archived": True}, 
        sort=[("archive_date", -1)]
    )
    
    if not latest_log or "archive_date" not in latest_log:
        await flash("No archived sessions found to rollback.", "error")
        return redirect(url_for('auth.system_diagnostics'))
    
    target_session = latest_log["archive_date"]

    # 2. Revert all logs belonging to that specific session
    result = await db.logs.update_many(
        {"archive_date": target_session},
        {
            "$set": {"is_archived": False},
            "$unset": {"archive_date": ""} # Remove the archive metadata
        }
    )

    await log_event(f"EMERGENCY ROLLBACK: Session {target_session} restored to active.", level="error")
    await flash(f"Rollback Successful. {result.modified_count} logs restored to Active status.", "success")
    
    return redirect(url_for('auth.system_diagnostics'))