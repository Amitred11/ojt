import asyncio
import sqlite3
from datetime import datetime, date
from quart import Quart, render_template_string, request, redirect, url_for

app = Quart(__name__)

# CHANGED: New DB name to avoid conflict with your old single-entry table
DB = "ojt_v2.db"
REQUIRED_HOURS = 486

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT UNIQUE,
                am_in TEXT,
                am_out TEXT,
                pm_in TEXT,
                pm_out TEXT,
                hours REAL
            )
        """)

def get_logs():
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        raw_logs = conn.execute("SELECT * FROM logs ORDER BY log_date DESC").fetchall()
        
        processed_logs = []
        for log in raw_logs:
            d = datetime.strptime(log['log_date'], '%Y-%m-%d')
            log_dict = dict(log)
            log_dict['display_day'] = d.strftime('%d')
            log_dict['display_month'] = d.strftime('%b')
            log_dict['display_weekday'] = d.strftime('%A')
            
            # Format empty times for display
            log_dict['am_str'] = f"{log['am_in']} - {log['am_out']}" if log['am_in'] and log['am_out'] else "No AM Log"
            log_dict['pm_str'] = f"{log['pm_in']} - {log['pm_out']}" if log['pm_in'] and log['pm_out'] else "No PM Log"
            
            processed_logs.append(log_dict)
        return processed_logs

def get_total_hours():
    with sqlite3.connect(DB) as conn:
        result = conn.execute("SELECT SUM(hours) FROM logs").fetchone()[0]
        return round(result or 0, 2)

def calculate_session(t_in, t_out):
    """Helper to calculate hours between two time strings"""
    if not t_in or not t_out:
        return 0.0
    try:
        fmt = "%H:%M"
        tdelta = datetime.strptime(t_out, fmt) - datetime.strptime(t_in, fmt)
        return tdelta.total_seconds() / 3600
    except ValueError:
        return 0.0

@app.route("/", methods=["GET", "POST"])
async def index():
    if request.method == "POST":
        form = await request.form
        log_date = form.get("log_date")
        
        # Get all 4 time inputs
        am_in = form.get("am_in")
        am_out = form.get("am_out")
        pm_in = form.get("pm_in")
        pm_out = form.get("pm_out")
        
        # Calculate total
        morning_hours = calculate_session(am_in, am_out)
        afternoon_hours = calculate_session(pm_in, pm_out)
        total_hours = round(morning_hours + afternoon_hours, 2)

        with sqlite3.connect(DB) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO logs (log_date, am_in, am_out, pm_in, pm_out, hours)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (log_date, am_in, am_out, pm_in, pm_out, total_hours))
        return redirect(url_for("index"))

    logs = get_logs()
    total = get_total_hours()
    remaining = max(0, REQUIRED_HOURS - total)
    progress = min((total / REQUIRED_HOURS) * 100, 100)

    return await render_template_string(TEMPLATE,
        logs=logs,
        total=total,
        remaining=round(remaining, 2),
        required=REQUIRED_HOURS,
        progress=progress,
        today=date.today().isoformat()
    )

@app.route("/delete/<int:log_id>")
async def delete_log(log_id):
    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    return redirect(url_for("index"))

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>OJT Progress</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body { 
            font-family: 'Plus Jakarta Sans', sans-serif; 
            background-color: #020617;
            background-image: radial-gradient(at 0% 0%, rgba(30, 58, 138, 0.3) 0, transparent 50%), 
                              radial-gradient(at 100% 100%, rgba(76, 29, 149, 0.3) 0, transparent 50%);
            color: #f8fafc;
        }
        .card-glass {
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .neo-shadow { box-shadow: 0 0 20px rgba(99, 102, 241, 0.2); }
        input[type="time"], input[type="date"] { color-scheme: dark; }
    </style>
</head>
<body class="min-h-screen pb-24">
    <div class="max-w-md mx-auto px-6 pt-12">
        
        <!-- App Bar -->
        <div class="flex justify-between items-center mb-10">
            <div>
                <h1 class="text-3xl font-800 tracking-tightest">Activity</h1>
                <p class="text-slate-500 text-sm font-semibold">Internship Tracker</p>
            </div>
            <div class="w-12 h-12 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
                <i data-lucide="calendar-check" class="text-indigo-400 w-6 h-6"></i>
            </div>
        </div>
        
        <!-- Main Progress Card -->
        <div class="card-glass rounded-[2.5rem] p-8 mb-8 border-t border-white/10 neo-shadow">
            <div class="flex justify-between items-end mb-6">
                <div>
                    <span class="text-indigo-400 text-xs font-bold uppercase tracking-widest">Completed</span>
                    <div class="text-6xl font-800 tracking-tighter">{{ total }}<span class="text-xl text-slate-500 ml-1">h</span></div>
                </div>
                <div class="text-right pb-1">
                    <span class="block text-2xl font-bold text-white">{{ progress|round|int }}%</span>
                    <span class="text-[10px] text-slate-500 uppercase font-bold">Goal Reach</span>
                </div>
            </div>
            <div class="w-full bg-slate-900 rounded-full h-4 p-1 mb-6">
                <div class="bg-gradient-to-r from-indigo-500 to-cyan-400 h-full rounded-full transition-all duration-1000 shadow-[0_0_12px_rgba(99,102,241,0.4)]" 
                     style="width: {{ progress }}%"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-white/5 rounded-2xl p-4 border border-white/5">
                    <p class="text-[10px] text-slate-500 uppercase font-bold mb-1">Remaining</p>
                    <p class="text-lg font-bold">{{ remaining }} hrs</p>
                </div>
                <div class="bg-white/5 rounded-2xl p-4 border border-white/5">
                    <p class="text-[10px] text-slate-500 uppercase font-bold mb-1">Required</p>
                    <p class="text-lg font-bold">{{ required }} hrs</p>
                </div>
            </div>
        </div>

        <!-- Quick Log Form -->
        <div class="mb-8">
            <div class="flex justify-between items-center mb-4 px-2">
                <h2 class="text-sm font-bold uppercase tracking-widest text-slate-500">New Entry</h2>
                <div class="flex gap-2">
                    <button type="button" onclick="setYesterday()" class="text-[10px] font-bold text-slate-400 bg-white/5 px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/10 active:scale-90 transition-all">
                        ⏪ YESTERDAY
                    </button>
                    <button type="button" onclick="quickFill()" class="text-[10px] font-bold text-indigo-400 bg-indigo-500/10 px-3 py-1.5 rounded-lg border border-indigo-500/20 active:scale-90 transition-transform">
                        ⚡ QUICK 8-5
                    </button>
                </div>
            </div>
            
            <form method="POST" class="card-glass rounded-[2rem] p-6 space-y-5">
                <input type="date" name="log_date" id="log_date" value="{{ today }}" required
                    class="w-full bg-slate-800/40 border border-slate-700/50 rounded-2xl px-5 py-4 outline-none focus:border-indigo-500 transition-all font-semibold">
                
                <!-- Morning Section -->
                <div class="space-y-2">
                    <label class="text-[10px] uppercase font-bold text-indigo-400 tracking-wider ml-1">Morning Session</label>
                    <div class="grid grid-cols-2 gap-3">
                        <div class="bg-slate-800/40 border border-slate-700/50 rounded-xl px-3 py-2">
                            <span class="text-[9px] text-slate-500 block">IN</span>
                            <input type="time" name="am_in" id="am_in" class="bg-transparent w-full outline-none font-bold text-base">
                        </div>
                        <div class="bg-slate-800/40 border border-slate-700/50 rounded-xl px-3 py-2">
                            <span class="text-[9px] text-slate-500 block">OUT</span>
                            <input type="time" name="am_out" id="am_out" class="bg-transparent w-full outline-none font-bold text-base">
                        </div>
                    </div>
                </div>

                <!-- Afternoon Section -->
                <div class="space-y-2">
                    <label class="text-[10px] uppercase font-bold text-indigo-400 tracking-wider ml-1">Afternoon Session</label>
                    <div class="grid grid-cols-2 gap-3">
                        <div class="bg-slate-800/40 border border-slate-700/50 rounded-xl px-3 py-2">
                            <span class="text-[9px] text-slate-500 block">IN</span>
                            <input type="time" name="pm_in" id="pm_in" class="bg-transparent w-full outline-none font-bold text-base">
                        </div>
                        <div class="bg-slate-800/40 border border-slate-700/50 rounded-xl px-3 py-2">
                            <span class="text-[9px] text-slate-500 block">OUT</span>
                            <input type="time" name="pm_out" id="pm_out" class="bg-transparent w-full outline-none font-bold text-base">
                        </div>
                    </div>
                </div>

                <button class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-800 py-5 rounded-2xl shadow-lg shadow-indigo-600/20 active:scale-[0.98] transition-all flex items-center justify-center gap-3 mt-2">
                    <i data-lucide="plus" class="w-5 h-5"></i> Log Hours
                </button>
            </form>
        </div>

        <!-- History -->
        <div class="space-y-4 pb-12">
            <h2 class="text-sm font-bold uppercase tracking-widest text-slate-500 px-2 mb-4">Log History</h2>
            {% for log in logs %}
            <div class="card-glass rounded-[1.5rem] p-4 flex items-center justify-between group transition-all hover:bg-white/5">
                <div class="flex items-center gap-4">
                    <div class="bg-indigo-500/10 h-14 w-14 rounded-2xl flex flex-col items-center justify-center border border-indigo-500/10 group-hover:border-indigo-500/40 transition-colors">
                        <span class="text-[9px] uppercase font-bold text-indigo-400">{{ log.display_month }}</span>
                        <span class="text-xl font-800 text-white">{{ log.display_day }}</span>
                    </div>
                    <div>
                        <p class="font-bold text-white mb-1">{{ log.display_weekday }}</p>
                        <div class="space-y-0.5">
                            <div class="flex items-center gap-2">
                                <span class="text-[9px] font-bold text-slate-500 bg-white/5 px-1.5 rounded">AM</span>
                                <p class="text-xs text-slate-400 font-medium">{{ log.am_str }}</p>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="text-[9px] font-bold text-slate-500 bg-white/5 px-1.5 rounded">PM</span>
                                <p class="text-xs text-slate-400 font-medium">{{ log.pm_str }}</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="flex items-center gap-3">
                    <div class="text-right">
                        <span class="text-xl font-800 text-indigo-400">{{ log.hours }}</span>
                    </div>
                    <a href="/delete/{{ log.id }}" onclick="return confirm('Delete this record?')" class="w-8 h-8 rounded-full flex items-center justify-center text-slate-600 hover:bg-red-500/10 hover:text-red-400 transition-all">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </a>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <script>
        lucide.createIcons();
        
        function quickFill() {
            document.getElementById('am_in').value = "08:00";
            document.getElementById('am_out').value = "12:00";
            document.getElementById('pm_in').value = "13:00";
            document.getElementById('pm_out').value = "17:00";
        }
        function setYesterday() {
            const dateInput = document.getElementById('log_date');
            const d = new Date();
            d.setDate(d.getDate() - 1);
            dateInput.value = d.toISOString().split('T')[0];
        }
    </script>
</body>
</html>
"""

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)