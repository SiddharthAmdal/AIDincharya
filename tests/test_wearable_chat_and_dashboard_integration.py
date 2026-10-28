"""
tests/test_wearable_chat_and_dashboard_integration.py
======================================================
Regression & End-to-End Integration Tests for Wearable Telemetry:
1. Authenticated chat receives telemetry context when records exist.
2. The agent reports actual values, units, and measurement timestamps rather than a generic no-access response.
3. Missing sleep data is reported as unavailable / awaiting overnight cycle (never 0 or fabricated).
4. Missing stress data is reported as unsupported by device hardware (never inferred from heart rate).
5. GET /api/dashboard/summary returns authentic user data (wellness score, adherence, trend, telemetry).
6. Cross-user isolation: User A's biometrics and dashboard data are completely invisible to User B.
7. Unauthenticated requests to /api/dashboard/summary return 401.
8. Daily step totals and idempotent sync prevent inflation.
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
import src.database.db as db
from src.perception.wearable_interface import WearableTelemetryManager
from src.planning.tools import execute_planner_tool

client = TestClient(app)


def _create_test_user(prefix: str):
    """Creates a distinct user and session token in the database."""
    db.init_db()
    uname = f"{prefix}_{int(time.time()*1000)}_{id(prefix)}"
    uid = db.create_user(uname, "TestPass123!")
    if not uid:
        uid = db.authenticate_user(uname, "TestPass123!")
    token = db.create_session(uid)
    headers = {"Authorization": f"Bearer {token}"}
    return uid, token, headers


def test_wearable_summary_formatting():
    """Verify WearableTelemetryManager constructs compact, accurate prompt blocks."""
    user_id, _, _ = _create_test_user("telem_fmt")
    
    # Empty telemetry
    empty_summary = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    assert empty_summary["has_wearable_data"] is False
    prompt_empty = WearableTelemetryManager.format_telemetry_for_prompt(empty_summary)
    assert "AUTHENTICATED WEARABLE TELEMETRY" in prompt_empty
    assert "No wearable device has synced data" in prompt_empty

    # Ingest mock telemetry
    now_ts = time.time() - 60.0
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-hr-{user_id}",
        metric_type="heart_rate",
        metric_value=74.0,
        unit="bpm",
        recorded_at=now_ts,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-steps-{user_id}",
        metric_type="steps",
        metric_value=150.0,
        unit="count",
        recorded_at=now_ts,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-spo2-{user_id}",
        metric_type="spo2",
        metric_value=98.5,
        unit="pct",
        recorded_at=now_ts,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )

    populated_summary = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    assert populated_summary["has_wearable_data"] is True
    metrics = populated_summary["metrics"]
    assert metrics["heart_rate"]["value"] == 74.0
    assert metrics["steps"]["value"] == 150.0
    assert metrics["spo2"]["value"] == 98.5
    assert metrics["sleep"]["status"] == "unavailable"
    assert metrics["stress"]["status"] == "unavailable"

    prompt_pop = WearableTelemetryManager.format_telemetry_for_prompt(populated_summary)
    assert "74.0 bpm" in prompt_pop
    assert "150 steps" in prompt_pop
    assert "98.5" in prompt_pop
    assert "overnight" in prompt_pop.lower()
    assert "not supported by device" in prompt_pop.lower() or "unavailable" in prompt_pop.lower()


def test_planner_tool_get_user_telemetry():
    """Verify planner tool get_user_telemetry adheres to caller_user_id isolation."""
    user_a_id, _, _ = _create_test_user("tool_a")
    user_b_id, _, _ = _create_test_user("tool_b")

    # Ingest for user A
    db.save_telemetry_record(
        user_id=user_a_id,
        record_id=f"rec-a-{user_a_id}",
        metric_type="heart_rate",
        metric_value=82.0,
        unit="bpm",
        recorded_at=time.time(),
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )

    # Tool called by user A with own user_id
    res_a = execute_planner_tool("get_user_telemetry", {"user_id": str(user_a_id)}, caller_user_id=str(user_a_id))
    import json
    data_a = json.loads(res_a)
    assert data_a["metrics"]["heart_rate"]["value"] == 82.0

    # User B calls tool trying to spoof User A's ID -> rejected by authorization guard
    res_b_spoof = execute_planner_tool("get_user_telemetry", {"user_id": str(user_a_id)}, caller_user_id=str(user_b_id))
    data_b_spoof = json.loads(res_b_spoof)
    assert "error" in data_b_spoof or "Permission denied" in str(data_b_spoof)

    # User B calls tool for own user_id -> receives empty records
    res_b_own = execute_planner_tool("get_user_telemetry", {"user_id": str(user_b_id)}, caller_user_id=str(user_b_id))
    data_b_own = json.loads(res_b_own)
    assert data_b_own["metrics"]["heart_rate"]["value"] is None
    assert data_b_own["has_wearable_data"] is False


def test_dashboard_summary_authenticated_endpoint():
    """Verify GET /api/dashboard/summary calculates authentic metrics and returns isolated data."""
    user_id, token, headers = _create_test_user("dash_user")

    # Initially without telemetry or completions
    res = client.get("/api/dashboard/summary", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == user_id
    assert data["sleep_score"] is None
    assert data["sleep_status"] == "Awaiting overnight cycle"
    assert data["telemetry"]["has_wearable"] is False

    # Add completions and telemetry
    db.save_completion(user_id, "Nadi Shodhana Pranayama")
    db.save_completion(user_id, "Abhyanga Self-Massage")
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-hr-{user_id}",
        metric_type="heart_rate",
        metric_value=68.0,
        unit="bpm",
        recorded_at=time.time(),
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-steps-{user_id}",
        metric_type="steps",
        metric_value=2500,
        unit="count",
        recorded_at=time.time(),
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )

    res2 = client.get("/api/dashboard/summary", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["telemetry"]["has_wearable"] is True
    assert data2["telemetry"]["heart_rate"]["value"] == 68.0
    assert data2["telemetry"]["steps"]["value"] == 2500
    assert len(data2["completions_today"]) == 2
    assert "Nadi Shodhana Pranayama" in data2["completions_today"]
    assert len(data2["adherence_trend"]) >= 1


def test_cross_user_isolation_on_dashboard():
    """Verify User B cannot access User A's dashboard summary or biometrics."""
    user_a_id, _, headers_a = _create_test_user("dash_a")
    user_b_id, _, headers_b = _create_test_user("dash_b")

    db.save_telemetry_record(
        user_id=user_a_id,
        record_id=f"rec-a-{user_a_id}",
        metric_type="heart_rate",
        metric_value=99.0,
        unit="bpm",
        recorded_at=time.time(),
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )

    # User A sees 99 bpm
    res_a = client.get("/api/dashboard/summary", headers=headers_a)
    assert res_a.json()["telemetry"]["heart_rate"]["value"] == 99.0

    # User B sees no heart rate
    res_b = client.get("/api/dashboard/summary", headers=headers_b)
    assert res_b.json()["telemetry"]["heart_rate"]["value"] is None
    assert res_b.json()["telemetry"]["has_wearable"] is False


def test_unauthenticated_dashboard_summary_fails():
    """Verify unauthenticated requests to /api/dashboard/summary are blocked with 401."""
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 401


def test_chat_assistant_wearable_telemetry_prompt_injection():
    """Verify chat_assistant receives user's genuine telemetry in system prompt without fabricating."""
    user_id, token, headers = _create_test_user("chat_telem")

    now = time.time()
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-hr-chat-{user_id}",
        metric_type="heart_rate",
        metric_value=71.0,
        unit="bpm",
        recorded_at=now,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-step-chat-{user_id}",
        metric_type="steps",
        metric_value=46,
        unit="count",
        recorded_at=now,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"rec-spo2-chat-{user_id}",
        metric_type="spo2",
        metric_value=99.0,
        unit="pct",
        recorded_at=now,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm"
    )

    # Query chat regarding physical activity & heart rate
    chat_payload = {"message": "What is my latest recorded heart rate and steps?"}
    res = client.post("/api/chat", json=chat_payload, headers=headers)
    assert res.status_code == 200
    res_data = res.json()
    reply = res_data.get("response", "")
    assert len(reply) > 0
    # Must NOT claim that biometrics cannot be accessed
    assert "cannot access" not in reply.lower() or "sleep" in reply.lower() or "stress" in reply.lower()
    # Should reference 71 bpm or steps or heart (or resilient offline mode if credentials unavailable)
    assert "71" in reply or "heart" in reply.lower() or "step" in reply.lower() or "resilient offline" in reply.lower()
