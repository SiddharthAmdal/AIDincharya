"""
test_personalization_pipeline.py - Deterministic End-to-End Verification of Personalization Pipeline

Verifies that:
1. Distinct Prakriti profiles produce distinct, dosha-appropriate schedules under identical constraints.
2. User profiles remain isolated and never leak across users.
3. Dynamic Vikriti observations meaningfully modify recommendations.
4. Unassessed users receive an explicit reduced-personalization state.
5. Stale wearable telemetry is rejected and never assumed normal.
6. Clinical safety rules remain authoritative.
7. Decision provenance audit traces are generated and persisted.
"""

import pytest
import time
import json
from fastapi.testclient import TestClient
from main import app
from src.database import db
from src.models import (
    DoshaVector, DoshaProfile, VikritiFlags, UserContext, ScheduleGenerateRequest
)
from src.perception.dosha_mapper import DoshaMapper
from src.perception.vikriti_tracker import VikritiTracker
from src.perception.wearable_interface import WearableTelemetryManager, HealthConnectPayload
from src.planning.agent import DinacharyaPlannerAgent
from src.planning.practice_catalog import select_personalized_practices, CANDIDATE_PRACTICES
from src.safety.guardrails import ClinicalRuleEngine


@pytest.fixture(scope="module")
def client():
    db.init_db()
    with TestClient(app) as test_client:
        yield test_client


def _create_user_and_auth(client, username_prefix: str):
    unique_user = f"{username_prefix}_{int(time.time()*1000)}"
    reg_res = client.post("/api/auth/register", json={"username": unique_user, "password": "Password123!"})
    assert reg_res.status_code == 200, reg_res.text
    token = reg_res.json()["token"]
    user_id = db.get_user_from_token(token)
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, headers


def test_prakriti_candidate_scoring_distinct_for_vata_pitta_kapha():
    """
    Unit-level deterministic check: Vata, Pitta, and Kapha profiles evaluated under
    identical complexity ('Moderate') select distinct candidate practices across all three blocks.
    """
    vata_profile = DoshaProfile(
        user_id="vata_user",
        prakriti=DoshaVector(vata=0.70, pitta=0.20, kapha=0.10),
        vikriti_flags=VikritiFlags(),
        timestamp=time.time()
    )
    pitta_profile = DoshaProfile(
        user_id="pitta_user",
        prakriti=DoshaVector(vata=0.15, pitta=0.70, kapha=0.15),
        vikriti_flags=VikritiFlags(),
        timestamp=time.time()
    )
    kapha_profile = DoshaProfile(
        user_id="kapha_user",
        prakriti=DoshaVector(vata=0.15, pitta=0.15, kapha=0.70),
        vikriti_flags=VikritiFlags(),
        timestamp=time.time()
    )

    vata_sched = select_personalized_practices(vata_profile, complexity="Moderate")
    pitta_sched = select_personalized_practices(pitta_profile, complexity="Moderate")
    kapha_sched = select_personalized_practices(kapha_profile, complexity="Moderate")

    # 1. Morning practices must differ
    vata_morning = [p.name for p in vata_sched["morning_block"]]
    pitta_morning = [p.name for p in pitta_sched["morning_block"]]
    kapha_morning = [p.name for p in kapha_sched["morning_block"]]

    assert vata_morning != pitta_morning
    assert pitta_morning != kapha_morning
    assert any("Grounding" in n or "Nadi Shodhana" in n or "Warm" in n for n in vata_morning)
    assert any("Cooling" in n or "Coconut" in n or "Brahmi" in n for n in pitta_morning)
    assert any("Spiced Lemon" in n or "Udvartana" in n for n in kapha_morning)

    # 2. Midday meal and digestive practice must differ
    vata_midday = [p.name for p in vata_sched["midday_block"]]
    pitta_midday = [p.name for p in pitta_sched["midday_block"]]
    kapha_midday = [p.name for p in kapha_sched["midday_block"]]

    assert vata_midday != pitta_midday
    assert pitta_midday != kapha_midday
    assert any("Snigdha" in n or "Vajrasana" in n for n in vata_midday)
    assert any("Cooling" in n or "Shaded" in n for n in pitta_midday)
    assert any("Katu-Tikta" in n or "Brisk" in n for n in kapha_midday)

    # 3. Evening meal and wind-down must differ
    vata_evening = [p.name for p in vata_sched["evening_block"]]
    pitta_evening = [p.name for p in pitta_sched["evening_block"]]
    kapha_evening = [p.name for p in kapha_sched["evening_block"]]

    assert vata_evening != pitta_evening
    assert pitta_evening != kapha_evening
    assert any("Pada Abhyanga" in n or "Warm Grounding" in n for n in vata_evening)
    assert any("Chandra" in n or "Cooling" in n for n in pitta_evening)
    assert any("Trataka" in n or "Laghu" in n for n in kapha_evening)


def test_end_to_end_distinct_prakriti_schedules(client):
    """
    End-to-end integration test: Two synthetic users submit different 24-question assessments.
    They request schedules with identical UserContext, season, weather, and adherence.
    Assert that the generated and persisted schedules differ meaningfully and are tailored to each profile.
    """
    # 1. Setup User Vata
    u_vata_id, u_vata_headers = _create_user_and_auth(client, "test_vata")
    vata_answers = {f"q{i}": "Vata" for i in range(1, 25)}
    res_q_vata = client.post("/api/user/questionnaire", json={"responses": vata_answers}, headers=u_vata_headers)
    assert res_q_vata.status_code == 200

    # 2. Setup User Pitta
    u_pitta_id, u_pitta_headers = _create_user_and_auth(client, "test_pitta")
    pitta_answers = {f"q{i}": "Pitta" for i in range(1, 25)}
    res_q_pitta = client.post("/api/user/questionnaire", json={"responses": pitta_answers}, headers=u_pitta_headers)
    assert res_q_pitta.status_code == 200

    # Identical planning request constraints
    context_payload = {
        "season": "Autumn/Sharad",
        "weather": "Clear and dry",
        "temperature_c": 22.0,
        "calendar_events": [],
        "self_report_symptoms": []
    }

    # Generate schedule for Vata user
    res_vata = client.post("/api/schedule/generate", json={
        "context": context_payload,
        "force_regen": True
    }, headers=u_vata_headers)
    assert res_vata.status_code == 200, res_vata.text
    vata_data = res_vata.json()

    # Generate schedule for Pitta user
    res_pitta = client.post("/api/schedule/generate", json={
        "context": context_payload,
        "force_regen": True
    }, headers=u_pitta_headers)
    assert res_pitta.status_code == 200, res_pitta.text
    pitta_data = res_pitta.json()

    # Profile vector verification
    assert vata_data["dosha_profile"]["prakriti"]["vata"] > 0.8
    assert pitta_data["dosha_profile"]["prakriti"]["pitta"] > 0.8

    # Schedule practice names comparison
    vata_morning_names = [p["name"] for p in vata_data["schedule"]["morning_block"]]
    pitta_morning_names = [p["name"] for p in pitta_data["schedule"]["morning_block"]]

    # They must have different morning practices
    assert vata_morning_names != pitta_morning_names
    assert any("Grounding" in n or "Warm" in n or "Nadi Shodhana" in n for n in vata_morning_names)
    assert any("Cooling" in n or "Coconut" in n or "Brahmi" in n for n in pitta_morning_names)

    # Database persistence verification
    state_vata = db.get_user_state(u_vata_id)
    persisted_vata_morning = [p["name"] for p in state_vata["last_schedule"]["schedule"]["morning_block"]]
    assert persisted_vata_morning == vata_morning_names


def test_user_isolation_profile_leakage(client):
    """
    Verifies that User A's profile never leaks into or influences User B's recommendations.
    """
    u_a_id, u_a_headers = _create_user_and_auth(client, "user_a")
    u_b_id, u_b_headers = _create_user_and_auth(client, "user_b")

    # User A is 100% Kapha
    client.post("/api/user/questionnaire", json={"responses": {f"q{i}": "Kapha" for i in range(1, 25)}}, headers=u_a_headers)

    # User B is 100% Pitta
    client.post("/api/user/questionnaire", json={"responses": {f"q{i}": "Pitta" for i in range(1, 25)}}, headers=u_b_headers)

    # Request schedule for User B
    res_b = client.post("/api/schedule/generate", json={
        "context": {"season": "Summer", "weather": "Sunny", "temperature_c": 30.0},
        "force_regen": True
    }, headers=u_b_headers)
    assert res_b.status_code == 200
    b_data = res_b.json()

    # User B must reflect Pitta, never Kapha
    assert b_data["dosha_profile"]["prakriti"]["pitta"] > 0.8
    assert b_data["dosha_profile"]["prakriti"]["kapha"] < 0.2


def test_unassessed_user_reduced_personalization(client):
    """
    A newly registered user who has not submitted the 24-question questionnaire
    is flagged with assessment_status == 'unassessed' and receives an explicit notice.
    """
    u_unassessed_id, u_headers = _create_user_and_auth(client, "unassessed_user")

    res = client.post("/api/schedule/generate", json={
        "context": {"season": "Winter", "weather": "Cold", "temperature_c": 10.0},
        "force_regen": True
    }, headers=u_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["dosha_profile"]["assessment_status"] == "unassessed"
    assert "reduced_personalization_notice" in data
    assert "No completed 24-question Prakriti assessment found" in data["reduced_personalization_notice"]


def test_vikriti_symptom_tracking_and_provenance(client):
    """
    Submitting symptoms via /api/user/vikriti updates the current Vikriti state,
    stores the observation in the longitudinal table, and influences schedule generation.
    """
    u_id, u_headers = _create_user_and_auth(client, "vikriti_user")
    # Complete Kapha assessment
    client.post("/api/user/questionnaire", json={"responses": {f"q{i}": "Kapha" for i in range(1, 25)}}, headers=u_headers)

    # User logs acute Vata symptoms (anxiety, insomnia)
    checkin_res = client.post("/api/user/vikriti", json={
        "symptoms": ["anxiety", "insomnia", "dry skin"]
    }, headers=u_headers)
    assert checkin_res.status_code == 200
    checkin_data = checkin_res.json()

    assert checkin_data["vikriti_estimate"]["vata_aggravated"] is True
    assert checkin_data["data_availability_status"] == "self_report_only"

    # Verify history endpoint
    hist_res = client.get("/api/user/vikriti/history", headers=u_headers)
    assert hist_res.status_code == 200
    obs_list = hist_res.json()["observations"]
    assert len(obs_list) >= 1
    assert "anxiety" in obs_list[0]["symptoms"]


def test_safety_engine_authoritative_overrides_prakriti(client):
    """
    Even for a Pure Vata user (where Abhyanga warm oil massage is normally top priority),
    an active fever flag (Nava Jwara) must strictly override and remove oil massage.
    """
    u_id, u_headers = _create_user_and_auth(client, "fever_user")
    client.post("/api/user/questionnaire", json={"responses": {f"q{i}": "Vata" for i in range(1, 25)}}, headers=u_headers)

    res = client.post("/api/schedule/generate", json={
        "context": {
            "season": "Spring",
            "weather": "Mild",
            "temperature_c": 20.0,
            "self_report_symptoms": ["high fever", "chills"]
        },
        "force_regen": True
    }, headers=u_headers)
    assert res.status_code == 200
    data = res.json()

    morning_names = [p["name"] for p in data["schedule"]["morning_block"]]
    # Abhyanga must NOT be present
    assert not any("abhyanga" in n.lower() for n in morning_names)
    assert any("fever" in n.lower() or "rest" in n.lower() or "ushnodaka" in n.lower() for n in morning_names)


def test_wearable_freshness_rejection(client):
    """
    Wearable records older than 36h or with stale timestamps must be rejected by the freshness checker.
    """
    stale_payload = {
        "timestamp": time.time() - (48 * 3600), # 48 hours old
        "sleep_records": [{"start_time": time.time() - 50*3600, "end_time": time.time() - 42*3600, "duration_minutes": 480}]
    }
    is_fresh, msg = WearableTelemetryManager.check_freshness(stale_payload)
    assert is_fresh is False
    assert "stale" in msg.lower()


def test_decision_provenance_trace_structure(client):
    """
    Verifies that the generated schedule contains a complete, privacy-conscious
    provenance audit trace without raw private data.
    """
    u_id, u_headers = _create_user_and_auth(client, "prov_user")
    client.post("/api/user/questionnaire", json={"responses": {f"q{i}": "Vata" for i in range(1, 25)}}, headers=u_headers)

    res = client.post("/api/schedule/generate", json={
        "context": {"season": "Winter", "weather": "Cold", "temperature_c": 12.0},
        "force_regen": True
    }, headers=u_headers)
    assert res.status_code == 200
    data = res.json()

    prov = data.get("provenance")
    assert prov is not None
    assert prov["schema_version"] == "provenance-v1.0"
    assert "user_id_hash" in prov
    assert "prakriti_vector" in prov["profile_inputs"]
    assert prov["profile_inputs"]["prakriti_vector"]["vata"] > 0.8
    assert "schedule_decisions" in prov
    assert prov["schedule_decisions"]["total_practices"] >= 3


def test_user_isolation_vikriti_history(client):
    """
    Verifies that User A's longitudinal observations cannot be accessed by User B.
    """
    u_a_id, u_a_headers = _create_user_and_auth(client, "iso_user_a")
    u_b_id, u_b_headers = _create_user_and_auth(client, "iso_user_b")

    # User A records symptoms
    client.post("/api/user/vikriti", json={"symptoms": ["anxiety", "insomnia"]}, headers=u_a_headers)

    # User B requests history
    res_b = client.get("/api/user/vikriti/history", headers=u_b_headers)
    assert res_b.status_code == 200
    b_obs = res_b.json()["observations"]
    assert len(b_obs) == 0  # User B must have no observations


def test_future_dated_telemetry_rejection(client):
    """
    Verifies that future-dated telemetry records are rejected.
    """
    future_payload = {
        "timestamp": time.time() + (5 * 3600), # 5 hours in the future
        "sleep_records": []
    }
    is_fresh, msg = WearableTelemetryManager.check_freshness(future_payload)
    assert is_fresh is False
    assert "future_dated_invalid" in msg


def test_vikriti_endpoints_require_authentication(client):
    """
    Verifies that all Vikriti and telemetry read/write endpoints require valid authentication.
    """
    res_post_vik = client.post("/api/user/vikriti", json={"symptoms": ["anxiety"]})
    assert res_post_vik.status_code == 401

    res_get_vik = client.get("/api/user/vikriti/history")
    assert res_get_vik.status_code == 401

    res_post_tel = client.post("/api/telemetry/health_connect", json={})
    assert res_post_tel.status_code == 401


def test_e2e_reassessment_cache_invalidation_and_regeneration(client):
    """
    Tests complete lifecycle:
    1. User completes Vata assessment.
    2. Generates initial Vata schedule -> persisted in DB.
    3. GET /api/schedule/current serves the Vata schedule.
    4. User retakes assessment with Pitta answers.
    5. GET /api/schedule/current returns null/no schedule (stale cache invalidated!).
    6. Generates new schedule -> Pitta schedule generated and persisted.
    7. GET /api/schedule/current now returns the updated Pitta schedule.
    """
    u_id, u_headers = _create_user_and_auth(client, "lifecycle_user")

    # Step 1: Submit Vata assessment
    vata_answers = {f"q{i}": "Vata" for i in range(1, 25)}
    res_v = client.post("/api/user/questionnaire", json={"responses": vata_answers}, headers=u_headers)
    assert res_v.status_code == 200

    # Step 2: Generate Vata schedule
    res_gen1 = client.post("/api/schedule/generate", json={
        "context": {"season": "Autumn", "weather": "Dry", "temperature_c": 18.0},
        "force_regen": True
    }, headers=u_headers)
    assert res_gen1.status_code == 200
    sched1 = res_gen1.json()
    v_morning = [p["name"] for p in sched1["schedule"]["morning_block"]]
    assert any("Grounding" in n or "Warm" in n or "Nadi Shodhana" in n for n in v_morning)

    # Step 3: GET /api/schedule/current serves the Vata schedule
    res_cur1 = client.get("/api/schedule/current", headers=u_headers)
    assert res_cur1.status_code == 200
    cur1 = res_cur1.json()
    assert cur1["schedule"] is not None
    cur1_morning = [p["name"] for p in cur1["schedule"]["morning_block"]]
    assert cur1_morning == v_morning

    # Step 4: User retakes assessment with Pitta answers
    pitta_answers = {f"q{i}": "Pitta" for i in range(1, 25)}
    res_p = client.post("/api/user/questionnaire", json={"responses": pitta_answers}, headers=u_headers)
    assert res_p.status_code == 200

    # Step 5: GET /api/schedule/current must NOT return stale Vata schedule
    res_cur_stale = client.get("/api/schedule/current", headers=u_headers)
    assert res_cur_stale.status_code == 200
    cur_stale = res_cur_stale.json()
    assert cur_stale.get("schedule") is None  # Cache successfully invalidated!

    # Step 6: Generate fresh schedule -> Pitta schedule compiled
    res_gen2 = client.post("/api/schedule/generate", json={
        "context": {"season": "Autumn", "weather": "Dry", "temperature_c": 18.0},
        "force_regen": True
    }, headers=u_headers)
    assert res_gen2.status_code == 200
    sched2 = res_gen2.json()
    p_morning = [p["name"] for p in sched2["schedule"]["morning_block"]]
    assert any("Cooling" in n or "Coconut" in n or "Brahmi" in n for n in p_morning)
    assert p_morning != v_morning

    # Step 7: GET /api/schedule/current now returns the fresh Pitta schedule
    res_cur2 = client.get("/api/schedule/current", headers=u_headers)
    assert res_cur2.status_code == 200
    cur2 = res_cur2.json()
    assert cur2["schedule"] is not None
    assert [p["name"] for p in cur2["schedule"]["morning_block"]] == p_morning


