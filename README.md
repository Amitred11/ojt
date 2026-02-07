This is a professional and comprehensive **README.md** file tailored specifically for your **Predictive OJT Activity Tracker**. It includes your tech stack, folder structure, and the specific predictive features we just implemented.

***

# 🚀 Predictive OJT Activity Tracker

A high-performance, asynchronous web application designed to help students track their On-the-Job Training (OJT) progress with real-time analytics and completion forecasting.

![Dashboard Preview](https://img.shields.io/badge/UI-Tailwind_CSS-blue)
![Backend](https://img.shields.io/badge/Backend-Quart_Python-green)
![Database](https://img.shields.io/badge/Database-MongoDB-white)

## ✨ Features

- **Live Progress Tracking:** Visual progress bar showing total hours completed against the **486-hour goal**.
- **Predictive Analytics:** 
    - **Daily Pace:** Automatically calculates your average work hours based on past entries.
    - **Est. Days Left:** Forecasts how many days remain until you reach your goal.
    - **Target Finish Date:** A smart projection that calculates your completion date by **skipping weekends (Sat/Sun)**.
- **Efficient Logging:** 
    - **Quick-Fill:** One-tap logging for standard 8:00 AM - 5:00 PM shifts.
    - **Session Editing:** Retroactively update or correct past logs easily.
- **Smart History Archive:**
    - **Collapsible Months:** Organizes logs by month for a clean interface.
    - **Full Search:** Quickly find specific dates or tasks.
- **Modern UI:** Built with a dark-mode "Glassmorphism" aesthetic using Tailwind CSS and Lucide Icons.

## 🛠️ Tech Stack

- **Framework:** [Quart](https://pgjones.gitlab.io/quart/) (Asynchronous Python web framework)
- **Database:** [MongoDB](https://www.mongodb.com/) with [Motor](https://motor.readthedocs.io/) (Async driver)
- **Frontend:** Tailwind CSS & Lucide Icons
- **Deployment:** Optimized for Vercel (Serverless)

## 📂 Project Structure

```text
wwwww                                    
├─ routes                                     
│  ├─ auth.py                            
│  ├─ leaderboard.py                     
│  ├─ portfolio.py                       
│  ├─ tracker.py                         
│  └─ __init__.py                        
├─ static                                
│  └─ uploads                            
├─ templates                             
│  ├─ auth                               
│  │  ├─ admin_users.html                
│  │  ├─ login.html                      
│  │  ├─ migration_tool.html             
│  │  └─ register.html                   
│  ├─ main                               
│  │  ├─ base.html                       
│  │  ├─ index.html                      
│  │  ├─ leaderboard.html                
│  │  └─ profile.html                    
│  └─ portfolio                          
│     ├─ portfolio.html                  
│     ├─ portfolio_form_dtr.html         
│     ├─ portfolio_form_log.html         
│     ├─ portfolio_form_reflection.html  
│     ├─ portfolio_setup.html            
│     └─ print_journal.html              
├─ utils                                 
│  └─ achievements.py                             
├─ app.py                                
├─ config.py                             
├─ db.py                                 
├─ README.md                             
├─ requirements.txt                      
├─ util.py                               
└─ vercel.json                           
```

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
Create a `.env` file in the root directory (or set these in Vercel/System):
```env
MONGO_URI=your_mongodb_connection_string
SECRET_KEY=your_super_secret_key
```

### 4. Running Locally
```bash
python app.py
```
Visit `http://localhost:5000` in your browser.

## 📊 How the Predictions Work
The application uses a dynamic formula to estimate your finish date:
1. **Total Minutes** are summed from all your logs (handling both decimal `hours` and integer `minutes` for legacy support).
2. **Daily Pace** is calculated as `Total Minutes / Number of Logged Days`.
3. **Estimated Finish** iterates through future dates, counting only weekdays (Monday-Friday) until the remaining required minutes are covered.

## 📄 License
This project is for educational purposes as part of the OJT requirements.

---
*Developed to make OJT documentation faster and smarter.*