# 🚀 Predictive OJT Activity Tracker

A high-performance, asynchronous web application designed to help students track their On-the-Job Training (OJT) progress with real-time analytics, automated documentation, and completion forecasting.

![Dashboard Preview](https://img.shields.io/badge/UI-Tailwind_CSS-blue)
![Backend](https://img.shields.io/badge/Backend-Quart_Python-green)
![Database](https://img.shields.io/badge/Database-MongoDB-white)

## ✨ Core Modules

### 📈 1. Smart Tracker & Analytics
The heart of the application, focusing on data-driven progress tracking.
- **Live Progress Tracking:** Visual progress bar showing total hours completed against the **486-hour goal**.
- **Predictive Analytics:** 
    - **Daily Pace:** Automatically calculates your average work hours based on past entries.
    - **Est. Days Left:** Forecasts how many days remain until you reach your goal.
    - **Target Finish Date:** A smart projection that calculates your completion date by **skipping weekends (Sat/Sun)**.
- **Efficient Logging:** One-tap "Quick-Fill" for standard 8:00 AM - 5:00 PM shifts and session editing for corrections.

### 📁 2. Automated Portfolio Builder
Streamline your final documentation with a built-in portfolio generator.
- **DTR Management:**
- **Structured Reflections:** Modular forms for logging daily/weekly reflections and learning outcomes.
- **Journal Generation:** A specialized "Print Journal" view formatted for physical submission or PDF export.
- **Setup Wizard:** Step-by-step configuration to personalize your portfolio details (Company info, Supervisor name, etc.).

### 🏆 3. Social Leaderboard & Gamification
Stay motivated by tracking your progress alongside your peers.
- **Real-time Rankings:** See where you stand compared to other students in terms of hours completed.
- **Achievement System:** Earn badges and milestones (via `utils/achievements.py`) for consistency and reaching hour targets.
- **Engagement:** Encourages a healthy competitive environment for cohort-based training.

---

## 🛠️ Tech Stack

- **Framework:** [Quart](https://pgjones.gitlab.io/quart/) (Asynchronous Python web framework)
- **Database:** [MongoDB](https://www.mongodb.com/) with [Motor](https://motor.readthedocs.io/) (Async driver)
- **Frontend:** Tailwind CSS & Lucide Icons
- **Deployment:** Optimized for Vercel (Serverless)

---

## 📂 Project Structure

```text
.                                    
├─ routes                                     
│  ├─ auth.py             # User authentication & session management
│  ├─ leaderboard.py      # Rankings & student progress comparison
│  ├─ portfolio.py        # DTR, Reflections, and Journal generation
│  └─ tracker.py          # Hours logging & predictive logic
├─ templates                             
│  ├─ auth                # Login, Register, Admin tools
│  ├─ main                # Dashboard, Profile, Leaderboard UI
│  └─ portfolio           # DTR forms, Reflection logs, Print views
├─ utils                                 
│  └─ achievements.py     # Logic for unlocking milestones
├─ app.py                 # Application entry point
├─ config.py              # Environment configurations
├─ db.py                  # MongoDB/Motor connection setup
└─ vercel.json            # Deployment configuration
```

---

## 📊 How the Predictions Work
The application uses a dynamic formula to estimate your finish date:
1. **Total Minutes** are summed from all logs (handling both decimal `hours` and integer `minutes` for legacy support).
2. **Daily Pace** is calculated as `Total Minutes / Number of Logged Days`.
3. **Estimated Finish** iterates through future dates, counting only **weekdays (Monday-Friday)** until the remaining required minutes are covered.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9+
- MongoDB Atlas Account (or local instance)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/ojt-tracker.git
cd ojt-tracker

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory:
```env
MONGO_URI=your_mongodb_connection_string
SECRET_KEY=your_super_secret_key
```

### 4. Running Locally
```bash
python app.py
```
Visit `http://localhost:5000` in your browser.

---
*Developed to bridge the gap between manual logging and professional internship documentation.*