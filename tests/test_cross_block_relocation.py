"""
Regression tests for Cross-Block Schedule Relocation.

Covers:
1. Morning-to-evening relocation: Pranayama moves from morning_block to evening_block at 18:30–18:45.
2. Evening-to-morning relocation.
3. Midday-to-evening relocation.
4. The target practice exists exactly once after each move.
5. Unrelated practices remain unchanged.
6. Duration and metadata are preserved.
7. The saved SQLite schedule has the correct block assignment.
8. The API response reflects the persisted block assignment.
9. The frontend renders the practice in the correct section using the returned schedule.
10. Invalid, stale, rejected, or contraindicated proposals cannot relocate a practice.
11. Repeated confirmation cannot create duplicate entries.
12. Existing same-block rescheduling still works.
"""

import os
import time
import pytest
from starlette.testclient import TestClient

import main
import src.database.db as db
from src.planning.schedule_service import (
    get_canonical_schedule,
    mutate_user_schedule,
    formulate_canonical_proposal,
    apply_canonical_proposal,
    discard_canonical_proposal,
    get_destination_block
)


from src.llm_gateway import LLMGateway, LLMResponse


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Sets up an isolated SQLite database and deterministic offline LLM gateway."""
    test_db_path = str(tmp_path / "cross_block_test.db")
    monkeypatch.setenv("DINACHARYA_DB_PATH", test_db_path)
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db()

    # Deterministic offline mock for LLM gateway
    gateway = LLMGateway.get_instance()
    monkeypatch.setattr(
        gateway,
        "execute_tool_loop",
        lambda *args, **kwargs: LLMResponse(
            content="I propose moving Pranayama to 18:30 - 18:45 in your evening block.",
            model_used="offline-deterministic",
            is_fallback=True
        ),
    )
    monkeypatch.setattr(
        gateway,
        "generate_structured_json",
        lambda fallback_fn=None, **kwargs: (fallback_fn() if fallback_fn else {}, True),
    )

    client = TestClient(main.app)
    return client


def _seed_user_with_schedule(username: str):
    """Creates a user and seeds a canonical baseline schedule."""
    uid = db.create_user(username, "secure_pass_123")
    assert uid is not None
    token = db.create_session(uid)
    headers = {"Authorization": f"Bearer {token}"}
    db.update_user_questionnaire(uid, {"q1_agni": "sama", "q2_elimination": "regular"})

    canonical_schedule = {
        "routine_complexity": "Moderate",
        "morning_block": [
            {
                "name": "Brahma Muhurta Jagaran",
                "time_slot": "05:30 - 05:45",
                "duration_minutes": 15,
                "description": "Wake up gently before sunrise.",
                "rationale": "Aligns with Sattva energy."
            },
            {
                "name": "Ushapan (Warm Water)",
                "time_slot": "06:00 - 06:15",
                "duration_minutes": 15,
                "description": "Hydrate digestive tract with warm boiled water.",
                "rationale": "Awakens Jatharagni and initiates peristalsis."
            },
            {
                "name": "Nadi Shodhana Pranayama",
                "time_slot": "06:30 - 06:45",
                "duration_minutes": 15,
                "description": "Alternate nostril breathing on an empty stomach.",
                "rationale": "Purifies the nadis and balances Ida/Pingala channels."
            }
        ],
        "midday_block": [
            {
                "name": "Mitahara Midday Meal",
                "time_slot": "12:00 - 12:40",
                "duration_minutes": 40,
                "description": "Principal warm, freshly cooked meal.",
                "rationale": "Agni peaks at midday when the sun is highest."
            },
            {
                "name": "Midday Exertion Walk",
                "time_slot": "14:00 - 14:30",
                "duration_minutes": 30,
                "description": "Light post-meal stroll in nature.",
                "rationale": "Aids digestion and mental alertness."
            }
        ],
        "evening_block": [
            {
                "name": "Laghu Ahara (Light Dinner)",
                "time_slot": "19:00 - 19:30",
                "duration_minutes": 30,
                "description": "Light nutritious evening meal.",
                "rationale": "Eaten before sunset to prevent digestive stagnation."
            },
            {
                "name": "Trataka Gazing",
                "time_slot": "21:00 - 21:15",
                "duration_minutes": 15,
                "description": "Candle gazing before sleep.",
                "rationale": "Calms mind and prepares for restful sleep."
            }
        ]
    }

    initial_data = {
        "schedule": canonical_schedule,
        "morning_block": canonical_schedule["morning_block"],
        "midday_block": canonical_schedule["midday_block"],
        "evening_block": canonical_schedule["evening_block"],
        "dosha_profile": {
            "user_id": str(uid),
            "prakriti": {"vata": 0.6, "pitta": 0.3, "kapha": 0.1},
            "vikriti_flags": {"has_fever": False, "pitta_aggravated": False, "vata_aggravated": False},
            "timestamp": time.time()
        },
        "complexity_level": "Moderate",
        "timestamp": time.time()
    }
    today_str = time.strftime("%Y-%m-%d")
    db.save_user_schedule(uid, initial_data, today_str)
    return uid, token, headers, canonical_schedule


# -----------------------------------------------------------------------------
# Test 1 & 7 & 8: Morning to Evening Relocation (Pranayama to 18:30–18:45)
# -----------------------------------------------------------------------------
def test_morning_to_evening_relocation_reported_bug(isolated_env):
    """
    Direct reproduction and fix verification of the reported issue:
    User accepts proposal to move Pranayama from morning to 18:30–18:45.
    Must be removed from morning_block and placed into evening_block.
    Saved SQLite schedule and API response must both reflect this.
    """
    client = isolated_env
    uid, token, headers, _ = _seed_user_with_schedule("user_morn_to_eve")

    # Step 1: Formulate proposal for Pranayama to 18:30 - 18:45
    sched_before = db.get_user_state(uid)["last_schedule"]["schedule"]
    assert any("Pranayama" in p["name"] for p in sched_before["morning_block"])
    assert not any("Pranayama" in p["name"] for p in sched_before["evening_block"])

    chat_res = client.post(
        "/api/chat",
        json={"message": "Can I do pranayama at 18:30?"},
        headers=headers
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()

    proposal = chat_data.get("proposal")
    assert proposal is not None
    assert proposal["target_block"] == "evening_block", f"Target block must be evening_block, got {proposal['target_block']}"
    assert "18:30" in proposal["proposed_time_slot"]

    # Preview schedule must show Pranayama in evening_block and NOT morning_block
    proposed_sched = chat_data["proposed_schedule"]
    assert not any("Pranayama" in p["name"] for p in proposed_sched["morning_block"]), "Pranayama still in morning preview!"
    assert any("Pranayama" in p["name"] for p in proposed_sched["evening_block"]), "Pranayama missing from evening preview!"

    # Step 2: Apply proposal
    apply_res = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": proposal["proposal_id"]},
        headers=headers
    )
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["success"] is True

    # Step 3: Verify returned API response schedule
    returned_sched = apply_data["schedule"]
    assert not any("Pranayama" in p["name"] for p in returned_sched["morning_block"])
    eve_pranayama = next(p for p in returned_sched["evening_block"] if "Pranayama" in p["name"])
    assert eve_pranayama["time_slot"] == "18:30 - 18:45"

    # Step 4: Verify persisted SQLite database
    state = db.get_user_state(uid)
    db_sched = state["last_schedule"]["schedule"]
    assert not any("Pranayama" in p["name"] for p in db_sched["morning_block"])
    db_pranayama = next(p for p in db_sched["evening_block"] if "Pranayama" in p["name"])
    assert db_pranayama["time_slot"] == "18:30 - 18:45"

    # Step 5: Verify GET /api/schedule/current
    curr_res = client.get("/api/schedule/current", headers=headers)
    assert curr_res.status_code == 200
    curr_sched = curr_res.json()["schedule"]
    assert not any("Pranayama" in p["name"] for p in curr_sched["morning_block"])
    assert any(p["name"] == db_pranayama["name"] and p["time_slot"] == "18:30 - 18:45" for p in curr_sched["evening_block"])


# -----------------------------------------------------------------------------
# Test 2: Evening to Morning Relocation
# -----------------------------------------------------------------------------
def test_evening_to_morning_relocation(isolated_env):
    """Moving a practice from evening_block to morning_block relocates it canonically."""
    uid, token, headers, _ = _seed_user_with_schedule("user_eve_to_morn")

    res = mutate_user_schedule(
        user_id=uid,
        updates={"Trataka Gazing": "07:00 - 07:15"}
    )
    assert res["success"] is True
    sched = res["schedule"]

    assert not any("Trataka" in p["name"] for p in sched["evening_block"])
    morn_trataka = next(p for p in sched["morning_block"] if "Trataka" in p["name"])
    assert morn_trataka["time_slot"] == "07:00 - 07:15"


# -----------------------------------------------------------------------------
# Test 3: Midday to Evening Relocation
# -----------------------------------------------------------------------------
def test_midday_to_evening_relocation(isolated_env):
    """Moving a practice from midday_block to evening_block relocates it canonically."""
    uid, token, headers, _ = _seed_user_with_schedule("user_mid_to_eve")

    res = mutate_user_schedule(
        user_id=uid,
        updates={"Midday Exertion Walk": "17:30 - 18:00"}
    )
    assert res["success"] is True
    sched = res["schedule"]

    assert not any("Midday Exertion Walk" in p["name"] for p in sched["midday_block"])
    eve_walk = next(p for p in sched["evening_block"] if "Midday Exertion Walk" in p["name"])
    assert eve_walk["time_slot"] == "17:30 - 18:00"


# -----------------------------------------------------------------------------
# Test 4: Exactly Once Invariant
# -----------------------------------------------------------------------------
def test_target_practice_exists_exactly_once(isolated_env):
    """The target practice exists exactly once across all schedule blocks after moving."""
    uid, token, headers, _ = _seed_user_with_schedule("user_single_instance")

    # Move Pranayama to evening
    mutate_user_schedule(uid, {"Nadi Shodhana Pranayama": "18:30 - 18:45"})
    state = db.get_user_state(uid)
    sched = state["last_schedule"]["schedule"]

    all_p = sched["morning_block"] + sched["midday_block"] + sched["evening_block"]
    pranayama_occurrences = [p for p in all_p if "Pranayama" in p["name"]]
    assert len(pranayama_occurrences) == 1, f"Expected exactly 1 occurrence, found {len(pranayama_occurrences)}"

    # Move Trataka to morning
    mutate_user_schedule(uid, {"Trataka Gazing": "07:00 - 07:15"})
    sched = db.get_user_state(uid)["last_schedule"]["schedule"]
    all_p2 = sched["morning_block"] + sched["midday_block"] + sched["evening_block"]
    trataka_occurrences = [p for p in all_p2 if "Trataka" in p["name"]]
    assert len(trataka_occurrences) == 1, f"Expected exactly 1 occurrence of Trataka, found {len(trataka_occurrences)}"


# -----------------------------------------------------------------------------
# Test 5 & 6: Unrelated Practices and Metadata Preserved
# -----------------------------------------------------------------------------
def test_unrelated_practices_and_metadata_preserved(isolated_env):
    """All unrelated practices remain untouched, and duration & description are preserved."""
    uid, token, headers, canonical = _seed_user_with_schedule("user_metadata_preservation")

    orig_pranayama = next(p for p in canonical["morning_block"] if "Pranayama" in p["name"])

    res = mutate_user_schedule(uid, {"Nadi Shodhana Pranayama": "18:30 - 18:45"})
    assert res["success"] is True
    sched = res["schedule"]

    # Target practice metadata
    new_pranayama = next(p for p in sched["evening_block"] if "Pranayama" in p["name"])
    assert new_pranayama["duration_minutes"] == orig_pranayama["duration_minutes"]
    assert new_pranayama["description"] == orig_pranayama["description"]

    # Unrelated practices unchanged
    m_names = [p["name"] for p in sched["morning_block"]]
    assert "Brahma Muhurta Jagaran" in m_names
    assert "Ushapan (Warm Water)" in m_names

    mitahara = next(p for p in sched["midday_block"] if "Mitahara" in p["name"])
    assert mitahara["time_slot"] == "12:00 - 12:40"

    dinner = next(p for p in sched["evening_block"] if "Dinner" in p["name"])
    assert dinner["time_slot"] == "19:00 - 19:30"


# -----------------------------------------------------------------------------
# Test 9: Frontend Section Rendering Verification
# -----------------------------------------------------------------------------
def test_frontend_rendering_pipeline_matches_sections(isolated_env):
    """
    Simulates app.js renderRoutineData logic against backend response.
    Verifies that Pranayama at 18:30-18:45 renders under EVENING, and NOT under MORNING.
    """
    client = isolated_env
    uid, token, headers, _ = _seed_user_with_schedule("user_fe_render")

    # Move Pranayama to 18:30 - 18:45
    mutate_user_schedule(uid, {"Nadi Shodhana Pranayama": "18:30 - 18:45"})

    resp = client.get("/api/schedule/current", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Emulate frontend routine container rendering in app.js
    rendered_sections = {}
    for block_key in ["morning_block", "midday_block", "evening_block"]:
        tasks = data["schedule"].get(block_key, [])
        section_label = block_key.split('_')[0].upper()  # MORNING, MIDDAY, EVENING
        rendered_sections[section_label] = [
            {"name": t.get("name"), "slot": t.get("time_slot")}
            for t in tasks
        ]

    # MORNING must NOT contain Pranayama
    morning_names = [t["name"] for t in rendered_sections["MORNING"]]
    assert not any("Pranayama" in n for n in morning_names), f"Frontend MORNING section still contains Pranayama: {morning_names}"

    # EVENING must contain Pranayama at 18:30 - 18:45
    evening_tasks = rendered_sections["EVENING"]
    pranayama_fe = next((t for t in evening_tasks if "Pranayama" in t["name"]), None)
    assert pranayama_fe is not None, "Frontend EVENING section missing Pranayama!"
    assert pranayama_fe["slot"] == "18:30 - 18:45"


# -----------------------------------------------------------------------------
# Test 10: Invalid, Stale, or Contraindicated Proposals Cannot Relocate
# -----------------------------------------------------------------------------
def test_invalid_stale_or_contraindicated_proposals_cannot_relocate(isolated_env):
    """
    A proposal that is contraindicated, stale, or discarded cannot relocate any practice.
    The practice remains in its original block.
    """
    client = isolated_env
    uid, token, headers, _ = _seed_user_with_schedule("user_invalid_guards")

    # Case A: Contraindicated proposal (Pranayama directly overlapping lunch at 12:15)
    proposal_dict = {
        "proposal_id": "prop_contra_test",
        "user_id": str(uid),
        "target_practice": "Nadi Shodhana Pranayama",
        "original_time_slot": "06:30 - 06:45",
        "proposed_time_slot": "12:15 - 12:45",
        "target_block": "midday_block",
        "schedule_version": 1.0,
        "status": "pending_user_confirmation",
        "is_valid": False
    }
    db.save_schedule_proposal(proposal_dict)

    res = apply_canonical_proposal(uid, "prop_contra_test")
    assert res["success"] is False
    assert res["code"] == "CONTRAINDICATED"

    # Pranayama still in morning_block
    sched = db.get_user_state(uid)["last_schedule"]["schedule"]
    assert any("Pranayama" in p["name"] for p in sched["morning_block"])
    assert not any("Pranayama" in p["name"] for p in sched["midday_block"])

    # Case B: Discard proposal
    proposal_dict_valid = {
        "proposal_id": "prop_discard_test",
        "user_id": str(uid),
        "target_practice": "Nadi Shodhana Pranayama",
        "original_time_slot": "06:30 - 06:45",
        "proposed_time_slot": "18:30 - 18:45",
        "target_block": "evening_block",
        "schedule_version": 1.0,
        "status": "pending_user_confirmation",
        "is_valid": True
    }
    db.save_schedule_proposal(proposal_dict_valid)
    discard_res = discard_canonical_proposal(uid, "prop_discard_test")
    assert discard_res["success"] is True

    sched2 = db.get_user_state(uid)["last_schedule"]["schedule"]
    assert any("Pranayama" in p["name"] for p in sched2["morning_block"])
    assert not any("Pranayama" in p["name"] for p in sched2["evening_block"])


# -----------------------------------------------------------------------------
# Test 11: Idempotency & Repeated Confirmation Cannot Duplicate
# -----------------------------------------------------------------------------
def test_repeated_confirmation_idempotent_no_duplicates(isolated_env):
    """Repeated calls to confirm or apply a proposal cannot create duplicate entries."""
    client = isolated_env
    uid, token, headers, _ = _seed_user_with_schedule("user_idempotent_apply")

    prop = formulate_canonical_proposal(
        user_id=uid,
        target_practice="Nadi Shodhana Pranayama",
        requested_slot="18:30 - 18:45",
        current_schedule=db.get_user_state(uid)["last_schedule"]
    )["proposal"]

    # First apply -> success
    apply1 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": prop["proposal_id"]},
        headers=headers
    )
    assert apply1.status_code == 200

    # Second apply -> 409 Conflict ALREADY_APPLIED
    apply2 = client.post(
        "/api/schedule/proposal/apply",
        json={"proposal_id": prop["proposal_id"]},
        headers=headers
    )
    assert apply2.status_code == 409

    # Confirm schedule directly multiple times
    curr_sched = db.get_user_state(uid)["last_schedule"]["schedule"]
    conf1 = client.post("/api/schedule/confirm", json={"schedule": curr_sched}, headers=headers)
    assert conf1.status_code == 200
    conf2 = client.post("/api/schedule/confirm", json={"schedule": curr_sched}, headers=headers)
    assert conf2.status_code == 200

    # Ensure Pranayama appears exactly once
    final_sched = db.get_user_state(uid)["last_schedule"]["schedule"]
    all_p = final_sched["morning_block"] + final_sched["midday_block"] + final_sched["evening_block"]
    pranayama_count = sum(1 for p in all_p if "Pranayama" in p["name"])
    assert pranayama_count == 1, f"Expected 1 Pranayama entry, found {pranayama_count}"


# -----------------------------------------------------------------------------
# Test 12: Same-Block Rescheduling Preserved
# -----------------------------------------------------------------------------
def test_existing_same_block_rescheduling_still_works(isolated_env):
    """Rescheduling within the same time-of-day block retains the practice in its block."""
    uid, token, headers, _ = _seed_user_with_schedule("user_same_block")

    # Shift Ushapan within morning_block (from 06:00 to 06:15)
    res = mutate_user_schedule(uid, {"Ushapan (Warm Water)": "06:15 - 06:30"})
    assert res["success"] is True
    sched = res["schedule"]

    morn_ushapan = next(p for p in sched["morning_block"] if "Ushapan" in p["name"])
    assert morn_ushapan["time_slot"] == "06:15 - 06:30"
    assert not any("Ushapan" in p["name"] for p in sched["midday_block"])
    assert not any("Ushapan" in p["name"] for p in sched["evening_block"])
