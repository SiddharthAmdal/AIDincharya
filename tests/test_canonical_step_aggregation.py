"""
tests/test_canonical_step_aggregation.py - Deterministic Regression Tests for Step Aggregation

Covers all 12 priority regression scenarios:
1. Valid daily aggregate of 2,287 steps.
2. Daily total accompanied by intervals already included in that total (prevents addition).
3. Duplicate records from repeated synchronization.
4. Overlapping intervals.
5. Multiple source applications with overlapping records.
6. Records spanning UTC midnight vs local midnight.
7. Stale previous-day total.
8. Missing records and unavailable Health Connect data.
9. Strict user isolation.
10. Dashboard API and AI agent returning identical canonical result.
11. Repeated syncs not increasing daily total.
12. Reconciliation when authoritative aggregate and persisted intervals disagree.
"""

import time
import datetime
import pytest
import sqlite3
from typing import Dict, Any

from src.database.db import get_db_connection, save_telemetry_record, get_daily_steps
from src.perception.step_aggregation import get_canonical_daily_steps
from src.perception.wearable_interface import WearableTelemetryManager
from src.planning.tools import execute_planner_tool


@pytest.fixture
def isolated_user_id():
    """Generates a temporary unique user ID to avoid polluting existing user data."""
    test_uid = 999000 + int(time.time() % 10000)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM telemetry_records WHERE user_id = ?", (test_uid,))
    conn.commit()
    conn.close()
    yield test_uid
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM telemetry_records WHERE user_id = ?", (test_uid,))
    conn.commit()
    conn.close()


def test_1_valid_daily_aggregate_2287(isolated_user_id):
    """
    Simulates the verified Fastrack Noir Charm dataset where interval steps sum to 2,287:
    394 + 1079 + 216 + 25 + 302 + 64 + 46 + 142 + 19 = 2,287.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    intervals = [394, 1079, 216, 25, 302, 64, 46, 142, 19]
    base_ts = 1793082600.0  # 12:00 PM on 2026-10-27

    for idx, steps_val in enumerate(intervals):
        save_telemetry_record(
            user_id=uid,
            record_id=f"hc-test-rec-{idx}",
            metric_type="steps",
            metric_value=float(steps_val),
            unit="count",
            recorded_at=base_ts + (idx * 3600),
            source_package="com.titan.fastrack.reflex",
            aggregation_type="interval"
        )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    assert res["status"] == "verified"
    assert res["steps"] == 2287
    assert res["interval_count"] == 9
    assert res["source_package"] == "com.titan.fastrack.reflex"


def test_2_daily_total_accompanied_by_intervals_never_adds(isolated_user_id):
    """
    Critical regression: Cumulative daily snapshots (e.g. 2,016 and 2,268) must NEVER
    be added to the intervals that are already included in that total.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    base_ts = 1793082600.0

    # Insert intervals that sum to 2016
    for idx, steps_val in enumerate([394, 1079, 216, 25, 302]):
        save_telemetry_record(
            user_id=uid,
            record_id=f"hc-sub-rec-{idx}",
            metric_type="steps",
            metric_value=float(steps_val),
            unit="count",
            recorded_at=base_ts + (idx * 1800),
            source_package="com.titan.fastrack.reflex",
            aggregation_type="interval"
        )

    # Insert cumulative snapshot of 2016 for the same timeframe
    save_telemetry_record(
        user_id=uid,
        record_id="hc-cum-snapshot-2016",
        metric_type="steps_daily_summary",
        metric_value=2016.0,
        unit="count",
        recorded_at=base_ts + 7200,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="daily_total"
    )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    # Must NOT sum 2016 + 2016 = 4032!
    assert res["steps"] == 2016


def test_3_duplicate_records_from_repeated_sync(isolated_user_id):
    """
    Submitting the same Health Connect interval record multiple times must be deduplicated
    and must not inflate the daily step total.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    # First sync
    save_telemetry_record(
        user_id=uid,
        record_id="dup-check-uuid-1",
        metric_type="steps",
        metric_value=500.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    # Re-sync (identical record_id)
    save_telemetry_record(
        user_id=uid,
        record_id="dup-check-uuid-1",
        metric_type="steps",
        metric_value=500.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    assert res["steps"] == 500


def test_4_overlapping_intervals_deduplicated(isolated_user_id):
    """
    Duplicate interval measurements with identical timestamp from same package must not double count.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    save_telemetry_record(
        user_id=uid,
        record_id="rec-int-a",
        metric_type="steps",
        metric_value=300.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )
    save_telemetry_record(
        user_id=uid,
        record_id="rec-int-b",
        metric_type="steps",
        metric_value=300.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    assert res["steps"] == 300


def test_5_multiple_sources_prioritizes_wearable(isolated_user_id):
    """
    Phone pedometer (com.android.healthconnect.phone...) or test fixtures must not be
    summed on top of watch records (com.titan.fastrack.reflex).
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    # Watch records
    save_telemetry_record(
        user_id=uid,
        record_id="watch-rec-1",
        metric_type="steps",
        metric_value=1200.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    # Phone records for the same time
    save_telemetry_record(
        user_id=uid,
        record_id="phone-rec-1",
        metric_type="steps",
        metric_value=15.0,
        unit="count",
        recorded_at=rec_time + 60,
        source_package="com.android.healthconnect.phone.jf21f6dcc41f233d4aa3e820c60beec8a",
        aggregation_type="interval"
    )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    assert res["steps"] == 1200
    assert res["source_package"] == "com.titan.fastrack.reflex"


def test_6_timezone_boundary_handling(isolated_user_id):
    """
    Records spanning UTC midnight vs local midnight (IST = UTC+05:30):
    A record at 2026-10-27 01:00 UTC is 2026-10-27 06:30 IST (belongs to 2026-10-27).
    A record at 2026-10-27 20:00 UTC is 2026-10-28 01:30 IST (belongs to 2026-10-28 in IST).
    """
    uid = isolated_user_id
    
    # 2026-10-27 18:00:00 UTC = 2026-10-27 23:30:00 IST
    in_day_ts = 1793124000.0  # 2026-10-27 23:30 IST
    # 2026-10-27 19:00:00 UTC = 2026-10-28 00:30:00 IST (Next day in local time)
    next_day_ts = 1793127600.0

    save_telemetry_record(
        user_id=uid,
        record_id="in-day-rec",
        metric_type="steps",
        metric_value=700.0,
        unit="count",
        recorded_at=in_day_ts,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )
    save_telemetry_record(
        user_id=uid,
        record_id="next-day-rec",
        metric_type="steps",
        metric_value=400.0,
        unit="count",
        recorded_at=next_day_ts,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    res_today = get_canonical_daily_steps(user_id=uid, date_str="2026-10-27", timezone_str="Asia/Kolkata")
    assert res_today["steps"] == 700

    res_tomorrow = get_canonical_daily_steps(user_id=uid, date_str="2026-10-28", timezone_str="Asia/Kolkata")
    assert res_tomorrow["steps"] == 400


def test_7_stale_previous_day_not_substituted(isolated_user_id):
    """
    When querying a date with no records, canonical aggregation must NOT silently
    substitute a prior day's steps.
    """
    uid = isolated_user_id
    
    # Put records in 2026-10-25
    save_telemetry_record(
        user_id=uid,
        record_id="old-rec-25",
        metric_type="steps",
        metric_value=1500.0,
        unit="count",
        recorded_at=1792900000.0,  # 2026-10-25
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    # Query 2026-10-26 (empty)
    res = get_canonical_daily_steps(user_id=uid, date_str="2026-10-26")
    assert res["status"] == "unavailable"
    assert res["steps"] == 0


def test_8_empty_results_return_unavailable(isolated_user_id):
    """
    User with no telemetry returns explicit unavailable state without crashing.
    """
    res = get_canonical_daily_steps(user_id=isolated_user_id, date_str="2026-10-27")
    assert res["status"] == "unavailable"
    assert res["steps"] == 0
    assert res["is_stale"] is True


def test_9_strict_user_isolation(isolated_user_id):
    """
    Records from other users must never leak into the target user's aggregation.
    """
    target_uid = isolated_user_id
    other_uid = target_uid + 1
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    save_telemetry_record(
        user_id=target_uid,
        record_id="target-user-rec",
        metric_type="steps",
        metric_value=850.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )
    save_telemetry_record(
        user_id=other_uid,
        record_id="other-user-rec",
        metric_type="steps",
        metric_value=5000.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    res = get_canonical_daily_steps(user_id=target_uid, date_str=today_str)
    assert res["steps"] == 850


def test_10_dashboard_and_agent_return_identical_canonical_result(isolated_user_id):
    """
    Verifies that WearableTelemetryManager, db.get_daily_steps, and AI execute_planner_tool
    all resolve to the exact same canonical daily total.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    save_telemetry_record(
        user_id=uid,
        record_id="concordant-test-rec",
        metric_type="steps",
        metric_value=1750.0,
        unit="count",
        recorded_at=rec_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    # 1. Direct canonical call
    canon = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    # 2. db.get_daily_steps
    db_steps = get_daily_steps(user_id=uid, date_str=today_str)
    # 3. Telemetry summary
    summary = WearableTelemetryManager.get_user_telemetry_summary(user_id=uid)
    # 4. Agent tool
    import json
    agent_raw = execute_planner_tool("get_user_telemetry", {"user_id": uid, "metric_type": "steps"}, caller_user_id=str(uid))
    agent_data = json.loads(agent_raw)

    assert canon["steps"] == 1750
    assert db_steps == 1750
    assert summary["metrics"]["steps"]["value"] == 1750
    assert agent_data["metrics"]["steps"]["value"] == 1750


def test_11_repeated_syncs_do_not_increase_daily_total(isolated_user_id):
    """
    Simulates repeated sync loop from Android bridge. Total must remain invariant.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    rec_time = 1793082600.0

    for i in range(5):
        save_telemetry_record(
            user_id=uid,
            record_id="repeated-sync-rec-1",
            metric_type="steps",
            metric_value=920.0,
            unit="count",
            recorded_at=rec_time,
            source_package="com.titan.fastrack.reflex",
            aggregation_type="interval"
        )
        res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
        assert res["steps"] == 920


def test_12_reconciliation_when_snapshot_and_intervals_disagree(isolated_user_id):
    """
    When a daily cumulative snapshot exists (e.g. 1,000 at 2 PM) and subsequent intervals
    occur later in the day (e.g. 200 at 4 PM), only the subsequent intervals are added:
    1,000 + 200 = 1,200.
    """
    uid = isolated_user_id
    today_str = "2026-10-27"
    snapshot_time = 1793090000.0

    # Cumulative snapshot at 2 PM
    save_telemetry_record(
        user_id=uid,
        record_id="cum-snap-1000",
        metric_type="steps_daily_summary",
        metric_value=1000.0,
        unit="count",
        recorded_at=snapshot_time,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="daily_total"
    )

    # Interval strictly AFTER snapshot at 4 PM
    save_telemetry_record(
        user_id=uid,
        record_id="subsequent-interval-200",
        metric_type="steps",
        metric_value=200.0,
        unit="count",
        recorded_at=snapshot_time + 7200,
        source_package="com.titan.fastrack.reflex",
        aggregation_type="interval"
    )

    res = get_canonical_daily_steps(user_id=uid, date_str=today_str)
    assert res["steps"] == 1200
    assert res["aggregation_method"] == "reconciled_snapshot_plus_subsequent_intervals"
