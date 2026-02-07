from datetime import timedelta

def get_achievements(stats):
    """
    stats = {
        'rank': int,
        'total_hours': float,
        'log_count': int,
        'avg_daily': float,
        'progress': int,
        'streak_days': int,
        'early_logs': int,
        'late_logs': int,
        'max_daily_hours': float,
        'weekend_logs': int
    }
    """
    ach = []
    
    # 1. Rank Based
    rank = stats.get('rank', 99)
    if rank == 1:
        ach.append({"title": "The GOAT", "desc": "Currently dominating the board at #1 Rank.", "color": "amber", "icon": "crown"})
    elif rank <= 3:
        ach.append({"title": "Podium", "desc": "Top-tier performance in the top 3.", "color": "slate", "icon": "medal"})

    # 2. Pace Based
    avg = stats.get('avg_daily', 0)
    if avg >= 9.5:
        ach.append({"title": "Overtime King", "desc": "Averaging 9.5+ hours. Extreme workflow.", "color": "rose", "icon": "flame"})
    elif avg >= 8:
        ach.append({"title": "Consistent", "desc": "Maintaining a solid 8h/day workflow.", "color": "cyan", "icon": "zap"})

    # 3. Volume Based
    logs = stats.get('log_count', 0)
    if logs >= 100:
        ach.append({"title": "Legend", "desc": "100+ sessions logged. Unstoppable.", "color": "emerald", "icon": "award"})
    elif logs >= 50:
        ach.append({"title": "Veteran", "desc": "50+ sessions logged. Serious dedication.", "color": "emerald", "icon": "shield-check"})
    elif logs >= 25:
        ach.append({"title": "Committed", "desc": "25+ logs. You've made this a daily habit.", "color": "blue", "icon": "calendar-check"})

    # 4. Milestone Based
    prog = stats.get('progress', 0)
    if prog >= 100:
        ach.append({"title": "Elite", "desc": "Mission Accomplished: 486 Hours Finalized.", "color": "indigo", "icon": "trophy"})
    elif prog >= 75:
        ach.append({"title": "Final Stretch", "desc": "75% complete. Almost there!", "color": "purple", "icon": "flag-triangle-right"})
    elif prog >= 50:
        ach.append({"title": "Halfway", "desc": "Crossed the 50% mark of the requirement.", "color": "orange", "icon": "star"})

    # 5. Streak Based
    streak = stats.get('streak_days', 0)
    if streak >= 30:
        ach.append({"title": "Unbreakable", "desc": "30-day streak without missing a log.", "color": "red", "icon": "infinity"})
    elif streak >= 5:
        ach.append({"title": "Momentum", "desc": "7-day streak. The habit is forming.", "color": "lime", "icon": "trending-up"})

    # 6. Time & Special Grinds
    if stats.get('early_logs', 0) >= 10:
        ach.append({"title": "Early Bird", "desc": "10+ sessions started before 8 AM.", "color": "yellow", "icon": "sunrise"})
    if stats.get('late_logs', 0) >= 10:
        ach.append({"title": "Night Owl", "desc": "10+ late-night grind sessions.", "color": "purple", "icon": "moon"})
    if stats.get('max_daily_hours', 0) >= 12:
        ach.append({"title": "Beast Mode", "desc": "Logged a massive 12+ hour day.", "color": "fuchsia", "icon": "skull"})
    if stats.get('weekend_logs', 0) >= 5:
        ach.append({"title": "Warrior", "desc": "5+ logs recorded on weekends.", "color": "orange", "icon": "swords"})

    return ach