"""
Priority 5: Comprehensive End-to-End Verification of Full Data Path.

Validates the full data path across all 5 key flows:
1. Health Connect ingestion -> Canonical step aggregation -> Dashboard summary display.
2. User query -> Chat stream -> Assistant response persistence -> History reload.
3. Routine page display -> Task completion -> Persistence -> Reload -> Task remains visible.
4. AI-proposed task (journaling) -> Confirmation -> activity_lifecycle stable ID -> Routine page appearance.
5. Simulated NVIDIA NIM failure -> Graceful failover/recovery -> History preserved -> User informed.
"""

import time
import json
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app
from src.database import db
from src.planning.schedule_service import mutate_user_schedule
from src.llm_gateway import LLMGateway

client = TestClient(app)


def _create_authenticated_user(prefix: str):
    uname = f"{prefix}_{int(time.time() * 1000)}"
    user_id = db.create_user(uname, "password123")
    token = db.create_session(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, token, headers


def test_flow_1_health_connect_to_dashboard_canonical_steps():
    """Flow 1: Health Connect ingestion -> Canonical step aggregation -> Dashboard summary display."""
    user_id, token, headers = _create_authenticated_user("p5_flow1")
    today = time.strftime("%Y-%m-%d")

    # Ingest 3 real interval records (200 + 350 + 450 = 1000 steps) from wearable package
    now_ts = time.time()
    wearable_pkg = "com.titan.fastrack.reflex"
    device_model = "Noir Charm"

    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hc_int1_{user_id}",
        metric_type="steps",
        metric_value=200.0,
        unit="count",
        recorded_at=now_ts - 3600,
        aggregation_type="interval",
        source_package=wearable_pkg,
        device_model=device_model
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hc_int2_{user_id}",
        metric_type="steps",
        metric_value=350.0,
        unit="count",
        recorded_at=now_ts - 2400,
        aggregation_type="interval",
        source_package=wearable_pkg,
        device_model=device_model
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hc_int3_{user_id}",
        metric_type="steps",
        metric_value=450.0,
        unit="count",
        recorded_at=now_ts - 1200,
        aggregation_type="interval",
        source_package=wearable_pkg,
        device_model=device_model
    )

    # Also ingest a daily cumulative snapshot of 1000 steps that should NOT be added to intervals
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hc_snap_{user_id}",
        metric_type="steps",
        metric_value=1000.0,
        unit="count",
        recorded_at=now_ts,
        aggregation_type="daily_total",
        source_package=wearable_pkg,
        device_model=device_model
    )

    # Ingest a phone pedometer record that should be de-prioritized in favor of the smartwatch
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hc_phone_{user_id}",
        metric_type="steps",
        metric_value=25.0,
        unit="count",
        recorded_at=now_ts - 3000,
        aggregation_type="interval",
        source_package="com.google.android.apps.fitness",
        device_model="Pixel 8"
    )

    # Query Dashboard Summary
    dash_res = client.get("/api/dashboard/summary", headers=headers)
    assert dash_res.status_code == 200
    dash_data = dash_res.json()

    # Step count must equal exactly 1,000 steps (not 2,025!)
    steps_telemetry = dash_data["telemetry"]["steps"]
    assert steps_telemetry["value"] == 1000
    assert dash_data["telemetry"]["source_package"] == wearable_pkg
    assert dash_data["telemetry"]["device_model"] == device_model
    assert steps_telemetry["provenance"] is not None
    assert isinstance(steps_telemetry["provenance"], str)


def test_flow_2_chat_stream_persistence_and_history_reload():
    """Flow 2: User query -> Chat stream -> Assistant response persistence -> History reload."""
    user_id, token, headers = _create_authenticated_user("p5_flow2")
    user_query = f"What is the classical Ayurvedic rationale for Brahma Muhurta? {time.time()}"

    # Stream the chat
    stream_res = client.post("/api/chat/stream", headers=headers, json={"message": user_query})
    assert stream_res.status_code == 200

    lines = stream_res.text.strip().split("\n\n")
    events = [json.loads(line.replace("data: ", "")) for line in lines if line.startswith("data: ")]

    assert len(events) >= 1
    final_events = [e for e in events if e.get("type") == "final_response"]
    assert len(final_events) == 1
    final_res = final_events[0]
    assert "response" in final_res
    assert len(final_res["response"]) > 0
    assert "message_id" in final_res

    # Query persistent history from SQLite
    hist_res = client.get("/api/chat/history?limit=5", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.json().get("history", [])

    # Verify user message and assistant message both exist
    assert any(m["role"] == "user" and user_query in m["content"] for m in history)
    assert any(m["role"] == "assistant" and len(m["content"]) > 0 for m in history)


def test_flow_3_routine_completion_visibility_and_persistence():
    """Flow 3: Routine page display -> Task completion -> Persistence -> Reload -> Task remains visible."""
    user_id, token, headers = _create_authenticated_user("p5_flow3")
    today = time.strftime("%Y-%m-%d")

    sched = {
        "schedule": {
            "morning_block": [
                {"name": "Brahma Muhurta Awakening", "time_slot": "05:30 - 06:00", "description": "Early wake and warm water"}
            ],
            "midday_block": [
                {"name": "Mitahara Nourishing Lunch", "time_slot": "12:30 - 13:15", "description": "Mindful lunch"}
            ],
            "evening_block": [
                {"name": "Trataka Candle Gazing", "time_slot": "21:00 - 21:15", "description": "Focus meditation"}
            ]
        }
    }
    db.save_user_schedule(user_id, sched, today)

    # Initial routine check
    r1 = client.get("/api/schedule/current", headers=headers)
    assert r1.status_code == 200
    assert len(r1.json()["schedule"]["morning_block"]) == 1

    # Complete the morning task
    comp_res = client.post(
        "/api/activities/complete",
        headers=headers,
        json={"practice_name": "Brahma Muhurta Awakening"}
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["success"] is True

    # Check /api/activities/today: all 3 tasks remain visible, morning is completed_by_user
    acts_res = client.get("/api/activities/today", headers=headers)
    assert acts_res.status_code == 200
    acts = acts_res.json()["activities"]
    assert len(acts) == 3

    status_map = {a["practice_name"]: a["status"] for a in acts}
    assert status_map["Brahma Muhurta Awakening"] == "completed_by_user"
    assert status_map["Mitahara Nourishing Lunch"] == "scheduled"
    assert status_map["Trataka Candle Gazing"] == "scheduled"

    # Check /api/schedule/current: schedule remains intact
    r2 = client.get("/api/schedule/current", headers=headers)
    assert r2.status_code == 200
    assert len(r2.json()["schedule"]["morning_block"]) == 1
    assert len(r2.json()["schedule"]["midday_block"]) == 1
    assert len(r2.json()["schedule"]["evening_block"]) == 1


def test_flow_4_ai_proposed_task_confirmation_and_lifecycle():
    """Flow 4: AI proposes a new task -> Confirmation -> activity_lifecycle stable ID -> Routine visibility."""
    user_id, token, headers = _create_authenticated_user("p5_flow4")
    today = time.strftime("%Y-%m-%d")

    sched = {
        "schedule": {
            "morning_block": [
                {"name": "Brahma Muhurta Awakening", "time_slot": "05:30 - 06:00", "description": "Wake and hydrate"}
            ],
            "midday_block": [],
            "evening_block": []
        }
    }
    db.save_user_schedule(user_id, sched, today)

    # User confirms AI proposed Evening Gratitude Journaling at 23:45 - 23:50
    mut_res = mutate_user_schedule(
        user_id=user_id,
        updates={"Evening Gratitude Journaling": "23:45 - 23:50"},
        date_str=today
    )
    assert mut_res["success"] is True

    # Verify it is in evening_block
    r_current = client.get("/api/schedule/current", headers=headers)
    assert r_current.status_code == 200
    evening_block = r_current.json()["schedule"]["evening_block"]
    journal_entries = [p for p in evening_block if "journal" in p["name"].lower()]
    assert len(journal_entries) == 1
    assert journal_entries[0]["time_slot"] == "23:45 - 23:50"

    # Verify stable activity_lifecycle ID in SQLite
    acts = db.get_user_activities(user_id, date_str=today)
    journal_act = [a for a in acts if "journal" in a["practice_name"].lower()][0]
    expected_stable_id = f"act_{user_id}_{today}_evening_gratitude_journaling"
    assert journal_act["id"] == expected_stable_id
    assert journal_act["status"] == "scheduled"


def test_flow_5_simulated_nim_failure_recovery_and_history():
    """Flow 5: Simulated NVIDIA NIM failure -> Graceful failover/recovery -> History preserved."""
    user_id, token, headers = _create_authenticated_user("p5_flow5")
    test_msg = f"Can I drink cold water right after lunch? {time.time()}"

    gateway = LLMGateway.get_instance()
    orig_loop = gateway.execute_tool_loop

    try:
        # Simulate complete failure of all LLM providers
        gateway.execute_tool_loop = MagicMock(side_effect=RuntimeError("NVIDIA NIM connection refused (503)"))

        res = client.post("/api/chat", headers=headers, json={"message": test_msg})
        assert res.status_code == 200
        data = res.json()
        assert "response" in data
        # Must return helpful clinical guidance instead of crashing
        assert "Vaidya AI Clinical Guidance" in data["response"] or "resilient offline" in data["response"] or "delay" in data["response"]

        # History in SQLite must contain user turn and assistant turn
        history = db.get_chat_history(user_id, limit=2)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    finally:
        gateway.execute_tool_loop = orig_loop
