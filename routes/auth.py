from quart import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import users_col

# Fix: Use __name__
auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    # If already logged in, go to home
    if 'user_id' in session:
        return redirect(url_for('tracker.index'))

    if request.method == "POST":
        form = await request.form
        username = form.get("username")
        password = form.get("password")

        user = await users_col.find_one({"username": username})

        # Secure password check
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            # Success Alert
            await flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for('tracker.index'))
        
        # Error Alert
        await flash("Invalid Username or Password.", "error")
        return redirect(url_for('auth.login'))

    return await render_template("login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
async def register():
    if 'user_id' in session:
        return redirect(url_for('tracker.index'))

    if request.method == "POST":
        form = await request.form
        username = form.get("username")
        password = form.get("password")
        security_code = form.get("security_code") # <--- Get the input

        # 1. CHECK THE SECURITY CODE
        required_code = current_app.config['REGISTRATION_KEY']
        
        if security_code != required_code:
            await flash("Invalid Security Access Key. Registration denied.", "error")
            return redirect(url_for('auth.register'))

        # 2. Check if username exists
        existing_user = await users_col.find_one({"username": username})
        if existing_user:
            await flash("Username is already taken.", "error")
            return redirect(url_for('auth.register'))

        # 3. Create Account
        hashed_pw = generate_password_hash(password)
        await users_col.insert_one({"username": username, "password": hashed_pw})
        
        await flash("Access Granted! Account created successfully.", "success")
        return redirect(url_for('auth.login'))

    return await render_template("register.html")
@auth_bp.route("/logout")
async def logout():
    session.clear()
    await flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))

# --- NEW: POP-UP MIGRATION HANDLER ---
@auth_bp.route("/fix-account", methods=["POST"])
async def fix_account():
    form = await request.form
    username = form.get("username")
    old_password = form.get("password")

    user = await users_col.find_one({"username": username})

    if user:
        # Case 1: Password is PLAIN TEXT (Needs fixing)
        if user['password'] == old_password:
            hashed_pw = generate_password_hash(old_password)
            await users_col.update_one(
                {"_id": user['_id']},
                {"$set": {"password": hashed_pw}}
            )
            await flash("Account repaired! You can now log in securely.", "success")
        
        # Case 2: Password is already HASHED (No fix needed)
        elif check_password_hash(user['password'], old_password):
            await flash("Your account is already secure. Just log in normally.", "info")
        
        # Case 3: Wrong password
        else:
            await flash("Incorrect old password. Cannot verify account.", "error")
    else:
        await flash("Username not found.", "error")

    return redirect(url_for('auth.login'))