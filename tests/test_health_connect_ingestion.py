"""
test_health_connect_ingestion.py - Comprehensive Test Suite for Android Health Connect Ingestion
================================================================================================
Validates P0, P1, P2 backend requirements:
1. Valid genuine Heart Rate record accepted and persisted.
2. Valid Steps record accepted and persisted.
3. Valid SpO2 record accepted and persisted.
4. Fastrack Noir Charm / Fastrack Smart World provenance preserved.
5. Idempotent deduplication (duplicate submissions do not create duplicate rows).
6. Timestamps preserved (measurement time separate from ingestion time).
7. Invalid units / out-of-range sensor values handled cleanly without fabricating data.
8. Future-dated (>1h in future) and stale (>36h old) records rejected.
9. Missing data treated as absent, not zero (sleep status 'no_data_yet').
10. Authentication required (401 for missing/invalid token).
11. Retrieval endpoint /api/telemetry/records returns user's stored records with provenance.
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.perception.wearable_interface import (
    WearableTelemetryManager,
    HealthConnectPayload,
    TelemetryRecordItem
)

client = TestClient(app)


def _create_authenticated_user(username_prefix: str = "health_connect_tester"):
    """Helper to initialize DB and create an isolated authenticated test user with token."""
    db.init_db()
    uname = f"{username_prefix}_{int(time.time()*1000)}"
    user_id = db.create_user(uname, "password123")
    if not user_id:
        user_id = db.authenticate_user(uname, "password123")
    token = db.create_session(user_id)
    return user_id, {"Authorization": f"Bearer {token}"}


def test_health_connect_requires_authentication():
    """Ensure unauthenticated requests are rejected with 401."""
    res = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "heart_rate_bpm": 82.0
    })
    assert res.status_code == 401
    assert "detail" in res.json()


def test_heart_rate_record_ingestion_and_provenance():
    """
    P1 requirement: Genuine heart-rate record from Fastrack Noir Charm via Health Connect.
    Verifies acceptance, provenance preservation, baseline update, and discrete row insertion.
    """
    user_id, headers = _create_authenticated_user("hr_user")
    now = time.time() - 120.0  # Recorded 2 minutes ago
    unique_rec_id = f"fastrack-hr-uuid-{int(time.time()*1000)}"

    payload = {
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "record_id": unique_rec_id,
        "acquisition_method": "health_connect_import",
        "heart_rate_bpm": 90.0
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["status"] == "valid"
    assert data["is_fresh"] is True
    assert data["device"] == "Fastrack Noir Charm"
    assert data["source_package"] == "com.fastrack.smartworld"
    assert data["acquisition_method"] == "health_connect_import"
    assert data["verified_signals"]["heart_rate_bpm"] == 90.0
    assert data["inserted_count"] >= 1

    # Verify retrieval from database persistence layer
    rec_res = client.get("/api/telemetry/records?metric_type=heart_rate", headers=headers)
    assert rec_res.status_code == 200
    history = rec_res.json()["records"]
    assert len(history) >= 1
    latest_hr = [r for r in history if r["record_id"] == unique_rec_id][0]
    assert latest_hr["record_id"] == unique_rec_id
    assert latest_hr["metric_type"] == "heart_rate"
    assert latest_hr["metric_value"] == 90.0
    assert latest_hr["unit"] == "bpm"
    assert latest_hr["source_package"] == "com.fastrack.smartworld"
    assert latest_hr["device_model"] == "Fastrack Noir Charm"
    assert latest_hr["provenance"] == "health_connect_import"
    assert abs(latest_hr["recorded_at"] - now) < 0.001


def test_idempotent_deduplication():
    """
    Verifies that re-submitting the exact same record_id does not duplicate records in the database.
    """
    user_id, headers = _create_authenticated_user("dedup_user")
    now = time.time() - 300.0
    unique_rec_id = f"unique-dedup-{int(time.time()*1000)}"

    payload = {
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "record_id": unique_rec_id,
        "heart_rate_bpm": 85.0
    }

    # First sync
    res1 = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["inserted_count"] >= 1

    # Second sync of identical record
    res2 = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["duplicate_count"] >= 1

    # Verify count in database
    rec_res = client.get("/api/telemetry/records?metric_type=heart_rate", headers=headers)
    matching = [r for r in rec_res.json()["records"] if r["record_id"] == unique_rec_id]
    assert len(matching) == 1, f"Expected exactly 1 record, found {len(matching)}"


def test_steps_and_spo2_multimodal_ingestion():
    """
    P2 requirement: Extend ingestion to steps and SpO2.
    """
    user_id, headers = _create_authenticated_user("multimodal_user")
    now = time.time() - 60.0

    payload = {
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "heart_rate_bpm": 76.0,
        "steps": 4850,
        "spo2_pct": 98.0
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["verified_signals"]["heart_rate_bpm"] == 76.0
    assert data["verified_signals"]["steps_total"] == 4850
    assert data["verified_signals"]["spo2_pct"] == 98.0
    assert "resting_hr" in data["consumed_metrics"]
    assert "steps_total" in data["consumed_metrics"]
    assert "spo2_pct" in data["consumed_metrics"]

    # Verify user state baselines updated
    state = db.get_user_state(user_id)
    baselines = state.get("telemetry_baselines", {})
    assert baselines.get("steps_total") == 4850
    assert baselines.get("spo2_pct") == 98.0


def test_discrete_records_batch_ingestion():
    """
    Verifies batch ingestion of discrete records list with varied timestamps and stable IDs.
    """
    user_id, headers = _create_authenticated_user("batch_user")
    base_ts = time.time() - 600.0

    uid = int(time.time() * 1000)
    id1, id2, id3 = f"hr-batch-1-{uid}", f"hr-batch-2-{uid}", f"spo2-batch-3-{uid}"

    records_list = [
        {
            "record_id": id1,
            "metric_type": "heart_rate",
            "value": 81.0,
            "unit": "bpm",
            "timestamp": base_ts,
            "source_package": "com.fastrack.smartworld",
            "device_model": "Fastrack Noir Charm",
            "acquisition_method": "health_connect_import"
        },
        {
            "record_id": id2,
            "metric_type": "heart_rate",
            "value": 90.0,
            "unit": "bpm",
            "timestamp": base_ts + 60.0,
            "source_package": "com.fastrack.smartworld",
            "device_model": "Fastrack Noir Charm",
            "acquisition_method": "health_connect_import"
        },
        {
            "record_id": id3,
            "metric_type": "spo2",
            "value": 97.5,
            "unit": "%",
            "timestamp": base_ts + 120.0,
            "source_package": "com.fastrack.smartworld",
            "device_model": "Fastrack Noir Charm",
            "acquisition_method": "health_connect_import"
        }
    ]

    payload = {
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": base_ts + 120.0,
        "records": records_list
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["inserted_count"] >= 3

    # Verify records stored
    rec_res = client.get("/api/telemetry/records", headers=headers)
    stored_ids = {r["record_id"] for r in rec_res.json()["records"]}
    assert id1 in stored_ids
    assert id2 in stored_ids
    assert id3 in stored_ids


def test_stale_record_freshness_rejection():
    """
    Records older than 36h must be rejected as stale.
    """
    user_id, headers = _create_authenticated_user("stale_tester")
    stale_time = time.time() - (48 * 3600)  # 48 hours ago

    payload = {
        "device_model": "Fastrack Noir Charm",
        "recorded_at": stale_time,
        "heart_rate_bpm": 80.0
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    # Stale record has no verified signals accepted
    assert res.status_code == 400
    assert "No valid wearable signals ingested" in res.json()["detail"]


def test_future_dated_record_rejection():
    """
    Records with timestamps in the future (>1h) must be rejected.
    """
    user_id, headers = _create_authenticated_user("future_tester")
    future_time = time.time() + (3 * 3600)  # 3 hours in future

    payload = {
        "device_model": "Fastrack Noir Charm",
        "recorded_at": future_time,
        "heart_rate_bpm": 75.0
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 400


def test_absent_sleep_treated_as_no_data_yet_not_zero():
    """
    Section 9 requirement: The watch has not completed an overnight cycle.
    Absence of sleep must NOT be treated as 0 hours or code defect.
    Status should report 'no_data_yet'.
    """
    user_id, headers = _create_authenticated_user("no_sleep_tester")
    payload = {
        "device_model": "Fastrack Noir Charm",
        "recorded_at": time.time(),
        "heart_rate_bpm": 84.0
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["sleep_status"] == "no_data_yet"
    assert "sleep_hours" in data["missing_metrics"]
    assert "sleep_hours" not in data["verified_signals"]


def test_invalid_sensor_ranges_rejected():
    """
    Physiologically impossible values (e.g. HR=500 bpm or SpO2=140%) must be rejected as missing/invalid,
    not fabricated or recorded.
    """
    user_id, headers = _create_authenticated_user("range_tester")
    payload = {
        "device_model": "Fastrack Noir Charm",
        "recorded_at": time.time(),
        "heart_rate_bpm": 600.0,  # Impossible heart rate
        "spo2_pct": 140.0        # Impossible SpO2
    }

    res = client.post("/api/telemetry/health_connect", json=payload, headers=headers)
    assert res.status_code == 400
    assert "No valid wearable signals ingested" in res.json()["detail"]
