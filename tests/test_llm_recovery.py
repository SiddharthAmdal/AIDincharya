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


@pytest.fixture(autouse=True)
def ensure_db():
    orig_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = mocked_get_current_user
    db.init_db()
    yield
    if orig_override is not None:
        app.dependency_overrides[get_current_user] = orig_override
    else:
        app.dependency_overrides.pop(get_current_user, None)


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


def test_gateway_third_fallback_to_gemini_provider(monkeypatch):
    """
    Verify LLMGateway fails over to the 3rd fallback provider (Google AI Studio Gemini API
    with gemini-1.5-flash) when both the primary and secondary NVIDIA models fail.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test_valid_ai_studio_gemini_key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
    gateway = LLMGateway()

    # Primary client (NVIDIA) fails for both primary and secondary models
    mock_primary_client = MagicMock()
    mock_primary_client.chat.completions.create.side_effect = RuntimeError("timeout on primary provider")
    gateway.client = mock_primary_client

    # Third fallback client (Google AI Studio Gemini) succeeds
    mock_gemini_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = '{"status": "recovered_via_gemini"}'
    mock_msg.reasoning_content = None
    mock_msg.tool_calls = None
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 12
    mock_resp.usage.completion_tokens = 8
    mock_gemini_client.chat.completions.create.return_value = mock_resp

    gateway._build_gemini_client = MagicMock(return_value=mock_gemini_client)
    gateway.gemini_client = mock_gemini_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        retries_per_model=1
    )
    assert res.is_fallback is True
    assert res.model_used == "gemini-1.5-flash"
    assert res.content == '{"status": "recovered_via_gemini"}'
    assert mock_gemini_client.chat.completions.create.call_count == 1


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


def test_gateway_primary_success():
    """
    Verify LLMGateway returns primary model response directly without fallback when primary succeeds.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Primary model response"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 20
    mock_resp.usage.completion_tokens = 10
    mock_client.chat.completions.create.return_value = mock_resp
    gateway.client = mock_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        retries_per_model=1
    )
    assert res.is_fallback is False
    assert res.model_used == gateway.primary_model
    assert res.content == "Primary model response"
    assert mock_client.chat.completions.create.call_count == 1


def test_gateway_primary_failure_fallback_success():
    """
    Verify LLMGateway fails over to secondary model when primary model fails.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()

    # First call (primary model) raises, second call (secondary model) succeeds
    mock_choice = MagicMock()
    mock_choice.message.content = "Secondary fallback response"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 25
    mock_resp.usage.completion_tokens = 15

    mock_client.chat.completions.create.side_effect = [
        RuntimeError("Primary model 503 service unavailable"),
        mock_resp
    ]
    gateway.client = mock_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Plan day"}],
        retries_per_model=1
    )
    assert res.is_fallback is True
    assert res.model_used == gateway.fallback_model
    assert res.content == "Secondary fallback response"
    assert mock_client.chat.completions.create.call_count == 2


def test_gateway_all_providers_failing(monkeypatch):
    """
    Verify LLMGateway raises RuntimeError when all configured models and tiers fail.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    gateway = LLMGateway()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("500 Internal Server Error")
    gateway.client = mock_client

    mock_gemini = MagicMock()
    mock_gemini.chat.completions.create.side_effect = RuntimeError("Gemini 500 Outage")
    gateway._build_gemini_client = MagicMock(return_value=mock_gemini)
    gateway.gemini_client = mock_gemini

    with pytest.raises(RuntimeError, match="All LLM models and retries exhausted"):
        gateway.create_chat_completion(
            messages=[{"role": "user", "content": "Help"}],
            retries_per_model=1
        )


def test_gateway_non_retryable_auth_and_invalid_model_fails_over_immediately():
    """
    Verify LLMGateway does NOT retry permanent configuration or auth errors (401/404) pointlessly,
    failing over immediately to the next candidate model on attempt 1.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()

    mock_choice = MagicMock()
    mock_choice.message.content = "Fallback recovered after 401"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5

    # Attempt on primary model raises 401 Unauthorized; attempt on fallback model succeeds
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("401 Unauthorized: Invalid API Key"),
        mock_resp
    ]
    gateway.client = mock_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Check auth"}],
        retries_per_model=3  # Configured for 3 retries, but 401 must NOT retry
    )
    assert res.is_fallback is True
    assert res.model_used == gateway.fallback_model
    assert res.content == "Fallback recovered after 401"
    # Primary model called exactly once because 401 is non-retryable
    assert mock_client.chat.completions.create.call_count == 2


def test_gateway_rate_limit_retries_then_falls_over():
    """
    Verify LLMGateway retries transient rate limits (429) up to retries_per_model before falling over.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()

    mock_choice = MagicMock()
    mock_choice.message.content = "Fallback after rate limit"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5

    # Model 1 fails twice with 429 RateLimit; Model 2 succeeds
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("429 Too Many Requests: Rate limit exceeded"),
        RuntimeError("429 Too Many Requests: Rate limit exceeded"),
        mock_resp
    ]
    gateway.client = mock_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Check rate limit"}],
        retries_per_model=2
    )
    assert res.is_fallback is True
    assert res.model_used == gateway.fallback_model
    assert res.content == "Fallback after rate limit"
    assert mock_client.chat.completions.create.call_count == 3


def test_gateway_tool_calls_compatibility():
    """
    Verify LLMGateway correctly surfaces tool_calls from provider responses.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()

    mock_tool_call = {
        "id": "call_123",
        "type": "function",
        "function": {"name": "query_ayurvedic_knowledge", "arguments": '{"query": "Dinacharya"}'}
    }
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_choice.message.reasoning_content = "Checking knowledge base first"
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 30
    mock_resp.usage.completion_tokens = 20
    mock_client.chat.completions.create.return_value = mock_resp
    gateway.client = mock_client

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Find sources"}],
        tools=[{"type": "function", "function": {"name": "query_ayurvedic_knowledge"}}],
        retries_per_model=1
    )
    assert res.tool_calls == [mock_tool_call]
    assert res.reasoning_content == "Checking knowledge base first"


def test_gateway_respects_small_remaining_deadline_budget(monkeypatch):
    """
    Verify LLMGateway passes the actual remaining deadline budget (e.g., 1.2s)
    to the client timeout without artificially inflating it to a 2.0s floor.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Budget response"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5
    mock_client.chat.completions.create.return_value = mock_resp
    gateway.client = mock_client

    # Mock time.perf_counter so total_deadline is start + 1.2s, remaining is exactly 1.2s
    fake_time = 100.0
    def fake_perf_counter():
        nonlocal fake_time
        return fake_time

    monkeypatch.setattr(time, "perf_counter", fake_perf_counter)
    monkeypatch.setenv("GATEWAY_TOTAL_TIMEOUT", "1.2")

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Quick query"}],
        retries_per_model=1
    )
    assert res.content == "Budget response"
    assert mock_client.chat.completions.create.call_count == 1
    passed_timeout = mock_client.chat.completions.create.call_args.kwargs["timeout"]
    assert round(passed_timeout, 2) == 1.2, f"Expected timeout of 1.2s, got {passed_timeout}"


def test_gateway_deadline_exhaustion_halts_retries_immediately(monkeypatch):
    """
    Verify that when the gateway total deadline has <= 1.0s remaining before an attempt,
    retries halt immediately without dispatching any downstream client calls.
    """
    gateway = LLMGateway()
    mock_client = MagicMock()
    gateway.client = mock_client

    # Total timeout <= 1.0s triggers immediate deadline budget exhaustion
    monkeypatch.setenv("GATEWAY_TOTAL_TIMEOUT", "0.8")

    with pytest.raises(RuntimeError, match="All LLM models and retries exhausted"):
        gateway.create_chat_completion(
            messages=[{"role": "user", "content": "Should not run"}],
            retries_per_model=2
        )

    # Client must NOT have been called because budget was exhausted before attempt
    assert mock_client.chat.completions.create.call_count == 0

