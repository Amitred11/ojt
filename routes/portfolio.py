import base64
from quart import Blueprint, render_template, request, redirect, url_for, session
from bson.objectid import ObjectId
from datetime import datetime
from db import reports_col

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route("/portfolio")
async def list_reports():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    cursor = reports_col.find({"user_id": session['user_id']}).sort("week_end_date", -1)
    reports = await cursor.to_list(length=None)
    for r in reports: r['_id'] = str(r['_id'])
    
    return await render_template("portfolio.html", reports=reports)

@portfolio_bp.route("/portfolio/new", methods=["GET", "POST"])
async def new_report():
    if 'user_id' not in session: return redirect(url_for('auth.login'))

    if request.method == "POST":
        form = await request.form
        files = await request.files
        
        # Process Image for Database Storage (Base64)
        image_data = None
        if 'photo' in files:
            file = files['photo']
            if file.filename:
                # Read file bytes, encode to base64 string
                file_content = file.read()
                image_data = base64.b64encode(file_content).decode('utf-8')

        report_data = {
            "user_id": session['user_id'],
            "week_end_date": form.get("week_end_date"),
            "learnings": form.get("learnings"),
            "activities": form.get("activities"),
            "reflections": form.get("reflections"),
            "image_data": image_data # Storing string directly in DB
        }
        
        await reports_col.insert_one(report_data)
        return redirect(url_for("portfolio.list_reports"))

    return await render_template("portfolio_form.html", today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route("/portfolio/delete/<report_id>")
async def delete_report(report_id):
    if 'user_id' in session:
        await reports_col.delete_one({"_id": ObjectId(report_id), "user_id": session['user_id']})
    return redirect(url_for("portfolio.list_reports"))