import asyncio
from quart import Blueprint, render_template, request, redirect, url_for, session
from db import get_db
from datetime import datetime, timedelta
from util import process_multiple_images
from bson import ObjectId
# new
from utils.achievements import get_achievements
from routes.tracker import PH_HOLIDAYS
import re
# new
def is_workday(date_obj):
    if date_obj.weekday() >= 5: return False
    if date_obj.strftime('%Y-%m-%d') in PH_HOLIDAYS: return False
    return True

def get_previous_workday(date_obj):
    prev = date_obj - timedelta(days=1)
    while not is_workday(prev):
        prev -= timedelta(days=1)
    return prev

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

@portfolio_bp.route('/')
async def list_reports():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    db = get_db()
    uid = session['user_id']
    
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

from datetime import timedelta

# new
@portfolio_bp.route('/my-profile')
async def view_profile():
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    db = get_db()
    uid = session['user_id']
    
    p = await db.profiles.find_one({'user_id': uid}) or {}
    logs = await db.logs.find({'user_id': uid}).sort('log_date', -1).to_list(None)
    
    # --- INTERNAL LOGIC HELPERS (Matches tracker.py) ---
    def get_min_diff(t_in, t_out):
        if not t_in or not t_out: return 0
        try:
            t1 = datetime.strptime(t_in, "%H:%M")
            t2 = datetime.strptime(t_out, "%H:%M")
            return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
        except: return 0

    def get_ot_min(pm_out):
        if not pm_out: return 0
        try:
            out_time = datetime.strptime(pm_out, "%H:%M")
            threshold = datetime.strptime("17:00", "%H:%M")
            return int((out_time - threshold).total_seconds() // 60) if out_time > threshold else 0
        except: return 0
    # ---------------------------------------------------

    processed_logs = []
    total_credited_minutes = 0
    
    for l in logs:
        # 1. Parse date for the timeline
        log_dt_str = l['log_date']
        log_date_obj = datetime.strptime(log_dt_str, '%Y-%m-%d') if isinstance(log_dt_str, str) else log_dt_str
        
        # 2. RE-CALCULATE credited minutes from raw strings
        # This ensures old logs follow the 8h cap + OT rule
        am_m = get_min_diff(l.get('am_in'), l.get('am_out'))
        pm_m = get_min_diff(l.get('pm_in'), l.get('pm_out'))
        raw_ot = get_ot_min(l.get('pm_out'))
        
        # Apply the 8-hour (480 min) cap logic
        reg_m = min((am_m + pm_m) - raw_ot, 480)
        credited_m = reg_m + raw_ot
        
        total_credited_minutes += credited_m
        
        # Prepare for template display
        l['log_date_obj'] = log_date_obj
        l['display_hours'] = round(credited_m / 60, 1)
        processed_logs.append(l)

    # 3. Final Totals
    total_hours_numeric = total_credited_minutes / 60
    log_count = len(processed_logs)
    avg_daily = round(total_hours_numeric / log_count, 1) if log_count else 0

    # 4. Target & Progress
    target = 486 
    if p.get('duration'):
        digits = re.findall(r'\d+', str(p['duration']))
        if digits: target = int(digits[0])
    progress = min(int((total_hours_numeric / target) * 100), 100) if target > 0 else 0

    # 5. Leaderboard Rank
    # For the leaderboard, we still use the stored credited_minutes for efficiency
    pipeline = [
        {"$group": {"_id": "$user_id", "total_m": {"$sum": "$credited_minutes"}}}, 
        {"$match": {"total_m": {"$gt": total_credited_minutes}}}
    ]
    higher_users = await db.logs.aggregate(pipeline).to_list(None)
    rank = len(higher_users) + 1

    # 6. Streak
    streak_days = 0
    if processed_logs:
        log_dates = sorted({l['log_date_obj'].date() for l in processed_logs}, reverse=True)
        streak_days = 1
        for i in range(len(log_dates) - 1):
            expected = get_previous_workday(log_dates[i])
            if log_dates[i+1] == expected:
                streak_days += 1
            else:
                break

    # 7. Achievement Stats
    stats = {
        'rank': rank, 
        'total_hours': total_hours_numeric, 
        'log_count': log_count,
        'avg_daily': avg_daily, 
        'progress': progress, 
        'streak_days': streak_days,
        'early_logs': sum(1 for l in processed_logs if l.get('am_in') and int(l.get('am_in').split(':')[0]) < 8), 
        'late_logs': sum(1 for l in processed_logs if l.get('pm_out') and int(l.get('pm_out').split(':')[0]) >= 21), 
        'max_daily_hours': max([l['display_hours'] for l in processed_logs]) if processed_logs else 0, 
        'weekend_logs': sum(1 for l in processed_logs if l['log_date_obj'].weekday() >= 5)
    }
    
    achievements = get_achievements(stats)

    return await render_template(
        'main/profile.html', 
        p=p, 
        total_hours=round(total_hours_numeric, 1), 
        log_count=log_count, 
        avg_hours=avg_daily, 
        progress=progress, 
        recent_activity=processed_logs[:5], 
        achievements=achievements
    )

# --- WEEKLY LOGS ---

@portfolio_bp.route('/log/new', methods=['GET', 'POST'])
async def new_log():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    if request.method == 'POST':
        try:
            db = get_db()
            form = await request.form
            files = (await request.files).getlist('photos')
            if len(files) > 6:
                return "Error: Maximum 6 images allowed", 400
            images = await process_multiple_images(files)
            await db.weekly_logs.insert_one({
                'user_id': session['user_id'],
                'week_end_date': form.get('week_end_date'),
                'tasks': form.get('tasks'),
                'competencies': form.get('competencies'),
                'knowledge': form.get('knowledge'),
                'images': images,
                'created_at': datetime.utcnow()
            })
            return redirect(url_for('portfolio.list_reports'))
        except Exception as e:
            return f"Error: {e}", 500
    return await render_template('portfolio/portfolio_form_log.html', today=datetime.today().strftime('%Y-%m-%d'), log=None)

@portfolio_bp.route('/log/edit/<log_id>', methods=['GET', 'POST'])
async def edit_log(log_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    if request.method == 'POST':
        form = await request.form
        files = (await request.files).getlist('photos')
        update_data = {
            'week_end_date': form.get('week_end_date'),
            'tasks': form.get('tasks'),
            'competencies': form.get('competencies'),
            'knowledge': form.get('knowledge'),
            'updated_at': datetime.utcnow()
        }
        if files and files[0].filename != '':
            if len(files) > 6:
                return "Error: Maximum 6 images allowed", 400
            
            new_imgs = await process_multiple_images(files)
            if new_imgs: update_data['images'] = new_imgs
        await db.weekly_logs.update_one({'_id': ObjectId(log_id), 'user_id': session['user_id']}, {'$set': update_data})
        return redirect(url_for('portfolio.list_reports'))
    
    log = await db.weekly_logs.find_one({'_id': ObjectId(log_id)})
    return await render_template('portfolio/portfolio_form_log.html', log=log)

# --- DTR ---

@portfolio_bp.route('/dtr/upload', methods=['GET', 'POST'])
async def upload_dtr():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        files = await request.files
        f_img = await process_multiple_images(files.getlist('dtr_front'))
        b_img = await process_multiple_images(files.getlist('dtr_back'))
        await db.dtr_uploads.insert_one({
            'user_id': session['user_id'],
            'description': form.get('description'),
            'image_front': f_img[0] if f_img else None,
            'image_back': b_img[0] if b_img else None,
            'uploaded_at': datetime.utcnow()
        })
        return redirect(url_for('portfolio.list_reports'))
    return await render_template('portfolio/portfolio_form_dtr.html', dtr=None)

@portfolio_bp.route('/dtr/edit/<dtr_id>', methods=['GET', 'POST'])
async def edit_dtr(dtr_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    if request.method == 'POST':
        form = await request.form
        files = await request.files
        update_data = {'description': form.get('description'), 'updated_at': datetime.utcnow()}
        
        f_check = files.getlist('dtr_front')
        if f_check and f_check[0].filename != '':
            imgs = await process_multiple_images(f_check)
            if imgs: update_data['image_front'] = imgs[0]
            
        b_check = files.getlist('dtr_back')
        if b_check and b_check[0].filename != '':
            imgs = await process_multiple_images(b_check)
            if imgs: update_data['image_back'] = imgs[0]

        await db.dtr_uploads.update_one({'_id': ObjectId(dtr_id), 'user_id': session['user_id']}, {'$set': update_data})
        return redirect(url_for('portfolio.list_reports'))
    
    dtr = await db.dtr_uploads.find_one({'_id': ObjectId(dtr_id)})
    return await render_template('portfolio/portfolio_form_dtr.html', dtr=dtr)

# --- REFLECTIONS ---

@portfolio_bp.route('/reflection/new', methods=['GET', 'POST'])
async def new_reflection():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    if request.method == 'POST':
        db = get_db()
        form = await request.form
        await db.reflections.insert_one({
            'user_id': session['user_id'],
            'month_date': form.get('month_date'),
            'monthly_reflection': form.get('monthly_reflection'),
            'self_evaluation': form.get('self_evaluation'),
            'feedback': form.get('feedback'),
            'created_at': datetime.utcnow()
        })
        return redirect(url_for('portfolio.list_reports'))
    return await render_template('portfolio/portfolio_form_reflection.html', r=None)

@portfolio_bp.route('/reflection/edit/<r_id>', methods=['GET', 'POST'])
async def edit_reflection(r_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    if request.method == 'POST':
        form = await request.form
        await db.reflections.update_one(
            {'_id': ObjectId(r_id), 'user_id': session['user_id']},
            {'$set': {
                'month_date': form.get('month_date'),
                'monthly_reflection': form.get('monthly_reflection'),
                'self_evaluation': form.get('self_evaluation'),
                'feedback': form.get('feedback'),
                'updated_at': datetime.utcnow()
            }}
        )
        return redirect(url_for('portfolio.list_reports'))
    
    reflection = await db.reflections.find_one({'_id': ObjectId(r_id)})
    return await render_template('portfolio/portfolio_form_reflection.html', r=reflection)

# --- ACTIONS ---

@portfolio_bp.route('/delete/<report_id>')
async def delete_report(report_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    oid = ObjectId(report_id)
    uid = session['user_id']
    await asyncio.gather(
        db.weekly_logs.delete_one({'_id': oid, 'user_id': uid}),
        db.reflections.delete_one({'_id': oid, 'user_id': uid}),
        db.dtr_uploads.delete_one({'_id': oid, 'user_id': uid})
    )
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
    p, weekly_logs, reflections, dtr_uploads, tracker_logs = await asyncio.gather(p_task, w_task, r_task, d_task, t_task)
    total_hours = sum([log.get('hours', 0) for log in tracker_logs])
    return await render_template('portfolio/print_journal.html', p=p or {}, weekly_logs=weekly_logs, reflections=reflections, dtr_uploads=dtr_uploads, total_hours=total_hours)