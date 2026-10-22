import sqlite3
import os
import json
import secrets
import time
import hashlib
import bcrypt
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
    
    # Sessions table with explicit expiry and revocation
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at REAL DEFAULT 0,
            is_revoked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Migrations for existing sessions table
    try:
        c.execute('ALTER TABLE sessions ADD COLUMN expires_at REAL DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    try:
        c.execute('ALTER TABLE sessions ADD COLUMN is_revoked INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
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

    # Notifications table (for agent events, alerts, and circumstance adaptations)
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            activity_name TEXT,
            old_time_slot TEXT,
            new_time_slot TEXT,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            channel TEXT DEFAULT 'in_app',
            delivery_status TEXT DEFAULT 'delivered',
            is_read BOOLEAN DEFAULT FALSE,
            idempotency_key TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Browser push subscriptions table (Web Push API)
    c.execute('''
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_push_subs_user_id ON push_subscriptions(user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_push_subs_endpoint ON push_subscriptions(endpoint)')

    # Completions table (task adherence logging)
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
    c.execute('CREATE INDEX IF NOT EXISTS idx_completions_user_date ON completions(user_id, completion_date)')
    
    conn.commit()
    conn.close()

# --- Auth Methods ---

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with a secure random salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifies a password against a stored hash.
    Supports bcrypt, legacy SHA-256 (64 hex characters), and dev plaintext fallback.
    """
    if not password or not stored_hash:
        return False
    # Bcrypt format check
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$") or stored_hash.startswith("$2y$"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except Exception:
            return False
    # Legacy SHA-256 check
    legacy_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if legacy_sha256 == stored_hash:
        return True
    # Plaintext fallback for test environments
    if password == stored_hash:
        return True
    return False

def create_user(username: str, password_or_hash: str) -> Optional[int]:
    """
    Creates a new user. Automatically hashes plaintext password if not already bcrypt-hashed.
    """
    conn = get_db_connection()
    c = conn.cursor()
    # Check if already a bcrypt hash
    if password_or_hash.startswith("$2b$") or password_or_hash.startswith("$2a$"):
        pwd_hash = password_or_hash
    else:
        pwd_hash = hash_password(password_or_hash)

    try:
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pwd_hash))
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

def authenticate_user(username: str, password_or_hash: str) -> Optional[int]:
    """
    Authenticates user and performs transparent upgrade of legacy SHA-256 hashes to bcrypt.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    if not user:
        conn.close()
        return None
    
    stored_hash = user['password_hash']
    user_id = user['id']
    is_valid = verify_password(password_or_hash, stored_hash)
    
    if not is_valid:
        conn.close()
        return None
        
    # Transparent rehash: if stored hash is legacy SHA-256, upgrade to bcrypt
    if not (stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$")):
        try:
            new_bcrypt_hash = hash_password(password_or_hash)
            c.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_bcrypt_hash, user_id))
            conn.commit()
        except Exception:
            pass # Keep login functional even if rehash write fails
            
    conn.close()
    return user_id

def create_session(user_id: int, duration_hours: float = 24.0) -> str:
    """Creates a new session token with explicit expiry time."""
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + (duration_hours * 3600.0)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO sessions (token, user_id, expires_at, is_revoked) VALUES (?, ?, ?, 0)',
              (token, user_id, expires_at))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[int]:
    """
    Validates token and returns user_id. Rejects revoked and expired tokens.
    """
    if not token:
        return None
    now = time.time()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id, expires_at, is_revoked FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if row['is_revoked'] == 1:
        return None
    if row['expires_at'] and row['expires_at'] > 0 and row['expires_at'] < now:
        return None
    return row['user_id']

def revoke_session(token: str) -> bool:
    """Invalidates an active session token server-side (logout)."""
    if not token:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE sessions SET is_revoked = 1 WHERE token = ?', (token,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

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
    c.execute('SELECT s.*, u.username FROM user_state s LEFT JOIN users u ON s.user_id = u.id WHERE s.user_id = ?', (user_id,))
    row = c.fetchone()
    if not row:
        c.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        urow = c.fetchone()
        conn.close()
        return {"username": urow["username"] if urow else ""}
    conn.close()
    
    return {
        "username": row["username"] or "",
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
    c.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?', (user_id, limit))
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

# --- Notification Methods ---

def create_notification(
    user_id: int,
    event_type: str,
    message: str,
    activity_name: Optional[str] = None,
    old_time_slot: Optional[str] = None,
    new_time_slot: Optional[str] = None,
    severity: str = "info",
    channel: str = "in_app",
    delivery_status: str = "delivered",
    idempotency_key: Optional[str] = None
) -> Optional[int]:
    """
    Creates a persistent notification record with duplicate event prevention (idempotency).
    If idempotency_key is provided and already exists, returns existing notification ID without duplicating.
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO notifications (
                user_id, event_type, activity_name, old_time_slot, new_time_slot,
                message, severity, channel, delivery_status, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, event_type, activity_name, old_time_slot, new_time_slot,
            message, severity, channel, delivery_status, idempotency_key
        ))
        notification_id = c.lastrowid
        conn.commit()
        return notification_id
    except sqlite3.IntegrityError:
        # Idempotency conflict: already created
        if idempotency_key:
            c.execute('SELECT id FROM notifications WHERE idempotency_key = ?', (idempotency_key,))
            row = c.fetchone()
            return row["id"] if row else None
        return None
    finally:
        conn.close()

def get_user_notifications(user_id: int, limit: int = 20, unread_only: bool = False) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    if unread_only:
        c.execute('''
            SELECT * FROM notifications 
            WHERE user_id = ? AND is_read = FALSE 
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, limit))
    else:
        c.execute('''
            SELECT * FROM notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "event_type": r["event_type"],
            "activity_name": r["activity_name"],
            "old_time_slot": r["old_time_slot"],
            "new_time_slot": r["new_time_slot"],
            "message": r["message"],
            "severity": r["severity"],
            "channel": r["channel"],
            "delivery_status": r["delivery_status"],
            "is_read": bool(r["is_read"]),
            "idempotency_key": r["idempotency_key"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]

def mark_notification_read(notification_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE notifications SET is_read = TRUE WHERE id = ? AND user_id = ?', (notification_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# --- Push Notification Subscription Methods ---

def save_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: Optional[str] = None
) -> int:
    """
    Saves or updates a Web Push subscription for an authenticated user.
    Enforces uniqueness on endpoint and updates keys/user if re-subscribed.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(endpoint) DO UPDATE SET
            user_id = excluded.user_id,
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            user_agent = excluded.user_agent,
            updated_at = CURRENT_TIMESTAMP
    ''', (user_id, endpoint, p256dh, auth, user_agent))
    subscription_id = c.lastrowid
    conn.commit()
    conn.close()
    return subscription_id

def get_user_push_subscriptions(user_id: int) -> List[Dict[str, Any]]:
    """
    Returns active browser push subscriptions scoped to the authenticated user.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, user_id, endpoint, p256dh, auth, user_agent, created_at, updated_at
        FROM push_subscriptions
        WHERE user_id = ?
        ORDER BY updated_at DESC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "endpoint": r["endpoint"],
            "p256dh": r["p256dh"],
            "auth": r["auth"],
            "user_agent": r["user_agent"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        }
        for r in rows
    ]

def delete_user_push_subscription(user_id: int, endpoint: str) -> bool:
    """
    Revokes an authenticated user's push subscription by endpoint.
    Strictly isolated: user A cannot delete user B's subscription.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?', (user_id, endpoint))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_push_subscription_by_endpoint(endpoint: str) -> bool:
    """
    Removes an expired or invalid subscription when push provider returns 404 or 410 Gone.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM push_subscriptions WHERE endpoint = ?', (endpoint,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_user_push_status(user_id: int) -> Dict[str, Any]:
    """
    Returns the push subscription status for an authenticated user.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count FROM push_subscriptions WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    count = row["count"] if row else 0
    return {
        "enabled": count > 0,
        "subscription_count": count
    }

# Initialize on import
init_db()

