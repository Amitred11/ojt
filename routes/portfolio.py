import asyncio
from quart import Blueprint, render_template, request, redirect, url_for, flash,  session
from db import get_db
from datetime import datetime, timedelta
from util import process_multiple_images
from bson import ObjectId
# new
from utils.achievements import get_achievements
from routes.tracker import PH_HOLIDAYS
import re

def calculate_credited_minutes(log, settings):
    """Matches the exact logic used in the Leaderboard route."""
    def normalize_time(t_str):
        if not t_str or ":" not in t_str: return None
        try:
            parts = t_str.split(':')
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except: return None

    nai = normalize_time(log.get('am_in'))
    nao = normalize_time(log.get('am_out'))
    npi = normalize_time(log.get('pm_in'))
    npo = normalize_time(log.get('pm_out'))

    # Start time logic (e.g., 7am vs 8am)
    eff_ai = "08:00" if (not settings.get('allow_before_7am') and nai and nai < "08:00") else nai
    
    # Calculate durations
    def get_diff(t1_str, t2_str):
        if not t1_str or not t2_str: return 0
        try:
            t1 = datetime.strptime(t1_str, "%H:%M")
            t2 = datetime.strptime(t2_str, "%H:%M")
            return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
        except: return 0

    m_am = get_diff(eff_ai, nao)
    m_pm = get_diff(npi, npo)
    
    # Lunch Logic
    m_lunch = 60 if (settings.get('count_lunch') and nao and npi and 
                    "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15") else 0
    
    # OT Logic
    day_ot = 0
    if settings.get('allow_after_5pm') and npo:
        try:
            out_time = datetime.strptime(npo, "%H:%M")
            threshold = datetime.strptime("17:00", "%H:%M")
            day_ot = int((out_time - threshold).total_seconds() // 60) if out_time > threshold else 0
        except: pass

    total = m_am + m_pm + m_lunch
    
    if settings.get('strict_8h'):
        return min(total, 480)
    
    return total + day_ot

def normalize_time(t_str):
    if not t_str or ":" not in t_str: return None
    try:
        parts = t_str.split(':')
        # This ensures "8:30" becomes "08:30", making string comparison ("<") work!
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except: return None

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
        files = await request.files
        
        # Process new document images
        cert_img = await process_multiple_images(files.getlist('certificate_img'))
        struct_img = await process_multiple_images(files.getlist('structure_img'))
        work_samples = await process_multiple_images(files.getlist('work_samples'))

        data = {
            'user_id': session['user_id'],
            'full_name': form.get('full_name'),
            'course': form.get('course'),
            'duration': form.get('duration'),
            'objectives': form.get('objectives'),
            'hte_name': form.get('hte_name'),
            'supervisor': form.get('supervisor'),
            # New Guide Fields
            'coordinator_name': form.get('coordinator_name'),
            'acknowledgement': form.get('acknowledgement'),
            'company_desc': form.get('company_desc'),
            'dept_desc': form.get('dept_desc'),
            'updated_at': datetime.utcnow()
        }

        # Only update images if new ones are uploaded
        if cert_img: data['certificate_img'] = cert_img[0]
        if struct_img: data['structure_img'] = struct_img[0]
        if work_samples: data['work_samples'] = work_samples # List of images

        await db.profiles.update_one({'user_id': session['user_id']}, {'$set': data}, upsert=True)
        return redirect(url_for('portfolio.list_reports'))

    p = await db.profiles.find_one({'user_id': session['user_id']}) or {}
    return await render_template('portfolio/portfolio_setup.html', p=p)

# new
# routes/portfolio.py

@portfolio_bp.route('/user/<user_id>')
@portfolio_bp.route('/my-profile')
async def view_profile(user_id=None):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    db = get_db()
    curr_uid = str(session['user_id'])
    target_uid = user_id if user_id else curr_uid
    is_owner = (target_uid == curr_uid)

    # 1. Fetch All Data for Ranking (Sync with Leaderboard)
    all_logs = await db.logs.find({}).to_list(None)
    all_settings = await db.settings.find({}).to_list(None)
    p = await db.profiles.find_one({'user_id': target_uid}) or {}
    
    settings_map = {str(s['user_id']): s for s in all_settings}
    
    # 2. Process ALL users to determine Rank (The Leaderboard Logic)
    user_totals = {} 
    target_user_logs = []
    
    # Achievement-specific counters for target user
    early_logs = 0
    late_logs = 0
    weekend_logs = 0

    for log in all_logs:
        uid = str(log['user_id'])
        # Get settings or default
        u_set = settings_map.get(uid, {
            "strict_8h": False, "count_lunch": False, 
            "allow_before_7am": False, "allow_after_5pm": True, 
            "include_weekends_eta": False
        })
        
        # Calculate minutes using the EXACT same logic as leaderboard
        credited_m = calculate_credited_minutes(log, u_set)
        
        # Add to global totals for ranking
        user_totals[uid] = user_totals.get(uid, 0) + credited_m
        
        # If this log belongs to the profile we are viewing, track extra stats
        if uid == target_uid:
            log_date_str = log.get('log_date', "")
            try:
                log_date_obj = datetime.strptime(log_date_str, '%Y-%m-%d')
                if log_date_obj.weekday() >= 5: weekend_logs += 1
            except: 
                log_date_obj = datetime.now()

            # Early Bird / Night Owl checks
            nai = normalize_time(log.get('am_in'))
            npo = normalize_time(log.get('pm_out'))
            if nai and nai < "08:00": early_logs += 1
            if npo and npo >= "20:00": late_logs += 1

            log['log_date_obj'] = log_date_obj
            log['display_hours'] = round(credited_m / 60, 2)
            target_user_logs.append(log)

    # 3. Determine Rank (Sort everyone by total minutes)
    sorted_ranking = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)
    
    actual_rank = 0
    for i, (uid, total) in enumerate(sorted_ranking, 1):
        if uid == target_uid:
            actual_rank = i
            break

    # 4. Final Calculations for the Target User
    total_minutes = user_totals.get(target_uid, 0)
    total_hours = total_minutes / 60
    log_count = len(target_user_logs)
    
    # Goal logic
    target_goal = 486
    progress = min(int((total_hours / target_goal) * 100), 100)
    avg_daily = round(total_hours / log_count, 1) if log_count > 0 else 0

    # 5. Sync Achievements with stats
    stats = {
        'rank': actual_rank, 
        'total_hours': total_hours,
        'log_count': log_count,
        'avg_daily': avg_daily, 
        'progress': progress,
        'early_logs': early_logs, 
        'late_logs': late_logs,
        'weekend_logs': weekend_logs
    }
    achievements = get_achievements(stats)
    
    context = {
        'p': p, 
        'total_hours': round(total_hours, 2), 
        'log_count': log_count, 
        'avg_hours': avg_daily, 
        'progress': progress, 
        'achievements': achievements, 
        'rank': actual_rank,
        'is_owner': is_owner,
    }

    template = 'main/profile.html' if is_owner else 'main/public_profile.html'
    return await render_template(template, **context, recent_activity=target_user_logs[:5])

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

@portfolio_bp.route('/setup/delete-file/<field_name>')
async def delete_profile_file(field_name):
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    db = get_db()
    allowed_fields = ['certificate_img', 'structure_img']
    
    if field_name in allowed_fields:
        await db.profiles.update_one(
            {'user_id': session['user_id']},
            {'$unset': {field_name: ""}}
        )
        flash(f"{field_name.replace('_img', '').title()} deleted successfully", "success")
    
    return redirect(url_for('portfolio.view_profile'))

@portfolio_bp.route('/setup/delete-work-sample/<int:index>')
async def delete_work_sample(index):
    if 'user_id' not in session: 
        return redirect(url_for('auth.login'))
    
    db = get_db()
    p = await db.profiles.find_one({'user_id': session['user_id']})
    
    if p and 'work_samples' in p:
        samples = p['work_samples']
        if 0 <= index < len(samples):
            samples.pop(index)
            await db.profiles.update_one(
                {'user_id': session['user_id']},
                {'$set': {'work_samples': samples}}
            )
            flash("Work sample removed", "success")
            
    return redirect(url_for('portfolio.view_profile'))