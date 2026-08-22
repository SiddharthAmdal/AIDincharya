import time
from datetime import datetime
from src.database import db

def test_password_hashing_and_verification():
    raw_password = "securePassword123"
    hashed = db.hash_password(raw_password)
    assert hashed != raw_password
    assert ":" in hashed
    assert db.verify_password(raw_password, hashed) is True
    assert db.verify_password("wrongPassword", hashed) is False

def test_user_creation_and_authentication():
    username = f"unittest_user_{time.time()}"
    password = "MySecretPassword"
    pwd_hash = db.hash_password(password)

    user_id = db.create_user(username, pwd_hash)
    assert user_id is not None

    # Duplicate username registration fails
    dup_id = db.create_user(username, pwd_hash)
    assert dup_id is None

    # Authenticate user successfully
    auth_id = db.authenticate_user(username, password)
    assert auth_id == user_id

    # Authenticate invalid password fails
    invalid_auth = db.authenticate_user(username, "wrong_password")
    assert invalid_auth is None

def test_session_lifecycle():
    username = f"session_user_{time.time()}"
    user_id = db.create_user(username, db.hash_password("pass"))
    
    token = db.create_session(user_id)
    assert token is not None

    # Resolve user from token
    fetched_user_id = db.get_user_from_token(token)
    assert fetched_user_id == user_id

    # Delete session (Logout)
    deleted = db.delete_session(token)
    assert deleted is True

    # Token no longer resolves
    assert db.get_user_from_token(token) is None

def test_user_state_and_settings():
    username = f"state_user_{time.time()}"
    user_id = db.create_user(username, db.hash_password("pass"))

    # Initial state
    state = db.get_user_state(user_id)
    assert state["has_completed_onboarding"] is False
    assert state["adherence_score"] == 1.0

    # Save questionnaire
    q_responses = {"q1": "vata", "q2": "pitta"}
    db.update_user_questionnaire(user_id, q_responses)

    updated_state = db.get_user_state(user_id)
    assert updated_state["has_completed_onboarding"] is True
    assert updated_state["questionnaire_responses"] == q_responses

    # Update settings
    settings = {"theme": "dark", "notifications": True}
    db.update_user_settings(user_id, settings)
    state_with_settings = db.get_user_state(user_id)
    assert state_with_settings["user_settings"] == settings

def test_task_completions_local_date():
    username = f"completion_user_{time.time()}"
    user_id = db.create_user(username, db.hash_password("pass"))

    today_str = datetime.now().strftime('%Y-%m-%d')
    db.save_completion(user_id, "Abhyanga", today_str)
    db.save_completion(user_id, "Pranayama", today_str)

    completions = db.get_today_completions(user_id, today_str)
    assert "Abhyanga" in completions
    assert "Pranayama" in completions
    assert len(completions) == 2
