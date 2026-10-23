import os
import json
import time
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

import main
import src.database.db as db
from src.llm_gateway import LLMGateway, LLMResponse
from src.models import DinacharyaSchedule, Practice, ScheduleProposal, ProposalActionRequest
from src.safety.guardrails import ClinicalRuleEngine
from src.planning.schedule_service import (
    resolve_practice_intent,
    formulate_canonical_proposal,
    apply_canonical_proposal,
    discard_canonical_proposal,
    mutate_user_schedule
)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Sets up an isolated SQLite database and deterministic LLM fallback for proposal sync tests."""
    test_db_path = str(tmp_path / "test_proposal_sync.db")
    monkeypatch.setenv("DINACHARYA_DB_PATH", test_db_path)
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db()

    # Deterministic offline mock for LLM gateway by default
    gateway = LLMGateway.get_instance()
    monkeypatch.setattr(
        gateway,
        "execute_tool_loop",
        lambda *args, **kwargs: LLMResponse(content="", model_used="offline-deterministic", is_fallback=True),
    )
    monkeypatch.setattr(
        gateway,
        "generate_structured_json",
        lambda fallback_fn=None, **kwargs: (fallback_fn() if fallback_fn else {}, True),
    )

    client = TestClient(main.app)
    return client


def _seed_test_user_schedule(username: str = "sync_user"):
    """
    Seeds a test user with the exact schedule from the user's reproduction context:
    - Mitahara: 12:00 - 12:40 (Midday meal)
    - Pranayama: 11:05 - 11:45 (Morning practice)
    - Light Early Dinner: 19:30 - 20:00 (Evening practice)
    """
    uid = db.create_user(username, "secure_pass_123")
    assert uid is not None
    token = db.create_session(uid)
    headers = {"Authorization": f"Bearer {token}"}
    db.update_user_questionnaire(uid, {"q1_agni": "sama", "q2_elimination": "regular"})

    today_str = datetime.now().strftime("%Y-%m-%d")
    canonical_schedule = {
        "user_id": str(uid),
        "adherence_score": 1.0,
        "routine_complexity": "Moderate",
        "morning_block": [
            {
                "name": "Brahma Muhurta Rising & Ushapan",
                "time_slot": "06:00 - 06:15",
                "duration_minutes": 15,
                "description": "Drink warm water.",
                "rationale": "Awakens peristalsis.",
            },
            {
                "name": "Nadi Shodhana Pranayama",
                "time_slot": "11:05 - 11:45",
                "duration_minutes": 40,
                "description": "Alternate nostril breathing.",
                "rationale": "Soothes nervous system.",
            }
        ],
        "midday_block": [
            {
                "name": "Mitahara Midday Meal",
                "time_slot": "12:00 - 12:40",
                "duration_minutes": 40,
                "description": "Nourishing mindful meal.",
                "rationale": "Jatharagni peak.",
            }
        ],
        "evening_block": [
            {
                "name": "Light Early Dinner",
                "time_slot": "19:30 - 20:00",
                "duration_minutes": 30,
                "description": "Easily digestible supper.",
                "rationale": "Supports restful sleep.",
            }
        ],
        "timestamp": time.time()
    }

    db_payload = {
        "schedule": canonical_schedule,
        "morning_block": canonical_schedule["morning_block"],
        "midday_block": canonical_schedule["midday_block"],
        "evening_block": canonical_schedule["evening_block"],
        "timestamp": time.time()
    }
    db.save_user_schedule(uid, db_payload, today_str)
    return uid, token, headers, canonical_schedule


# -----------------------------------------------------------------------------
# Test 1: Identical times in chat response data and planner payload
# -----------------------------------------------------------------------------
def test_post_meal_pranayama_proposal_identical_times(isolated_env):
    """
    Reproduction case: User asks 'can I do pranayama after my mitahara??'
    Mitahara: 12:00 - 12:40. Existing Pranayama: 11:05 - 11:45.
    Verifies that chat response and proposed_schedule return identical times (e.g. 15:40 - 16:20).
    """
    client = isolated_env
    uid, token, headers, initial_sched = _seed_test_user_schedule("user_identical_times")

    resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()

    # 1. Proposal object must exist
    proposal = data.get("proposal")
    assert proposal is not None, "Missing structured canonical proposal in chat response"
    assert proposal["target_practice"] == "Nadi Shodhana Pranayama"
    proposed_slot = proposal["proposed_time_slot"]

    # Must provide empty stomach gap (not 12:45)
    assert proposed_slot == "15:40 - 16:20"

    # 2. Planner proposed_schedule payload must show the exact same time
    proposed_schedule = data.get("proposed_schedule")
    assert proposed_schedule is not None, "Missing proposed_schedule payload"

    pranayama_tasks = [
        p for p in (
            proposed_schedule.get("morning_block", []) +
            proposed_schedule.get("midday_block", []) +
            proposed_schedule.get("evening_block", [])
        )
        if "Pranayama" in p.get("name", "")
    ]
    assert len(pranayama_tasks) == 1
    assert pranayama_tasks[0]["time_slot"] == proposed_slot, (
        f"Planner schedule ({pranayama_tasks[0]['time_slot']}) differs from structured proposal ({proposed_slot})"
    )

    # 3. Chat prose must accurately state the proposed slot
    chat_text = data["response"]
    assert proposed_slot in chat_text, f"Chat response text does not state the proposed slot {proposed_slot}"


# -----------------------------------------------------------------------------
# Test 2: Planner renders proposed time, not original time, in proposal state
# -----------------------------------------------------------------------------
def test_planner_renders_proposed_time_not_original(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_render_proposed")

    resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    data = resp.json()
    proposal = data["proposal"]
    proposed_sched = data["proposed_schedule"]

    # In proposal state, Pranayama time in proposed_schedule must NOT be the original 11:05 - 11:45
    # Cross-block relocation: 15:40 belongs to midday_block, not morning_block
    assert not any("Pranayama" in p["name"] for p in proposed_sched.get("morning_block", []))
    p_task = next(p for p in proposed_sched["midday_block"] if "Pranayama" in p["name"])
    assert p_task["time_slot"] != "11:05 - 11:45"
    assert p_task["time_slot"] == proposal["proposed_time_slot"]


# -----------------------------------------------------------------------------
# Test 3: Displayed current time remains distinguishable from proposed time
# -----------------------------------------------------------------------------
def test_distinguishable_current_vs_proposed_time(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_distinguishable")

    resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    data = resp.json()
    proposal = data["proposal"]

    assert proposal["original_time_slot"] == "11:05 - 11:45"
    assert proposal["proposed_time_slot"] == "15:40 - 16:20"
    assert proposal["original_time_slot"] != proposal["proposed_time_slot"]

    # Current database schedule must NOT have mutated yet
    state = db.get_user_state(uid)
    persisted_morning = state["last_schedule"]["schedule"]["morning_block"]
    persisted_pranayama = next(p for p in persisted_morning if "Pranayama" in p["name"])
    assert persisted_pranayama["time_slot"] == "11:05 - 11:45", "Current schedule was mutated prematurely!"


# -----------------------------------------------------------------------------
# Test 4: Apply & Synchronize persists exactly the proposed time
# -----------------------------------------------------------------------------
def test_apply_and_synchronize_persists_exact_proposed_time(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_apply_sync")

    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]
    proposal_id = proposal["proposal_id"]

    apply_resp = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal_id, "expected_schedule_version": proposal["schedule_version"]},
        headers=headers
    )
    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()
    assert apply_data["success"] is True

    # Check persisted SQLite database
    state = db.get_user_state(uid)
    # Cross-block relocation: Pranayama moved from morning_block to midday_block
    assert not any("Pranayama" in p["name"] for p in state["last_schedule"]["schedule"].get("morning_block", []))
    persisted_midday = state["last_schedule"]["schedule"]["midday_block"]
    persisted_pranayama = next(p for p in persisted_midday if "Pranayama" in p["name"])
    assert persisted_pranayama["time_slot"] == "15:40 - 16:20"


# -----------------------------------------------------------------------------
# Test 5: Keep Current leaves schedule and schedule timestamp unchanged
# -----------------------------------------------------------------------------
def test_keep_current_leaves_schedule_and_timestamp_unchanged(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_keep_current")

    state_before = db.get_user_state(uid)
    t_before = state_before["schedule_timestamp"]

    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]
    proposal_id = proposal["proposal_id"]

    discard_resp = client.post(
        "/api/schedule/proposal/discard",
        json={"proposal_id": proposal_id},
        headers=headers
    )
    assert discard_resp.status_code == 200
    assert discard_resp.json()["success"] is True

    state_after = db.get_user_state(uid)
    t_after = state_after["schedule_timestamp"]
    assert t_after == t_before

    persisted_morning = state_after["last_schedule"]["schedule"]["morning_block"]
    persisted_pranayama = next(p for p in persisted_morning if "Pranayama" in p["name"])
    assert persisted_pranayama["time_slot"] == "11:05 - 11:45"


# -----------------------------------------------------------------------------
# Test 6: A rejected or contraindicated proposal cannot be applied
# -----------------------------------------------------------------------------
def test_rejected_or_contraindicated_proposal_cannot_be_applied(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_contraindicated")

    # Manually formulate a contraindicated proposal (Pranayama immediately after Mitahara at 12:45)
    prop_bad = {
        "proposal_id": f"prop_bad_{uid}",
        "user_id": str(uid),
        "target_practice": "Nadi Shodhana Pranayama",
        "original_time_slot": "11:05 - 11:45",
        "proposed_time_slot": "12:45 - 13:25",
        "target_block": "midday_block",
        "schedule_version": db.get_user_state(uid)["schedule_timestamp"],
        "status": "pending_user_confirmation",
        "rationale": "Test post-meal unsafe slot",
        "clinical_explanation": "Violates Bhuktavastu empty-stomach rule",
        "violated_principles": ["Bhuktavastu"],
        "recommended_alternatives": [],
        "is_valid": False,  # Contraindicated!
        "created_at": time.time()
    }
    db.save_schedule_proposal(prop_bad)

    apply_resp = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": prop_bad["proposal_id"]},
        headers=headers
    )
    # Must reject application
    assert apply_resp.status_code in [400, 409]
    assert "contraindicated" in apply_resp.json()["detail"].lower() or "clinical validation failed" in apply_resp.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Test 7: Stale proposals cannot overwrite a newer schedule
# -----------------------------------------------------------------------------
def test_stale_proposals_cannot_overwrite_newer_schedule(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_stale_guard")

    # Step 1: Create proposal
    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]

    # Step 2: Underlying schedule changes in the interim (e.g. user moved dinner)
    time.sleep(0.01)
    mutate_user_schedule(uid, {"Light Early Dinner": "20:00 - 20:30"})

    # Step 3: Attempt to apply the earlier proposal (which now has stale schedule_version)
    apply_resp = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"], "expected_schedule_version": proposal["schedule_version"]},
        headers=headers
    )
    assert apply_resp.status_code == 409
    assert "stale" in apply_resp.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Test 8: Duplicate acceptance does not create duplicate mutations
# -----------------------------------------------------------------------------
def test_duplicate_acceptance_prevented(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_duplicate_accept")

    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]

    # First apply: succeeds
    res1 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"]},
        headers=headers
    )
    assert res1.status_code == 200

    # Second apply: blocked
    res2 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"]},
        headers=headers
    )
    assert res2.status_code == 409
    assert "already been applied" in res2.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Test 9: A proposal naming one practice cannot accidentally modify another
# -----------------------------------------------------------------------------
def test_proposal_strictly_modifies_target_practice(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_unrelated_safe")

    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]

    client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"]},
        headers=headers
    )

    state = db.get_user_state(uid)
    sched = state["last_schedule"]["schedule"]

    # Pranayama moved across block boundaries from morning to midday
    assert not any("Pranayama" in p["name"] for p in sched.get("morning_block", []))
    pranayama = next(p for p in sched["midday_block"] if "Pranayama" in p["name"])
    assert pranayama["time_slot"] == "15:40 - 16:20"

    # All other practices preserved exactly
    ushapan = next(p for p in sched["morning_block"] if "Ushapan" in p["name"])
    assert ushapan["time_slot"] == "06:00 - 06:15"

    mitahara = next(p for p in sched["midday_block"] if "Mitahara" in p["name"])
    assert mitahara["time_slot"] == "12:00 - 12:40"

    dinner = next(p for p in sched["evening_block"] if "Dinner" in p["name"])
    assert dinner["time_slot"] == "19:30 - 20:00"


# -----------------------------------------------------------------------------
# Test 10: Prose and proposal disagreement handling
# -----------------------------------------------------------------------------
def test_prose_and_proposal_harmony_invariant(isolated_env):
    """
    Verifies that when a canonical proposal is formulated, the assistant prose returned
    is harmonized so that it always includes the canonical proposal time slot.
    """
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_prose_harmony")

    resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    data = resp.json()
    assert data["proposal"] is not None
    proposed_slot = data["proposal"]["proposed_time_slot"]
    chat_response = data["response"]

    assert proposed_slot in chat_response


# -----------------------------------------------------------------------------
# Test 11: Missing or malformed proposal data fails safely
# -----------------------------------------------------------------------------
def test_malformed_proposal_data_fails_safely(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_malformed")

    # Non-existent proposal ID
    res1 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": "non_existent_proposal_999"},
        headers=headers
    )
    assert res1.status_code == 404

    # Unauthorized access (user trying to apply another user's proposal)
    other_uid = db.create_user("other_user", "pass_other")
    prop_other = {
        "proposal_id": "prop_other_user_1",
        "user_id": str(other_uid),
        "target_practice": "Light Early Dinner",
        "original_time_slot": "19:30 - 20:00",
        "proposed_time_slot": "20:00 - 20:30",
        "target_block": "evening_block",
        "schedule_version": 100.0,
        "status": "pending_user_confirmation",
        "rationale": "",
        "clinical_explanation": "",
        "violated_principles": [],
        "recommended_alternatives": [],
        "is_valid": True,
        "created_at": time.time()
    }
    db.save_schedule_proposal(prop_other)

    res2 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": "prop_other_user_1"},
        headers=headers
    )
    assert res2.status_code == 403


# -----------------------------------------------------------------------------
# Test 12: UI refreshes from persisted backend response after successful apply
# -----------------------------------------------------------------------------
def test_ui_and_api_schedule_refresh_from_canonical_backend(isolated_env):
    client = isolated_env
    uid, token, headers, _ = _seed_test_user_schedule("user_refresh_test")

    chat_resp = client.post(
        "/api/chat",
        json={"message": "can I do pranayama after my mitahara??"},
        headers=headers
    )
    proposal = chat_resp.json()["proposal"]

    apply_resp = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"]},
        headers=headers
    )
    assert apply_resp.status_code == 200
    returned_schedule = apply_resp.json()["schedule"]

    # Verify endpoint GET /api/schedule/current returns the exact saved state
    current_resp = client.get("/api/schedule/current", headers=headers)
    assert current_resp.status_code == 200
    current_data = current_resp.json()["schedule"]

    # The persisted and returned schedules match exactly and reflect cross-block relocation to midday_block
    assert not any("Pranayama" in p["name"] for p in returned_schedule.get("morning_block", []))
    assert not any("Pranayama" in p["name"] for p in current_data.get("morning_block", []))
    ret_p = next(p for p in returned_schedule["midday_block"] if "Pranayama" in p["name"])
    curr_p = next(p for p in current_data["midday_block"] if "Pranayama" in p["name"])
    assert ret_p["time_slot"] == "15:40 - 16:20"
    assert curr_p["time_slot"] == "15:40 - 16:20"


# -----------------------------------------------------------------------------
# Live NIM Test: Opt-in end-to-end integration test with real NIM model
# -----------------------------------------------------------------------------
def test_live_nim_proposal_synchronization():
    """
    Opt-in live NIM end-to-end test.
    Run with: RUN_LIVE_NIM=1 pytest tests/test_proposal_synchronization.py -k test_live_nim
    Verifies live NIM model integration with structured proposal and isolated database.
    """
    if os.getenv("RUN_LIVE_NIM") != "1":
        pytest.skip("Opt-in live NIM test. Set RUN_LIVE_NIM=1 to execute.")

    # Use a temporary isolated database
    import tempfile
    temp_db_fd, temp_db_path = tempfile.mkstemp(prefix="live_nim_sync_test_", suffix=".db")
    os.close(temp_db_fd)
    os.environ["DINACHARYA_DB_PATH"] = temp_db_path

    try:
        db.init_db()
        client = TestClient(main.app)
        uid, token, headers, initial_sched = _seed_test_user_schedule("live_nim_user")

        # Step 1: Send message through live agent
        resp = client.post(
            "/api/chat",
            json={"message": "can I do pranayama after my mitahara??"},
            headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()

        proposal = data.get("proposal")
        proposed_schedule = data.get("proposed_schedule")
        chat_text = data.get("response", "")

        assert proposal is not None
        assert proposed_schedule is not None
        assert proposal["target_practice"] == "Nadi Shodhana Pranayama"

        # Step 2: Database before acceptance is untouched
        db_before = db.get_user_state(uid)["last_schedule"]["schedule"]
        p_before = next(p for p in db_before["morning_block"] if "Pranayama" in p["name"])
        assert p_before["time_slot"] == "11:05 - 11:45"

        # Step 3: Apply proposal
        apply_resp = client.post(
            "/api/schedule/proposal/apply",
            json={"proposal_id": proposal["proposal_id"]},
            headers=headers
        )
        assert apply_resp.status_code == 200

        # Step 4: Database after acceptance is updated to proposed time in midday_block
        db_after = db.get_user_state(uid)["last_schedule"]["schedule"]
        assert not any("Pranayama" in p["name"] for p in db_after.get("morning_block", []))
        p_after = next(p for p in db_after["midday_block"] if "Pranayama" in p["name"])
        assert p_after["time_slot"] == proposal["proposed_time_slot"]

        # Step 5: Unrelated practices remain unchanged
        mitahara_after = next(p for p in db_after["midday_block"] if "Mitahara" in p["name"])
        assert mitahara_after["time_slot"] == "12:00 - 12:40"

    finally:
        os.environ.pop("DINACHARYA_DB_PATH", None)
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
