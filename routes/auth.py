from quart import Blueprint, render_template, request, redirect, url_for, session
from db import users_col

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    if request.method == "POST":
        form = await request.form
        username = form.get("username")
        password = form.get("password")

        user = await users_col.find_one({"username": username})

        if user and user['password'] == password:
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            return redirect(url_for('tracker.index'))
        
        return await render_template("login.html", error="Invalid credentials")

    return await render_template("login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
async def register():
    if request.method == "POST":
        form = await request.form
        username = form.get("username")
        password = form.get("password")

        existing_user = await users_col.find_one({"username": username})
        if existing_user:
            return await render_template("register.html", error="Username taken")

        await users_col.insert_one({"username": username, "password": password})
        return redirect(url_for('auth.login'))

    return await render_template("register.html")

@auth_bp.route("/logout")
async def logout():
    session.clear()
    return redirect(url_for('auth.login'))