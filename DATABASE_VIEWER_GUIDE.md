# ⚡ AIDincharya Database Viewer Guide

This document provides instructions on how to run and access the **AIDincharya Database Inspector Website** to view and inspect all tables, schemas, and user records stored in `dinacharya.db`.

> [!NOTE]  
> **Isolated Design**: The Database Viewer is completely independent and is **NOT** connected to or linked from the main application page or navigation bar. Regular users will not see any database buttons or links.

---

## 🚀 How to Run & Access

You can access the Database Viewer website in **two ways**:

### Option 1: Via the Main Backend (Port 8000)

If your main backend server is already running (`python main.py` or `uvicorn main:app`):

1. Ensure the main backend server is active:
   ```bash
   cd backend
   python main.py
   ```
2. Open your web browser and navigate directly to:
   👉 **`http://localhost:8000/db-viewer`**

---

### Option 2: Standalone Mode on Dedicated Port (Port 8005)

If you want to view the database completely separately without running the full main app server:

1. Open a terminal and run the standalone DB Viewer script:
   ```bash
   cd backend
   python run_db_viewer.py
   ```
2. Open your web browser and navigate to:
   👉 **`http://localhost:8005`**

---

## 📊 Features of the Database Inspector

| Feature | Description |
| :--- | :--- |
| **Table Navigation** | Switch between all SQLite tables (`users`, `user_state`, `sessions`, `chat_history`, `completions`) from the left sidebar with real-time record badges. |
| **Live Record Search** | Type in the search box to instantly filter rows across any column in real time. |
| **Formatted JSON Inspector** | Click the **`{ } Format JSON`** badge on complex JSON fields (such as `questionnaire_responses`, `current_vikriti`, or `last_schedule`) to open a syntax-highlighted modal view. |
| **Schema Inspector** | Toggle to **Schema Info** mode to inspect column names, SQL data types, default values, and primary key status. |
| **Refresh Data** | Click **Refresh Data** to immediately fetch fresh data after taking actions in the app. |

---

## 🗄️ SQLite Database File Location

* **Database File**: `backend/dinacharya.db`
* **Python Controller**: [`backend/src/database/db.py`](file:///c:/Users/Shreyansh/Desktop/AIDincharya-main/AIDincharya-Unified/backend/src/database/db.py)
* **HTML Interface File**: [`backend/src/static/db_viewer.html`](file:///c:/Users/Shreyansh/Desktop/AIDincharya-main/AIDincharya-Unified/backend/src/static/db_viewer.html)
* **Standalone Server File**: [`backend/run_db_viewer.py`](file:///c:/Users/Shreyansh/Desktop/AIDincharya-main/AIDincharya-Unified/backend/run_db_viewer.py)
