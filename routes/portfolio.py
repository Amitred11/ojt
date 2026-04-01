import asyncio
from quart import Blueprint, render_template, request, redirect, url_for, flash,  session
from db import get_db
from datetime import datetime, timedelta, date # Add date here
from util import process_multiple_images
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
# new
from utils.achievements import get_achievements
from routes.tracker import PH_HOLIDAYS
import re

def get_minutes_diff(t_in, t_out):
    if not t_in or not t_out: return 0
    try:
        t1 = datetime.strptime(normalize_time(t_in), "%H:%M")
        t2 = datetime.strptime(normalize_time(t_out), "%H:%M")
        return int((t2 - t1).total_seconds() // 60) if t2 > t1 else 0
    except: return 0

def calculate_credited_minutes(log, settings):
    """
    MATCHES TRACKER/LEADERBOARD LOGIC:
    Handles Manual Override, 10h Transitions, and absence (empty logs).
    """
    # 1. Handle Manual Override
    manual_val = log.get('manual_credit')
    if manual_val is not None:
        return int(manual_val * 60)

    # 2. Setup Variables
    log_date_str = log.get('log_date', "")
    try:
        log_date_obj = datetime.strptime(log_date_str, '%Y-%m-%d').date()
    except:
        log_date_obj = date.today()

    transition_date = date(2026, 3, 16)
    is_10h_mode = settings.get('is_10h_mode', False)
    
    nai = normalize_time(log.get('am_in'))
    nao = normalize_time(log.get('am_out'))
    npi = normalize_time(log.get('pm_in'))
    npo = normalize_time(log.get('pm_out'))

    # 3. Absence Check
    if not (nai or npi):
        return 0

    # 4. Start time restriction
    effective_start = "07:00" if (is_10h_mode and log_date_obj >= transition_date) else "08:00"
    
    # AM Calc
    if not nai or not nao:
        m_am = 0
    else:
        calc_ai = effective_start if (not settings.get('allow_before_7am') and nai < effective_start) else nai
        m_am = get_minutes_diff(calc_ai, nao)
    
    # PM Calc
    m_pm = get_minutes_diff(npi, npo) if (npi and npo) else 0
    
    # Lunch Logic
    m_lunch = 60 if (settings.get('count_lunch') and nao and npi and 
                    "11:45" <= nao <= "12:15" and "12:45" <= npi <= "13:15") else 0
    
    total = m_am + m_pm + m_lunch
    
    # 5. Apply Caps
    if is_10h_mode:
        cap = 600 if log_date_obj >= transition_date else 480
        total = min(total, cap)
    elif settings.get('strict_8h'):
        total = min(total, 480)
    
    return total

def minutes_to_str(m):
    h = int(m // 60)
    minutes = int(m % 60)
    return f"{h}h {minutes}m"

def normalize_time(t_str):
    if not t_str or ":" not in t_str: return None
    try:
        parts = t_str.split(':')
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
        
        # Process new document images (ADDED profile_photo)
        cert_img = await process_multiple_images(files.getlist('certificate_img'))
        struct_img = await process_multiple_images(files.getlist('structure_img'))
        work_samples = await process_multiple_images(files.getlist('work_samples'))
        prof_img = await process_multiple_images(files.getlist('profile_photo'))

        data = {
            'user_id': session['user_id'],
            'full_name': form.get('full_name'),
            'email': form.get('email'),               # Added to fix missing email
            'phone': form.get('phone'),               # Added to fix missing phone
            'course': form.get('course'),
            'duration': form.get('duration'),
            'objectives': form.get('objectives'),
            'hte_name': form.get('hte_name'),
            'dept_assigned': form.get('dept_assigned'), # Added to fix missing dept_assigned
            'supervisor': form.get('supervisor'),
            'coordinator_name': form.get('coordinator_name'),
            'acknowledgement': form.get('acknowledgement'),
            'company_desc': form.get('company_desc'),
            'dept_desc': form.get('dept_desc'),
            'updated_at': datetime.utcnow()
        }

        # Only update images if new ones are uploaded
        if cert_img: data['certificate_img'] = cert_img[0]
        if struct_img: data['structure_img'] = struct_img[0]
        if work_samples: data['work_samples'] = work_samples 
        if prof_img: data['profile_photo'] = prof_img[0] # Save Profile Photo

        await db.profiles.update_one({'user_id': session['user_id']}, {'$set': data}, upsert=True)
        return redirect(url_for('portfolio.view_profile'))

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

    # 1. Fetch Data
    all_logs = await db.logs.find({}).to_list(None)
    all_settings = await db.settings.find({}).to_list(None)
    p = await db.profiles.find_one({'user_id': target_uid}) or {}
    
    # Handle Hype Notifications
    received_hype = await db.notifications.find({"target_uid": target_uid}).sort("created_at", -1).limit(5).to_list(None)
    for hype in received_hype:
        if 'created_at' in hype:
            hype['ph_time'] = hype['created_at'] + timedelta(hours=8)
            
    settings_map = {str(s['user_id']): s for s in all_settings if 'user_id' in s}
    
    # 2. Process ALL users for Ranking and TARGET user for History
    user_totals = {} 
    student_logs = [] # This is for the "Training Activity Log" UI
    early_logs, late_logs, weekend_logs = 0, 0, 0
    
    # Sort all logs by date descending so history shows newest first
    all_logs.sort(key=lambda x: x.get('log_date', ""), reverse=False)

    for log in all_logs:
        uid = str(log['user_id'])
        u_set = settings_map.get(uid, {
            "strict_8h": False, "is_10h_mode": False, "count_lunch": False, 
            "allow_before_7am": False, "allow_after_5pm": True, 
            "allow_weekend_duty": False, "allow_holiday_duty": False
        })
        
        # Calculate Credited Minutes using your fixed engine
        credited_m = calculate_credited_minutes(log, u_set)
        
        # Date Restrictions
        log_date_str = log.get('log_date', "")
        is_holiday = log_date_str in PH_HOLIDAYS
        is_weekend = False
        try:
            log_date_obj = datetime.strptime(log_date_str, '%Y-%m-%d')
            is_weekend = log_date_obj.weekday() >= 5
        except:
            log_date_obj = datetime.now()

        if (is_weekend and not u_set.get('allow_weekend_duty')) or \
           (is_holiday and not u_set.get('allow_holiday_duty')):
            credited_m = 0

        # Update global totals for ranking
        user_totals[uid] = user_totals.get(uid, 0) + credited_m
        
        # POPULATE LOG HISTORY FOR THE TARGET USER
        if uid == target_uid:
            # Achievement Stats
            if is_weekend and credited_m > 0: weekend_logs += 1
            nai = normalize_time(log.get('am_in'))
            npo = normalize_time(log.get('pm_out'))
            if nai and nai < "08:00": early_logs += 1
            if npo and npo >= "18:00": late_logs += 1

            # Format entry for the UI list
            student_logs.append({
                'display_day': log_date_obj.strftime('%d'),
                'display_weekday': log_date_obj.strftime('%A'),
                'month_key': log_date_obj.strftime('%B %Y'),
                'am_str': f"{log.get('am_in') or '--'} - {log.get('am_out') or '--'}",
                'pm_str': f"{log.get('pm_in') or '--'} - {log.get('pm_out') or '--'}",
                'credited_str': minutes_to_str(credited_m),
                'is_ot': npo and npo > "17:00" and not u_set.get('is_10h_mode'),
                'has_time': credited_m > 0
            })

    # 3. Final Profile Stats
    total_minutes = user_totals.get(target_uid, 0)
    total_hours = total_minutes / 60
    # Count only days where time was actually earned
    log_count = len([l for l in student_logs if l['has_time']])
    
    # Determine Rank
    sorted_ranking = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)
    actual_rank = next((i for i, (uid, total) in enumerate(sorted_ranking, 1) if uid == target_uid), 0)

    # Goal logic
    target_goal = 486
    progress = min(int((total_hours / target_goal) * 100), 100)
    avg_daily = round(total_hours / log_count, 1) if log_count > 0 else 0

    # 4. Achievements
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
        'total_hours': round(total_hours, 1), 
        'log_count': log_count, 
        'avg_hours': avg_daily, 
        'progress': progress, 
        'achievements': achievements, 
        'rank': actual_rank,
        'is_owner': is_owner,
        'received_hype': received_hype,
        'student_logs': student_logs # Passed to HTML
    }

    template = 'main/profile.html' if is_owner else 'main/public_profile.html'
    return await render_template(template, **context)

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

@portfolio_bp.route('/security/recovery', methods=['GET', 'POST'])
async def manage_recovery():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    db = get_db()
    uid = ObjectId(session['user_id'])
    user = await db.users.find_one({'_id': uid})

    if request.method == 'POST':
        form = await request.form
        current_password = form.get('current_password')
        new_question = form.get('security_question')
        new_answer = form.get('security_answer')

        # 1. Verify user identity before allowing security changes
        if not check_password_hash(user['password'], current_password):
            await flash("Identity verification failed. Incorrect password.", "error")
            return redirect(url_for('portfolio.manage_recovery'))

        # 2. Hash and save the new recovery method
        hashed_answer = generate_password_hash(new_answer.lower().strip())
        await db.users.update_one(
            {'_id': uid},
            {'$set': {
                'security_question': new_question,
                'security_answer': hashed_answer
            }}
        )
        
        await flash("Recovery Protocol successfully updated.", "success")
        return redirect(url_for('portfolio.view_profile'))

    return await render_template('portfolio/recovery_method.html', u=user)