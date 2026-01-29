import base64
from quart import Blueprint, render_template, request, redirect, url_for, session
from bson.objectid import ObjectId
from datetime import datetime
from db import reports_col, profiles_col

# --- FIX: Use __name__ instead of name ---
portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route("/portfolio")
async def list_reports():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']

    # 1. Fetch Profile Data
    profile = await profiles_col.find_one({"user_id": user_id})

    # 2. Fetch Weekly Logs
    cursor_logs = reports_col.find({"user_id": user_id, "type": "weekly"}).sort("week_end_date", -1)
    weekly_logs = await cursor_logs.to_list(length=None)
    for r in weekly_logs: r['_id'] = str(r['_id'])

    # 3. Fetch Monthly Reflections
    cursor_ref = reports_col.find({"user_id": user_id, "type": "monthly"}).sort("month_date", -1)
    reflections = await cursor_ref.to_list(length=None)
    for r in reflections: r['_id'] = str(r['_id'])

    return await render_template("portfolio.html", 
                                 profile=profile, 
                                 weekly_logs=weekly_logs, 
                                 reflections=reflections)

@portfolio_bp.route("/portfolio/setup", methods=["GET", "POST"])
async def setup_profile():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']

    if request.method == "POST":
        form = await request.form
        profile_data = {
            "user_id": user_id,
            "full_name": form.get("full_name"),
            "course": form.get("course"),
            "hte_name": form.get("hte_name"),
            "duration": form.get("duration"),
            "supervisor": form.get("supervisor"),
            "objectives": form.get("objectives"),
            "company_desc": form.get("company_desc"),
            "dept_desc": form.get("dept_desc"),
        }
        
        await profiles_col.update_one(
            {"user_id": user_id}, 
            {"$set": profile_data}, 
            upsert=True
        )
        return redirect(url_for("portfolio.list_reports"))

    profile = await profiles_col.find_one({"user_id": user_id})
    return await render_template("portfolio_setup.html", p=profile or {})

@portfolio_bp.route("/portfolio/log/new", methods=["GET", "POST"])
async def new_log():
    if 'user_id' not in session: return redirect(url_for('auth.login'))

    if request.method == "POST":
        form = await request.form
        files = await request.files
        
        image_data = None
        if 'photo' in files:
            file = files['photo']
            if file.filename:
                file_content = file.read()
                image_data = base64.b64encode(file_content).decode('utf-8')

        report_data = {
            "user_id": session['user_id'],
            "type": "weekly",
            "week_end_date": form.get("week_end_date"),
            "tasks": form.get("tasks"),
            "competencies": form.get("competencies"),
            "knowledge": form.get("knowledge"),
            "image_data": image_data
        }
        
        await reports_col.insert_one(report_data)
        return redirect(url_for("portfolio.list_reports"))

    return await render_template("portfolio_form_log.html", today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route("/portfolio/reflection/new", methods=["GET", "POST"])
async def new_reflection():
    if 'user_id' not in session: return redirect(url_for('auth.login'))

    if request.method == "POST":
        form = await request.form
        
        reflection_data = {
            "user_id": session['user_id'],
            "type": "monthly",
            "month_date": form.get("month_date"),
            "monthly_reflection": form.get("monthly_reflection"),
            "self_evaluation": form.get("self_evaluation"),
            "feedback": form.get("feedback")
        }
        
        await reports_col.insert_one(reflection_data)
        return redirect(url_for("portfolio.list_reports"))

    return await render_template("portfolio_form_reflection.html", today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route("/portfolio/delete/<report_id>")
async def delete_report(report_id):
    if 'user_id' in session:
        await reports_col.delete_one({"_id": ObjectId(report_id), "user_id": session['user_id']})
    return redirect(url_for("portfolio.list_reports"))