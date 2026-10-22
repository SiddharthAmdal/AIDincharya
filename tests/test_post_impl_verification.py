import time
import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.llm_gateway import LLMGateway, LLMResponse
from src.planning.tools import (
    AVAILABLE_PLANNER_TOOLS,
    execute_planner_tool,
    propose_schedule_adaptation,
    get_user_profile,
    get_adherence_history
)
from src.models import DinacharyaSchedule, Practice, DoshaProfile, DoshaVector, VikritiFlags
from src.safety.guardrails import ClinicalRuleEngine

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    """Ensure this module tests real bearer authentication and user isolation."""
    orig = app.dependency_overrides.pop(get_current_user, None)
    yield
    if orig is not None:
        app.dependency_overrides[get_current_user] = orig


# =====================================================================
# 1. TOOL CALLING EDGE CASES & RESILIENCE TESTS
# =====================================================================

def test_tool_dispatcher_unknown_tool():
    """Verify that calling an unknown tool returns an explicit error JSON instead of raising an exception."""
    res_str = execute_planner_tool("non_existent_magic_tool", {"arg1": "val1"}, caller_user_id="1")
    res = json.loads(res_str)
    assert "error" in res
    assert "Unknown tool" in res["error"]


def test_tool_dispatcher_unauthorized_user_access():
    """Verify that caller_user_id 100 cannot access or modify user 200's profile."""
    res_str = execute_planner_tool(
        "get_user_profile",
        {"user_id": "200"},
        caller_user_id="100"
    )
    res = json.loads(res_str)
    assert "error" in res
    assert "Permission denied" in res["error"]


def test_tool_dispatcher_alias_user_id_resolution():
    """Verify that 'current_user', 'me', 'self' aliases cleanly resolve to caller_user_id."""
    u_name = f"alias_test_{uuid.uuid4().hex[:10]}"
    uid = db.create_user(u_name, "password123")
    db.update_adherence_score(uid, 0.85)

    for alias in ["current_user", "me", "self", ""]:
        res_str = execute_planner_tool(
            "get_adherence_history",
            {"user_id": alias},
            caller_user_id=str(uid)
        )
        res = json.loads(res_str)
        assert res["user_id"] == str(uid)
        assert res["adherence_score"] == 0.85


def test_tool_loop_iteration_limit():
    """Verify execute_tool_loop halts strictly after max_steps even if the model continues requesting tools."""
    gateway = LLMGateway()

    # Create a mock tool call object
    mock_func = MagicMock()
    mock_func.name = "get_user_profile"
    mock_func.arguments = json.dumps({"user_id": "1"})

    mock_tc = MagicMock()
    mock_tc.id = "mock_call_inf"
    mock_tc.function = mock_func

    # Mock gateway.create_chat_completion to continuously return a tool call
    step_count = 0
    def mock_create_completion(*args, **kwargs):
        nonlocal step_count
        step_count += 1
        if "tools" in kwargs and kwargs["tools"]:
            # Returns a tool call
            return LLMResponse(content="", tool_calls=[mock_tc], model_used="mock-loop-model")
        else:
            # Final non-tool turn
            return LLMResponse(content="Final graceful termination after max steps", model_used="mock-loop-model")

    with patch.object(gateway, "create_chat_completion", side_effect=mock_create_completion):
        res = gateway.execute_tool_loop(
            messages=[{"role": "user", "content": "Keep looping"}],
            tools=AVAILABLE_PLANNER_TOOLS,
            tool_executor_fn=lambda name, args: json.dumps({"status": "ok"}),
            max_steps=3
        )
        # Must terminate without infinite loop and return final response
        assert res.content == "Final graceful termination after max steps"
        # 3 tool turns + 1 final turn = 4 total invocations
        assert step_count == 4


def test_tool_loop_malformed_arguments_handling():
    """Verify tool loop safely handles unparseable/malformed JSON in tool call arguments."""
    gateway = LLMGateway()

    mock_func = MagicMock()
    mock_func.name = "get_user_profile"
    mock_func.arguments = "NOT_VALID_JSON{:::broken"

    mock_tc = MagicMock()
    mock_tc.id = "mock_call_bad_json"
    mock_tc.function = mock_func

    call_index = 0
    def mock_create_completion(*args, **kwargs):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            return LLMResponse(content="", tool_calls=[mock_tc], model_used="mock-model")
        return LLMResponse(content="Handled malformed arguments cleanly", model_used="mock-model")

    received_args = None
    def capturing_executor(name, args):
        nonlocal received_args
        received_args = args
        return json.dumps({"status": "recovered"})

    with patch.object(gateway, "create_chat_completion", side_effect=mock_create_completion):
        res = gateway.execute_tool_loop(
            messages=[{"role": "user", "content": "Test bad args"}],
            tools=AVAILABLE_PLANNER_TOOLS,
            tool_executor_fn=capturing_executor,
            max_steps=2
        )
        assert res.content == "Handled malformed arguments cleanly"
        assert "raw_arguments" in received_args
        assert received_args["raw_arguments"] == "NOT_VALID_JSON{:::broken"


def test_tool_loop_tool_exception_recovery():
    """Verify that an unexpected exception inside a tool does not crash the loop and is reported to the model."""
    gateway = LLMGateway()

    mock_func = MagicMock()
    mock_func.name = "get_user_profile"
    mock_func.arguments = json.dumps({"user_id": "1"})

    mock_tc = MagicMock()
    mock_tc.id = "mock_call_err"
    mock_tc.function = mock_func

    call_index = 0
    def mock_create_completion(*args, **kwargs):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            return LLMResponse(content="", tool_calls=[mock_tc], model_used="mock-model")
        # Second call: check that error was passed back in tool role
        tool_turn = args[0] if args else kwargs.get("messages", [])
        tool_msgs = [m for m in tool_turn if m.get("role") == "tool"]
        assert len(tool_msgs) >= 1
        assert "Simulated database connection crash" in tool_msgs[0]["content"]
        return LLMResponse(content="I caught the tool error and recovered gracefully", model_used="mock-model")

    def crashing_executor(name, args):
        raise RuntimeError("Simulated database connection crash")

    with patch.object(gateway, "create_chat_completion", side_effect=mock_create_completion):
        res = gateway.execute_tool_loop(
            messages=[{"role": "user", "content": "Trigger crash"}],
            tools=AVAILABLE_PLANNER_TOOLS,
            tool_executor_fn=crashing_executor,
            max_steps=2
        )
        assert res.content == "I caught the tool error and recovered gracefully"


# =====================================================================
# 2. COMPLETE ADAPTATION WORKFLOW: CHAT -> REJECT -> CONFIRM -> PERSIST
# =====================================================================

def test_complete_conversational_adaptation_lifecycle():
    """
    Test the full user journey:
    1. Register user & seed initial schedule with Trataka at 07:00.
    2. Propose schedule shift to 22:00.
    3. User explicitly rejects -> verify routine in DB is 100% UNCHANGED.
    4. Propose schedule shift again.
    5. User confirms -> verify routine in DB updates to 22:00.
    6. Verify fresh authenticated GET /api/schedule/current returns new time.
    7. Verify idempotent notification created.
    """
    u_name = f"adapt_lifecycle_{uuid.uuid4().hex[:10]}"
    reg_res = client.post("/api/auth/register", json={"username": u_name, "password": "Password123!"})
    token = reg_res.json()["token"]
    user_id = db.get_user_from_token(token)

    # 1. Seed initial schedule
    initial_schedule = {
        "schedule": {
            "routine_complexity": "Moderate",
            "morning_block": [
                {"name": "Trataka", "time_slot": "07:00 - 07:15", "duration_minutes": 15, "description": "Gazing", "rationale": "Focus"},
                {"name": "Dantadhavana", "time_slot": "07:15 - 07:25", "duration_minutes": 10, "description": "Teeth cleaning", "rationale": "Hygiene"}
            ],
            "midday_block": [],
            "evening_block": []
        }
    }
    today = time.strftime("%Y-%m-%d")
    db.save_user_schedule(user_id, initial_schedule, today)

    # Verify initial schedule via API
    init_res = client.get("/api/schedule/current", headers={"Authorization": f"Bearer {token}"})
    assert init_res.status_code == 200
    morning_slots = {p["name"]: p["time_slot"] for p in init_res.json()["schedule"]["morning_block"]}
    assert morning_slots["Trataka"] == "07:00 - 07:15"

    # 2. Assistant proposes change
    db.save_chat_message(user_id, "assistant", "I propose shifting Trataka to 22:00 - 22:15 tonight. Would you like me to update your routine?")

    # 3. User REJECTS
    reject_res = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "No, please don't change it. Keep my original schedule."}
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["schedule_updated"] is False

    # Verify fresh database read: schedule remains UNCHANGED
    state_after_reject = db.get_user_state(user_id)
    morning_after_reject = state_after_reject["last_schedule"]["schedule"]["morning_block"]
    trataka_after_reject = next(p for p in morning_after_reject if p["name"] == "Trataka")
    assert trataka_after_reject["time_slot"] == "07:00 - 07:15"

    # 4. Assistant proposes change again
    db.save_chat_message(user_id, "assistant", "I can shift Trataka to 22:00 - 22:15 tonight. Should I apply this change?")

    # 5. User CONFIRMS
    confirm_res = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Yes, please update it now."}
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["schedule_updated"] is True

    # 6. Verify fresh authenticated GET /api/schedule/current reflects the new time
    updated_res = client.get("/api/schedule/current", headers={"Authorization": f"Bearer {token}"})
    assert updated_res.status_code == 200
    sched_now = updated_res.json()["schedule"]
    
    # Check if Trataka was shifted to evening or updated in morning
    all_p = sched_now.get("morning_block", []) + sched_now.get("midday_block", []) + sched_now.get("evening_block", [])
    trataka_now = next((p for p in all_p if p["name"] == "Trataka"), None)
    assert trataka_now is not None
    assert trataka_now["time_slot"] == "22:00 - 22:15"

    # 7. Check notification persistence and idempotency
    notifs = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"}).json()
    assert notifs["count"] >= 1
    assert any("adaptation_confirmed" in n["event_type"] for n in notifs["notifications"])


# =====================================================================
# 3. SECURITY & AUTHORIZATION REGRESSION TESTS
# =====================================================================

def test_expired_session_token_rejected_at_all_endpoints():
    """Verify expired token receives 401 Unauthorized across state, schedule, and chat."""
    u_name = f"expired_user_{uuid.uuid4().hex[:10]}"
    uid = db.create_user(u_name, "password123")
    expired_token = db.create_session(uid, duration_hours=-2.0)

    # 1. User state
    res1 = client.get("/api/user/state", headers={"Authorization": f"Bearer {expired_token}"})
    assert res1.status_code == 401

    # 2. Schedule current
    res2 = client.get("/api/schedule/current", headers={"Authorization": f"Bearer {expired_token}"})
    assert res2.status_code == 401

    # 3. Chat
    res3 = client.post("/api/chat", headers={"Authorization": f"Bearer {expired_token}"}, json={"message": "hello"})
    assert res3.status_code == 401


def test_revoked_session_token_rejected_immediately():
    """Verify token is rejected immediately after calling /api/auth/logout."""
    u_name = f"revoked_user_{uuid.uuid4().hex[:10]}"
    reg = client.post("/api/auth/register", json={"username": u_name, "password": "password123"}).json()
    token = reg["token"]

    # Initial request works
    assert client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # Immediately rejected
    assert client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_user_a_cannot_read_or_mark_user_b_notifications():
    """Verify strict cross-user tenant isolation on notifications."""
    u_a = f"usera_{uuid.uuid4().hex[:10]}"
    u_b = f"userb_{uuid.uuid4().hex[:10]}"

    tok_a = client.post("/api/auth/register", json={"username": u_a, "password": "pwd"}).json()["token"]
    tok_b = client.post("/api/auth/register", json={"username": u_b, "password": "pwd"}).json()["token"]

    uid_a = db.get_user_from_token(tok_a)
    uid_b = db.get_user_from_token(tok_b)

    # Create notification for User B
    nid_b = db.create_notification(uid_b, "private_alert", "Secret for User B only")

    # User A tries to read notifications
    notifs_a = client.get("/api/notifications", headers={"Authorization": f"Bearer {tok_a}"}).json()
    assert not any(n["id"] == nid_b for n in notifs_a["notifications"])

    # User A tries to mark User B's notification read
    mark_attempt = client.post(f"/api/notifications/{nid_b}/read", headers={"Authorization": f"Bearer {tok_a}"}).json()
    assert mark_attempt["success"] is False
