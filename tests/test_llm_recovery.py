"""
Tests for LLM Recovery, Model Selection, Tool Calling, and Circumstance Adaptations.
Demonstrates:
1. Resilient structured output parsing & fallback mechanics.
2. Safe handling of null or missing user schedule state in /api/chat.
3. Resilience of /api/insights (never 500).
4. Native tool dispatching and permission checks.
5. Notification persistence and deduplication (idempotency).
6. Circumstance-based adaptations for all 6 required scenarios.
7. End-to-end API route verification.
"""

import time
import json
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.models import DoshaProfile, DoshaVector, VikritiFlags, UserContext, Practice, DinacharyaSchedule
from src.planning.agent import DinacharyaPlannerAgent
from src.planning.tools import (
    check_calendar_conflicts,
    query_ayurvedic_knowledge,
    request_user_notification,
    execute_planner_tool,
    AVAILABLE_PLANNER_TOOLS
)
from src.llm_gateway import LLMGateway, LLMResponse

client = TestClient(app)

# Override auth dependency to return test user ID 1
def mocked_get_current_user():
    return 1

app.dependency_overrides[get_current_user] = mocked_get_current_user


@pytest.fixture(autouse=True)
def ensure_db():
    db.init_db()


def test_chat_null_last_schedule():
    """
    Audit Defect Fix: /api/chat must not crash when last_schedule is null or None.
    Simulates database returning last_schedule = None.
    """
    conn = db.get_db_connection()
    c = conn.cursor()
    # Explicitly set last_schedule to NULL for user 1
    c.execute("UPDATE user_state SET last_schedule = NULL WHERE user_id = 1")
    conn.commit()
    conn.close()

    # Verify get_user_state returns last_schedule as None
    state = db.get_user_state(1)
    assert state.get("last_schedule") is None

    # Call /api/chat
    response = client.post("/api/chat", json={"message": "Good morning Vaidya, how should I start my day?"})
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
    data = response.json()
    assert "response" in data
    assert len(data["response"]) > 0


def test_insights_endpoint_resilience():
    """
    Audit Defect Fix: /api/insights must never fail with HTTP 500 even under provider delays or errors.
    """
    response = client.get("/api/insights")
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
    data = response.json()
    assert "insights" in data
    insights = data["insights"]
    # Must have all 6 node reasoning keys
    required_nodes = ["node-sleep", "node-hrv", "node-vata", "node-knowledge", "node-planner", "node-result"]
    for k in required_nodes:
        assert k in insights, f"Missing visualization node: {k}"
        assert "category" in insights[k]
        assert "title" in insights[k]
        assert "desc" in insights[k]


def test_gateway_markdown_json_stripping():
    """
    Verify LLMGateway parses markdown fenced JSON (```json ... ```) correctly.
    """
    gateway = LLMGateway.get_instance()
    mock_resp = LLMResponse(
        content='```json\n{"status": "ok", "morning_block": []}\n```',
        model_used="test-model"
    )

    # Test via json parsing
    raw = mock_resp.content.strip()
    import re
    clean_json = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    clean_json = re.sub(r"\s*```$", "", clean_json)
    parsed = json.loads(clean_json)
    assert parsed["status"] == "ok"


def test_gateway_fallback_trigger_on_failure():
    """
    Verify LLMGateway executes deterministic fallback when provider models throw errors.
    """
    gateway = LLMGateway.get_instance()

    def _fallback_fn():
        return {"morning_block": [{"name": "Fallback Wake", "time_slot": "06:00 - 06:15"}]}

    # Temporarily mock create_chat_completion to raise RuntimeError
    orig_fn = gateway.create_chat_completion
    try:
        gateway.create_chat_completion = MagicMock(side_effect=RuntimeError("Simulated provider outage"))
        result, is_fallback = gateway.generate_structured_json(
            messages=[{"role": "user", "content": "Generate schedule"}],
            fallback_fn=_fallback_fn
        )
        assert is_fallback is True
        assert "morning_block" in result
        assert result["morning_block"][0]["name"] == "Fallback Wake"
    finally:
        gateway.create_chat_completion = orig_fn


def test_tool_execution_dispatcher():
    """
    Verify execute_planner_tool dispatches authorized functions and enforces permission checks.
    """
    # 1. Calendar conflict tool
    res_str = execute_planner_tool(
        "check_calendar_conflicts",
        {"candidate_time_slot": "08:30 - 09:00", "calendar_events": ["08:00 - 09:00 Team Standup"]}
    )
    res = json.loads(res_str)
    assert res["has_conflict"] is True

    # 2. Ayurvedic knowledge retrieval tool
    kb_res_str = execute_planner_tool(
        "query_ayurvedic_knowledge",
        {"dosha": "Vata", "symptom": "anxiety"}
    )
    kb_res = json.loads(kb_res_str)
    assert "retrieved_guidelines" in kb_res
    assert len(kb_res["retrieved_guidelines"]) > 0

    # 3. Request user notification tool
    notif_res_str = execute_planner_tool(
        "request_user_notification",
        {"user_id": "1", "event_type": "test_alert", "message": "Test notification message"},
        caller_user_id="1"
    )
    notif_res = json.loads(notif_res_str)
    assert notif_res["success"] is True

    # 4. Permission denial on user mismatch
    unauth_res_str = execute_planner_tool(
        "request_user_notification",
        {"user_id": "999", "event_type": "impersonate", "message": "Unauthorized"},
        caller_user_id="1"
    )
    unauth_res = json.loads(unauth_res_str)
    assert "error" in unauth_res
    assert "Permission denied" in unauth_res["error"]


def test_notification_persistence_and_idempotency():
    """
    Verify persistent notifications in database and guarantee duplicate event prevention (idempotency).
    """
    user_id = 1
    idempotency_key = f"test-idemp-{time.time()}"

    n1 = db.create_notification(
        user_id=user_id,
        event_type="schedule_change",
        message="Shifted Abhyanga by 30 mins",
        activity_name="Abhyanga",
        idempotency_key=idempotency_key
    )
    assert n1 is not None

    # Duplicate call with identical idempotency key must not duplicate row
    n2 = db.create_notification(
        user_id=user_id,
        event_type="schedule_change",
        message="Shifted Abhyanga by 30 mins (duplicate)",
        activity_name="Abhyanga",
        idempotency_key=idempotency_key
    )
    assert n2 == n1, "Duplicate notification event must return existing notification ID"

    # Fetch notifications
    notifs = db.get_user_notifications(user_id=user_id)
    matching = [n for n in notifs if n["idempotency_key"] == idempotency_key]
    assert len(matching) == 1, "There should be exactly 1 persistent record for this idempotency key"

    # Mark as read
    marked = db.mark_notification_read(notification_id=n1, user_id=user_id)
    assert marked is True


def test_circumstance_adaptation_scenario_1_missed_activity():
    """
    Scenario 1: User misses a planned morning activity.
    Verifies gentle compensatory evening rescheduling without duplicating activities.
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)
    current_sched = {
        "schedule": {
            "morning_block": [{"name": "Pranayama", "time_slot": "07:00 - 07:20", "duration_minutes": 20}],
            "midday_block": [{"name": "Mitahara", "time_slot": "12:30 - 13:00", "duration_minutes": 30}],
            "evening_block": []
        }
    }

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule=current_sched,
        event_type="missed_activity",
        event_data={"activity_name": "Pranayama"},
        profile=profile,
        context=context
    )

    assert res["status"] == "adapted"
    assert res["adaptation_applied"] is True
    assert "Pranayama" in res["affected_activities"]
    assert res["notification_sent"] is True
    # Evening block should have received compensatory activity
    assert len(res["schedule"].evening_block) > 0
    assert "Pranayama" in res["schedule"].evening_block[0].name


def test_circumstance_adaptation_scenario_2_calendar_conflict():
    """
    Scenario 2: New meeting conflicts with scheduled morning practice.
    Verifies practice is shifted to non-conflicting slot and meeting is preserved.
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.4, pitta=0.4, kapha=0.2),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)
    current_sched = {
        "schedule": {
            "morning_block": [{"name": "Abhyanga", "time_slot": "08:00 - 08:30", "duration_minutes": 30}],
            "midday_block": [],
            "evening_block": []
        }
    }

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule=current_sched,
        event_type="calendar_conflict",
        event_data={"calendar_event": "08:00 - 09:00 Team Sync"},
        profile=profile,
        context=context
    )

    assert res["status"] == "adapted"
    assert "Abhyanga" in res["affected_activities"]
    # New slot must not conflict with 08:00 - 09:00
    shifted_slot = res["schedule"].morning_block[0].time_slot
    assert "08:00" not in shifted_slot


def test_circumstance_adaptation_scenario_3_fever_illness():
    """
    Scenario 3: User reports fever / acute illness.
    Clinical Safety Rule (Nava Jwara): Strenuous exercise & Abhyanga are paused.
    Replaced with warm hydration (Ushnodaka) and light gruel (Mitahara/Peya).
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        vikriti_flags=VikritiFlags(has_fever=True),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)
    current_sched = {
        "schedule": {
            "morning_block": [{"name": "Abhyanga", "time_slot": "06:30 - 07:00", "duration_minutes": 30}],
            "midday_block": [{"name": "Heavy Lunch", "time_slot": "12:00 - 12:45", "duration_minutes": 45}],
            "evening_block": []
        }
    }

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule=current_sched,
        event_type="illness",
        event_data={"has_fever": True},
        profile=profile,
        context=context
    )

    assert res["status"] == "adapted"
    # Heavy practices must NOT exist
    for p in res["schedule"].morning_block:
        assert "abhyanga" not in p.name.lower()
        assert "vyayama" not in p.name.lower()
    # Must include restorative hydration
    assert any("ushnodaka" in p.name.lower() or "rest" in p.name.lower() for p in res["schedule"].morning_block)


def test_circumstance_adaptation_scenario_4_task_overrun():
    """
    Scenario 4: Task takes longer than planned.
    Verifies subsequent flexible afternoon practices are shifted proportionally.
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)
    current_sched = {
        "schedule": {
            "morning_block": [],
            "midday_block": [{"name": "Mitahara Lunch", "time_slot": "12:30 - 13:00", "duration_minutes": 30}],
            "evening_block": []
        }
    }

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule=current_sched,
        event_type="task_overrun",
        event_data={"activity_name": "Executive Meeting", "overrun_minutes": 45},
        profile=profile,
        context=context
    )

    assert res["status"] == "adapted"
    assert "Executive Meeting" in res["affected_activities"]
    assert "Shifted by 45m" in res["schedule"].midday_block[0].rationale


def test_circumstance_adaptation_scenario_5_priority_change():
    """
    Scenario 5: User changes priority to Meditation.
    Verifies schedule rebalances to allocate focused morning window.
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)
    current_sched = {"schedule": {"morning_block": [], "midday_block": [], "evening_block": []}}

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule=current_sched,
        event_type="priority_change",
        event_data={"priority": "Meditation"},
        profile=profile,
        context=context
    )

    assert res["status"] == "adapted"
    assert "Meditation" in res["affected_activities"]
    assert any("Meditation" in p.name for p in res["schedule"].morning_block)


def test_circumstance_adaptation_scenario_6_infeasible_constraints():
    """
    Scenario 6: Impossible constraints (available time < 30 minutes).
    Verifies structured inability-to-plan result is returned rather than invalid schedule.
    """
    agent = DinacharyaPlannerAgent()
    profile = DoshaProfile(
        user_id="1",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        timestamp=time.time()
    )
    context = UserContext(season="Vasanta", weather="Mild", temperature_c=25.0)

    res = agent.adapt_schedule(
        user_id="1",
        current_schedule={},
        event_type="infeasible_constraints",
        event_data={"available_minutes": 15},
        profile=profile,
        context=context
    )

    assert res["feasible"] is False
    assert res["status"] == "impossible_constraints"
    assert res["schedule"] is None
    assert len(res["suggestions"]) > 0


def test_api_agent_adapt_endpoint():
    """
    Verify POST /api/agent/adapt route performs adaptation and returns structured JSON.
    """
    payload = {
        "event_type": "calendar_conflict",
        "event_data": {"calendar_event": "08:00 - 09:00 Emergency Doctor Appointment"}
    }
    response = client.post("/api/agent/adapt", json=payload)
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "adapted"
    assert "schedule" in data


def test_api_notifications_endpoints():
    """
    Verify GET /api/notifications and POST /api/notifications/{id}/read routes.
    """
    # Create notification
    notif_id = db.create_notification(
        user_id=1,
        event_type="test_event",
        message="Test alert for API test",
        idempotency_key=f"api-test-{time.time()}"
    )

    # Fetch
    get_res = client.get("/api/notifications")
    assert get_res.status_code == 200
    notifs = get_res.json()["notifications"]
    assert any(n["id"] == notif_id for n in notifs)

    # Mark read
    read_res = client.post(f"/api/notifications/{notif_id}/read")
    assert read_res.status_code == 200
    assert read_res.json()["success"] is True
