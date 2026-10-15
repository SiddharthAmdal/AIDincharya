import time
import json
import hashlib
import uuid
import pytest
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db
from src.models import DinacharyaSchedule, DoshaProfile, DoshaVector, VikritiFlags, Practice
from src.safety.guardrails import ClinicalRuleEngine
from src.behavior.tracker import AdherenceTracker
from src.perception.dosha_mapper import DoshaMapper
from src.planning.tools import (
    AVAILABLE_PLANNER_TOOLS,
    execute_planner_tool,
    get_user_profile,
    get_adherence_history,
    validate_clinical_safety,
    persist_schedule_adaptation
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    """Ensure this module tests real bearer authentication and user isolation."""
    orig = app.dependency_overrides.pop(get_current_user, None)
    yield
    if orig is not None:
        app.dependency_overrides[get_current_user] = orig


# =====================================================================
# 1. AUTHENTICATION & SECURITY REGRESSION TESTS
# =====================================================================

def test_bcrypt_password_hashing():
    """Verify passwords are encrypted with bcrypt salts."""
    pwd = "SecurePassword123!"
    hashed = db.hash_password(pwd)
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert db.verify_password(pwd, hashed) is True
    assert db.verify_password("WrongPassword", hashed) is False


def test_transparent_legacy_sha256_migration():
    """Verify existing legacy users with SHA-256 hashes are transparently upgraded to bcrypt on login."""
    legacy_user = f"legacy_{uuid.uuid4().hex[:10]}"
    raw_pwd = "OldLegacyPass123"
    legacy_sha256 = hashlib.sha256(raw_pwd.encode("utf-8")).hexdigest()

    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (legacy_user, legacy_sha256))
    conn.commit()
    conn.close()

    # Authenticate user with plaintext
    authenticated_id = db.authenticate_user(legacy_user, raw_pwd)
    assert authenticated_id is not None

    # Check that database now has the upgraded bcrypt hash
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute('SELECT password_hash FROM users WHERE username = ?', (legacy_user,))
    row = c.fetchone()
    conn.close()
    new_hash = row["password_hash"]
    assert new_hash.startswith("$2b$") or new_hash.startswith("$2a$")
    assert db.verify_password(raw_pwd, new_hash) is True


def test_session_creation_expiry_and_revocation():
    """Test session lifecycle: creation, expiration, and server-side revocation."""
    u_name = f"sess_user_{uuid.uuid4().hex[:10]}"
    user_id = db.create_user(u_name, "password123")
    assert user_id is not None

    # 1. Normal active session (24h)
    token = db.create_session(user_id, duration_hours=24.0)
    assert db.get_user_from_token(token) == user_id

    # 2. Expired session
    expired_token = db.create_session(user_id, duration_hours=-1.0)
    assert db.get_user_from_token(expired_token) is None

    # 3. Server-side Revocation (Logout)
    assert db.revoke_session(token) is True
    assert db.get_user_from_token(token) is None


def test_api_logout_endpoint():
    """Test POST /api/auth/logout invalidates session on the server."""
    u_name = f"logout_user_{uuid.uuid4().hex[:10]}"
    # Register via API
    reg_res = client.post("/api/auth/register", json={"username": u_name, "password": "password123"})
    assert reg_res.status_code == 200
    token = reg_res.json()["token"]

    # Verify protected endpoint works
    state_res = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"})
    assert state_res.status_code == 200

    # Call logout
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # Token must now be rejected
    state_res_after = client.get("/api/user/state", headers={"Authorization": f"Bearer {token}"})
    assert state_res_after.status_code == 401


def test_cross_user_isolation():
    """Verify that User A cannot read User B's notifications or state."""
    user_a = f"usera_{uuid.uuid4().hex[:10]}"
    user_b = f"userb_{uuid.uuid4().hex[:10]}"

    reg_a = client.post("/api/auth/register", json={"username": user_a, "password": "password123"})
    token_a = reg_a.json()["token"]
    user_a_id = db.get_user_from_token(token_a)

    reg_b = client.post("/api/auth/register", json={"username": user_b, "password": "password123"})
    token_b = reg_b.json()["token"]
    user_b_id = db.get_user_from_token(token_b)

    # Create notification specifically for User B
    notif_b_id = db.create_notification(
        user_id=user_b_id,
        event_type="test_event",
        message="Confidential to User B"
    )

    # User A lists notifications -> should NOT see User B's notification
    notifs_a = client.get("/api/notifications", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert not any(n["id"] == notif_b_id for n in notifs_a["notifications"])

    # User A tries to mark User B's notification as read -> should fail
    mark_res = client.post(f"/api/notifications/{notif_b_id}/read", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert mark_res["success"] is False


# =====================================================================
# 2. DETERMINISTIC SAFETY BOUNDARY & MULTI-RULE MATRIX
# =====================================================================

def test_safety_dead_code_fixed_and_deep_copy():
    """Verify that line 95 dead-code fix preserves practice isolation and sets slot properly."""
    raw_schedule = DinacharyaSchedule(
        user_id="test_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[
            Practice(name="Abhyanga", time_slot="07:15 - 07:45", duration_minutes=30, description="Oil massage", rationale="Vata pacification")
        ],
        midday_block=[],
        evening_block=[],
        timestamp=time.time()
    )
    profile = DoshaProfile(
        user_id="test_user",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        vikriti_flags=VikritiFlags(has_fever=True),
        timestamp=time.time()
    )

    validated = ClinicalRuleEngine.validate(raw_schedule, profile)
    # Abhyanga must be removed
    names = [p.name for p in validated.morning_block]
    assert "Abhyanga" not in names
    assert "Nava Jwara Rest & Hydration" in names
    # Time slot was preserved from the replaced practice
    rep_practice = next(p for p in validated.morning_block if p.name == "Nava Jwara Rest & Hydration")
    assert rep_practice.time_slot == "07:15 - 07:45"


def test_safety_rule_pitta_hyperacidity_override():
    """Verify Rule 2: heating pranayama and sun salutations are overridden during Pitta aggravation."""
    schedule = DinacharyaSchedule(
        user_id="pitta_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[],
        midday_block=[
            Practice(name="Bhastrika Pranayama", time_slot="12:00 - 12:20", duration_minutes=20, description="Fast bellows breathing", rationale="Energy")
        ],
        evening_block=[],
        timestamp=time.time()
    )
    profile = DoshaProfile(
        user_id="pitta_user",
        prakriti=DoshaVector(vata=0.2, pitta=0.6, kapha=0.2),
        vikriti_flags=VikritiFlags(pitta_aggravated=True),
        timestamp=time.time()
    )

    eval_result = ClinicalRuleEngine.evaluate_safety(schedule, profile)
    assert len(eval_result["overrides_applied"]) == 1
    override = eval_result["overrides_applied"][0]
    assert override["rule"] == "Pitta Prakopa Override"
    assert override["removed_practice"] == "Bhastrika Pranayama"
    assert "Sheetali Pranayama" in override["replacement_practice"]


def test_safety_rule_vata_insomnia_override():
    """Verify Rule 3: cold showers and late intense cardio are overridden during Vata aggravation."""
    schedule = DinacharyaSchedule(
        user_id="vata_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[],
        midday_block=[],
        evening_block=[
            Practice(name="Cold Shower & HIIT Cardio", time_slot="21:00 - 21:30", duration_minutes=30, description="Cold water and high intensity", rationale="Fitness")
        ],
        timestamp=time.time()
    )
    profile = DoshaProfile(
        user_id="vata_user",
        prakriti=DoshaVector(vata=0.7, pitta=0.2, kapha=0.1),
        vikriti_flags=VikritiFlags(vata_aggravated=True),
        timestamp=time.time()
    )

    eval_result = ClinicalRuleEngine.evaluate_safety(schedule, profile)
    assert len(eval_result["overrides_applied"]) == 1
    override = eval_result["overrides_applied"][0]
    assert override["rule"] == "Vata / Insomnia Override"
    assert "Padabhyanga" in override["replacement_practice"]


def test_safety_rule_indigestion_ajeerna_override():
    """Verify Rule 4: heavy solid breakfast is overridden during acute indigestion."""
    schedule = DinacharyaSchedule(
        user_id="indigestion_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[
            Practice(name="Heavy Breakfast Buffet", time_slot="08:00 - 08:30", duration_minutes=30, description="Dense solid meal", rationale="Fuel")
        ],
        midday_block=[],
        evening_block=[],
        timestamp=time.time()
    )
    profile = DoshaProfile(
        user_id="indigestion_user",
        prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
        vikriti_flags=VikritiFlags(),
        timestamp=time.time()
    )

    eval_result = ClinicalRuleEngine.evaluate_safety(schedule, profile, symptoms=["Severe indigestion and bloating"])
    assert len(eval_result["overrides_applied"]) == 1
    override = eval_result["overrides_applied"][0]
    assert override["rule"] == "Ajeerna (Indigestion) Override"
    assert "Ushnodaka" in override["replacement_practice"]


# =====================================================================
# 3. MINIMUM USEFUL TOOL REGISTRY & DISPATCHER TESTS
# =====================================================================

def test_tool_registry_contains_all_9_tools():
    """Verify that all 9 required MVP tools are registered in AVAILABLE_PLANNER_TOOLS."""
    registered_names = {t["function"]["name"] for t in AVAILABLE_PLANNER_TOOLS}
    expected_tools = {
        "get_user_profile",
        "query_ayurvedic_knowledge",
        "get_current_schedule",
        "check_calendar_conflicts",
        "propose_schedule_adaptation",
        "validate_clinical_safety",
        "persist_schedule_adaptation",
        "get_adherence_history",
        "request_user_notification"
    }
    assert expected_tools.issubset(registered_names)


def test_tool_execution_profile_and_adherence():
    """Test get_user_profile and get_adherence_history tools."""
    u_name = f"tool_user_{uuid.uuid4().hex[:10]}"
    user_id = db.create_user(u_name, "password123")
    db.update_adherence_score(user_id, 0.92)

    # Dispatch get_user_profile
    res_prof = execute_planner_tool("get_user_profile", {"user_id": str(user_id)}, caller_user_id=str(user_id))
    prof_dict = json.loads(res_prof)
    assert prof_dict["user_id"] == str(user_id)
    assert "prakriti" in prof_dict

    # Dispatch get_adherence_history
    res_adh = execute_planner_tool("get_adherence_history", {"user_id": str(user_id)}, caller_user_id=str(user_id))
    adh_dict = json.loads(res_adh)
    assert adh_dict["adherence_score"] == 0.92
    assert adh_dict["recommended_complexity"] == "Advanced"


def test_tool_persist_schedule_enforces_safety():
    """Verify persist_schedule_adaptation runs safety validation at persistence boundary."""
    u_name = f"persist_tool_user_{uuid.uuid4().hex[:10]}"
    user_id = db.create_user(u_name, "password123")
    # Set fever state in vikriti
    db.update_current_vikriti(user_id, telemetry={"body_temp_c": 39.0}, symptoms=["High fever"])

    candidate = {
        "morning_block": [
            {"name": "Abhyanga", "time_slot": "07:00 - 07:30", "duration_minutes": 30, "description": "Oil massage", "rationale": "Relax"}
        ],
        "midday_block": [],
        "evening_block": []
    }

    res_str = execute_planner_tool(
        "persist_schedule_adaptation",
        {"user_id": str(user_id), "schedule": candidate},
        caller_user_id=str(user_id)
    )
    res = json.loads(res_str)
    assert res["success"] is True

    # Check that persisted schedule in DB has safety override applied
    state = db.get_user_state(user_id)
    persisted = state["last_schedule"]
    morning_names = [p["name"] for p in persisted["morning_block"]]
    assert "Abhyanga" not in morning_names
    assert "Nava Jwara Rest & Hydration" in morning_names


# =====================================================================
# 4. CONVERSATIONAL PROPOSAL REJECTION AND ACCEPTANCE WORKFLOW
# =====================================================================

def test_conversational_proposal_rejection_leaves_routine_untouched():
    """Verify that rejecting a proposal leaves the original schedule completely intact."""
    u_name = f"reject_user_{uuid.uuid4().hex[:10]}"
    reg_res = client.post("/api/auth/register", json={"username": u_name, "password": "password123"})
    token = reg_res.json()["token"]
    user_id = db.get_user_from_token(token)

    original_schedule = {
        "schedule": {
            "routine_complexity": "Moderate",
            "morning_block": [{"name": "Trataka", "time_slot": "07:00 - 07:15", "duration_minutes": 15, "description": "Gazing", "rationale": "Focus"}],
            "midday_block": [],
            "evening_block": []
        }
    }
    db.save_user_schedule(user_id, original_schedule, "2026-10-15")

    # Seed an assistant message proposing a change
    db.save_chat_message(user_id, "assistant", "I propose shifting Trataka to 22:00 - 22:15 tonight. Would you like me to update your routine?")

    # User explicitly rejects
    chat_res = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "No, please don't change it. Keep my original routine."}
    )
    assert chat_res.status_code == 200
    res_data = chat_res.json()
    assert res_data["schedule_updated"] is False
    assert "unchanged" in res_data["response"].lower()

    # Verify persistent state was NOT modified
    state = db.get_user_state(user_id)
    assert state["last_schedule"]["schedule"]["morning_block"][0]["time_slot"] == "07:00 - 07:15"


# =====================================================================
# 5. PERSONALIZATION RUBRIC & EXPONENTIAL TIME DECAY ADHERENCE
# =====================================================================

def test_prakriti_scoring_rubric_deterministic():
    """Verify that the Prakriti rubric scores consistently and generates explainable output."""
    vata_responses = {
        "q_digestion": "vata",
        "q_sleep": "light, easily interrupted, difficult to fall asleep",
        "q_stress": "anxiety and worry"
    }
    vector = DoshaMapper.classify_prakriti(vata_responses)
    assert vector.vata > vector.pitta
    assert vector.vata > vector.kapha

    explanation = DoshaMapper.explain_prakriti_classification(vata_responses)
    assert explanation["rubric_version"] == "v1.2-rubric"
    assert "Vata" in explanation["primary_dosha"]


def test_adherence_exponential_time_decay():
    """Verify that recent completions have greater influence than older ones (decay factor 0.85)."""
    # History A: Skipped 5 days ago, completed today
    history_recent_complete = [
        {"activity": "Abhyanga", "status": "completed", "days_ago": 0},
        {"activity": "Pranayama", "status": "skipped", "days_ago": 5}
    ]
    score_recent = AdherenceTracker.calculate_time_decay_adherence(history_recent_complete, decay_factor=0.85)

    # History B: Completed 5 days ago, skipped today
    history_old_complete = [
        {"activity": "Abhyanga", "status": "skipped", "days_ago": 0},
        {"activity": "Pranayama", "status": "completed", "days_ago": 5}
    ]
    score_old = AdherenceTracker.calculate_time_decay_adherence(history_old_complete, decay_factor=0.85)

    # Recent completed activity must yield a strictly higher adherence score
    assert score_recent > score_old
    assert score_recent >= 0.65
    assert score_old <= 0.40


def test_adherence_rescheduled_weight():
    """Verify that rescheduled activities earn partial (0.7) weight instead of full failure."""
    history = [{"activity": "Meditation", "status": "rescheduled", "days_ago": 0}]
    score = AdherenceTracker.calculate_time_decay_adherence(history)
    assert score == 0.70


# =====================================================================
# 6. NOTIFICATIONS INBOX & UNREAD COUNT
# =====================================================================

def test_notifications_unread_count_and_mark_read():
    """Verify unread_count is computed and mark-as-read decrements it."""
    u_name = f"notif_user_{uuid.uuid4().hex[:10]}"
    reg_res = client.post("/api/auth/register", json={"username": u_name, "password": "password123"})
    token = reg_res.json()["token"]
    user_id = db.get_user_from_token(token)

    # Create two notifications
    n1 = db.create_notification(user_id=user_id, event_type="alert", message="First alert")
    n2 = db.create_notification(user_id=user_id, event_type="alert", message="Second alert")

    # Fetch notifications via API
    res = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["unread_count"] == 2

    # Mark first notification as read
    read_res = client.post(f"/api/notifications/{n1}/read", headers={"Authorization": f"Bearer {token}"})
    assert read_res.status_code == 200

    # Fetch again -> unread_count must be 1
    res_after = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res_after.json()["unread_count"] == 1
