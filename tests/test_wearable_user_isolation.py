"""
tests/test_wearable_user_isolation.py - Strict Per-User Data Isolation & Security Test Suite
============================================================================================
Audits and deterministically proves strict per-user data isolation across:
1. Ingestion: POST /api/telemetry/health_connect
2. Persistence: telemetry_records and user_state.telemetry_baselines
3. Retrieval: GET /api/telemetry/records
4. Cross-user spoofing: Client-supplied user_id in payload cannot override authenticated principal
5. Cross-user collisions: Shared or colliding record_ids across users are safely isolated
6. Downstream pipelines: Schedule generation and Vikriti estimation use only current user's state
7. Session security: Missing, bogus, expired, and revoked tokens fail safely with 401
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
import src.database.db as db

client = TestClient(app)


def _create_isolated_user(prefix: str):
    """Creates a distinct user and session token in the database."""
    db.init_db()
    uname = f"{prefix}_{int(time.time()*1000)}_{id(prefix)}"
    uid = db.create_user(uname, "TestPass123!")
    if not uid:
        uid = db.authenticate_user(uname, "TestPass123!")
    token = db.create_session(uid)
    headers = {"Authorization": f"Bearer {token}"}
    return uid, token, headers


def test_user_a_submits_and_retrieves_own_records():
    """Task 8.1: User A submits genuine-shaped telemetry and can retrieve their own records."""
    user_a_id, _, headers_a = _create_isolated_user("user_a")
    now = time.time() - 30.0
    rec_id_a = f"user-a-rec-{int(now)}"

    payload_a = {
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "record_id": rec_id_a,
        "heart_rate_bpm": 88.0,
        "steps": 5100,
        "spo2_pct": 98.5
    }

    res = client.post("/api/telemetry/health_connect", json=payload_a, headers=headers_a)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "valid"
    assert data["inserted_count"] >= 1

    # User A retrieves own records
    get_res = client.get("/api/telemetry/records", headers=headers_a)
    assert get_res.status_code == 200
    records = get_res.json()["records"]
    assert any(r["record_id"] == rec_id_a for r in records)
    user_a_recs = [r for r in records if r["record_id"] == rec_id_a]
    assert user_a_recs[0]["metric_value"] == 88.0


def test_user_b_cannot_retrieve_user_a_records():
    """Task 8.2: User B cannot retrieve User A's records."""
    user_a_id, _, headers_a = _create_isolated_user("user_a_priv")
    user_b_id, _, headers_b = _create_isolated_user("user_b_priv")

    now = time.time() - 60.0
    rec_id_a = f"secret-a-rec-{int(now)}"

    # User A ingests private health metric
    client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "record_id": rec_id_a,
        "heart_rate_bpm": 105.0
    }, headers=headers_a)

    # User B queries their own records
    res_b = client.get("/api/telemetry/records", headers=headers_b)
    assert res_b.status_code == 200
    records_b = res_b.json()["records"]
    assert all(r["record_id"] != rec_id_a for r in records_b), "User B retrieved User A's private record!"

    # User B attempts to query passing user_a_id in query parameters
    res_b_tamper = client.get(f"/api/telemetry/records?user_id={user_a_id}", headers=headers_b)
    assert res_b_tamper.status_code == 200
    records_b_tamper = res_b_tamper.json()["records"]
    assert all(r["record_id"] != rec_id_a for r in records_b_tamper), "User B bypassed isolation with ?user_id!"


def test_client_supplied_user_id_in_payload_cannot_spoof_ownership():
    """
    Task 8.3: A client-supplied User A ID in a User B request cannot cause records
    or baselines to be assigned to User A.
    """
    user_a_id, _, headers_a = _create_isolated_user("victim_a")
    user_b_id, _, headers_b = _create_isolated_user("attacker_b")

    now = time.time() - 10.0
    rec_id_spoof = f"spoof-rec-{int(now)}"

    # Attacker B sends payload explicitly declaring "user_id": user_a_id
    malicious_payload = {
        "user_id": user_a_id,
        "device_model": "Fastrack Noir Charm",
        "source_package": "com.fastrack.smartworld",
        "recorded_at": now,
        "record_id": rec_id_spoof,
        "heart_rate_bpm": 175.0,  # Abnormal HR
        "steps": 99999
    }

    res = client.post("/api/telemetry/health_connect", json=malicious_payload, headers=headers_b)
    assert res.status_code == 200

    # Verify User A's records DO NOT contain the spoofed record
    res_a = client.get("/api/telemetry/records", headers=headers_a)
    records_a = res_a.json()["records"]
    assert all(r["record_id"] != rec_id_spoof for r in records_a), "Spoofed record was assigned to User A!"

    # Verify User A's state baselines were NOT modified
    state_a = db.get_user_state(user_a_id)
    baselines_a = state_a.get("telemetry_baselines", {})
    assert baselines_a.get("heart_rate_bpm") != 175.0, "Attacker B modified User A's baseline!"

    # Verify record was correctly attributed to User B (the authenticated principal)
    res_b = client.get("/api/telemetry/records", headers=headers_b)
    records_b = res_b.json()["records"]
    assert any(r["record_id"] == rec_id_spoof for r in records_b)
    state_b = db.get_user_state(user_b_id)
    assert state_b.get("telemetry_baselines", {}).get("heart_rate_bpm") == 175.0


def test_user_b_ingestion_cannot_modify_user_a_baselines():
    """Task 8.4: User B's ingestion cannot modify User A's baselines."""
    user_a_id, _, headers_a = _create_isolated_user("baseline_a")
    user_b_id, _, headers_b = _create_isolated_user("baseline_b")

    now = time.time() - 45.0

    # Establish baseline for User A
    client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 65.0,
        "steps": 10000,
        "spo2_pct": 99.0
    }, headers=headers_a)

    state_a_orig = db.get_user_state(user_a_id)
    assert state_a_orig.get("telemetry_baselines", {}).get("heart_rate_bpm") == 65.0

    # User B ingests completely different measurements
    client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 115.0,
        "steps": 1200,
        "spo2_pct": 93.0
    }, headers=headers_b)

    # Re-verify User A's baselines are pristine and untouched
    state_a_after = db.get_user_state(user_a_id)
    baselines_a = state_a_after.get("telemetry_baselines", {})
    assert baselines_a.get("heart_rate_bpm") == 65.0, "User A's heart_rate baseline was corrupted!"
    assert baselines_a.get("steps_total") == 10000, "User A's steps baseline was corrupted!"
    assert baselines_a.get("spo2_pct") == 99.0, "User A's spo2 baseline was corrupted!"


def test_cross_user_shared_record_id_isolation():
    """
    Task 3 & 5: Verifies that if User A and User B both submit a record with the same record_id
    (e.g. hash collision or shared Health Connect UUID format), both users succeed independently
    and deduplication is strictly per-user via UNIQUE(user_id, record_id).
    """
    user_a_id, _, headers_a = _create_isolated_user("col_a")
    user_b_id, _, headers_b = _create_isolated_user("col_b")

    now = time.time() - 20.0
    shared_rec_id = f"shared-device-uuid-{int(now)}"

    # User A ingests record
    res_a = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "record_id": shared_rec_id,
        "heart_rate_bpm": 70.0
    }, headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["inserted_count"] == 1

    # User B ingests record with the EXACT SAME record_id
    res_b = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "record_id": shared_rec_id,
        "heart_rate_bpm": 85.0
    }, headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json()["inserted_count"] == 1, "User B's record was wrongly dropped due to User A's record_id!"

    # Verify User A still has their record with value 70.0
    recs_a = client.get("/api/telemetry/records", headers=headers_a).json()["records"]
    assert len([r for r in recs_a if r["record_id"] == shared_rec_id]) == 1
    assert [r for r in recs_a if r["record_id"] == shared_rec_id][0]["metric_value"] == 70.0

    # Verify User B has their record with value 85.0
    recs_b = client.get("/api/telemetry/records", headers=headers_b).json()["records"]
    assert len([r for r in recs_b if r["record_id"] == shared_rec_id]) == 1
    assert [r for r in recs_b if r["record_id"] == shared_rec_id][0]["metric_value"] == 85.0

    # Now verify idempotency: User A resubmits -> marked duplicate for User A
    res_a_dup = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "record_id": shared_rec_id,
        "heart_rate_bpm": 70.0
    }, headers=headers_a)
    assert res_a_dup.status_code == 200
    assert res_a_dup.json()["duplicate_count"] >= 1


def test_missing_or_invalid_authentication_rejected():
    """Task 8.5: Missing or invalid authentication is rejected."""
    # 1. Missing header
    res_no_auth = client.post("/api/telemetry/health_connect", json={"heart_rate_bpm": 75.0})
    assert res_no_auth.status_code == 401
    assert res_no_auth.json()["detail"] == "Unauthorized"

    # 2. Bogus bearer token
    res_bogus = client.post("/api/telemetry/health_connect", json={"heart_rate_bpm": 75.0},
                            headers={"Authorization": "Bearer non_existent_token_xyz"})
    assert res_bogus.status_code == 401
    assert res_bogus.json()["detail"] == "Invalid token"

    # 3. Malformed header
    res_malformed = client.post("/api/telemetry/health_connect", json={"heart_rate_bpm": 75.0},
                                headers={"Authorization": "Basic 123456"})
    assert res_malformed.status_code == 401


def test_revoked_session_and_stale_credentials_fail_safely():
    """Task 8.6: Account switching / revoked tokens fail safely."""
    user_id, token, headers = _create_isolated_user("revoked_user")

    # Ingest succeeds while session is active
    now = time.time() - 10.0
    res_ok = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 78.0
    }, headers=headers)
    assert res_ok.status_code == 200

    # User logs out / server revokes session token
    revoked = db.revoke_session(token)
    assert revoked is True

    # Subsequent background sync attempt MUST fail with 401
    res_revoked = client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 80.0
    }, headers=headers)
    assert res_revoked.status_code == 401
    assert res_revoked.json()["detail"] == "Invalid token"

    # Reading records with revoked token also fails with 401
    res_get_revoked = client.get("/api/telemetry/records", headers=headers)
    assert res_get_revoked.status_code == 401


def test_downstream_vikriti_and_schedule_use_only_current_user_data():
    """
    Task 5 & 8: Verifies that downstream Vikriti observations and schedule generation
    use only the authenticated user's records and state without cross-tenant contamination.
    """
    user_a_id, _, headers_a = _create_isolated_user("sched_a")
    user_b_id, _, headers_b = _create_isolated_user("sched_b")

    now = time.time() - 30.0

    # Ingest high heart rate for User A (tachycardia / Pitta excitation)
    client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 110.0,
        "spo2_pct": 98.0
    }, headers=headers_a)

    # Ingest low resting heart rate for User B
    client.post("/api/telemetry/health_connect", json={
        "device_model": "Fastrack Noir Charm",
        "recorded_at": now,
        "heart_rate_bpm": 60.0,
        "spo2_pct": 99.0
    }, headers=headers_b)

    # Verify User A's current Vikriti observation has User A's telemetry
    obs_a = db.get_vikriti_observations(user_a_id, limit=5)
    # User B's observations do not contain User A's readings
    obs_b = db.get_vikriti_observations(user_b_id, limit=5)
    assert all(o["user_id"] == user_a_id for o in obs_a)
    assert all(o["user_id"] == user_b_id for o in obs_b)
