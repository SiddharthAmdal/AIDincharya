import sqlite3
import os
import json
import secrets
import time
from typing import Dict, Any, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "dinacharya.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Sessions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # User state table (Questionnaires, adherence, telemetry, and cached schedule)
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY,
            questionnaire_responses TEXT,
            telemetry_baselines TEXT,
            current_vikriti TEXT DEFAULT '{}',
            adherence_score REAL DEFAULT 1.0,
            has_completed_onboarding BOOLEAN DEFAULT FALSE,
            last_schedule TEXT,
            schedule_timestamp REAL DEFAULT 0,
            schedule_date TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Migration for existing DBs
    try:
        c.execute('ALTER TABLE user_state ADD COLUMN current_vikriti TEXT DEFAULT "{}"')
    except sqlite3.OperationalError:
        pass # Column already exists

    # Chat history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Task completions table (for date-specific tracking)
    c.execute('''
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            practice_name TEXT NOT NULL,
            completion_date DATE DEFAULT (CURRENT_DATE),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Auth Methods ---

def create_user(username, password_hash):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        user_id = c.lastrowid
        # Initialize empty state
        c.execute('INSERT INTO user_state (user_id, questionnaire_responses, telemetry_baselines) VALUES (?, ?, ?)',
                  (user_id, '{}', '{}'))
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def authenticate_user(username, password_hash):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE username = ? AND password_hash = ?', (username, password_hash))
    user = c.fetchone()
    conn.close()
    return user['id'] if user else None

def create_session(user_id):
    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, user_id))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[int]:
    if not token:
        return None
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()
    return row['user_id'] if row else None

# --- State Methods ---

def update_user_questionnaire(user_id, responses: Dict[str, Any]):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_state SET questionnaire_responses = ?, has_completed_onboarding = ? WHERE user_id = ?',
              (json.dumps(responses), True, user_id))
    conn.commit()
    conn.close()

def get_user_state(user_id) -> Dict[str, Any]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM user_state WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    
    return {
        "adherence_score": row["adherence_score"],
        "has_completed_onboarding": bool(row["has_completed_onboarding"]),
        "questionnaire_responses": json.loads(row["questionnaire_responses"] or '{}'),
        "telemetry_baselines": json.loads(row["telemetry_baselines"] or '{}'),
        "current_vikriti": json.loads(row["current_vikriti"] or '{}'),
        "last_schedule": json.loads(row["last_schedule"] or 'null'),
        "schedule_timestamp": row["schedule_timestamp"],
        "schedule_date": row["schedule_date"]
    }

def update_current_vikriti(user_id, telemetry: Dict[str, Any], symptoms: List[str]):
    conn = get_db_connection()
    c = conn.cursor()
    vikriti_state = {
        "telemetry": telemetry,
        "symptoms": symptoms
    }
    c.execute('UPDATE user_state SET current_vikriti = ? WHERE user_id = ?',
              (json.dumps(vikriti_state), user_id))
    conn.commit()
    conn.close()

def save_user_schedule(user_id, schedule: Dict[str, Any], date_str: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_state SET last_schedule = ?, schedule_timestamp = ?, schedule_date = ? WHERE user_id = ?',
              (json.dumps(schedule), time.time(), date_str, user_id))
    conn.commit()
    conn.close()

def invalidate_user_schedule(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_state SET schedule_timestamp = 0, schedule_date = "" WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def update_adherence_score(user_id, score: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_state SET adherence_score = ? WHERE user_id = ?', (score, user_id))
    conn.commit()
    conn.close()

# --- Chat Methods ---

def save_chat_message(user_id, role, content):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(user_id, limit=20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    # Reverse to get chronological order
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

# --- Completion Methods ---

def save_completion(user_id, practice_name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO completions (user_id, practice_name) VALUES (?, ?)', (user_id, practice_name))
    conn.commit()
    conn.close()

def get_today_completions(user_id) -> List[str]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT practice_name FROM completions WHERE user_id = ? AND completion_date = CURRENT_DATE', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row["practice_name"] for row in rows]

# Initialize on import
init_db()
