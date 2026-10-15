import time
import json
import sqlite3
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app, get_current_user
from src.database import db
from src.models import (
    DinacharyaSchedule,
    Practice,
    DoshaProfile,
    DoshaVector,
    UserContext,
)
from src.planning.agent import DinacharyaPlannerAgent, standardize_slot

client = TestClient(app)

TEST_USER_ID = 9999


@pytest.fixture(autouse=True)
def setup_teardown_test_user():
    """Ensure a clean test user state in SQLite before and after each test."""
    orig_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID

    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (TEST_USER_ID,))
    c.execute("DELETE FROM user_state WHERE user_id = ?", (TEST_USER_ID,))
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (TEST_USER_ID,))
    
    # Create test user
    c.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
        (TEST_USER_ID, "test_routine_user", "hashed_pw")
    )
    c.execute(
        """INSERT INTO user_state (
            user_id, questionnaire_responses, telemetry_baselines, 
            current_vikriti, adherence_score, has_completed_onboarding, 
            last_schedule, schedule_timestamp, schedule_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            TEST_USER_ID,
            json.dumps({"sleep": "moderate", "energy": "variable"}),
            json.dumps({}),
            json.dumps({"telemetry": {}, "symptoms": []}),
            1.0,
            True,
            None,
            0.0,
            ""
        )
    )
    conn.commit()
    conn.close()
    
    yield
    
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (TEST_USER_ID,))
    c.execute("DELETE FROM user_state WHERE user_id = ?", (TEST_USER_ID,))
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (TEST_USER_ID,))
    conn.commit()
    conn.close()

    if orig_override is not None:
        app.dependency_overrides[get_current_user] = orig_override
    else:
        app.dependency_overrides.pop(get_current_user, None)


def _create_sample_schedule(trataka_slot="21:30 - 21:45"):
    """Helper to generate a canonical DinacharyaSchedule for testing."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    return {
        "schedule": {
            "user_id": str(TEST_USER_ID),
            "adherence_score": 1.0,
            "routine_complexity": "Moderate",
            "morning_block": [
                {
                    "name": "Brahma Muhurta Jagaran",
                    "time_slot": "06:00 - 06:15",
                    "duration_minutes": 15,
                    "description": "Awaken in Sattvic dawn window.",
                    "rationale": "Balances Vata dosha."
                },
                {
                    "name": "Ushapan (Warm Water)",
                    "time_slot": "06:15 - 06:30",
                    "duration_minutes": 15,
                    "description": "Drink warm water.",
                    "rationale": "Stimulates peristalsis."
                }
            ],
            "midday_block": [
                {
                    "name": "Mitahara Midday Meal",
                    "time_slot": "12:30 - 13:00",
                    "duration_minutes": 30,
                    "description": "Warm, wholesome midday meal.",
                    "rationale": "Peak Agni digestion."
                }
            ],
            "evening_block": [
                {
                    "name": "Trataka / Reflection",
                    "time_slot": trataka_slot,
                    "duration_minutes": 15,
                    "description": "Candle flame meditation and quiet reflection.",
                    "rationale": "Settles optic nerve and calms Pitta-Vata before sleep."
                }
            ],
            "timestamp": time.time()
        },
        "dosha_profile": {
            "user_id": str(TEST_USER_ID),
            "prakriti": {"vata": 0.5, "pitta": 0.3, "kapha": 0.2},
            "vikriti_flags": {"vata_aggravated": False, "pitta_aggravated": False, "kapha_aggravated": False, "has_fever": False},
            "timestamp": time.time()
        },
        "complexity_level": "Moderate",
        "timestamp": time.time()
    }


# ============================================================================
# Scenario 1: Persisted routine loads without unnecessary schedule regeneration
# ============================================================================
def test_1_persisted_routine_loads_without_regeneration():
    """Verify that a user with an existing valid routine for today gets it loaded instantly (<50ms) with 0 LLM calls."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    sample_sched = _create_sample_schedule()
    db.save_user_schedule(TEST_USER_ID, sample_sched, today_date)

    with patch.object(DinacharyaPlannerAgent, "generate") as mock_generate:
        t0 = time.perf_counter()
        # Direct current schedule retrieval
        res_current = client.get("/api/schedule/current")
        t_current = (time.perf_counter() - t0) * 1000

        assert res_current.status_code == 200
        current_data = res_current.json()
        assert current_data["schedule"]["morning_block"][0]["name"] == "Brahma Muhurta Jagaran"
        assert t_current < 50.0, f"Expected <50ms DB lookup, got {t_current:.2f}ms"

        # POST /api/schedule/generate without force_regen
        t1 = time.perf_counter()
        res_gen = client.post("/api/schedule/generate", json={
            "user_id": str(TEST_USER_ID),
            "force_regen": False,
            "context": {"season": "Hemanta", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []}
        })
        t_gen = (time.perf_counter() - t1) * 1000

        assert res_gen.status_code == 200
        gen_data = res_gen.json()
        assert gen_data["schedule"]["morning_block"][0]["name"] == "Brahma Muhurta Jagaran"
        assert t_gen < 50.0, f"Expected <50ms cache return, got {t_gen:.2f}ms"

        # Planner generate must NEVER have been called
        assert mock_generate.call_count == 0


# ============================================================================
# Scenario 2: Genuinely missing routine follows the existing generation workflow
# ============================================================================
def test_2_missing_routine_follows_generation_workflow():
    """Verify that when no routine exists for today, the generation workflow creates and persists a new one."""
    state = db.get_user_state(TEST_USER_ID)
    assert state.get("last_schedule") is None

    # Call generate on clean user
    res = client.post("/api/schedule/generate", json={
        "user_id": str(TEST_USER_ID),
        "force_regen": False,
        "context": {"season": "Hemanta", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []}
    })
    assert res.status_code == 200
    data = res.json()
    assert "schedule" in data
    assert len(data["schedule"]["morning_block"]) > 0

    # Verify saved in persistent storage
    today_date = datetime.now().strftime("%Y-%m-%d")
    updated_state = db.get_user_state(TEST_USER_ID)
    assert updated_state["schedule_date"] == today_date
    assert updated_state["last_schedule"] is not None


# ============================================================================
# Scenario 3: Accepting a Trataka/Reflection change to 10:15–10:30 PM persists the update
# ============================================================================
def test_3_accepting_trataka_schedule_change_persists():
    """Verify that accepting moving Trataka to 10:15–10:30 PM persists to canonical SQLite."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    sample_sched = _create_sample_schedule(trataka_slot="21:30 - 21:45")
    db.save_user_schedule(TEST_USER_ID, sample_sched, today_date)

    # 1. Test via /api/schedule/confirm
    proposed = json.loads(json.dumps(sample_sched["schedule"]))
    for p in proposed["evening_block"]:
        if "trataka" in p["name"].lower():
            p["time_slot"] = "22:15 - 22:30"

    res = client.post("/api/schedule/confirm", json={"schedule": proposed})
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify in DB
    state = db.get_user_state(TEST_USER_ID)
    saved_evening = state["last_schedule"]["schedule"]["evening_block"]
    trataka = next(p for p in saved_evening if "trataka" in p["name"].lower())
    assert trataka["time_slot"] == "22:15 - 22:30"


# ============================================================================
# Scenario 4: The Routine API returns the new time after the update
# ============================================================================
def test_4_routine_api_returns_new_time_after_update():
    """Verify that subsequent Routine API requests return 22:15 - 22:30 after the update."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    updated_sched = _create_sample_schedule(trataka_slot="22:15 - 22:30")
    db.save_user_schedule(TEST_USER_ID, updated_sched, today_date)

    # GET /api/schedule/current
    res_curr = client.get("/api/schedule/current")
    assert res_curr.status_code == 200
    evening = res_curr.json()["schedule"]["evening_block"]
    trataka = next(p for p in evening if "trataka" in p["name"].lower())
    assert trataka["time_slot"] == "22:15 - 22:30"

    # POST /api/schedule/generate without force_regen
    res_gen = client.post("/api/schedule/generate", json={
        "user_id": str(TEST_USER_ID),
        "force_regen": False,
        "context": {"season": "Hemanta", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []}
    })
    assert res_gen.status_code == 200
    evening_gen = res_gen.json()["schedule"]["evening_block"]
    trataka_gen = next(p for p in evening_gen if "trataka" in p["name"].lower())
    assert trataka_gen["time_slot"] == "22:15 - 22:30"


# ============================================================================
# Scenario 5: Refreshing /routine continues to show the new time
# ============================================================================
def test_5_refreshing_routine_continues_to_show_new_time():
    """Verify that simulating a page refresh (fresh DB query without in-memory state) retains 22:15 - 22:30."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    updated_sched = _create_sample_schedule(trataka_slot="22:15 - 22:30")
    db.save_user_schedule(TEST_USER_ID, updated_sched, today_date)

    # Simulate fresh connection / page refresh
    fresh_state = db.get_user_state(TEST_USER_ID)
    evening = fresh_state["last_schedule"]["schedule"]["evening_block"]
    trataka = next(p for p in evening if "trataka" in p["name"].lower())
    assert trataka["time_slot"] == "22:15 - 22:30"


# ============================================================================
# Scenario 6: A failed database write does not produce a success confirmation
# ============================================================================
def test_6_failed_database_write_does_not_produce_success():
    """Verify that if database write fails, the API returns an error and never claims the schedule was updated."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    sample_sched = _create_sample_schedule()
    db.save_user_schedule(TEST_USER_ID, sample_sched, today_date)

    proposed = sample_sched["schedule"]

    with patch.object(db, "save_user_schedule", side_effect=sqlite3.OperationalError("database is locked")):
        # Confirm endpoint should return 500
        res = client.post("/api/schedule/confirm", json={"schedule": proposed})
        assert res.status_code == 500
        assert "Failed to persist" in res.json()["detail"]

        # Chat acceptance should return explicit failure notification
        db.save_chat_message(TEST_USER_ID, "assistant", "I will move Trataka / Reflection to 10:15 - 10:30 PM.")
        chat_res = client.post("/api/chat", json={"message": "I accept the proposed change"})
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["schedule_updated"] is False
        assert "error persisting" in data["response"].lower()
        assert "synchronized" not in data["response"].lower()


# ============================================================================
# Scenario 7: A failed LLM call does not leave the Routine page loading indefinitely
# ============================================================================
def test_7_failed_llm_call_does_not_hang():
    """Verify that when LLM generation fails or times out, the planner returns deterministic fallback within deadline."""
    planner = DinacharyaPlannerAgent()
    # Force OpenAI client error
    planner.openai_client.api_key = "invalid_key_for_timeout_test"

    profile = DoshaProfile(
        user_id=str(TEST_USER_ID),
        prakriti=DoshaVector(vata=0.6, pitta=0.2, kapha=0.2),
        timestamp=time.time()
    )
    context = UserContext(season="Winter", weather="Cold", temperature_c=10.0, calendar_events=[], self_report_symptoms=[])

    t0 = time.time()
    result = planner.generate(
        user_id=str(TEST_USER_ID),
        profile=profile,
        context=context,
        adherence_score=0.9,
        complexity="Moderate"
    )
    duration = time.time() - t0

    assert duration < 10.0, "Planner fallback took too long"
    assert result["schedule"] is not None
    assert len(result["schedule"].morning_block) > 0


# ============================================================================
# Scenario 8: A repeated schedule-change request does not duplicate the activity
# ============================================================================
def test_8_repeated_schedule_change_no_duplicates():
    """Verify that confirming or accepting the same schedule change repeatedly does not duplicate tasks."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    sample_sched = _create_sample_schedule(trataka_slot="21:30 - 21:45")
    db.save_user_schedule(TEST_USER_ID, sample_sched, today_date)

    proposed = json.loads(json.dumps(sample_sched["schedule"]))
    for p in proposed["evening_block"]:
        if "trataka" in p["name"].lower():
            p["time_slot"] = "22:15 - 22:30"

    # Confirm three times
    for _ in range(3):
        res = client.post("/api/schedule/confirm", json={"schedule": proposed})
        assert res.status_code == 200

    state = db.get_user_state(TEST_USER_ID)
    evening = state["last_schedule"]["schedule"]["evening_block"]
    trataka_count = sum(1 for p in evening if "trataka" in p["name"].lower())
    assert trataka_count == 1, f"Expected exactly 1 Trataka activity, found {trataka_count}"


# ============================================================================
# Scenario 9: The update preserves unrelated activities and fixed commitments
# ============================================================================
def test_9_update_preserves_unrelated_activities():
    """Verify that moving Trataka leaves morning and midday activities intact."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    sample_sched = _create_sample_schedule(trataka_slot="21:30 - 21:45")
    db.save_user_schedule(TEST_USER_ID, sample_sched, today_date)

    proposed = json.loads(json.dumps(sample_sched["schedule"]))
    for p in proposed["evening_block"]:
        if "trataka" in p["name"].lower():
            p["time_slot"] = "22:15 - 22:30"

    res = client.post("/api/schedule/confirm", json={"schedule": proposed})
    assert res.status_code == 200

    state = db.get_user_state(TEST_USER_ID)
    saved = state["last_schedule"]["schedule"]

    # Morning block must remain identical
    assert len(saved["morning_block"]) == 2
    assert saved["morning_block"][0]["name"] == "Brahma Muhurta Jagaran"
    assert saved["morning_block"][0]["time_slot"] == "06:00 - 06:15"
    assert saved["morning_block"][1]["name"] == "Ushapan (Warm Water)"
    assert saved["morning_block"][1]["time_slot"] == "06:15 - 06:30"

    # Midday block must remain identical
    assert len(saved["midday_block"]) == 1
    assert saved["midday_block"][0]["name"] == "Mitahara Midday Meal"
    assert saved["midday_block"][0]["time_slot"] == "12:30 - 13:00"


# ============================================================================
# Scenario 10: Missing or nullable schedule state is handled safely
# ============================================================================
def test_10_missing_or_nullable_schedule_state_handled_safely():
    """Verify that NoneType or empty last_schedule does not crash the endpoints."""
    # Ensure user has None last_schedule
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE user_state SET last_schedule = NULL, schedule_date = '' WHERE user_id = ?", (TEST_USER_ID,))
    conn.commit()
    conn.close()

    # GET /api/schedule/current
    res_curr = client.get("/api/schedule/current")
    assert res_curr.status_code == 200
    assert res_curr.json()["schedule"] is None

    # POST /api/chat with null schedule in state
    with patch("src.llm_gateway.LLMGateway.create_chat_completion") as mock_chat:
        mock_response = MagicMock()
        mock_response.content = "Namaste! Your routine looks good."
        mock_chat.return_value = mock_response

        res_chat = client.post("/api/chat", json={"message": "Can I check my routine?"})
        assert res_chat.status_code == 200
        assert "response" in res_chat.json()
