import pytest
import time
import json
from datetime import datetime
from fastapi.testclient import TestClient
from main import app
import src.database.db as db
from src.perception.wearable_interface import WearableTelemetryManager
from src.planning.adherence_evaluator import evaluate_user_telemetry_and_adherence
from src.planning.tools import execute_planner_tool

client = TestClient(app)


def create_test_user(suffix: str):
    db.init_db()
    uname = f"usr_{suffix}_{int(time.time()*1000)}"
    uid = db.create_user(uname, "SecurePass123!")
    token = db.create_session(uid)
    return uid, {"Authorization": f"Bearer {token}"}


def test_step_semantics_interval_vs_daily_total():
    """
    Validates that Health Connect discrete interval steps (e.g. 46, 142) and daily summary totals
    (e.g. 2,126) are segregated by aggregation_type and never summed together, preventing inflation.
    """
    user_id, headers = create_test_user("step_semantics")
    now = time.time()

    # Ingest discrete interval steps (46 steps and 142 steps)
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"step-int-1-{user_id}",
        metric_type="steps",
        metric_value=46.0,
        unit="count",
        recorded_at=now - 300,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm",
        aggregation_type="interval"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"step-int-2-{user_id}",
        metric_type="steps",
        metric_value=142.0,
        unit="count",
        recorded_at=now - 60,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm",
        aggregation_type="interval"
    )

    # Ingest daily cumulative summary (2126 steps)
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"step-daily-{user_id}",
        metric_type="steps_daily_summary",
        metric_value=2126.0,
        unit="count",
        recorded_at=now,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm",
        aggregation_type="daily_total"
    )

    # Check db.get_daily_steps: it must sum ONLY interval steps for today = 46 + 142 = 188
    # It must NOT include 2126 (which would inflate it to 2314)
    daily_steps = db.get_daily_steps(user_id)
    assert daily_steps == 188

    # Query summary via WearableTelemetryManager
    summary = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    assert summary["metrics"]["steps"]["value"] == 188
    assert summary["metrics"]["steps"]["latest_interval"]["steps"] == 142
    assert summary["metrics"]["steps"]["status"] == "available"


def test_upstream_staleness_detection():
    """
    Validates detection of stale upstream watch readings (>30m old) prompting user
    to open the Fastrack companion app.
    """
    user_id, headers = create_test_user("stale_detector")
    now = time.time()

    # Record from 45 minutes ago (> 1800s)
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hr-stale-{user_id}",
        metric_type="heart_rate",
        metric_value=72.0,
        unit="bpm",
        recorded_at=now - 2700,  # 45 minutes ago
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm",
        aggregation_type="instantaneous"
    )

    summary_stale = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    assert summary_stale["is_upstream_stale"] is True
    assert "Fastrack Smart World" in summary_stale["stale_warning_message"]

    # Now ingest fresh record (2 minutes ago)
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hr-fresh-{user_id}",
        metric_type="heart_rate",
        metric_value=74.0,
        unit="bpm",
        recorded_at=now - 120,
        source_package="com.titan.fastrack.reflex",
        device_model="Fastrack Noir Charm",
        aggregation_type="instantaneous"
    )

    summary_fresh = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    assert summary_fresh["is_upstream_stale"] is False
    assert not summary_fresh["stale_warning_message"]


def test_temporal_reasoning_tools():
    """
    Validates the 5 temporal telemetry tools exposed to the AI reasoning engine:
    - get_user_telemetry_reading
    - get_telemetry_history_range
    - compare_telemetry_periods
    - get_activity_completion_evidence
    - review_schedule_adherence
    """
    user_id, headers = create_test_user("temporal_tools")
    now = time.time()

    # Record heart rate sequence
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hr-t1-{user_id}",
        metric_type="heart_rate",
        metric_value=65.0,
        unit="bpm",
        recorded_at=now - 7200,  # 2 hours ago
        source_package="com.titan.fastrack.reflex"
    )
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"hr-t2-{user_id}",
        metric_type="heart_rate",
        metric_value=85.0,
        unit="bpm",
        recorded_at=now - 3600,  # 1 hour ago
        source_package="com.titan.fastrack.reflex"
    )

    # 1. get_user_telemetry_reading
    raw_res = execute_planner_tool(
        "get_user_telemetry_reading",
        {"metric_type": "heart_rate"},
        caller_user_id=str(user_id)
    )
    reading_res = json.loads(raw_res)
    assert reading_res["user_id"] == user_id
    assert reading_res["metric_type"] == "heart_rate"
    assert reading_res["reading"]["value"] == 85.0

    # Test permission isolation: attempt to access another user's data
    other_res = execute_planner_tool(
        "get_user_telemetry_reading",
        {"user_id": "99999", "metric_type": "heart_rate"},
        caller_user_id=str(user_id)
    )
    assert "Permission denied" in other_res

    # 2. get_telemetry_history_range
    raw_range = execute_planner_tool(
        "get_telemetry_history_range",
        {"metric_type": "heart_rate", "period": "today"},
        caller_user_id=str(user_id)
    )
    range_res = json.loads(raw_range)
    assert range_res["metric_type"] == "heart_rate"
    assert range_res["count"] == 2
    assert range_res["avg"] == 75.0

    # 3. compare_telemetry_periods
    raw_comp = execute_planner_tool(
        "compare_telemetry_periods",
        {"metric_type": "heart_rate", "period_1": "today", "period_2": "yesterday"},
        caller_user_id=str(user_id)
    )
    comp_res = json.loads(raw_comp)
    assert comp_res["metric_type"] == "heart_rate"
    assert "period_1" in comp_res
    assert "period_2" in comp_res

    # Ingest discrete steps for Shathapavali window (150 steps)
    today_str = datetime.now().strftime("%Y-%m-%d")
    sched = {
        "morning_block": [],
        "midday_block": [{"name": "Active Shathapavali (100 Steps)", "time_slot": "13:00 - 13:20"}],
        "evening_block": []
    }
    db.sync_schedule_to_activity_lifecycle(user_id, sched, today_str)
    acts = db.get_user_activities(user_id, today_str)
    shatha = acts[0]

    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"step-shatha-test-{user_id}",
        metric_type="steps",
        metric_value=150.0,
        unit="count",
        recorded_at=shatha["start_time_ts"] + 60,
        aggregation_type="interval"
    )

    # 4. get_activity_completion_evidence
    raw_ev = execute_planner_tool(
        "get_activity_completion_evidence",
        {"practice_name": "Active Shathapavali", "schedule_date": today_str},
        caller_user_id=str(user_id)
    )
    ev_res = json.loads(raw_ev)
    assert ev_res["practice_name"] == shatha["practice_name"]
    assert ev_res["interval_steps_measured"] == 150.0
    assert ev_res["is_evidence_sufficient"] is True

    # 5. review_schedule_adherence
    raw_adh = execute_planner_tool(
        "review_schedule_adherence",
        {"days": 7},
        caller_user_id=str(user_id)
    )
    adh_res = json.loads(raw_adh)
    assert adh_res["user_id"] == user_id
    assert adh_res["total_scheduled_activities"] >= 1


def test_activity_lifecycle_auto_completion_and_compensation():
    """
    Validates:
    - Syncing schedule items to activity_lifecycle table
    - Auto-completing Active Shathapavali when steps >= 100
    - Marking missed activities when window expires without evidence
    - Scheduling restorative compensation (e.g. gentle pranayama/walk)
    - Deduplicating notifications via idempotency_key
    """
    user_id, headers = create_test_user("lifecycle_eval")
    today = datetime.now().strftime("%Y-%m-%d")

    # Set up user state with canonical schedule
    sched_dict = {
        "morning_block": [
            {"name": "Morning Surya Namaskar", "time_slot": "07:00 - 07:30"}
        ],
        "midday_block": [
            {"name": "Active Shathapavali (100 Steps)", "time_slot": "12:00 - 12:20"}
        ],
        "evening_block": []
    }
    db.save_user_schedule(user_id=user_id, schedule=sched_dict, date_str=today)
    db.sync_schedule_to_activity_lifecycle(user_id, sched_dict, today)

    activities = db.get_user_activities(user_id, date_str=today)
    assert len(activities) == 2

    # Find the Shathapavali activity and Yoga activity
    shatha_act = next(a for a in activities if "Shathapavali" in a["practice_name"])
    yoga_act = next(a for a in activities if "Surya Namaskar" in a["practice_name"])

    # Simulate steps within Shathapavali window
    db.save_telemetry_record(
        user_id=user_id,
        record_id=f"step-act-{shatha_act['id']}",
        metric_type="steps",
        metric_value=120.0,
        unit="count",
        recorded_at=shatha_act["start_time_ts"] + 60,
        aggregation_type="interval"
    )

    # Run adherence evaluation with simulated current time after both activities
    eval_time = max(shatha_act["end_time_ts"], yoga_act["end_time_ts"]) + 600
    result = evaluate_user_telemetry_and_adherence(user_id, current_ts=eval_time)

    # Shathapavali should be auto-completed by evidence
    assert result["auto_completed_count"] >= 1
    # Morning Yoga had no evidence and is closed -> marked missed and compensation proposed
    assert result["missed_count"] >= 1
    assert result["compensations_scheduled_count"] >= 1

    # Verify updated DB states
    updated_shatha = db.get_activity_by_id(shatha_act["id"])
    assert updated_shatha["status"] == "auto_completed_evidence"

    updated_yoga = db.get_activity_by_id(yoga_act["id"])
    assert updated_yoga["status"] == "compensation_scheduled"

    # Verify compensation record created in activity_lifecycle
    all_acts = db.get_user_activities(user_id, date_str=today)
    comp_act = next((a for a in all_acts if a["compensation_for_id"] == yoga_act["id"]), None)
    assert comp_act is not None
    assert comp_act["status"] == "compensation_scheduled"

    # Verify notification deduplication:
    # Running evaluation a second time must NOT create duplicate notifications
    notifs_before = db.get_user_notifications(user_id)
    evaluate_user_telemetry_and_adherence(user_id, current_ts=eval_time + 60)
    notifs_after = db.get_user_notifications(user_id)
    assert len(notifs_before) == len(notifs_after)


def test_agent_execution_trace_in_chat():
    """
    Validates that /api/chat returns transparent trace_events capturing real tool calls
    without exposing internal prompt tokens or system prompts.
    """
    user_id, headers = create_test_user("chat_trace")

    chat_payload = {"message": "Can you check my steps history and review my schedule adherence?"}
    res = client.post("/api/chat", json=chat_payload, headers=headers)
    assert res.status_code == 200
    res_data = res.json()

    assert "response" in res_data
    assert "trace_events" in res_data
    trace_events = res_data["trace_events"]

    # Verify structure of trace_events if any events were recorded
    for event in trace_events:
        assert "stage" in event or "event_type" in event
        # Must not contain private internal prompt instructions or system prompts
        assert "system_prompt" not in event
        assert "hidden_thought" not in event
