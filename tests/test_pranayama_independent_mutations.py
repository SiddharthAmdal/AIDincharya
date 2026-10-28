"""
tests/test_pranayama_independent_mutations.py

Regression test suite verifying independent schedule mutations, stable activity identities,
conflict detection, and completion preservation for practices sharing root terms:
1. 'Pranayama (Nadi Shodhana with Cooling Exhalation)'
2. 'Pranayama (Nadi Shodhana Balancing Breath)'
"""

import time
import pytest
from src.models import Practice, DinacharyaSchedule
import src.database.db as db
from src.planning.schedule_service import (
    mutate_user_schedule,
    resolve_practice_intent,
    formulate_canonical_proposal,
    apply_canonical_proposal,
    get_stable_practice_id,
    score_practice_match
)


@pytest.fixture
def setup_pranayama_user():
    """Sets up a test user with a schedule containing both pranayama practices."""
    user_id = 99201
    date_str = "2026-10-28"

    # Initialize DB tables
    db.init_db()

    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, ?, ?)", (user_id, "pranayama_user", "hash"))
    c.execute("DELETE FROM activity_lifecycle WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM completions WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM schedule_proposals WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()

    p1 = Practice(
        id="prac_pranayama_cooling",
        name="Pranayama (Nadi Shodhana with Cooling Exhalation)",
        time_slot="06:45 - 07:00",
        duration_minutes=15,
        description="Cooling breathwork to balance Pitta.",
        rationale="Pitta pacification via Sheetali and Nadi Shodhana."
    )
    p2 = Practice(
        id="prac_abhyanga",
        name="Abhyanga",
        time_slot="07:00 - 07:30",
        duration_minutes=30,
        description="Warm sesame oil self-massage.",
        rationale="Vata grounding."
    )
    p3 = Practice(
        id="prac_pranayama_balancing",
        name="Pranayama (Nadi Shodhana Balancing Breath)",
        time_slot="17:30 - 17:45",
        duration_minutes=15,
        description="Evening balancing breathwork.",
        rationale="Calms Vata and transitions into evening."
    )

    sched = {
        "schedule": {
            "routine_complexity": "Moderate",
            "morning_block": [p1.model_dump(), p2.model_dump()],
            "midday_block": [],
            "evening_block": [p3.model_dump()]
        },
        "morning_block": [p1.model_dump(), p2.model_dump()],
        "midday_block": [],
        "evening_block": [p3.model_dump()],
        "timestamp": time.time()
    }

    db.save_user_schedule(user_id, sched, date_str=date_str)
    db.sync_schedule_to_activity_lifecycle(user_id, sched, date_str=date_str)

    return user_id, date_str, p1, p2, p3


def test_independent_reschedule_cooling_pranayama(setup_pranayama_user):
    """
    Test 1: Rescheduling Cooling Exhalation leaves Balancing Breath untouched.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user

    res = mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana with Cooling Exhalation)": "08:00 - 08:15"},
        date_str=date_str
    )

    assert res["success"] is True
    sched = res["schedule"]

    # Verify Cooling Exhalation moved to 08:00 - 08:15
    morning = sched.get("morning_block", [])
    cooling = next((p for p in morning if "Cooling" in p["name"]), None)
    assert cooling is not None
    assert cooling["time_slot"] == "08:00 - 08:15"

    # Verify Balancing Breath is untouched at 17:30 - 17:45 in evening_block
    evening = sched.get("evening_block", [])
    balancing = next((p for p in evening if "Balancing" in p["name"]), None)
    assert balancing is not None
    assert balancing["time_slot"] == "17:30 - 17:45"


def test_independent_reschedule_balancing_breath(setup_pranayama_user):
    """
    Test 2: Rescheduling Balancing Breath leaves Cooling Exhalation untouched.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user

    res = mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana Balancing Breath)": "18:00 - 18:15"},
        date_str=date_str
    )

    assert res["success"] is True
    sched = res["schedule"]

    # Verify Cooling Exhalation is untouched at 06:45 - 07:00
    morning = sched.get("morning_block", [])
    cooling = next((p for p in morning if "Cooling" in p["name"]), None)
    assert cooling is not None
    assert cooling["time_slot"] == "06:45 - 07:00"

    # Verify Balancing Breath moved to 18:00 - 18:15
    evening = sched.get("evening_block", [])
    balancing = next((p for p in evening if "Balancing" in p["name"]), None)
    assert balancing is not None
    assert balancing["time_slot"] == "18:00 - 18:15"


def test_restore_original_slot_does_not_mutate_other_practice(setup_pranayama_user):
    """
    Test 3: Restoring Cooling Exhalation to its original slot does not move Balancing Breath.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user

    # Move Cooling Exhalation first
    mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana with Cooling Exhalation)": "08:30 - 08:45"},
        date_str=date_str
    )

    # Now restore it back to 06:45 - 07:00
    res = mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana with Cooling Exhalation)": "06:45 - 07:00"},
        date_str=date_str
    )

    assert res["success"] is True
    sched = res["schedule"]

    morning = sched.get("morning_block", [])
    cooling = next((p for p in morning if "Cooling" in p["name"]), None)
    assert cooling is not None
    assert cooling["time_slot"] == "06:45 - 07:00"

    evening = sched.get("evening_block", [])
    balancing = next((p for p in evening if "Balancing" in p["name"]), None)
    assert balancing is not None
    assert balancing["time_slot"] == "17:30 - 17:45"


def test_preserve_completion_status_on_reschedule(setup_pranayama_user):
    """
    Test 4: Preserve completion status of a practice already completed in its original slot.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user

    # Mark Cooling Exhalation completed
    comp_res = db.complete_user_activity(user_id, "prac_pranayama_cooling", date_str=date_str)
    assert comp_res["success"] is True

    # Verify initial completion state
    acts = db.get_user_activities(user_id, date_str=date_str)
    cooling_act = next((a for a in acts if "cooling" in a["id"]), None)
    balancing_act = next((a for a in acts if "balancing" in a["id"]), None)
    assert cooling_act["status"] == "completed_by_user"
    assert balancing_act["status"] != "completed_by_user"

    # Reschedule Cooling Exhalation
    mut_res = mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana with Cooling Exhalation)": "08:00 - 08:15"},
        date_str=date_str
    )
    assert mut_res["success"] is True

    # Re-sync and check activity lifecycle
    db.sync_schedule_to_activity_lifecycle(user_id, mut_res["canonical_data"], date_str=date_str)
    acts_after = db.get_user_activities(user_id, date_str=date_str)

    cooling_after = next((a for a in acts_after if "cooling" in a["id"]), None)
    balancing_after = next((a for a in acts_after if "balancing" in a["id"]), None)

    # STRICT REQUIREMENT: Cooling completion preserved!
    assert cooling_after["status"] == "completed_by_user"
    assert cooling_after["time_slot"] == "08:00 - 08:15"

    # STRICT REQUIREMENT: Balancing breath NOT marked complete!
    assert balancing_after["status"] != "completed_by_user"


def test_detect_conflict_and_prevent_unintended_mutation(setup_pranayama_user):
    """
    Test 5: Attempting to move Cooling Exhalation to 07:00 - 07:15 (where Abhyanga is scheduled at 07:00 - 07:30)
    returns a conflict proposal and does NOT move unrelated activities.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user

    res = mutate_user_schedule(
        user_id=user_id,
        updates={"Pranayama (Nadi Shodhana with Cooling Exhalation)": "07:00 - 07:15"},
        date_str=date_str
    )

    assert res["success"] is False
    assert res.get("conflict") is True
    assert "Abhyanga" in res["conflicting_activity"]
    assert "07:00 - 07:30" in res["conflicting_slot"]

    # Verify schedule remained completely unchanged
    canonical = db.get_user_state(user_id)["last_schedule"]["schedule"]
    cooling = next((p for p in canonical["morning_block"] if "Cooling" in p["name"]), None)
    assert cooling["time_slot"] == "06:45 - 07:00"


def test_resolve_practice_intent_distinguishes_subtypes(setup_pranayama_user):
    """
    Test 6: Natural language resolution cleanly distinguishes between both pranayamas.
    """
    user_id, date_str, p1, p2, p3 = setup_pranayama_user
    sched = db.get_user_state(user_id)["last_schedule"]

    intent_cooling = resolve_practice_intent(
        "Please move my cooling exhalation pranayama to 08:30",
        sched
    )
    assert intent_cooling is not None
    assert "Cooling" in intent_cooling["target_practice"]

    intent_balancing = resolve_practice_intent(
        "Can we push my evening balancing breath to 18:00",
        sched
    )
    assert intent_balancing is not None
    assert "Balancing" in intent_balancing["target_practice"]
