"""
tests/test_onboarding_assessment.py

Comprehensive test suite verifying the 24-question Prakriti assessment workflow:
- Questionnaire catalog endpoint schema and section organization
- New user registration and onboarding status initialization
- Strict server-side validation (incomplete submissions, invalid IDs, invalid values)
- Unauthenticated rejection
- Successful persistence, user account association, and state isolation
- Provisional Prakriti profile calculation (Single, Dual, and Tridoshic classification)
- Schedule generation pipeline integration using saved assessment
- Reassessment and cache invalidation
"""

import time
import pytest
from fastapi.testclient import TestClient
from main import app
from src.database import db
from src.perception.dosha_mapper import DoshaMapper
from src.perception.prakriti_questions import (
    PRAKRITI_QUESTIONS,
    PRAKRITI_SECTIONS,
    validate_questionnaire_responses,
    get_prakriti_catalog
)

client = TestClient(app)


def test_questionnaire_catalog_structure():
    """Verify the 24-question catalog contains 24 valid questions across sections A, B, and C."""
    catalog = get_prakriti_catalog()
    assert catalog["total_questions"] == 24
    assert len(catalog["sections"]) == 3
    assert len(catalog["questions"]) == 24

    for q in catalog["questions"]:
        assert q["id"].startswith("q")
        assert 1 <= q["number"] <= 24
        assert q["section"] in ("A", "B", "C")
        assert len(q["options"]) == 3
        option_doshas = {opt["value"] for opt in q["options"]}
        assert option_doshas == {"vata", "pitta", "kapha"}
        for opt in q["options"]:
            assert len(opt["text"]) > 10


def test_api_get_questions_endpoint():
    """Verify GET /api/user/questionnaire/questions returns 200 and complete question catalog."""
    res = client.get("/api/user/questionnaire/questions")
    assert res.status_code == 200
    data = res.json()
    assert data["total_questions"] == 24
    assert len(data["questions"]) == 24
    assert data["sections"][0]["title"] == "Section A: Physical Characteristics"


def test_registration_initializes_onboarding_false():
    """Verify that registering a new user sets has_completed_onboarding to False."""
    username = f"newuser_{int(time.time() * 1000)}"
    res = client.post("/api/auth/register", json={"username": username, "password": "securepassword"})
    assert res.status_code == 200
    data = res.json()
    assert data["has_completed_onboarding"] is False
    assert "token" in data

    token = data["token"]
    # Check state endpoint
    state_res = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"})
    assert state_res.status_code == 200
    state = state_res.json()
    assert state["has_completed_onboarding"] is False
    assert state["questionnaire_responses"] == {}


def test_submission_requires_authentication():
    """Verify that submitting the questionnaire without a token returns 401 Unauthorized."""
    answers = {f"q{i}": "vata" for i in range(1, 25)}
    res = client.post("/api/user/questionnaire", json={"responses": answers})
    assert res.status_code == 401


def test_submission_rejects_incomplete_responses():
    """Verify that submitting fewer than 24 questions returns 422 Unprocessable Entity."""
    username = f"incom_user_{int(time.time() * 1000)}"
    reg_res = client.post("/api/auth/register", json={"username": username, "password": "password123"})
    token = reg_res.json()["token"]

    # Only 20 questions
    partial_answers = {f"q{i}": "vata" for i in range(1, 21)}
    res = client.post("/api/user/questionnaire", json={"responses": partial_answers}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "Missing 4 question(s)" in res.json()["detail"]

    # Verify onboarding status remains False
    state_res = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"})
    assert state_res.json()["has_completed_onboarding"] is False


def test_submission_rejects_invalid_question_identifiers():
    """Verify that submitting unknown question identifiers returns 422."""
    username = f"invalid_q_{int(time.time() * 1000)}"
    reg_res = client.post("/api/auth/register", json={"username": username, "password": "password123"})
    token = reg_res.json()["token"]

    answers = {f"q{i}": "vata" for i in range(1, 24)}
    answers["q99_invalid"] = "vata"
    res = client.post("/api/user/questionnaire", json={"responses": answers}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "Missing 1 question(s): q24" in res.json()["detail"] or "Invalid question identifier" in res.json()["detail"]


def test_submission_rejects_invalid_answer_values():
    """Verify that submitting an answer value other than vata/pitta/kapha returns 422."""
    username = f"invalid_val_{int(time.time() * 1000)}"
    reg_res = client.post("/api/auth/register", json={"username": username, "password": "password123"})
    token = reg_res.json()["token"]

    answers = {f"q{i}": "vata" for i in range(1, 25)}
    answers["q5"] = "super_warm"  # Not vata, pitta, or kapha
    res = client.post("/api/user/questionnaire", json={"responses": answers}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "Invalid value" in res.json()["detail"]
    assert "q5" in res.json()["detail"]


def test_successful_24_question_assessment_submission():
    """Verify successful assessment persistence, preliminary profile generation, and onboarding completion."""
    username = f"vata_user_{int(time.time() * 1000)}"
    reg_res = client.post("/api/auth/register", json={"username": username, "password": "password123"})
    token = reg_res.json()["token"]

    # 18 Vata, 3 Pitta, 3 Kapha
    answers = {}
    for i in range(1, 25):
        if i <= 18:
            answers[f"q{i}"] = "vata"
        elif i <= 21:
            answers[f"q{i}"] = "pitta"
        else:
            answers[f"q{i}"] = "kapha"

    res = client.post("/api/user/questionnaire", json={"responses": answers}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["has_completed_onboarding"] is True
    assert data["prakriti"]["vata"] == pytest.approx(0.75, abs=0.01)

    summary = data["assessment_summary"]
    assert "Pure Vata" in summary["constitution_type"] or "Vata" in summary["primary_dosha"]

    # Verify user state via GET /api/user/state
    state_res = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"})
    state = state_res.json()
    assert state["has_completed_onboarding"] is True
    assert len(state["questionnaire_responses"]) == 24
    assert state["prakriti_profile"]["primary_dosha"] == "Vata"


def test_user_state_isolation():
    """Verify that User A's questionnaire answers and profile are isolated from User B."""
    # User A: Pitta dominant
    user_a = f"usera_{int(time.time() * 1000)}"
    token_a = client.post("/api/auth/register", json={"username": user_a, "password": "password"}).json()["token"]
    answers_a = {f"q{i}": "pitta" for i in range(1, 25)}
    client.post("/api/user/questionnaire", json={"responses": answers_a}, headers={"Authorization": f"Bearer {token_a}"})

    # User B: Kapha dominant
    user_b = f"userb_{int(time.time() * 1000)}"
    token_b = client.post("/api/auth/register", json={"username": user_b, "password": "password"}).json()["token"]
    answers_b = {f"q{i}": "kapha" for i in range(1, 25)}
    client.post("/api/user/questionnaire", json={"responses": answers_b}, headers={"Authorization": f"Bearer {token_b}"})

    # Verify User A state
    state_a = client.get("/api/user/state", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert state_a["prakriti_profile"]["primary_dosha"] == "Pitta"
    assert state_a["questionnaire_responses"]["q1"] == "pitta"

    # Verify User B state
    state_b = client.get("/api/user/state", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert state_b["prakriti_profile"]["primary_dosha"] == "Kapha"
    assert state_b["questionnaire_responses"]["q1"] == "kapha"


def test_login_returns_has_completed_onboarding():
    """Verify that logging in as an onboarded user returns has_completed_onboarding: True."""
    username = f"logintest_{int(time.time() * 1000)}"
    password = "testpassword123"
    token = client.post("/api/auth/register", json={"username": username, "password": password}).json()["token"]

    # Initial login before questionnaire -> False
    login_1 = client.post("/api/auth/login", json={"username": username, "password": password}).json()
    assert login_1["has_completed_onboarding"] is False

    # Complete assessment
    answers = {f"q{i}": "vata" for i in range(1, 25)}
    client.post("/api/user/questionnaire", json={"responses": answers}, headers={"Authorization": f"Bearer {token}"})

    # Second login after questionnaire -> True
    login_2 = client.post("/api/auth/login", json={"username": username, "password": password}).json()
    assert login_2["has_completed_onboarding"] is True


def test_tridoshic_sama_prakriti_scoring():
    """Verify that an equal distribution of 8 Vata, 8 Pitta, 8 Kapha classifies as Tridoshic (Sama Prakriti)."""
    answers = {}
    for i in range(1, 25):
        if i <= 8:
            answers[f"q{i}"] = "vata"
        elif i <= 16:
            answers[f"q{i}"] = "pitta"
        else:
            answers[f"q{i}"] = "kapha"

    explanation = DoshaMapper.explain_prakriti_classification(answers)
    assert explanation["constitution_type"] == "Tridoshic (Sama Prakriti)"
    assert explanation["dosha_vector"]["vata"] == pytest.approx(0.333, abs=0.01)
    assert explanation["dosha_vector"]["pitta"] == pytest.approx(0.333, abs=0.01)
    assert explanation["dosha_vector"]["kapha"] == pytest.approx(0.333, abs=0.01)


def test_dual_prakriti_scoring():
    """Verify that a close distribution (12 Vata, 10 Pitta, 2 Kapha) classifies as Dual Vata-Pitta."""
    answers = {}
    for i in range(1, 25):
        if i <= 12:
            answers[f"q{i}"] = "vata"
        elif i <= 22:
            answers[f"q{i}"] = "pitta"
        else:
            answers[f"q{i}"] = "kapha"

    explanation = DoshaMapper.explain_prakriti_classification(answers)
    assert "Dual" in explanation["constitution_type"]
    assert "Vata" in explanation["constitution_type"] and "Pitta" in explanation["constitution_type"]


def test_reassessment_invalidates_stale_cached_schedule():
    """Verify that submitting an updated questionnaire resets cached schedule so fresh recommendations are generated."""
    username = f"reassess_user_{int(time.time() * 1000)}"
    reg = client.post("/api/auth/register", json={"username": username, "password": "password"}).json()
    token = reg["token"]

    # Initial assessment: Vata
    v_answers = {f"q{i}": "vata" for i in range(1, 25)}
    client.post("/api/user/questionnaire", json={"responses": v_answers}, headers={"Authorization": f"Bearer {token}"})

    # Simulate saving a schedule in db
    state_1 = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"}).json()
    # Manually seed cached schedule
    db.save_user_schedule(1, {"schedule": {"morning_block": [{"name": "Old Practice"}]}}, "2026-10-26")

    # Now user retakes assessment with Pitta answers
    p_answers = {f"q{i}": "pitta" for i in range(1, 25)}
    res_re = client.post("/api/user/questionnaire", json={"responses": p_answers}, headers={"Authorization": f"Bearer {token}"})
    assert res_re.status_code == 200

    # User state should now reflect updated Pitta profile
    state_updated = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"}).json()
    assert state_updated["prakriti_profile"]["primary_dosha"] == "Pitta"
    assert state_updated["last_schedule"] is None  # Invalidated so new routine compiles


def test_pure_pitta_and_pure_kapha_scoring():
    """Verify Pure Pitta and Pure Kapha classifications when a single dosha exceeds 60%."""
    # Pure Pitta (18 Pitta, 3 Vata, 3 Kapha)
    p_answers = {f"q{i}": "pitta" if i <= 18 else ("vata" if i <= 21 else "kapha") for i in range(1, 25)}
    p_expl = DoshaMapper.explain_prakriti_classification(p_answers)
    assert p_expl["constitution_type"] == "Pure Pitta"
    assert p_expl["dosha_vector"]["pitta"] == pytest.approx(0.75, abs=0.01)

    # Pure Kapha (18 Kapha, 3 Vata, 3 Pitta)
    k_answers = {f"q{i}": "kapha" if i <= 18 else ("vata" if i <= 21 else "pitta") for i in range(1, 25)}
    k_expl = DoshaMapper.explain_prakriti_classification(k_answers)
    assert k_expl["constitution_type"] == "Pure Kapha"
    assert k_expl["dosha_vector"]["kapha"] == pytest.approx(0.75, abs=0.01)


def test_classification_boundary_thresholds():
    """
    Test exact classification boundary thresholds:
    1. >= 0.60 is Pure (15/24 = 0.625) vs < 0.60 (14/24 = 0.583 with equal split of others -> Dominant).
    2. diff <= 0.08 is Tridoshic (8/8/8 diff = 0.0).
    3. diff <= 0.15 between primary and secondary is Dual (11 Vata, 9 Pitta, 4 Kapha).
    """
    # Boundary 1: Exactly 15/24 (62.5% >= 60%) -> Pure
    ans_15 = {f"q{i}": "vata" if i <= 15 else ("pitta" if i <= 20 else "kapha") for i in range(1, 25)}
    expl_15 = DoshaMapper.explain_prakriti_classification(ans_15)
    assert expl_15["constitution_type"] == "Pure Vata"

    # Boundary 2: 14 Vata, 5 Pitta, 5 Kapha (58.3% < 60%, diff to sec = 0.583 - 0.208 = 0.375 > 0.15) -> Vata-dominant
    ans_14 = {f"q{i}": "vata" if i <= 14 else ("pitta" if i <= 19 else "kapha") for i in range(1, 25)}
    expl_14 = DoshaMapper.explain_prakriti_classification(ans_14)
    assert expl_14["constitution_type"] == "Vata-dominant"

    # Boundary 3: Dual Dosha (11 Vata, 9 Pitta, 4 Kapha) -> primary - secondary = 11/24 - 9/24 = 2/24 = 0.083 <= 0.15
    ans_dual = {f"q{i}": "vata" if i <= 11 else ("pitta" if i <= 20 else "kapha") for i in range(1, 25)}
    expl_dual = DoshaMapper.explain_prakriti_classification(ans_dual)
    assert expl_dual["constitution_type"] == "Dual Vata-Pitta"


def test_score_normalization_consistency():
    """Verify that score vectors strictly normalize to 1.0 across diverse answer patterns."""
    for pattern in [
        {f"q{i}": "vata" for i in range(1, 25)},
        {f"q{i}": "pitta" for i in range(1, 25)},
        {f"q{i}": "kapha" for i in range(1, 25)},
        {f"q{i}": "vata" if i % 2 == 0 else "pitta" for i in range(1, 25)},
        {f"q{i}": "vata" if i % 3 == 0 else ("pitta" if i % 3 == 1 else "kapha") for i in range(1, 25)},
    ]:
        vec = DoshaMapper.classify_prakriti(pattern)
        total = vec.vata + vec.pitta + vec.kapha
        assert total == pytest.approx(1.0, abs=0.001)

