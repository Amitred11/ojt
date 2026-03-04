def get_achievements(stats):
    ach = []
    
    # 1. Rank Based
    rank = stats.get('rank', 99)
    if rank == 1:
        ach.append({"title": "The GOAT", "desc": "Currently dominating the board at #1 Rank.", "color": "amber", "icon": "crown"})
    elif rank <= 3:
        ach.append({"title": "Podium", "desc": "Top-tier performance in the top 3.", "color": "slate", "icon": "medal"})
    elif rank <= 10:
        ach.append({"title": "Elite 10", "desc": "Ranked among the top 10 students.", "color": "indigo", "icon": "users"})
    elif rank <= 25:
        ach.append({"title": "Top 25", "desc": "Holding a strong position in the top 25.", "color": "blue", "icon": "trending-up"})

    # 2. Pace & Efficiency
    avg = stats.get('avg_daily', 0)
    if avg >= 12:
        ach.append({"title": "Beyond Human", "desc": "Averaging 12+ hours. When do you sleep?", "color": "red", "icon": "battery-charging"})
    elif avg >= 9.5:
        ach.append({"title": "Overtime King", "desc": "Averaging 9.5+ hours. Extreme workflow.", "color": "rose", "icon": "flame"})
    elif avg >= 8:
        ach.append({"title": "Consistent", "desc": "Maintaining a solid 8h/day workflow.", "color": "cyan", "icon": "zap"})
    elif 7.9 <= avg <= 8.1:
        ach.append({"title": "The Perfectionist", "desc": "Hitting the 8-hour mark with surgical precision.", "color": "emerald", "icon": "target"})
    
    if stats.get('max_daily_hours', 0) >= 14:
        ach.append({"title": "Android", "desc": "Logged a 14+ hour shift. Are you even human?", "color": "red", "icon": "cpu"})

    # 3. Volume & Experience
    logs = stats.get('log_count', 0)
    if logs >= 200:
        ach.append({"title": "Godfather", "desc": "200+ logs. You own this company now.", "color": "zinc", "icon": "briefcase"})
    elif logs >= 150:
        ach.append({"title": "Grandmaster", "desc": "150+ logs. Unparalleled dedication.", "color": "orange", "icon": "star"})
    elif logs >= 100:
        ach.append({"title": "Legend", "desc": "100+ sessions logged. Unstoppable.", "color": "emerald", "icon": "award"})
    elif logs >= 50:
        ach.append({"title": "Veteran", "desc": "50+ sessions logged. Serious dedication.", "color": "emerald", "icon": "shield-check"})
    elif logs >= 10:
        ach.append({"title": "Rising Star", "desc": "First 10 logs completed.", "color": "blue", "icon": "trending-up"})

    # 4. Milestone Based
    prog = stats.get('progress', 0)
    if prog > 100:
        ach.append({"title": "Overachiever", "desc": "Exceeded the required 486 hours. Absolute unit.", "color": "pink", "icon": "rocket"})
    elif prog >= 100:
        ach.append({"title": "Elite", "desc": "Mission Accomplished: 486 Hours Finalized.", "color": "indigo", "icon": "trophy"})
    elif prog >= 90:
        ach.append({"title": "Near the Finish", "desc": "90% complete. The end is in sight.", "color": "teal", "icon": "check-circle"})
    elif prog >= 75:
        ach.append({"title": "Final Stretch", "desc": "75% complete. Almost there!", "color": "purple", "icon": "flag-triangle-right"})
    elif prog >= 50:
        ach.append({"title": "Halfway", "desc": "Crossed the 50% mark of the requirement.", "color": "orange", "icon": "star"})
    elif prog >= 25:
        ach.append({"title": "Quarter Century", "desc": "25% of hours completed.", "color": "amber", "icon": "pie-chart"})

    # 5. Streak Based
    streak = stats.get('streak_days', 0)
    if streak >= 30:
        ach.append({"title": "Immovable", "desc": "A full month of perfect attendance.", "color": "fuchsia", "icon": "mountain"})
    elif streak >= 20:
        ach.append({"title": "Unbreakable", "desc": "20-day workday streak. Pure discipline.", "color": "red", "icon": "infinity"})
    elif streak >= 10:
        ach.append({"title": "The Machine", "desc": "Two weeks of perfect workday attendance.", "color": "violet", "icon": "binary"})
    elif streak >= 5:
        ach.append({"title": "Momentum", "desc": "5-day workday streak. Habit formed.", "color": "lime", "icon": "zap"})
     # 6. Time & Special Grinds
    early = stats.get('early_logs', 0)
    late = stats.get('late_logs', 0)
    if early >= 30:
        ach.append({"title": "Early Bird Pro", "desc": "30+ sessions started before 8 AM.", "color": "yellow", "icon": "sun"})
    elif early >= 15:
        ach.append({"title": "First to Arrive", "desc": "15 sessions started before 8 AM.", "color": "yellow", "icon": "sunrise"})
        
    if late >= 30:
        ach.append({"title": "Night King", "desc": "30+ late-night grind sessions.", "color": "slate", "icon": "ghost"})
    elif late >= 15:
        ach.append({"title": "Last to Leave", "desc": "15 late-night grind sessions.", "color": "purple", "icon": "moon"})
    
    # 7. Work-Life Balance Logic
    weekends = stats.get('weekend_logs', 0)
    if weekends == 0 and prog >= 20:
        ach.append({"title": "Corporate Pro", "desc": "High progress while strictly keeping weekends for rest.", "color": "teal", "icon": "sun"})
    elif weekends >= 20:
        ach.append({"title": "Weekend Overlord", "desc": "20+ logs recorded on weekends. You never stop.", "color": "orange", "icon": "swords"})
    elif weekends >= 10:
        ach.append({"title": "Weekend Warrior", "desc": "10+ logs recorded on weekends.", "color": "orange", "icon": "swords"})

    # 8. Consistency Logic
    if stats.get('total_hours', 0) >= 300 and avg >= 8:
         ach.append({"title": "Iron Pillar", "desc": "Over 300 hours maintained at a high pace.", "color": "stone", "icon": "shield"})
    return ach