"""
End-to-End Task Persistence, Completion Idempotency, and Adherence Verification Tests.

Verifies:
1. Task completion writes to both activity_lifecycle and completions tables in SQLite.
2. Completion survives a subsequent API read and browser refresh.
3. Duplicate completion clicks are idempotent (do not create duplicate rows or inflate adherence).
4. Strict user isolation: User B cannot complete User A's activity.
5. Adherence score updates accurately according to (completed / total_eligible) * 100.
6. Error handling for missing task identifiers.
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
from src.database import db
from src.models import DinacharyaSchedule, Practice

client = TestClient(app)


def _create_test_user_with_routine(username_prefix: str):
    """Creates a unique authenticated user with a seeded schedule and activity lifecycle."""
    uname = f"{username_prefix}_{int(time.time() * 1000)}"
    user_id = db.create_user(uname, "password123")
    token = db.create_session(user_id)

    # Seed 3 distinct practices
    sched_dict = {
        "morning_block": [
            {"name": "Brahma Muhurta Awakening", "time_slot": "05:30 - 06:00", "description": "Early wake and warm water"},
            {"name": "Pranayama Breathwork", "time_slot": "06:30 - 07:00", "description": "Nadi Shodhana breathing"}
        ],
        "midday_block": [
            {"name": "Mitahara Nourishing Lunch", "time_slot": "12:30 - 13:15", "description": "Six-tastes lunch"}
        ],
        "evening_block": []
    }
    date_str = time.strftime("%Y-%m-%d")
    db.save_user_schedule(user_id, sched_dict, date_str)
    db.sync_schedule_to_activity_lifecycle(user_id, sched_dict, date_str)

    return user_id, token, date_str


def test_task_completion_persistence_and_adherence():
    """Verifies that completing a practice persists to SQLite and recalculates adherence."""
    user_id, token, date_str = _create_test_user_with_routine("task_persist_usr")
    headers = {"Authorization": f"Bearer {token}"}

    # Initial state: 0 completed out of 3 scheduled -> adherence = 0%
    dash_pre = client.get("/api/dashboard/summary", headers=headers)
    assert dash_pre.status_code == 200
    pre_data = dash_pre.json()
    assert pre_data["adherence_pct"] == 0
    assert len(pre_data["completions_today"]) == 0

    # 1. Complete Practice 1
    res1 = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Brahma Muhurta Awakening"}
    )
    assert res1.status_code == 200
    res1_data = res1.json()
    assert res1_data["success"] is True
    assert res1_data["status"] == "completed_by_user"
    assert res1_data["completed_count"] == 1
    assert res1_data["total_eligible_count"] == 3
    # 1 / 3 = 33.33% -> rounded 33%
    assert res1_data["adherence"]["rounded_score"] == 33

    # 2. Read back from /api/dashboard/summary to verify persistence in SQLite
    dash_post1 = client.get("/api/dashboard/summary", headers=headers)
    assert dash_post1.status_code == 200
    post1_data = dash_post1.json()
    assert "Brahma Muhurta Awakening" in post1_data["completions_today"]
    assert post1_data["adherence_pct"] == 33

    # 3. Read back from /api/activities/today
    acts_res = client.get("/api/activities/today", headers=headers)
    assert acts_res.status_code == 200
    acts = acts_res.json()["activities"]
    completed_acts = [a for a in acts if a["status"] == "completed_by_user"]
    assert len(completed_acts) == 1
    assert completed_acts[0]["practice_name"] == "Brahma Muhurta Awakening"


def test_task_completion_idempotency():
    """Verifies that repeated clicks or retries do not create duplicate records or inflate adherence."""
    user_id, token, date_str = _create_test_user_with_routine("idempotent_usr")
    headers = {"Authorization": f"Bearer {token}"}

    # First completion
    client.post("/api/activities/complete", headers=headers, json={"practice_name": "Pranayama Breathwork"})

    # Duplicate completion calls
    for _ in range(3):
        res = client.post("/api/activities/complete", headers=headers, json={"practice_name": "Pranayama Breathwork"})
        assert res.status_code == 200
        # Should stay 1 completed out of 3, NOT 2 or 3!
        assert res.json()["completed_count"] == 1

    # Check raw DB completions count for this user
    completions = db.get_today_completions(user_id)
    # Deduplication ensures only 1 entry for Pranayama Breathwork
    pranayama_entries = [p for p in completions if p == "Pranayama Breathwork"]
    assert len(pranayama_entries) == 1


def test_cross_user_completion_isolation():
    """Verifies that User B cannot complete or tamper with User A's scheduled tasks."""
    user_a, token_a, _ = _create_test_user_with_routine("usr_a_iso")
    user_b, token_b, _ = _create_test_user_with_routine("usr_b_iso")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Get User A's activity ID
    acts_a = client.get("/api/activities/today", headers=headers_a).json()["activities"]
    act_a_id = acts_a[0]["id"]

    # User B attempts to complete User A's activity ID
    res_b = client.post("/api/activities/complete", headers=headers_b, json={"activity_id": act_a_id})
    assert res_b.status_code == 200
    # The helper is user-scoped; it will not update User A's row
    act_a_fresh = db.get_activity_by_id(act_a_id)
    # User A's activity status remains 'scheduled'
    assert act_a_fresh["status"] == "scheduled"
    assert act_a_fresh["user_id"] == user_a

    # User A's adherence remains 0%
    dash_a = client.get("/api/dashboard/summary", headers=headers_a).json()
    assert dash_a["adherence_pct"] == 0


def test_missing_task_identifier_returns_400():
    """Verifies that requests without activity_id or practice_name fail with HTTP 400."""
    _, token, _ = _create_test_user_with_routine("err_usr")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/activities/complete", headers=headers, json={})
    assert res.status_code == 400
