from quart import Blueprint, render_template, request, redirect, url_for, session
from db import get_db
from datetime import datetime
import base64

# Import ObjectId safely
try:
    from bson.objectid import ObjectId
except ImportError:
    # Fallback if bson is missing, though motor usually includes it
    from bson import ObjectId

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

# --- HELPER ---
def process_image(file_storage):
    if not file_storage:
        return None
    try:
        if hasattr(file_storage, 'read'):
            return base64.b64encode(file_storage.read()).decode('utf-8')
    except Exception as e:
        print(f"Image Error: {e}")
    return None

# --- ROUTES ---

@portfolio_bp.route('/')
async def list_reports():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    db = get_db()
    user_id = session['user_id']
    
    profile = await db.profiles.find_one({'user_id': user_id})
    weekly_logs = await db.weekly_logs.find({'user_id': user_id}).sort('week_end_date', -1).to_list(length=100)
    reflections = await db.reflections.find({'user_id': user_id}).sort('month_date', -1).to_list(length=100)

    return await render_template('portfolio.html', profile=profile, weekly_logs=weekly_logs, reflections=reflections)

@portfolio_bp.route('/setup', methods=['GET', 'POST'])
async def setup_profile():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    
    if request.method == 'POST':
        form = await request.form
        data = {
            'user_id': session['user_id'],
            'full_name': form.get('full_name'),
            'course': form.get('course'),
            'duration': form.get('duration'),
            'objectives': form.get('objectives'),
            'hte_name': form.get('hte_name'),
            'supervisor': form.get('supervisor'),
            'company_desc': form.get('company_desc'),
            'dept_desc': form.get('dept_desc'),
            'updated_at': datetime.utcnow()
        }
        await db.profiles.update_one({'user_id': session['user_id']}, {'$set': data}, upsert=True)
        return redirect(url_for('portfolio.list_reports'))

    p = await db.profiles.find_one({'user_id': session['user_id']}) or {}
    return await render_template('portfolio_setup.html', p=p)

@portfolio_bp.route('/log/new', methods=['GET', 'POST'])
async def new_log():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        files = await request.files
        uploaded_photos = files.getlist('photos')
        
        images_list = []
        for photo in uploaded_photos:
            if photo.filename:
                b64 = process_image(photo)
                if b64: images_list.append(b64)

        entry = {
            'user_id': session['user_id'],
            'week_end_date': form.get('week_end_date'),
            'tasks': form.get('tasks'),
            'competencies': form.get('competencies'),
            'knowledge': form.get('knowledge'),
            'images': images_list,
            'created_at': datetime.utcnow()
        }
        await db.weekly_logs.insert_one(entry)
        return redirect(url_for('portfolio.list_reports'))

    return await render_template('portfolio_form_log.html', today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route('/reflection/new', methods=['GET', 'POST'])
async def new_reflection():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        entry = {
            'user_id': session['user_id'],
            'month_date': form.get('month_date'),
            'monthly_reflection': form.get('monthly_reflection'),
            'self_evaluation': form.get('self_evaluation'),
            'feedback': form.get('feedback'),
            'created_at': datetime.utcnow()
        }
        await db.reflections.insert_one(entry)
        return redirect(url_for('portfolio.list_reports'))

    return await render_template('portfolio_form_reflection.html', today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route('/dtr/upload', methods=['GET', 'POST'])
async def upload_dtr():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        files = await request.files
        dtr_photos = files.getlist('dtr_photos')
        
        processed_images = []
        for photo in dtr_photos:
            if photo.filename:
                b64 = process_image(photo)
                if b64: processed_images.append(b64)
        
        if processed_images:
            entry = {
                'user_id': session['user_id'],
                'description': form.get('description'),
                'images': processed_images,
                'uploaded_at': datetime.utcnow()
            }
            await db.dtr_uploads.insert_one(entry)
            
        return redirect(url_for('portfolio.list_reports'))

    return await render_template('portfolio_form_dtr.html')

@portfolio_bp.route('/delete/<report_id>')
async def delete_report(report_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    try:
        db = get_db()
        oid = ObjectId(report_id)
        # Attempt delete on all portfolio collections
        await db.weekly_logs.delete_one({'_id': oid, 'user_id': session['user_id']})
        await db.reflections.delete_one({'_id': oid, 'user_id': session['user_id']})
        await db.dtr_uploads.delete_one({'_id': oid, 'user_id': session['user_id']})
    except Exception as e:
        print(f"Delete Error: {e}")
        
    return redirect(url_for('portfolio.list_reports'))

@portfolio_bp.route('/print')
async def print_journal():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    user_id = session['user_id']
    
    p = await db.profiles.find_one({'user_id': user_id}) or {}
    weekly_logs = await db.weekly_logs.find({'user_id': user_id}).sort('week_end_date', 1).to_list(None)
    reflections = await db.reflections.find({'user_id': user_id}).sort('month_date', 1).to_list(None)
    dtr_uploads = await db.dtr_uploads.find({'user_id': user_id}).sort('uploaded_at', 1).to_list(None)
    
    # Optional Tracker Summary
    tracker_logs = await db.logs.find({'user_id': user_id}).to_list(None)
    total_hours = sum([log.get('hours', 0) for log in tracker_logs])
    
    return await render_template('print_journal.html', 
                                 p=p, 
                                 weekly_logs=weekly_logs, 
                                 reflections=reflections,
                                 dtr_uploads=dtr_uploads,
                                 total_hours=total_hours)