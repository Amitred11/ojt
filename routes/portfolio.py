import base64
from quart import Blueprint, render_template, request, redirect, url_for, session
from bson.objectid import ObjectId
from datetime import datetime
from db import journal_col, journal_entries_col, files_col, logs_col

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route("/portfolio")
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    
    # Fetch existing data
    journal = await journal_col.find_one({"user_id": user_id}) or {}
    
    # Fetch Journal Entries (Section 4)
    cursor = journal_entries_col.find({"user_id": user_id}).sort("date", -1)
    entries = await cursor.to_list(length=None)
    
    # Fetch Uploads (Section 6)
    cursor_files = files_col.find({"user_id": user_id})
    uploads = await cursor_files.to_list(length=None)

    return await render_template("portfolio.html", 
                                 journal=journal, 
                                 entries=entries, 
                                 uploads=uploads,
                                 section=request.args.get('section', '1'))

@portfolio_bp.route("/portfolio/save_static", methods=["POST"])
async def save_static():
    """Saves Sections 1, 2, 3, and 5 (Static Text Data)"""
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    form = await request.form
    data = form.to_dict()
    
    # Process generic updates for the main journal document
    update_fields = {}
    for key, value in data.items():
        if key not in ['_id', 'user_id']:
            update_fields[key] = value

    await journal_col.update_one(
        {"user_id": session['user_id']},
        {"$set": update_fields},
        upsert=True
    )
    
    # Redirect back to the specific tab
    section = form.get('active_section', '1')
    return redirect(url_for('portfolio.index', section=section))

@portfolio_bp.route("/portfolio/entry/add", methods=["POST"])
async def add_entry():
    """Saves Section 4: Daily/Weekly Work Log Item"""
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    form = await request.form
    
    entry_data = {
        "user_id": session['user_id'],
        "date": form.get("date"),
        "hours_worked": form.get("hours_worked"),
        "task_description": form.get("task_description"), # Bullet points
        "competencies": form.get("competencies"),
        "new_knowledge": form.get("new_knowledge")
    }
    
    await journal_entries_col.insert_one(entry_data)
    return redirect(url_for('portfolio.index', section='4'))

@portfolio_bp.route("/portfolio/upload", methods=["POST"])
async def upload_file():
    """Saves Section 6: Appendices"""
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    form = await request.form
    files = await request.files
    
    category = form.get("category") # 'photo', 'sample', 'certificate', 'org_chart'
    
    if 'file' in files:
        file = files['file']
        if file.filename:
            file_content = file.read()
            b64_data = base64.b64encode(file_content).decode('utf-8')
            
            await files_col.insert_one({
                "user_id": session['user_id'],
                "category": category,
                "caption": form.get("caption", ""),
                "image_data": b64_data
            })

    target_section = '3' if category == 'org_chart' else '6'
    return redirect(url_for('portfolio.index', section=target_section))

@portfolio_bp.route("/portfolio/entry/delete/<entry_id>")
async def delete_entry(entry_id):
    if 'user_id' in session:
        await journal_entries_col.delete_one({"_id": ObjectId(entry_id), "user_id": session['user_id']})
    return redirect(url_for('portfolio.index', section='4'))

@portfolio_bp.route("/portfolio/file/delete/<file_id>")
async def delete_file(file_id):
    if 'user_id' in session:
        await files_col.delete_one({"_id": ObjectId(file_id), "user_id": session['user_id']})
    return redirect(url_for('portfolio.index', section='6'))

@portfolio_bp.route("/portfolio/print")
async def print_view():
    """Generates the Full HTML Journal for Printing to PDF"""
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    
    journal = await journal_col.find_one({"user_id": user_id}) or {}
    entries = await journal_entries_col.find({"user_id": user_id}).sort("date", 1).to_list(None)
    
    # Group files by category
    files_cursor = files_col.find({"user_id": user_id})
    all_files = await files_cursor.to_list(None)
    
    docs = {
        'photos': [f for f in all_files if f.get('category') == 'photo'],
        'samples': [f for f in all_files if f.get('category') == 'sample'],
        'certs': [f for f in all_files if f.get('category') == 'certificate'],
        'org_chart': next((f for f in all_files if f.get('category') == 'org_chart'), None)
    }

    # Fetch DTR data from the Tracker part of the app
    dtr_logs = await logs_col.find({"user_id": user_id}).sort("log_date", 1).to_list(None)

    return await render_template("print_journal.html", j=journal, entries=entries, docs=docs, dtr=dtr_logs)