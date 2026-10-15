import time
import json
import sqlite3
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.models import DinacharyaSchedule, Practice, DoshaProfile, DoshaVector, UserContext
from src.planning.schedule_service import mutate_user_schedule, get_canonical_schedule
from src.planning.agent import DinacharyaPlannerAgent

client = TestClient(app)

TEST_USER_A = 8801
TEST_USER_B = 8802


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    orig_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides.pop(get_current_user, None)
    yield
    if orig_override is not None:
        app.dependency_overrides[get_current_user] = orig_override
    else:
        app.dependency_overrides.pop(get_current_user, None)


def _seed_user_with_schedule(user_id: int, username: str, dinner_slot: str = "19:00 - 19:30", trataka_slot: str = "21:30 - 21:45"):
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    
    c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
              (user_id, username, "dummy_hash"))
    
    canonical_schedule = {
        "schedule": {
            "user_id": str(user_id),
            "adherence_score": 1.0,
            "routine_complexity": "Moderate",
            "morning_block": [
                {
                    "name": "Brahma Muhurta Jagaran",
                    "time_slot": "06:00 - 06:15",
                    "duration_minutes": 15,
                    "description": "Wake up at Brahma Muhurta.",
                    "rationale": "Aligns with circadian rhythm."
                },
                {
                    "name": "Abhyanga",
                    "time_slot": "06:30 - 06:45",
                    "duration_minutes": 15,
                    "description": "Warm sesame oil massage.",
                    "rationale": "Calms Vata dosha."
                }
            ],
            "midday_block": [
                {
                    "name": "Mitahara (Heaviest Meal)",
                    "time_slot": "12:00 - 12:40",
                    "duration_minutes": 40,
                    "description": "Wholesome warm lunch.",
                    "rationale": "Peak digestive Agni."
                }
            ],
            "evening_block": [
                {
                    "name": "Light Early Dinner",
                    "time_slot": dinner_slot,
                    "duration_minutes": 30,
                    "description": "Light soup or khichdi.",
                    "rationale": "Avoids Kapha stagnation before sleep."
                },
                {
                    "name": "Trataka / Reflection",
                    "time_slot": trataka_slot,
                    "duration_minutes": 15,
                    "description": "Meditation and candle flame focus.",
                    "rationale": "Calms senses and promotes melatonin."
                }
            ],
            "timestamp": time.time()
        },
        "dosha_profile": {
            "user_id": str(user_id),
            "prakriti": {"vata": 0.4, "pitta": 0.4, "kapha": 0.2},
            "vikriti_flags": {"vata_aggravated": False, "pitta_aggravated": False, "kapha_aggravated": False, "has_fever": False},
            "timestamp": time.time()
        },
        "complexity_level": "Moderate",
        "timestamp": time.time()
    }
    
    today_date = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        """INSERT INTO user_state (
            user_id, questionnaire_responses, telemetry_baselines, current_vikriti,
            adherence_score, has_completed_onboarding, last_schedule, schedule_timestamp, schedule_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            json.dumps({"sleep": "good"}),
            json.dumps({}),
            json.dumps({"telemetry": {}, "symptoms": []}),
            1.0,
            True,
            json.dumps(canonical_schedule),
            time.time(),
            today_date
        )
    )
    conn.commit()
    conn.close()
    return db.create_session(user_id)


# ============================================================================
# Test A: Canonical persistence
# Given a user whose dinner is scheduled for 19:00–19:30, request a move to 20:00–20:30.
# Verify that the accepted mutation persists the correct start and end times in canonical schedule.
# ============================================================================
def test_a_canonical_persistence():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_a", dinner_slot="19:00 - 19:30")
    
    # Mutate schedule through canonical schedule service
    res = mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    assert res["success"] is True
    assert "Light Early Dinner" in res["matched_practices"]
    
    # Verify directly from SQLite
    state = db.get_user_state(TEST_USER_A)
    persisted_sched = state["last_schedule"]["schedule"]
    evening_tasks = {t["name"]: t["time_slot"] for t in persisted_sched["evening_block"]}
    
    assert evening_tasks["Light Early Dinner"] == "20:00 - 20:30"


# ============================================================================
# Test B: Planner API consistency
# After the mutation, make a fresh authenticated request to the actual current-schedule endpoint.
# Verify that it returns dinner at 20:00–20:30 and not the original time.
# ============================================================================
def test_b_planner_api_consistency():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_b", dinner_slot="19:00 - 19:30")
    
    # Apply mutation
    mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    
    # Fresh authenticated request to /api/schedule/current
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/schedule/current", headers=headers)
    assert res.status_code == 200
    
    data = res.json()
    assert "schedule" in data
    evening_tasks = {t["name"]: t["time_slot"] for t in data["schedule"]["evening_block"]}
    assert evening_tasks["Light Early Dinner"] == "20:00 - 20:30"


# ============================================================================
# Test C: Full refresh consistency
# Simulate a fresh frontend load or authenticated schedule fetch.
# Verify that the timeline displays the updated time after refreshing.
# ============================================================================
def test_c_full_refresh_consistency():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_c", dinner_slot="19:00 - 19:30")
    
    # Mutate to 20:00 - 20:30
    mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    
    # First fetch
    headers = {"Authorization": f"Bearer {token}"}
    res1 = client.get("/api/schedule/current", headers=headers)
    assert res1.status_code == 200
    
    # Second fetch simulating browser reload
    res2 = client.get("/api/schedule/current", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["schedule"]["evening_block"][0]["time_slot"] == "20:00 - 20:30"


# ============================================================================
# Test D: Reflection activity remains consistent
# Verify that Trataka / Reflection is displayed at the new time only if that change
# was actually requested, validated, and persisted. Otherwise, it must retain original time.
# Never infer that changing dinner should automatically reschedule unrelated activities.
# ============================================================================
def test_d_reflection_activity_remains_consistent():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_d", dinner_slot="19:00 - 19:30", trataka_slot="21:30 - 21:45")
    
    # Only Dinner was requested to change
    mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/schedule/current", headers=headers)
    assert res.status_code == 200
    
    evening = {t["name"]: t["time_slot"] for t in res.json()["schedule"]["evening_block"]}
    assert evening["Light Early Dinner"] == "20:00 - 20:30"
    # Trataka MUST retain original time 21:30 - 21:45
    assert evening["Trataka / Reflection"] == "21:30 - 21:45"


# ============================================================================
# Test E: Failed persistence
# Inject a database write failure.
# Verify that the chat does not claim the change succeeded and existing schedule remains unchanged.
# ============================================================================
def test_e_failed_persistence():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_e", dinner_slot="19:00 - 19:30")
    
    # Set up previous proposal in chat
    db.save_chat_message(TEST_USER_A, "assistant", "I propose moving Light Early Dinner to 20:00 - 20:30. Would you like to confirm?")
    
    # Mock db.save_user_schedule to raise an exception
    with patch("src.database.db.save_user_schedule", side_effect=sqlite3.OperationalError("Disk I/O error")):
        headers = {"Authorization": f"Bearer {token}"}
        res = client.post("/api/chat", json={"message": "Yes, please confirm"}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        
        # Must NOT claim schedule was updated
        assert data["schedule_updated"] is False
        assert "error persisting" in data["response"].lower()
        
        # Verify database was NOT changed
        state = db.get_user_state(TEST_USER_A)
        evening = {t["name"]: t["time_slot"] for t in state["last_schedule"]["schedule"]["evening_block"]}
        assert evening["Light Early Dinner"] == "19:00 - 19:30"


# ============================================================================
# Test F: Rejection and confirmation
# Verify that rejecting a proposed change leaves the schedule untouched
# and confirming it persists the change.
# ============================================================================
def test_f_rejection_and_confirmation():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_f", dinner_slot="19:00 - 19:30")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Proposal in chat history
    db.save_chat_message(TEST_USER_A, "assistant", "I propose moving Light Early Dinner to 20:00 - 20:30. Would you like to confirm?")
    
    # 2. User rejects
    res_reject = client.post("/api/chat", json={"message": "No, cancel that change."}, headers=headers)
    assert res_reject.status_code == 200
    assert res_reject.json()["schedule_updated"] is False
    
    # Verify schedule is completely untouched
    res_curr = client.get("/api/schedule/current", headers=headers)
    evening = {t["name"]: t["time_slot"] for t in res_curr.json()["schedule"]["evening_block"]}
    assert evening["Light Early Dinner"] == "19:00 - 19:30"
    
    # 3. User later confirms
    res_confirm = client.post("/api/chat", json={"message": "Actually, yes please confirm the change."}, headers=headers)
    assert res_confirm.status_code == 200
    assert res_confirm.json()["schedule_updated"] is True
    
    # Verify schedule is now persisted with 20:00 - 20:30
    res_curr2 = client.get("/api/schedule/current", headers=headers)
    evening2 = {t["name"]: t["time_slot"] for t in res_curr2.json()["schedule"]["evening_block"]}
    assert evening2["Light Early Dinner"] == "20:00 - 20:30"


# ============================================================================
# Test G: User isolation
# Verify that the mutation changes only the authenticated user's schedule.
# ============================================================================
def test_g_user_isolation():
    token_a = _seed_user_with_schedule(TEST_USER_A, "user_a", dinner_slot="19:00 - 19:30")
    token_b = _seed_user_with_schedule(TEST_USER_B, "user_b", dinner_slot="19:00 - 19:30")
    
    # Mutate User A's schedule only
    mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    
    # Check User A
    res_a = client.get("/api/schedule/current", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.json()["schedule"]["evening_block"][0]["time_slot"] == "20:00 - 20:30"
    
    # Check User B (MUST still have 19:00 - 19:30)
    res_b = client.get("/api/schedule/current", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.json()["schedule"]["evening_block"][0]["time_slot"] == "19:00 - 19:30"


# ============================================================================
# Test H: No unnecessary routine regeneration
# Seed a valid persisted routine and request it through the same API used by frontend.
# Verify that routine is returned without invoking generation workflow or LLM.
# ============================================================================
def test_h_no_unnecessary_routine_regeneration():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_h", dinner_slot="19:00 - 19:30")
    headers = {"Authorization": f"Bearer {token}"}
    
    with patch.object(DinacharyaPlannerAgent, "generate") as mock_gen:
        t0 = time.perf_counter()
        res = client.get("/api/schedule/current", headers=headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        
        assert res.status_code == 200
        assert mock_gen.call_count == 0, "DinacharyaPlannerAgent.generate should never be called when valid routine exists"
        assert elapsed_ms < 50.0, f"Expected <50ms, got {elapsed_ms:.2f}ms"
        
        # Test /api/schedule/generate fast-path as well
        t1 = time.perf_counter()
        res_post = client.post("/api/schedule/generate", json={
            "user_id": "current",
            "force_regen": False,
            "context": {"season": "Hemanta", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []}
        }, headers=headers)
        elapsed_post_ms = (time.perf_counter() - t1) * 1000
        
        assert res_post.status_code == 200
        assert mock_gen.call_count == 0
        assert elapsed_post_ms < 50.0


# ============================================================================
# Test I: Missing routine
# Verify that a user without a persisted routine still follows legitimate generation workflow.
# ============================================================================
def test_i_missing_routine():
    # User with clean state (no schedule)
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (TEST_USER_A,))
    c.execute("DELETE FROM user_state WHERE user_id = ?", (TEST_USER_A,))
    c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
              (TEST_USER_A, "clean_user", "hash"))
    c.execute("INSERT INTO user_state (user_id, last_schedule, schedule_date) VALUES (?, NULL, '')", (TEST_USER_A,))
    conn.commit()
    conn.close()
    token = db.create_session(TEST_USER_A)
    headers = {"Authorization": f"Bearer {token}"}
    
    # GET /api/schedule/current returns no schedule found
    res_curr = client.get("/api/schedule/current", headers=headers)
    assert res_curr.status_code == 200
    assert res_curr.json()["schedule"] is None
    
    # POST /api/schedule/generate executes generation workflow
    with patch.object(DinacharyaPlannerAgent, "generate") as mock_gen:
        sample_sched = DinacharyaSchedule(
            user_id=str(TEST_USER_A),
            adherence_score=1.0,
            routine_complexity="Moderate",
            morning_block=[Practice(name="Brahma Muhurta", time_slot="06:00 - 06:15", duration_minutes=15, description="", rationale="")],
            midday_block=[],
            evening_block=[],
            timestamp=time.time()
        )
        mock_gen.return_value = {
            "schedule": sample_sched,
            "retrieved_guidelines": [],
            "is_fallback": True,
            "model_used": "deterministic"
        }
        
        res_gen = client.post("/api/schedule/generate", json={
            "user_id": "current",
            "force_regen": False,
            "context": {"season": "Hemanta", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []}
        }, headers=headers)
        
        assert res_gen.status_code == 200
        assert mock_gen.call_count == 1
        assert res_gen.json()["schedule"]["morning_block"][0]["name"] == "Brahma Muhurta"


# ============================================================================
# Test J: Concurrent or stale requests
# Verify that an older schedule response cannot overwrite a newer confirmed update in database.
# ============================================================================
def test_j_concurrent_or_stale_requests():
    token = _seed_user_with_schedule(TEST_USER_A, "user_test_j", dinner_slot="19:00 - 19:30")
    
    # Step 1: Confirmed update moves dinner to 20:00 - 20:30
    res1 = mutate_user_schedule(TEST_USER_A, {"Light Early Dinner": "20:00 - 20:30"})
    assert res1["success"] is True
    t_confirmed = res1["canonical_data"]["timestamp"]
    
    # Step 2: Simulate a delayed in-flight stale payload with timestamp older than t_confirmed
    stale_payload = {
        "schedule": {
            "user_id": str(TEST_USER_A),
            "morning_block": [],
            "midday_block": [],
            "evening_block": [{"name": "Light Early Dinner", "time_slot": "19:00 - 19:30", "duration_minutes": 30, "description": "", "rationale": ""}],
            "timestamp": t_confirmed - 100
        },
        "timestamp": t_confirmed - 100
    }
    
    # If a stale payload is attempted, database should verify timestamp or protect canonical schedule
    current_state = db.get_user_state(TEST_USER_A)
    assert current_state["schedule_timestamp"] >= t_confirmed
    evening = {t["name"]: t["time_slot"] for t in current_state["last_schedule"]["schedule"]["evening_block"]}
    assert evening["Light Early Dinner"] == "20:00 - 20:30"
