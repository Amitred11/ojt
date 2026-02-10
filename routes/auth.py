from quart import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import users_col, get_db
from bson import ObjectId

auth_bp = Blueprint('auth', __name__)

# Constants
ADMIN_ID = "6979fc7f59b791fd5fcbf90f"

# Helper to check if user is the specific admin
def is_admin():
    return session.get('user_id') == ADMIN_ID

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
        await flash("Access Denied: Admin privileges required.", "error")
        return redirect(url_for('tracker.index'))
    
    db = get_db()
    
    # Aggregation to get users and their sum of hours from the logs collection
    pipeline = [
        {
            "$lookup": {
                "from": "logs",
                "localField": "_id",
                "foreignField": "user_id",
                "as": "user_logs"
            }
        },
        {
            "$project": {
                "username": 1,
                "status": 1,
                "total_hours": { "$sum": "$user_logs.hours" }
            }
        },
        { "$sort": {"username": 1} }
    ]
    
    all_users = await users_col.aggregate(pipeline).to_list(length=500)
    
    # Filter lists for the template
    pending = [u for u in all_users if u.get('status') == 'pending']
    active = [u for u in all_users if u.get('status') == 'approved']
    
    return await render_template(
        "auth/admin_users.html", 
        pending=pending, 
        active=active, 
        admin_id=ADMIN_ID
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