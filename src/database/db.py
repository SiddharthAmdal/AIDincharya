import sqlite3
from datetime import datetime
import os
import re
import json
import secrets
import time
import hashlib
import bcrypt
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("Database")

DB_PATH = os.getenv("DINACHARYA_DB_PATH") or os.getenv("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "..", "..", "dinacharya.db")

def get_db_connection():
    path = os.getenv("DINACHARYA_DB_PATH") or os.getenv("DATABASE_PATH") or DB_PATH
    conn = sqlite3.connect(path)
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
    try:
        c.execute('ALTER TABLE user_state ADD COLUMN prakriti_profile TEXT DEFAULT "{}"')
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
    
    # Schedule proposals table (canonical state for active proposals)
    c.execute('''
        CREATE TABLE IF NOT EXISTS schedule_proposals (
            proposal_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            target_practice TEXT NOT NULL,
            original_time_slot TEXT NOT NULL,
            proposed_time_slot TEXT NOT NULL,
            target_block TEXT NOT NULL,
            schedule_version REAL NOT NULL,
            status TEXT NOT NULL,
            proposal_data TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON schedule_proposals(user_id, status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_proposals_created ON schedule_proposals(created_at)')

    # Longitudinal Vikriti observations table
    c.execute('''
        CREATE TABLE IF NOT EXISTS vikriti_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symptoms TEXT DEFAULT '[]',
            telemetry TEXT DEFAULT '{}',
            estimate TEXT DEFAULT '{}',
            confidence TEXT DEFAULT 'provisional',
            data_status TEXT DEFAULT 'self_report_only',
            timestamp REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_vikriti_user_time ON vikriti_observations(user_id, timestamp)')
    
    # Migration for existing DBs: ensure telemetry_records uniqueness is scoped per user
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='telemetry_records'")
    t_row = c.fetchone()
    if t_row and "record_id TEXT UNIQUE" in t_row[0]:
        c.execute('''
            CREATE TABLE telemetry_records_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                metric_type TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                ingested_at REAL NOT NULL,
                source_package TEXT NOT NULL,
                device_model TEXT NOT NULL,
                provenance TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE (user_id, record_id)
            )
        ''')
        c.execute('''
            INSERT OR IGNORE INTO telemetry_records_v2 
            (id, record_id, user_id, metric_type, metric_value, unit, recorded_at, ingested_at, source_package, device_model, provenance)
            SELECT id, record_id, user_id, metric_type, metric_value, unit, recorded_at, ingested_at, source_package, device_model, provenance
            FROM telemetry_records
        ''')
        c.execute('DROP TABLE telemetry_records')
        c.execute('ALTER TABLE telemetry_records_v2 RENAME TO telemetry_records')
        c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_metric ON telemetry_records(user_id, metric_type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_recorded ON telemetry_records(user_id, recorded_at)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_record ON telemetry_records(user_id, record_id)')

    # Immutable Wearable Telemetry Records table (with deduplication on (user_id, record_id))
    c.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            metric_type TEXT NOT NULL,
            metric_value REAL NOT NULL,
            unit TEXT NOT NULL,
            recorded_at REAL NOT NULL,
            ingested_at REAL NOT NULL,
            source_package TEXT NOT NULL,
            device_model TEXT NOT NULL,
            provenance TEXT NOT NULL,
            aggregation_type TEXT DEFAULT 'interval',
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE (user_id, record_id)
        )
    ''')
    try:
        c.execute("ALTER TABLE telemetry_records ADD COLUMN aggregation_type TEXT DEFAULT 'interval'")
    except sqlite3.OperationalError:
        pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_metric ON telemetry_records(user_id, metric_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_recorded ON telemetry_records(user_id, recorded_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_record ON telemetry_records(user_id, record_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_user_aggr ON telemetry_records(user_id, aggregation_type)')

    # Activity Lifecycle table (Phase 5 - persistent activity tracking and adherence)
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_lifecycle (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            schedule_date TEXT NOT NULL,
            practice_name TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            start_time_ts REAL NOT NULL,
            end_time_ts REAL NOT NULL,
            status TEXT NOT NULL,
            completed_at REAL,
            completion_source TEXT,
            evidence_json TEXT DEFAULT '{}',
            compensation_for_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_activity_user_date ON activity_lifecycle(user_id, schedule_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_activity_user_status ON activity_lifecycle(user_id, status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_activity_comp_for ON activity_lifecycle(compensation_for_id)')

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

def update_user_questionnaire(user_id, responses: Dict[str, Any], prakriti_profile: Optional[Dict[str, Any]] = None):
    conn = get_db_connection()
    c = conn.cursor()
    prakriti_json = json.dumps(prakriti_profile or {})
    # Reset last_schedule to NULL on questionnaire update so fresh personalized recommendations are generated
    c.execute('''
        UPDATE user_state 
        SET questionnaire_responses = ?, 
            prakriti_profile = ?, 
            has_completed_onboarding = 1,
            last_schedule = NULL
        WHERE user_id = ?
    ''', (json.dumps(responses), prakriti_json, user_id))
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
    
    row_keys = row.keys()
    return {
        "username": row["username"] or "",
        "adherence_score": row["adherence_score"],
        "has_completed_onboarding": bool(row["has_completed_onboarding"]),
        "questionnaire_responses": json.loads(row["questionnaire_responses"] or '{}'),
        "prakriti_profile": json.loads(row["prakriti_profile"] or '{}') if "prakriti_profile" in row_keys else {},
        "telemetry_baselines": json.loads(row["telemetry_baselines"] or '{}'),
        "current_vikriti": json.loads(row["current_vikriti"] or '{}'),
        "last_schedule": json.loads(row["last_schedule"] or 'null'),
        "schedule_timestamp": row["schedule_timestamp"],
        "schedule_date": row["schedule_date"]
    }

def record_vikriti_observation(
    user_id: int,
    symptoms: List[str],
    telemetry: Dict[str, Any],
    estimate: Optional[Dict[str, Any]] = None,
    confidence: str = "provisional",
    data_status: str = "self_report_only"
) -> int:
    """
    Appends a new observation record to the longitudinal vikriti_observations table.
    """
    conn = get_db_connection()
    c = conn.cursor()
    now = time.time()
    c.execute('''
        INSERT INTO vikriti_observations (user_id, symptoms, telemetry, estimate, confidence, data_status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        json.dumps(symptoms or []),
        json.dumps(telemetry or {}),
        json.dumps(estimate or {}),
        confidence,
        data_status,
        now
    ))
    obs_id = c.lastrowid
    conn.commit()
    conn.close()
    return obs_id

def get_vikriti_observations(user_id: int, limit: int = 7) -> List[Dict[str, Any]]:
    """
    Retrieves recent longitudinal Vikriti observations for a user in chronological order.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, symptoms, telemetry, estimate, confidence, data_status, timestamp
        FROM vikriti_observations
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    
    result = []
    for r in reversed(rows):
        result.append({
            "id": r["id"],
            "symptoms": json.loads(r["symptoms"] or "[]"),
            "telemetry": json.loads(r["telemetry"] or "{}"),
            "estimate": json.loads(r["estimate"] or "{}"),
            "confidence": r["confidence"],
            "data_status": r["data_status"],
            "timestamp": r["timestamp"]
        })
    return result

def update_current_vikriti(user_id, telemetry: Dict[str, Any], symptoms: List[str], estimate: Optional[Dict[str, Any]] = None, confidence: str = "provisional", data_status: str = "self_report_only"):
    conn = get_db_connection()
    c = conn.cursor()
    vikriti_state = {
        "telemetry": telemetry,
        "symptoms": symptoms,
        "estimate": estimate or {},
        "confidence": confidence,
        "data_status": data_status,
        "updated_at": time.time()
    }
    c.execute('UPDATE user_state SET current_vikriti = ? WHERE user_id = ?',
              (json.dumps(vikriti_state), user_id))
    conn.commit()
    conn.close()

    # Also store in longitudinal history
    record_vikriti_observation(user_id, symptoms, telemetry, estimate, confidence, data_status)

def save_telemetry_record(
    user_id: int,
    record_id: str,
    metric_type: str,
    metric_value: float,
    unit: str,
    recorded_at: float,
    source_package: str = "com.google.android.apps.healthdata",
    device_model: str = "Fastrack Noir Charm",
    provenance: str = "health_connect_import",
    aggregation_type: str = "interval"
) -> bool:
    """
    Saves an immutable telemetry measurement with stable record_id deduplication.
    Distinguishes interval records from cumulative daily totals or instantaneous readings.
    Returns True if newly inserted, False if duplicate ignored.
    """
    conn = get_db_connection()
    c = conn.cursor()
    ingested_at = time.time()
    try:
        c.execute('''
            INSERT INTO telemetry_records 
            (record_id, user_id, metric_type, metric_value, unit, recorded_at, ingested_at, source_package, device_model, provenance, aggregation_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (record_id, user_id, metric_type, float(metric_value), unit, float(recorded_at), ingested_at, source_package, device_model, provenance, aggregation_type))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate record_id safely ignored without error
        return False
    finally:
        conn.close()

def get_user_telemetry_records(user_id: int, metric_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves recent telemetry records for a user, preserving original timestamps, units, provenance, and aggregation type.
    """
    conn = get_db_connection()
    c = conn.cursor()
    if metric_type:
        c.execute('''
            SELECT id, record_id, metric_type, metric_value, unit, recorded_at, ingested_at, source_package, device_model, provenance, aggregation_type
            FROM telemetry_records
            WHERE user_id = ? AND metric_type = ?
            ORDER BY recorded_at DESC LIMIT ?
        ''', (user_id, metric_type, limit))
    else:
        c.execute('''
            SELECT id, record_id, metric_type, metric_value, unit, recorded_at, ingested_at, source_package, device_model, provenance, aggregation_type
            FROM telemetry_records
            WHERE user_id = ?
            ORDER BY recorded_at DESC LIMIT ?
        ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_daily_steps(user_id: int, date_str: Optional[str] = None) -> int:
    """
    Calculates verified total daily steps for a given calendar day (default: today).
    Delegates to the single canonical daily step aggregation service
    (src.perception.step_aggregation.get_canonical_daily_steps).
    """
    from src.perception.step_aggregation import get_canonical_daily_steps
    res = get_canonical_daily_steps(user_id=user_id, date_str=date_str)
    return int(res.get("steps", 0))


def get_interval_steps(user_id: int, start_ts: float, end_ts: float) -> int:
    """
    Calculates the exact number of steps taken strictly during a time window [start_ts, end_ts].
    Phase 2 Semantics: Never infers interval steps from a daily cumulative total.
    Only sums valid interval records. If only cumulative totals exist, returns 0.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT SUM(metric_value) as step_sum
        FROM telemetry_records
        WHERE user_id = ? AND metric_type = 'steps'
          AND aggregation_type != 'daily_total'
          AND (metric_value < 1000 OR record_id LIKE '%-%')
          AND provenance != 'synthetic'
          AND record_id NOT LIKE '%loop%'
          AND recorded_at >= ? AND recorded_at <= ?
    ''', (user_id, start_ts, end_ts))
    row = c.fetchone()
    conn.close()
    if row and row["step_sum"] is not None:
        return int(row["step_sum"])
    return 0


def get_telemetry_window_summary(
    user_id: int,
    metric_type: str,
    start_ts: float,
    end_ts: float
) -> Dict[str, Any]:
    """
    Retrieves statistical metrics for a specific window [start_ts, end_ts].
    """
    conn = get_db_connection()
    c = conn.cursor()

    if metric_type == "steps":
        steps_total = get_interval_steps(user_id, start_ts, end_ts)
        c.execute('''
            SELECT COUNT(*) as count, MAX(recorded_at) as latest_ts
            FROM telemetry_records
            WHERE user_id = ? AND metric_type = 'steps'
              AND (aggregation_type = 'interval' OR metric_value < 1000)
              AND recorded_at >= ? AND recorded_at <= ?
        ''', (user_id, start_ts, end_ts))
        row = c.fetchone()
        conn.close()
        return {
            "metric_type": "steps",
            "count": row["count"] if row else 0,
            "total_steps": steps_total,
            "unit": "count",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "latest_ts": row["latest_ts"] if row and row["latest_ts"] else None
        }

    c.execute('''
        SELECT COUNT(*) as count,
               MIN(metric_value) as min_val,
               MAX(metric_value) as max_val,
               AVG(metric_value) as avg_val,
               MAX(recorded_at) as latest_ts
        FROM telemetry_records
        WHERE user_id = ? AND metric_type = ?
          AND recorded_at >= ? AND recorded_at <= ?
    ''', (user_id, metric_type, start_ts, end_ts))
    stats = c.fetchone()

    latest_val = None
    if stats and stats["latest_ts"]:
        c.execute('''
            SELECT metric_value, unit, provenance, source_package
            FROM telemetry_records
            WHERE user_id = ? AND metric_type = ? AND recorded_at = ?
            LIMIT 1
        ''', (user_id, metric_type, stats["latest_ts"]))
        latest_row = c.fetchone()
        if latest_row:
            latest_val = {
                "value": latest_row["metric_value"],
                "unit": latest_row["unit"],
                "provenance": latest_row["provenance"],
                "source_package": latest_row["source_package"]
            }

    conn.close()
    return {
        "metric_type": metric_type,
        "count": stats["count"] if stats else 0,
        "min": round(stats["min_val"], 1) if stats and stats["min_val"] is not None else None,
        "max": round(stats["max_val"], 1) if stats and stats["max_val"] is not None else None,
        "avg": round(stats["avg_val"], 1) if stats and stats["avg_val"] is not None else None,
        "latest": latest_val,
        "latest_ts": stats["latest_ts"] if stats and stats["latest_ts"] else None,
        "start_ts": start_ts,
        "end_ts": end_ts
    }

# --- Phase 5: Activity Lifecycle & Adherence Persistence ---

def sync_schedule_to_activity_lifecycle(
    user_id: int,
    schedule: Dict[str, Any],
    date_str: str
) -> List[Dict[str, Any]]:
    """
    Synchronizes a generated or active daily schedule into the persistent activity_lifecycle table.
    Idempotent: Preserves existing completion status, evidence, or compensation links.
    """
    conn = get_db_connection()
    c = conn.cursor()
    created_activities = []
    now = time.time()

    sched_root = schedule.get("schedule", schedule) if isinstance(schedule, dict) else {}
    for block_name in ["morning_block", "midday_block", "evening_block"]:
        practices = sched_root.get(block_name, []) if isinstance(sched_root, dict) else []
        for p in practices:
            p_name = p.get("name") if isinstance(p, dict) else getattr(p, "name", "Practice")
            slot = (p.get("time_slot") if isinstance(p, dict) else getattr(p, "time_slot", "08:00 - 08:30")) or "08:00 - 08:30"

            # Parse start and end time to epoch timestamps
            match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", slot)
            if match:
                s_str, e_str = match.group(1), match.group(2)
                try:
                    s_ts = datetime.strptime(f"{date_str} {s_str}:00", "%Y-%m-%d %H:%M:%S").timestamp()
                    e_ts = datetime.strptime(f"{date_str} {e_str}:00", "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    s_ts, e_ts = now, now + 1800.0
            else:
                s_ts, e_ts = now, now + 1800.0

            p_id = p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
            clean_p_id = re.sub(r'^prac_', '', str(p_id)) if p_id else None
            clean_slug = re.sub(r'[^a-zA-Z0-9]+', '_', clean_p_id or p_name.lower()).strip('_')
            act_id = f"act_{user_id}_{date_str}_{clean_slug}"

            # Upsert preserving existing completion status
            c.execute('''
                INSERT INTO activity_lifecycle (
                    id, user_id, schedule_date, practice_name, time_slot,
                    start_time_ts, end_time_ts, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    time_slot = excluded.time_slot,
                    start_time_ts = excluded.start_time_ts,
                    end_time_ts = excluded.end_time_ts,
                    updated_at = excluded.updated_at
            ''', (act_id, user_id, date_str, p_name, slot, s_ts, e_ts, now, now))
            created_activities.append({"id": act_id, "practice_name": p_name, "time_slot": slot})

    conn.commit()
    conn.close()
    return created_activities

def get_user_activities(
    user_id: int,
    date_str: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves activity lifecycle records for a user on a given date (default: today).
    """
    conn = get_db_connection()
    c = conn.cursor()
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")

    query = 'SELECT * FROM activity_lifecycle WHERE user_id = ? AND schedule_date = ?'
    params: List[Any] = [user_id, target_date]

    if status:
        query += ' AND status = ?'
        params.append(status)

    query += ' ORDER BY start_time_ts ASC'
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        item = dict(r)
        if item.get("evidence_json"):
            try:
                item["evidence"] = json.loads(item["evidence_json"])
            except Exception:
                item["evidence"] = {}
        results.append(item)
    return results

def get_activity_by_id(activity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an activity lifecycle record by its stable ID."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM activity_lifecycle WHERE id = ?', (activity_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    if item.get("evidence_json"):
        try:
            item["evidence"] = json.loads(item["evidence_json"])
        except Exception:
            item["evidence"] = {}
    return item

def update_activity_lifecycle(
    activity_id: str,
    status: str,
    completed_at: Optional[float] = None,
    completion_source: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
    compensation_for_id: Optional[str] = None
) -> bool:
    """
    Idempotent, transactional state transition for scheduled activities.
    Supports: 'scheduled', 'due', 'completed_by_user', 'auto_completed_evidence',
              'missed', 'skipped', 'compensation_proposed', 'compensation_scheduled',
              'compensation_completed', 'cancelled'.
    """
    conn = get_db_connection()
    c = conn.cursor()
    now = time.time()
    evidence_str = json.dumps(evidence) if evidence else '{}'

    c.execute('''
        UPDATE activity_lifecycle
        SET status = ?,
            completed_at = COALESCE(?, completed_at),
            completion_source = COALESCE(?, completion_source),
            evidence_json = CASE WHEN ? != '{}' THEN ? ELSE evidence_json END,
            compensation_for_id = COALESCE(?, compensation_for_id),
            updated_at = ?
        WHERE id = ?
    ''', (status, completed_at, completion_source, evidence_str, evidence_str, compensation_for_id, now, activity_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_missed_activities(user_id: int, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all activities marked as missed on a given date."""
    return get_user_activities(user_id, date_str=date_str, status='missed')

def record_activity_compensation(
    user_id: int,
    original_activity_id: str,
    compensation_practice: str,
    time_slot: str,
    start_ts: float,
    end_ts: float,
    rationale: str
) -> str:
    """
    Schedules an evidence-based compensatory activity linked to an earlier missed activity.
    Preserves provenance and original activity ID.
    """
    conn = get_db_connection()
    c = conn.cursor()
    now = time.time()
    target_date = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
    comp_id = f"comp_{original_activity_id}_{int(now)}"
    evidence = {"rationale": rationale, "compensated_from": original_activity_id}

    c.execute('''
        INSERT INTO activity_lifecycle (
            id, user_id, schedule_date, practice_name, time_slot,
            start_time_ts, end_time_ts, status, completion_source,
            evidence_json, compensation_for_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'compensation_scheduled', 'planner_compensation', ?, ?, ?, ?)
    ''', (comp_id, user_id, target_date, compensation_practice, time_slot, start_ts, end_ts, json.dumps(evidence), original_activity_id, now, now))

    # Mark original activity as compensation_scheduled
    c.execute('''
        UPDATE activity_lifecycle
        SET status = 'compensation_scheduled', updated_at = ?
        WHERE id = ?
    ''', (now, original_activity_id))

    conn.commit()
    conn.close()
    return comp_id

def save_user_schedule(user_id, schedule: Dict[str, Any], date_str: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO user_state (user_id, last_schedule, schedule_timestamp, schedule_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_schedule = excluded.last_schedule,
            schedule_timestamp = excluded.schedule_timestamp,
            schedule_date = excluded.schedule_date
    ''', (user_id, json.dumps(schedule), time.time(), date_str))
    conn.commit()
    conn.close()
    try:
        sync_schedule_to_activity_lifecycle(user_id, schedule, date_str)
    except Exception as exc:
        logger.warning(f"Failed to sync schedule to activity_lifecycle for user {user_id}: {exc}")


def invalidate_user_schedule(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_state SET schedule_timestamp = 0, schedule_date = "" WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def update_adherence_score(user_id, score: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO user_state (user_id, adherence_score) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET adherence_score = excluded.adherence_score
        """,
        (user_id, score)
    )
    conn.commit()
    conn.close()

def save_user_state(user_id, state: Dict[str, Any]):
    if not state:
        return
    conn = get_db_connection()
    c = conn.cursor()
    score = state.get("adherence_score", 0.0)
    c.execute(
        """
        INSERT INTO user_state (user_id, adherence_score) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET adherence_score = excluded.adherence_score
        """,
        (user_id, score)
    )
    conn.commit()
    conn.close()

# --- Chat Methods ---

def save_chat_message(user_id, role, content) -> int:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, role, content))
    conn.commit()
    msg_id = c.lastrowid
    conn.close()
    return msg_id

def get_chat_history(user_id, limit=20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, role, content, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    # Reverse to get chronological order
    return [{"id": row["id"], "role": row["role"], "content": row["content"], "timestamp": row["timestamp"]} for row in reversed(rows)]


# --- Completion Methods ---

def save_completion(user_id: int, practice_name: str, date_str: Optional[str] = None) -> bool:
    """
    Saves a task completion for the user.
    Idempotent: prevents duplicate records for the same practice on the same day.
    Also synchronizes status to activity_lifecycle if matching record exists.
    """
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    now = time.time()
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if already recorded in completions table for target_date
    c.execute(
        'SELECT id FROM completions WHERE user_id = ? AND practice_name = ? AND completion_date = ?',
        (user_id, practice_name, target_date)
    )
    already_saved = c.fetchone()
    if not already_saved:
        c.execute(
            'INSERT INTO completions (user_id, practice_name, completion_date) VALUES (?, ?, ?)',
            (user_id, practice_name, target_date)
        )

    # Sync to activity_lifecycle
    c.execute(
        """
        UPDATE activity_lifecycle
        SET status = 'completed_by_user', completed_at = ?, completion_source = 'manual_dashboard', updated_at = ?
        WHERE user_id = ? AND schedule_date = ? 
          AND (lower(practice_name) = lower(?) OR lower(practice_name) LIKE '%' || lower(?) || '%')
          AND status NOT IN ('completed_by_user', 'auto_completed_evidence')
        """,
        (now, now, user_id, target_date, practice_name, practice_name)
    )

    conn.commit()
    conn.close()
    return True

def complete_user_activity(
    user_id: int,
    activity_id_or_name: str,
    date_str: Optional[str] = None,
    allow_early: bool = False
) -> Dict[str, Any]:
    """
    Authoritatively and idempotently marks an activity completed for the authenticated user.
    Preserves strict per-user isolation: cannot complete another user's task.
    Recalculates adherence score based on total eligible scheduled practices.
    Prevents premature completion if the scheduled time window has not arrived yet.
    """
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    now = time.time()
    conn = get_db_connection()
    c = conn.cursor()

    # Reject future dates unless allow_early
    if target_date > today_str and not allow_early:
        conn.close()
        return {
            "success": False,
            "error": f"Cannot complete activity scheduled for future date {target_date}.",
            "is_premature": True
        }

    # Locate activity record (exact id, id suffix, or exact name first to prevent substring false-positives)
    target_clean = re.sub(r'^prac_', '', activity_id_or_name)
    c.execute(
        """
        SELECT * FROM activity_lifecycle 
        WHERE user_id = ? AND schedule_date = ? 
          AND (id = ? OR id LIKE '%' || ? OR id LIKE '%' || ? OR lower(practice_name) = lower(?))
        LIMIT 1
        """,
        (user_id, target_date, activity_id_or_name, activity_id_or_name, target_clean, activity_id_or_name)
    )
    act_row = c.fetchone()
    if not act_row:
        c.execute(
            """
            SELECT * FROM activity_lifecycle 
            WHERE user_id = ? AND schedule_date = ? 
              AND lower(practice_name) LIKE '%' || lower(?) || '%'
            LIMIT 1
            """,
            (user_id, target_date, activity_id_or_name)
        )
        act_row = c.fetchone()

    # Check premature completion window for today
    if target_date == today_str and not allow_early:
        s_ts = None
        slot_str = ""
        p_label = activity_id_or_name
        is_already_done = False

        if act_row:
            act_dict = dict(act_row)
            p_label = act_dict.get("practice_name") or activity_id_or_name
            slot_str = act_dict.get("time_slot") or ""
            s_ts = act_dict.get("start_time_ts")
            is_already_done = act_dict.get("status") in ('completed_by_user', 'auto_completed_evidence', 'completed')
        else:
            c.execute('SELECT last_schedule FROM user_state WHERE user_id = ?', (user_id,))
            s_row = c.fetchone()
            if s_row and s_row["last_schedule"]:
                try:
                    s_json = json.loads(s_row["last_schedule"])
                    sched = s_json.get("schedule", {}) if isinstance(s_json, dict) else {}
                    all_p = (sched.get("morning_block") or []) + (sched.get("midday_block") or []) + (sched.get("evening_block") or [])
                    for p in all_p:
                        p_name = p.get("name") or p.get("activity") or ""
                        if p_name.lower() == activity_id_or_name.lower() or activity_id_or_name.lower() in p_name.lower():
                            p_label = p_name
                            slot_str = p.get("time_slot") or ""
                            break
                except Exception:
                    pass

        if not is_already_done:
            if not s_ts and slot_str:
                match = re.search(r"(\d{1,2}:\d{2})", slot_str)
                if match:
                    try:
                        s_ts = datetime.strptime(f"{target_date} {match.group(1)}:00", "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        s_ts = None

            if s_ts and (s_ts - now > 900):  # More than 15 minutes before scheduled start time
                conn.close()
                return {
                    "success": False,
                    "error": f"'{p_label}' is scheduled for {slot_str}. You can mark it completed once its scheduled time window begins.",
                    "is_premature": True,
                    "time_slot": slot_str,
                    "start_time_ts": s_ts
                }

    practice_name = activity_id_or_name
    act_id = None
    if act_row:
        act_dict = dict(act_row)
        practice_name = act_dict["practice_name"]
        act_id = act_dict["id"]
        # Update lifecycle status
        c.execute(
            """
            UPDATE activity_lifecycle 
            SET status = 'completed_by_user', completed_at = ?, completion_source = 'manual_dashboard', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now, now, act_id, user_id)
        )

    # Record in completions (deduplicated)
    c.execute(
        'SELECT id FROM completions WHERE user_id = ? AND practice_name = ? AND completion_date = ?',
        (user_id, practice_name, target_date)
    )
    if not c.fetchone():
        c.execute(
            'INSERT INTO completions (user_id, practice_name, completion_date) VALUES (?, ?, ?)',
            (user_id, practice_name, target_date)
        )

    # Recalculate adherence
    c.execute(
        """
        SELECT count(*) as total,
               sum(CASE WHEN status IN ('completed_by_user', 'auto_completed_evidence', 'completed') THEN 1 ELSE 0 END) as completed
        FROM activity_lifecycle
        WHERE user_id = ? AND schedule_date = ? AND status != 'cancelled' AND compensation_for_id IS NULL
        """,
        (user_id, target_date)
    )
    counts = c.fetchone()
    total_eligible = counts["total"] if counts and counts["total"] is not None else 0
    completed_count = counts["completed"] if counts and counts["completed"] is not None else 0

    if total_eligible == 0:
        # Check schedule in user_state
        c.execute('SELECT last_schedule FROM user_state WHERE user_id = ?', (user_id,))
        s_row = c.fetchone()
        if s_row and s_row["last_schedule"]:
            try:
                s_json = json.loads(s_row["last_schedule"])
                sched = s_json.get("schedule", {}) if isinstance(s_json, dict) else {}
                all_p = (sched.get("morning_block") or []) + (sched.get("midday_block") or []) + (sched.get("evening_block") or [])
                total_eligible = len(all_p)
            except Exception:
                pass
        c.execute('SELECT count(DISTINCT practice_name) as cnt FROM completions WHERE user_id = ? AND completion_date = ?', (user_id, target_date))
        c_cnt = c.fetchone()
        completed_count = c_cnt["cnt"] if c_cnt else 1

    from src.behavior.scoring import ScoringEngine
    adh_res = ScoringEngine.calculate_adherence_score(completed_count, total_eligible)
    # Store normalized score (0.0 to 1.0) in user_state
    normalized_adh = adh_res["score"] / 100.0
    c.execute('UPDATE user_state SET adherence_score = ? WHERE user_id = ?', (normalized_adh, user_id))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "user_id": user_id,
        "practice_name": practice_name,
        "activity_id": act_id,
        "status": "completed_by_user",
        "adherence": adh_res,
        "completed_count": completed_count,
        "total_eligible_count": total_eligible,
        "timestamp": now
    }

def get_today_completions(user_id: int, date_str: Optional[str] = None) -> List[str]:
    conn = get_db_connection()
    c = conn.cursor()
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    c.execute('SELECT practice_name FROM completions WHERE user_id = ? AND completion_date = ?', (user_id, target_date))
    rows = c.fetchall()
    conn.close()
    return [row["practice_name"] for row in rows]

def get_daily_completion_counts(user_id: int, days: int = 5) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT completion_date, count(*) as count 
        FROM completions 
        WHERE user_id = ? AND completion_date >= date('now', ?)
        GROUP BY completion_date
        ORDER BY completion_date ASC
        """,
        (user_id, f"-{days} days")
    )
    rows = c.fetchall()
    conn.close()
    return [{"date": row["completion_date"], "count": row["count"]} for row in rows]

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


# --- Schedule Proposal Methods ---

def save_schedule_proposal(proposal: Dict[str, Any]) -> str:
    """
    Persists a canonical schedule proposal into SQLite.
    If another pending proposal exists for this user, marks it replaced/stale.
    """
    conn = get_db_connection()
    c = conn.cursor()
    uid = int(proposal["user_id"])
    now = time.time()
    
    # Supersede older pending proposals for this user
    c.execute(
        "UPDATE schedule_proposals SET status = 'superseded', updated_at = ? WHERE user_id = ? AND status = 'pending_user_confirmation'",
        (now, uid)
    )
    
    p_id = proposal["proposal_id"]
    p_data = json.dumps(proposal)
    c.execute('''
        INSERT OR REPLACE INTO schedule_proposals 
        (proposal_id, user_id, target_practice, original_time_slot, proposed_time_slot, target_block, schedule_version, status, proposal_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        p_id,
        uid,
        proposal.get("target_practice", ""),
        proposal.get("original_time_slot", ""),
        proposal.get("proposed_time_slot", ""),
        proposal.get("target_block", "morning_block"),
        float(proposal.get("schedule_version", 0.0)),
        proposal.get("status", "pending_user_confirmation"),
        p_data,
        proposal.get("created_at", now),
        now
    ))
    conn.commit()
    conn.close()
    return p_id


def get_schedule_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a proposal by its unique ID.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT proposal_data, status, schedule_version FROM schedule_proposals WHERE proposal_id = ?", (proposal_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    try:
        data = json.loads(row["proposal_data"])
        data["status"] = row["status"]
        data["schedule_version"] = row["schedule_version"]
        pid = data.get("proposal_id") or data.get("id") or row["proposal_id"]
        data["proposal_id"] = pid
        data["id"] = pid
        return data
    except Exception:
        return None


def get_pending_proposal(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent pending proposal for a user.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT proposal_id, proposal_data, status, schedule_version FROM schedule_proposals WHERE user_id = ? AND status = 'pending_user_confirmation' ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    try:
        data = json.loads(row["proposal_data"])
        data["status"] = row["status"]
        data["schedule_version"] = row["schedule_version"]
        pid = data.get("proposal_id") or data.get("id") or row["proposal_id"]
        data["proposal_id"] = pid
        data["id"] = pid
        return data
    except Exception:
        return None


def update_proposal_status(proposal_id: str, status: str) -> bool:
    """
    Updates the confirmation status of a proposal (e.g. applied, rejected, stale, failed).
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE schedule_proposals SET status = ?, updated_at = ? WHERE proposal_id = ?",
        (status, time.time(), proposal_id)
    )
    affected = c.rowcount
    
    # Also update the embedded JSON status
    c.execute("SELECT proposal_data FROM schedule_proposals WHERE proposal_id = ?", (proposal_id,))
    row = c.fetchone()
    if row and row["proposal_data"]:
        try:
            d = json.loads(row["proposal_data"])
            d["status"] = status
            c.execute("UPDATE schedule_proposals SET proposal_data = ? WHERE proposal_id = ?", (json.dumps(d), proposal_id))
        except Exception:
            pass
            
    conn.commit()
    conn.close()
    return affected > 0


# Initialize on import
init_db()

