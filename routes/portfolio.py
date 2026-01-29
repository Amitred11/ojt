import base64
from quart import Blueprint, render_template, request, redirect, url_for, session
from bson.objectid import ObjectId
from db import journal_col, journal_entries_col, files_col, logs_col

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route("/portfolio")
async def index():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    
    # Fetch data with safety defaults
    journal = await journal_col.find_one({"user_id": user_id}) or {}
    entries = await journal_entries_col.find({"user_id": user_id}).sort("date", -1).to_list(length=None)
    uploads = await files_col.find({"user_id": user_id}).to_list(length=None)

    return await render_template("portfolio.html", 
                                 journal=journal, 
                                 entries=entries, 
                                 uploads=uploads,
                                 section=request.args.get('section', '1'))

@portfolio_bp.route("/portfolio/save_static", methods=["POST"])
async def save_static():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    form = await request.form
    data = form.to_dict()
    
    # Remove technical keys
    update_fields = {k: v for k, v in data.items() if k not in ['_id', 'user_id', 'active_section']}

    await journal_col.update_one(
        {"user_id": session['user_id']},
        {"$set": update_fields},
        upsert=True
    )
    
    return redirect(url_for('portfolio.index', section=form.get('active_section', '1')))

@portfolio_bp.route("/portfolio/entry/add", methods=["POST"])
async def add_entry():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    form = await request.form
    
    entry_data = {
        "user_id": session['user_id'],
        "date": form.get("date"),
        "hours_worked": form.get("hours_worked"),
        "task_description": form.get("task_description"),
        "competencies": form.get("competencies"),
        "new_knowledge": form.get("new_knowledge")
    }
    
    await journal_entries_col.insert_one(entry_data)
    return redirect(url_for('portfolio.index', section='4'))

@portfolio_bp.route("/portfolio/upload", methods=["POST"])
async def upload_file():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    form = await request.form
    files = await request.files
    category = form.get("category")
    
    if 'file' in files:
        file = files['file']
        if file.filename:
            # Convert image to Base64 string for DB storage
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
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    
    journal = await journal_col.find_one({"user_id": user_id}) or {}
    entries = await journal_entries_col.find({"user_id": user_id}).sort("date", 1).to_list(None)
    all_files = await files_col.find({"user_id": user_id}).to_list(None)
    dtr_logs = await logs_col.find({"user_id": user_id}).sort("log_date", 1).to_list(None)
    
    docs = {
        'photos': [f for f in all_files if f.get('category') == 'photo'],
        'samples': [f for f in all_files if f.get('category') == 'sample'],
        'certs': [f for f in all_files if f.get('category') == 'certificate'],
        'org_chart': next((f for f in all_files if f.get('category') == 'org_chart'), None)
    }

    return await render_template("print_journal.html", j=journal, entries=entries, docs=docs, dtr=dtr_logs)