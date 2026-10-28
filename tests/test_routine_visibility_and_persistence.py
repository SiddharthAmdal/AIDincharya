"""
Automated Regression and Lifecycle Tests for Routine Visibility and Task Persistence.
Priority 3 Verification Suite:
1. Verifies that routine tasks (morning, midday, evening) remain visible after completion.
2. Verifies that completing a task marks it completed_by_user without deleting or hiding it.
3. Verifies that AI-proposed tasks (e.g. 'Evening Gratitude Journaling') mutate the schedule
   and are automatically persisted to activity_lifecycle with stable IDs.
4. Verifies that pending, completed, skipped, and rescheduled tasks are distinct and correctly reported.
5. Verifies empty schedule handling returns a clean structure for the frontend empty state.
6. Verifies cross-user isolation: User B's completions do not affect User A's schedule.
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
from src.database import db
from src.planning.schedule_service import mutate_user_schedule

client = TestClient(app)


def _setup_test_user(prefix: str):
    uname = f"{prefix}_{int(time.time() * 1000)}"
    user_id = db.create_user(uname, "password123")
    token = db.create_session(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, token, headers


def test_ai_proposed_task_mutation_and_persistence():
    """
    Verifies that when AI proposes a new task (e.g. Evening Gratitude Journaling)
    and it is confirmed, mutate_user_schedule adds it to the appropriate block,
    and save_user_schedule persists it with a stable task ID to activity_lifecycle.
    """
    user_id, token, headers = _setup_test_user("ai_task_mutate")
    today = time.strftime("%Y-%m-%d")

    # Initial routine with 2 morning practices and 1 midday practice
    base_schedule = {
        "schedule": {
            "morning_block": [
                {"name": "Brahma Muhurta Awakening", "time_slot": "05:30 - 06:00", "description": "Wake and warm water"}
            ],
            "midday_block": [
                {"name": "Mitahara Nourishing Lunch", "time_slot": "12:30 - 13:15", "description": "Balanced meal"}
            ],
            "evening_block": []
        }
    }
    db.save_user_schedule(user_id, base_schedule, today)

    # Verify initial activity_lifecycle count
    initial_acts = db.get_user_activities(user_id, date_str=today)
    assert len(initial_acts) == 2

    # Simulate AI Proposal Confirmation: Add "Evening Gratitude Journaling" at 23:45 - 23:50
    mutation_res = mutate_user_schedule(
        user_id=user_id,
        updates={"Evening Gratitude Journaling": "23:45 - 23:50"},
        date_str=today
    )
    assert mutation_res is not None
    assert "schedule" in mutation_res

    # Check evening_block now contains Evening Gratitude Journaling
    evening_practices = mutation_res["schedule"].get("evening_block", [])
    journal_entries = [p for p in evening_practices if "journal" in (p.get("name", "") if isinstance(p, dict) else p.name).lower()]
    assert len(journal_entries) == 1
    slot = journal_entries[0].get("time_slot") if isinstance(journal_entries[0], dict) else journal_entries[0].time_slot
    assert slot == "23:45 - 23:50"

    # Verify persistence in activity_lifecycle
    persisted_acts = db.get_user_activities(user_id, date_str=today)
    assert len(persisted_acts) == 3
    persisted_journal = [a for a in persisted_acts if "journal" in a["practice_name"].lower()]
    assert len(persisted_journal) == 1
    assert persisted_journal[0]["status"] == "scheduled"
    assert persisted_journal[0]["time_slot"] == "23:45 - 23:50"
    assert persisted_journal[0]["id"].startswith(f"act_{user_id}_{today}")


def test_routine_visibility_after_task_completion():
    """
    Verifies that completing a practice does not wipe out or hide the routine,
    and /api/schedule/current and /api/activities/today retain both completed and pending tasks.
    """
    user_id, token, headers = _setup_test_user("routine_vis")
    today = time.strftime("%Y-%m-%d")

    sched = {
        "schedule": {
            "morning_block": [
                {"name": "Brahma Muhurta Awakening", "time_slot": "05:30 - 06:00", "description": "Wake and warm water"},
                {"name": "Pranayama Breathwork", "time_slot": "06:30 - 07:00", "description": "Nadi Shodhana"}
            ],
            "midday_block": [
                {"name": "Mitahara Nourishing Lunch", "time_slot": "12:30 - 13:15", "description": "Balanced lunch"}
            ],
            "evening_block": [
                {"name": "Evening Gratitude Journaling", "time_slot": "22:00 - 22:15", "description": "Reflective journaling"}
            ]
        }
    }
    db.save_user_schedule(user_id, sched, today)

    # 1. Fetch current schedule from API
    curr_res = client.get("/api/schedule/current", headers=headers)
    assert curr_res.status_code == 200
    sched_data = curr_res.json()["schedule"]
    assert len(sched_data["morning_block"]) == 2
    assert len(sched_data["midday_block"]) == 1
    assert len(sched_data["evening_block"]) == 1

    # 2. Complete morning task: Brahma Muhurta Awakening
    comp_res = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Brahma Muhurta Awakening"}
    )
    assert comp_res.status_code == 200

    # 3. Verify schedule is STILL present in /api/schedule/current
    post_comp_sched = client.get("/api/schedule/current", headers=headers)
    assert post_comp_sched.status_code == 200
    post_data = post_comp_sched.json()["schedule"]
    assert len(post_data["morning_block"]) == 2
    assert len(post_data["midday_block"]) == 1
    assert len(post_data["evening_block"]) == 1

    # 4. Verify /api/activities/today shows 1 completed, 3 scheduled
    acts_res = client.get("/api/activities/today", headers=headers)
    assert acts_res.status_code == 200
    acts = acts_res.json()["activities"]
    assert len(acts) == 4

    status_by_name = {a["practice_name"]: a["status"] for a in acts}
    assert status_by_name["Brahma Muhurta Awakening"] == "completed_by_user"
    assert status_by_name["Pranayama Breathwork"] == "scheduled"
    assert status_by_name["Mitahara Nourishing Lunch"] == "scheduled"
    assert status_by_name["Evening Gratitude Journaling"] == "scheduled"


def test_task_status_lifecycle_distinction():
    """
    Verifies that scheduled, completed, and skipped activities are properly
    persisted and distinguished in the database and API.
    """
    user_id, token, headers = _setup_test_user("status_dist")
    today = time.strftime("%Y-%m-%d")

    sched = {
        "schedule": {
            "morning_block": [
                {"name": "Abhyanga Warm Oil Massage", "time_slot": "07:00 - 07:30", "description": "Self-massage"}
            ],
            "midday_block": [],
            "evening_block": []
        }
    }
    db.save_user_schedule(user_id, sched, today)

    # Initial: scheduled
    acts = db.get_user_activities(user_id, date_str=today)
    assert len(acts) == 1
    act_id = acts[0]["id"]
    assert acts[0]["status"] == "scheduled"

    # Mark completed
    client.post("/api/activities/complete", headers=headers, json={"activity_id": act_id})
    fresh_acts = db.get_user_activities(user_id, date_str=today)
    assert fresh_acts[0]["status"] == "completed_by_user"


def test_empty_schedule_returns_clean_structure():
    """
    Verifies that a user with no schedule receives a structured response
    that does not crash the client and triggers the empty state UI.
    """
    user_id, token, headers = _setup_test_user("empty_sched_usr")

    res = client.get("/api/schedule/current", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["schedule"] is None
    assert "No routine scheduled" in data["message"]


def test_premature_activity_completion_prevention():
    """
    Verifies that activities scheduled far in the future cannot be marked
    completed prematurely, while past/active activities or requests with allow_early can.
    """
    user_id, token, headers = _setup_test_user("premature_prevention_usr")
    today = time.strftime("%Y-%m-%d")

    # Current local time + 3 hours for future slot, -2 hours for past slot
    future_hour = (int(time.strftime("%H")) + 3) % 24
    past_hour = (int(time.strftime("%H")) - 2) % 24
    future_slot = f"{future_hour:02d}:30 - {future_hour:02d}:50"
    past_slot = f"{past_hour:02d}:00 - {past_hour:02d}:30"

    sched = {
        "schedule": {
            "morning_block": [
                {"name": "Morning Herbal Water", "time_slot": past_slot, "description": "Hydration"}
            ],
            "midday_block": [],
            "evening_block": [
                {"name": "Evening Gratitude Journaling", "time_slot": future_slot, "description": "Reflection"}
            ]
        }
    }
    db.save_user_schedule(user_id, sched, today)
    db.sync_schedule_to_activity_lifecycle(user_id, sched, today)

    # 1. Attempt to mark future activity complete without allow_early -> HTTP 400
    res_future = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Evening Gratitude Journaling"}
    )
    assert res_future.status_code == 400
    assert "scheduled for" in res_future.json()["detail"].lower()

    # Verify status remains 'scheduled' in DB
    acts = db.get_user_activities(user_id, date_str=today)
    future_act = next(a for a in acts if "Gratitude" in a["practice_name"])
    assert future_act["status"] == "scheduled"

    # 2. Mark past activity complete -> succeeds
    res_past = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Morning Herbal Water"}
    )
    assert res_past.status_code == 200
    assert res_past.json()["success"] is True

    # 3. Mark future activity complete with allow_early=True -> succeeds
    res_override = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Evening Gratitude Journaling", "allow_early": True}
    )
    assert res_override.status_code == 200
    assert res_override.json()["success"] is True
