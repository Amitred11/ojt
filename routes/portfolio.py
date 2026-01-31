import asyncio
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import get_db
from datetime import datetime
from utils import process_multiple_images
from bson import ObjectId

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

@portfolio_bp.route('/')
async def list_reports():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    db = get_db()
    uid = session['user_id']
    
    # Run all database queries at once for maximum speed
    p_task = db.profiles.find_one({'user_id': uid})
    w_task = db.weekly_logs.find({'user_id': uid}).sort('week_end_date', -1).to_list(50)
    r_task = db.reflections.find({'user_id': uid}).sort('month_date', -1).to_list(50)
    d_task = db.dtr_uploads.find({'user_id': uid}).sort('uploaded_at', -1).to_list(20)

    profile, weekly_logs, reflections, dtr_uploads = await asyncio.gather(
        p_task, w_task, r_task, d_task
    )

    return await render_template(
        'portfolio/portfolio.html', 
        profile=profile, 
        weekly_logs=weekly_logs, 
        reflections=reflections, 
        dtr_uploads=dtr_uploads
    )

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
    return await render_template('portfolio/portfolio_setup.html', p=p)

@portfolio_bp.route('/log/new', methods=['GET', 'POST'])
async def new_log():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        files = (await request.files).getlist('photos')
        
        # Process and compress images using the helper in utils.py
        images = await process_multiple_images(files)

        entry = {
            'user_id': session['user_id'],
            'week_end_date': form.get('week_end_date'),
            'tasks': form.get('tasks'),
            'competencies': form.get('competencies'),
            'knowledge': form.get('knowledge'),
            'images': images,
            'created_at': datetime.utcnow()
        }
        await db.weekly_logs.insert_one(entry)
        return redirect(url_for('portfolio.list_reports'))

    return await render_template('portfolio/portfolio_form_log.html', today=datetime.today().strftime('%Y-%m-%d'))

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

    return await render_template('portfolio/portfolio_form_reflection.html', today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route('/dtr/upload', methods=['GET', 'POST'])
async def upload_dtr():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        files = (await request.files).getlist('dtr_photos')
        
        images = await process_multiple_images(files)
        
        if images:
            await db.dtr_uploads.insert_one({
                'user_id': session['user_id'],
                'description': form.get('description'),
                'images': images,
                'uploaded_at': datetime.utcnow()
            })
            
        return redirect(url_for('portfolio.list_reports'))

    return await render_template('portfolio/portfolio_form_dtr.html')

@portfolio_bp.route('/delete/<report_id>')
async def delete_report(report_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    try:
        db = get_db()
        oid = ObjectId(report_id)
        uid = session['user_id']
        await asyncio.gather(
            db.weekly_logs.delete_one({'_id': oid, 'user_id': uid}),
            db.reflections.delete_one({'_id': oid, 'user_id': uid}),
            db.dtr_uploads.delete_one({'_id': oid, 'user_id': uid})
        )
    except Exception as e:
        print(f"Delete Error: {e}")
        
    return redirect(url_for('portfolio.list_reports'))

@portfolio_bp.route('/print')
async def print_journal():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    uid = session['user_id']
    
    p_task = db.profiles.find_one({'user_id': uid})
    w_task = db.weekly_logs.find({'user_id': uid}).sort('week_end_date', 1).to_list(None)
    r_task = db.reflections.find({'user_id': uid}).sort('month_date', 1).to_list(None)
    d_task = db.dtr_uploads.find({'user_id': uid}).sort('uploaded_at', 1).to_list(None)
    t_task = db.logs.find({'user_id': uid}).to_list(None)
    
    p, weekly_logs, reflections, dtr_uploads, tracker_logs = await asyncio.gather(
        p_task, w_task, r_task, d_task, t_task
    )
    
    total_hours = sum([log.get('hours', 0) for log in tracker_logs])
    
    return await render_template(
        'portfolio/print_journal.html', 
        p=p or {}, 
        weekly_logs=weekly_logs, 
        reflections=reflections,
        dtr_uploads=dtr_uploads,
        total_hours=total_hours
    )