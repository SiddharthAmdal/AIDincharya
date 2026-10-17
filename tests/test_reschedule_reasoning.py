import pytest
from fastapi.testclient import TestClient

import main
import src.database.db as db
from src.llm_gateway import LLMGateway, LLMResponse
from src.models import DinacharyaSchedule, Practice, DoshaProfile, DoshaVector
from src.safety.guardrails import ClinicalRuleEngine
from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.planning.agent import extract_practice_time_updates


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Sets up an isolated SQLite database and deterministic LLM fallback for end-to-end reschedule reasoning tests."""
    test_db_path = str(tmp_path / "test_reschedule_reasoning.db")
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db()

    # Force deterministic offline evaluation on LLMGateway so tests run fast and verify fallback resilience
    gateway = LLMGateway.get_instance()
    monkeypatch.setattr(
        gateway,
        "execute_tool_loop",
        lambda *args, **kwargs: LLMResponse(content="", model_used="offline-fallback", is_fallback=True),
    )
    monkeypatch.setattr(
        gateway,
        "generate_structured_json",
        lambda fallback_fn=None, **kwargs: (fallback_fn() if fallback_fn else {}, True),
    )

    client = TestClient(main.app)
    return client


def _create_user_with_mentor_schedule(client: TestClient, username: str = "mentor_user"):
    uid = db.create_user(username, "password123")
    assert uid is not None
    token = db.create_session(uid)
    headers = {"Authorization": f"Bearer {token}"}
    db.update_user_questionnaire(uid, {"q1_agni": "sama", "q2_elimination": "regular"})

    # Seed canonical schedule with Light Early Dinner at 19:00 - 19:30 and Pranayama at 06:30 - 06:45
    canonical_schedule = {
        "user_id": str(uid),
        "adherence_score": 1.0,
        "routine_complexity": "Moderate",
        "morning_block": [
            {
                "name": "Brahma Muhurta Rising & Ushapan",
                "time_slot": "06:00 - 06:15",
                "duration_minutes": 15,
                "description": "Drink warm water out of copper vessel.",
                "rationale": "Flushes GI tract and stimulates peristalsis.",
            },
            {
                "name": "Jihwa Nirlekhana & Gandusha",
                "time_slot": "06:15 - 06:30",
                "duration_minutes": 15,
                "description": "Tongue scraping and warm sesame oil pulling.",
                "rationale": "Clears Ama from oral cavity.",
            },
            {
                "name": "Nadi Shodhana Pranayama",
                "time_slot": "06:30 - 06:45",
                "duration_minutes": 15,
                "description": "Alternate nostril breathing.",
                "rationale": "Balances Ida and Pingala nadis.",
            },
            {
                "name": "Abhyanga (Warm Oil Massage)",
                "time_slot": "07:00 - 07:20",
                "duration_minutes": 20,
                "description": "Self-massage with warm sesame oil.",
                "rationale": "Pacifies Vata and nourishes Dhatus.",
            },
            {
                "name": "Snana (Warm Bath)",
                "time_slot": "07:30 - 07:50",
                "duration_minutes": 20,
                "description": "Warm bath after oil absorption.",
                "rationale": "Cleanses skin and refreshes senses.",
            },
        ],
        "midday_block": [
            {
                "name": "Warm Pitta-Pacifying Lunch",
                "time_slot": "12:30 - 13:15",
                "duration_minutes": 45,
                "description": "Primary cooked meal during peak Agni.",
                "rationale": "Digestive fire peaks during Pitta Kala.",
            }
        ],
        "evening_block": [
            {
                "name": "Light Early Dinner",
                "time_slot": "19:00 - 19:30",
                "duration_minutes": 30,
                "description": "Warm, easily digestible soup or Khichdi.",
                "rationale": "Allows complete digestion before sleep.",
            },
            {
                "name": "Trataka (Candle Gazing) & Digital Sunset",
                "time_slot": "21:30 - 21:45",
                "duration_minutes": 15,
                "description": "Disconnect from screens and calm the mind.",
                "rationale": "Prepares nervous system for restorative sleep.",
            },
        ],
        "timestamp": 1700000000.0,
    }

    db.save_user_schedule(
        uid,
        {
            "schedule": canonical_schedule,
            "morning_block": canonical_schedule["morning_block"],
            "midday_block": canonical_schedule["midday_block"],
            "evening_block": canonical_schedule["evening_block"],
            "dosha_profile": {
                "user_id": str(uid),
                "prakriti": {"vata": 0.4, "pitta": 0.3, "kapha": 0.3},
                "vikriti": {"vata": 0.4, "pitta": 0.3, "kapha": 0.3},
                "agni_state": "sama",
                "primary_imbalance": "vata",
                "secondary_imbalance": None,
            },
            "complexity_level": "Moderate",
            "behavioral_nudge": "Maintain steady rhythm.",
            "retrieved_guidelines": [],
            "timestamp": 1700000000.0,
        },
        "2026-10-17",
    )
    return uid, headers, canonical_schedule


def test_knowledge_base_ingests_authentic_pdfs_and_retrieves_reschedule_principles():
    """Verifies that ChromaDB ingests all authentic PDFs and retrieves relevant post-meal/yoga rules."""
    kb = AyurvedaKnowledgeBase()
    assert kb.collection.count() > 400, "Expected expanded multi-PDF knowledge base in ChromaDB"

    chunks = kb.retrieve_for_reschedule(
        activity_name="Nadi Shodhana Pranayama",
        proposed_slot="19:30 - 19:45",
        adjacent_context="Immediately after Light Early Dinner (19:00 - 19:30)",
        k=5,
    )
    assert len(chunks) > 0
    combined = " ".join(c["text"] for c in chunks).lower()
    assert any(term in combined for term in ["empty stomach", "meal", "pranayama", "food", "bladder", "bowel"])


def test_mentor_scenario_pranayama_right_after_dinner_is_rejected_with_valid_alternatives(isolated_env):
    """
    Mentor Scenario:
    Schedule has Light Early Dinner at 19:00 - 19:30.
    User asks to do Pranayama at 7:30 PM (19:30 - 19:45).
    Must be rejected with grounded rationale and valid alternative slots (e.g., 18:30 - 18:45 before dinner).
    """
    client = isolated_env
    uid, headers, sched_dict = _create_user_with_mentor_schedule(client, "mentor_case_1")

    sched_obj = DinacharyaSchedule(**sched_dict)
    profile = DoshaProfile(
        user_id=str(uid),
        prakriti=DoshaVector(vata=0.4, pitta=0.3, kapha=0.3),
        timestamp=1700000000.0,
    )

    eval_res = ClinicalRuleEngine.evaluate_reschedule_request(
        schedule=sched_obj,
        activity_name="Nadi Shodhana Pranayama",
        proposed_slot="19:30 - 19:45",
        profile=profile,
        user_message="Can I do pranayama at 7:30 PM?",
    )

    assert eval_res["is_valid"] is False
    assert len(eval_res["violations"]) >= 1
    assert "Light Early Dinner" in eval_res["violations"][0]
    assert len(eval_res["recommended_alternatives"]) >= 1

    alt_slots = [alt["slot"] for alt in eval_res["recommended_alternatives"]]
    # Should recommend 18:30 - 18:45 (before dinner) or 21:00 - 21:15 (after 90+ min digestion)
    assert any("18:30" in s or "21:00" in s for s in alt_slots), f"Unexpected alternatives: {alt_slots}"


def test_chat_flow_rejects_unsafe_pranayama_stages_alternative_and_handles_yes_no(isolated_env):
    """
    End-to-end conversational flow:
    1. User asks: 'Can I do pranayama at 7:30 PM?'
    2. Agent declines 7:30 PM (19:30 - 19:45), explains the post-meal principle, and stages the valid alternative (e.g. 18:30 - 18:45).
    3. User says 'Yes' -> schedule updates to the valid alternative (18:30 - 18:45), NEVER 19:30 - 19:45.
    """
    client = isolated_env
    uid, headers, _ = _create_user_with_mentor_schedule(client, "mentor_chat_yes")

    # Turn 1: Request 7:30 PM Pranayama
    chat_res = client.post(
        "/api/chat",
        json={"message": "Can I do pranayama at 7:30 PM?"},
        headers=headers,
    )
    assert chat_res.status_code == 200
    body = chat_res.json()
    reply = body["response"]

    # Must NOT have mutated the persisted schedule yet
    assert body["schedule_updated"] is False
    assert "Light Early Dinner" in reply or "meal" in reply.lower()
    assert "cannot recommend" in reply.lower() or "empty stomach" in reply.lower()

    # Check that proposed_schedule preview in response has the SAFE alternative (e.g. 18:30 - 18:45), NOT 19:30 - 19:45
    proposed_sched = body.get("proposed_schedule")
    assert proposed_sched is not None
    all_prop_practices = (
        proposed_sched.get("morning_block", [])
        + proposed_sched.get("midday_block", [])
        + proposed_sched.get("evening_block", [])
    )
    prop_pranayama = next(p for p in all_prop_practices if "pranayama" in p["name"].lower())
    staged_slot = prop_pranayama["time_slot"]
    assert staged_slot != "19:30 - 19:45", f"Unsafe slot 19:30 - 19:45 should never be staged! Got {staged_slot}"
    assert "18:30" in staged_slot or "21:00" in staged_slot

    # Turn 2: User replies 'Yes' to accept the recommended alternative slot
    confirm_res = client.post(
        "/api/chat",
        json={"message": "Yes"},
        headers=headers,
    )
    assert confirm_res.status_code == 200
    confirm_body = confirm_res.json()
    assert confirm_body["schedule_updated"] is True

    # Verify persisted schedule has Pranayama at the safe recommended slot, and Dinner untouched at 19:00 - 19:30
    updated_sched = confirm_body["proposed_schedule"]
    all_practices = (
        updated_sched.get("morning_block", [])
        + updated_sched.get("midday_block", [])
        + updated_sched.get("evening_block", [])
    )
    pranayama = next(p for p in all_practices if "pranayama" in p["name"].lower())
    dinner = next(p for p in all_practices if "dinner" in p["name"].lower())
    assert pranayama["time_slot"] == staged_slot
    assert dinner["time_slot"] == "19:00 - 19:30"


def test_chat_flow_user_says_no_keeps_original_schedule(isolated_env):
    """
    If the user declines the recommended alternative ('No, keep my current schedule'),
    the proposal is discarded and Pranayama stays at 06:30 - 06:45.
    """
    client = isolated_env
    uid, headers, _ = _create_user_with_mentor_schedule(client, "mentor_chat_no")

    chat_res = client.post(
        "/api/chat",
        json={"message": "Can I do pranayama at 7:30 PM?"},
        headers=headers,
    )
    assert chat_res.status_code == 200

    decline_res = client.post(
        "/api/chat",
        json={"message": "No, keep my current schedule"},
        headers=headers,
    )
    assert decline_res.status_code == 200
    decline_body = decline_res.json()
    assert decline_body["schedule_updated"] is False

    # Verify Pranayama is still at 06:30 - 06:45
    state = db.get_user_state(uid)
    sched = state["last_schedule"]["schedule"]
    pranayama = next(p for p in sched["morning_block"] if "pranayama" in p["name"].lower())
    assert pranayama["time_slot"] == "06:30 - 06:45"


def test_dynamic_categories_bath_after_meal_and_abhyanga_sequence_and_valid_trataka(isolated_env):
    """
    Verifies the full dynamic range of the 6-category Relational Temporal Constraint Matrix:
    - Snana (Warm Bath) right after Lunch (13:30 - 13:50) -> Rejected (Bhuktavastu post-meal bath rule)
    - Abhyanga after Snana (08:00 - 08:20 when Snana is 07:30 - 07:50) -> Rejected (Kriya Krama sequence rule)
    - Trataka moved from 21:30 - 21:45 to 21:45 - 22:00 -> Approved!
    """
    client = isolated_env
    uid, headers, sched_dict = _create_user_with_mentor_schedule(client, "dynamic_matrix_user")
    sched_obj = DinacharyaSchedule(**sched_dict)
    profile = DoshaProfile(
        user_id=str(uid),
        prakriti=DoshaVector(vata=0.4, pitta=0.3, kapha=0.3),
        timestamp=1700000000.0,
    )

    # 1. Snana right after Lunch (Lunch is 12:30 - 13:15, proposing Snana at 13:30 - 13:50)
    bath_eval = ClinicalRuleEngine.evaluate_reschedule_request(
        schedule=sched_obj,
        activity_name="Snana (Warm Bath)",
        proposed_slot="13:30 - 13:50",
        profile=profile,
    )
    assert bath_eval["is_valid"] is False
    assert any("Lunch" in v for v in bath_eval["violations"])

    # 2. Abhyanga scheduled AFTER Snana (Snana is 07:30 - 07:50, proposing Abhyanga at 08:00 - 08:20)
    abhyanga_eval = ClinicalRuleEngine.evaluate_reschedule_request(
        schedule=sched_obj,
        activity_name="Abhyanga (Warm Oil Massage)",
        proposed_slot="08:00 - 08:20",
        profile=profile,
    )
    assert abhyanga_eval["is_valid"] is False
    assert any("Kriya Krama" in v or "BEFORE Snana" in v for v in abhyanga_eval["violations"])

    # 3. Valid reschedule: Trataka moved from 21:30 - 21:45 to 21:45 - 22:00
    trataka_eval = ClinicalRuleEngine.evaluate_reschedule_request(
        schedule=sched_obj,
        activity_name="Trataka (Candle Gazing) & Digital Sunset",
        proposed_slot="21:45 - 22:00",
        profile=profile,
    )
    assert trataka_eval["is_valid"] is True
    assert len(trataka_eval["violations"]) == 0
