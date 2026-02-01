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
        try:
            db = get_db()
            form = await request.form
            files = (await request.files).getlist('photos')
            
            # Process images with the new robust utility
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
            print(f"Route Error (new_log): {e}")
            return "Internal Error: Image upload failed. Try smaller files.", 500

    return await render_template('portfolio/portfolio_form_log.html', today=datetime.today().strftime('%Y-%m-%d'))

@portfolio_bp.route('/dtr/upload', methods=['GET', 'POST'])
async def upload_dtr():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            db = get_db()
            form = await request.form
            files_data = await request.files
            
            # Process Front and Back separately
            front_img = await process_multiple_images(files_data.getlist('dtr_front'))
            back_img = await process_multiple_images(files_data.getlist('dtr_back'))
            
            if front_img:
                await db.dtr_uploads.insert_one({
                    'user_id': session['user_id'],
                    'description': form.get('description'), # e.g., "January 2026"
                    'image_front': front_img[0] if front_img else None,
                    'image_back': back_img[0] if back_img else None,
                    'uploaded_at': datetime.utcnow()
                })
            return redirect(url_for('portfolio.list_reports'))
        except Exception as e:
            print(f"DTR Error: {e}")
            return "Upload Failed", 500

    return await render_template('portfolio/portfolio_form_dtr.html')

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

@portfolio_bp.route('/log/edit/<log_id>', methods=['GET', 'POST'])
async def edit_log(log_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    
    # POST: Update the entry
    if request.method == 'POST':
        try:
            form = await request.form
            files = (await request.files).getlist('photos')
            
            update_data = {
                'week_end_date': form.get('week_end_date'),
                'tasks': form.get('tasks'),
                'competencies': form.get('competencies'),
                'knowledge': form.get('knowledge'),
                'updated_at': datetime.utcnow()
            }

            # Only process/replace images if new ones are uploaded
            # Note: Input type='file' is empty if no new file is selected
            if files and files[0].filename != '':
                new_images = await process_multiple_images(files)
                if new_images:
                    update_data['images'] = new_images

            await db.weekly_logs.update_one(
                {'_id': ObjectId(log_id), 'user_id': session['user_id']},
                {'$set': update_data}
            )
            return redirect(url_for('portfolio.list_reports'))
        except Exception as e:
            print(f"Edit Log Error: {e}")
            return "Error updating log", 500

    # GET: Fetch existing data to populate form
    log = await db.weekly_logs.find_one({'_id': ObjectId(log_id), 'user_id': session['user_id']})
    if not log:
        return redirect(url_for('portfolio.list_reports'))
        
    return await render_template(
        'portfolio/portfolio_form_log.html', 
        log=log, # Pass the existing log object
        today=datetime.today().strftime('%Y-%m-%d')
    )

@portfolio_bp.route('/dtr/edit/<dtr_id>', methods=['GET', 'POST'])
async def edit_dtr(dtr_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()

    if request.method == 'POST':
        try:
            form = await request.form
            files_data = await request.files
            
            update_data = {
                'description': form.get('description'),
                'updated_at': datetime.utcnow()
            }

            # Check Front Image
            front_files = files_data.getlist('dtr_front')
            if front_files and front_files[0].filename != '':
                front_img = await process_multiple_images(front_files)
                if front_img:
                    update_data['image_front'] = front_img[0]

            # Check Back Image
            back_files = files_data.getlist('dtr_back')
            if back_files and back_files[0].filename != '':
                back_img = await process_multiple_images(back_files)
                if back_img:
                    update_data['image_back'] = back_img[0]

            await db.dtr_uploads.update_one(
                {'_id': ObjectId(dtr_id), 'user_id': session['user_id']},
                {'$set': update_data}
            )
            return redirect(url_for('portfolio.list_reports'))
        except Exception as e:
            print(f"Edit DTR Error: {e}")
            return "Error updating DTR", 500

    dtr = await db.dtr_uploads.find_one({'_id': ObjectId(dtr_id), 'user_id': session['user_id']})
    if not dtr:
        return redirect(url_for('portfolio.list_reports'))

    return await render_template(
        'portfolio/portfolio_form_dtr.html',
        dtr=dtr # Pass the existing DTR object
    )

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

@portfolio_bp.route('/reflection/edit/<r_id>', methods=['GET', 'POST'])
async def edit_reflection(r_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    db = get_db()
    
    if request.method == 'POST':
        form = await request.form
        update_data = {
            'month_date': form.get('month_date'),
            'monthly_reflection': form.get('monthly_reflection'),
            'self_evaluation': form.get('self_evaluation'),
            'feedback': form.get('feedback'),
            'updated_at': datetime.utcnow()
        }
        await db.reflections.update_one(
            {'_id': ObjectId(r_id), 'user_id': session['user_id']},
            {'$set': update_data}
        )
        return redirect(url_for('portfolio.list_reports'))

    reflection = await db.reflections.find_one({'_id': ObjectId(r_id), 'user_id': session['user_id']})
    if not reflection: return redirect(url_for('portfolio.list_reports'))
    
    return await render_template('portfolio/portfolio_form_reflection.html', r=reflection)
