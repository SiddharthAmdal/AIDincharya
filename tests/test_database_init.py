"""
Regression tests for Database Initialization and Missing completions Table (Defect B).
Verifies:
1. Clean initialization on a genuinely nonexistent temporary database.
2. Idempotent initialization that preserves pre-existing records.
3. Presence of all required tables and columns (including completions and its index).
4. Full execution of completion methods: save_completion and get_today_completions.
5. Tool execution profile and adherence logging closed-loop without table errors.
6. Execution of /api/adherence/log endpoint on a fresh database.
"""

import os
import sqlite3
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.planning.tools import execute_planner_tool

client = TestClient(app)


def test_fresh_database_initialization(tmp_path, monkeypatch):
    """
    Verify that init_db() creates all required tables (including completions)
    on a completely fresh, nonexistent SQLite database.
    """
    temp_db_path = str(tmp_path / "fresh_test.db")
    assert not os.path.exists(temp_db_path), "Database file should not exist initially"

    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    # Initialize schema
    db.init_db()
    assert os.path.exists(temp_db_path), "Database file should be created by init_db"

    # Verify tables
    conn = sqlite3.connect(temp_db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in c.fetchall()}

    expected_tables = {
        "users",
        "sessions",
        "user_state",
        "chat_history",
        "notifications",
        "push_subscriptions",
        "completions"
    }
    missing_tables = expected_tables - tables
    assert not missing_tables, f"Database is missing expected tables: {missing_tables}"

    # Verify columns of completions table
    c.execute("PRAGMA table_info(completions)")
    col_names = {row[1] for row in c.fetchall()}
    expected_cols = {"id", "user_id", "practice_name", "completion_date", "timestamp"}
    assert expected_cols.issubset(col_names), f"Missing columns in completions: {expected_cols - col_names}"

    # Verify indices
    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indices = {row[0] for row in c.fetchall()}
    assert "idx_completions_user_date" in indices

    conn.close()


def test_completions_crud_and_idempotency(tmp_path, monkeypatch):
    """
    Verify completions operations and ensure repeated init_db() calls are idempotent
    and preserve pre-existing records.
    """
    temp_db_path = str(tmp_path / "idempotent_test.db")
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    # 1. Initialize fresh DB
    db.init_db()

    # 2. Create user and save completions
    uid = db.create_user("ayur_test_user", "SecurePass123!")
    assert uid is not None

    db.save_completion(uid, "Brahma Muhurta Wakeup")
    db.save_completion(uid, "Abhyanga Oil Massage")

    todays = db.get_today_completions(uid)
    assert len(todays) == 2
    assert "Brahma Muhurta Wakeup" in todays
    assert "Abhyanga Oil Massage" in todays

    # 3. Call init_db() a second time (simulating app restart or migration run)
    db.init_db()

    # Verify data survived intact
    todays_after = db.get_today_completions(uid)
    assert len(todays_after) == 2
    assert "Brahma Muhurta Wakeup" in todays_after
    assert "Abhyanga Oil Massage" in todays_after


def test_tool_execution_profile_and_adherence_with_fresh_db(tmp_path, monkeypatch):
    """
    Exercise user profile, adherence logging, and tool dispatcher on a fresh temporary database.
    Confirms get_today_completions does not throw sqlite3.OperationalError: no such table.
    """
    temp_db_path = str(tmp_path / "adherence_test.db")
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    db.init_db()

    # Create user
    uid = db.create_user("adherence_user", "SecretPass123")
    assert uid is not None

    # Update adherence score in db
    db.update_adherence_score(uid, 0.85)

    # Log completion in completions table
    db.save_completion(uid, "Ushapan (Warm Water)")
    completions = db.get_today_completions(uid)
    assert "Ushapan (Warm Water)" in completions

    # Execute planner tool to query adherence history
    res_str = execute_planner_tool(
        "get_adherence_history",
        {"user_id": str(uid)},
        caller_user_id=str(uid)
    )
    res = json.loads(res_str)
    assert "adherence_score" in res
    assert res["adherence_score"] == 0.85
    assert "today_completions" in res
    assert "Ushapan (Warm Water)" in res["today_completions"]


def test_tool_dispatcher_alias_user_id_resolution(tmp_path, monkeypatch):
    """
    Verify execute_planner_tool resolves integer/string user_id aliases safely.
    """
    temp_db_path = str(tmp_path / "alias_test.db")
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    db.init_db()

    uid = db.create_user("alias_user", "AliasPass123")
    assert uid is not None

    db.save_completion(uid, "Nadi Shodhana Pranayama")

    # Pass caller_user_id as string
    res_str = execute_planner_tool(
        "get_adherence_history",
        {},
        caller_user_id=str(uid)
    )
    res = json.loads(res_str)
    assert "Nadi Shodhana Pranayama" in res.get("today_completions", [])


def test_api_adherence_log_closed_loop_fresh_db(tmp_path, monkeypatch):
    """
    Verify /api/adherence/log inserts completions into the freshly created completions table.
    """
    temp_db_path = str(tmp_path / "api_adherence_test.db")
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    db.init_db()
    uid = db.create_user("api_test_user", "Pass456!")
    assert uid is not None

    # Override auth to return this user id
    orig_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: uid

    try:
        payload = {
            "user_id": str(uid),
            "completed_practices": ["Wake up call", "Warm Water"],
            "recommended_practices": ["Wake up call", "Warm Water", "Abhyanga", "Lunch", "Dinner"]
        }
        resp = client.post("/api/adherence/log", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["adherence_score"] == 0.4

        # Confirm saved in database completions table
        saved_completions = db.get_today_completions(uid)
        assert "Wake up call" in saved_completions
        assert "Warm Water" in saved_completions
    finally:
        if orig_override is not None:
            app.dependency_overrides[get_current_user] = orig_override
        else:
            app.dependency_overrides.pop(get_current_user, None)
