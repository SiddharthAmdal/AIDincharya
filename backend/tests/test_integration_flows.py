import time
from fastapi.testclient import TestClient
from main import app, get_current_user

client = TestClient(app)

def test_flow_1_complete_user_lifecycle():
    app.dependency_overrides.clear()
    username = f"e2e_user_flow1_{time.time()}"
    password = "e2e_password_123"

    # 1. Register
    reg_resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert "token" in reg_data
    assert reg_data["has_completed_onboarding"] is False
    token = reg_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Login
    login_resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login_resp.status_code == 200
    assert login_resp.json()["token"] is not None

    # 3. Create Profile / Questionnaire
    q_data = {
        "responses": {
            "body": "dry skin and light frame",
            "sleep": "restless sleep",
            "digestion": "variable"
        }
    }
    q_resp = client.post("/api/user/questionnaire", json=q_data, headers=headers)
    assert q_resp.status_code == 200
    assert q_resp.json()["status"] == "success"

    # 4. Generate Schedule
    gen_payload = {
        "user_id": "current",
        "context": {
            "season": "Winter",
            "weather": "Cold and dry",
            "temperature_c": 12.0,
            "calendar_events": [],
            "self_report_symptoms": ["Dry skin"]
        }
    }
    gen_resp = client.post("/api/schedule/generate", json=gen_payload, headers=headers)
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert "schedule" in gen_data
    assert "dosha_profile" in gen_data
    assert len(gen_data["schedule"]["morning_block"]) > 0

    # 5. Confirm / Save Schedule
    confirm_resp = client.post("/api/schedule/confirm", json={"schedule": gen_data["schedule"]}, headers=headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "success"

    # 6. Complete Activity & Log Adherence
    first_task = gen_data["schedule"]["morning_block"][0]["name"]
    log_payload = {
        "user_id": "current",
        "completed_practices": [first_task],
        "recommended_practices": [first_task, "Task 2", "Task 3"]
    }
    log_resp = client.post("/api/adherence/log", json=log_payload, headers=headers)
    assert log_resp.status_code == 200
    log_data = log_resp.json()
    assert log_data["adherence_score"] == 0.33

    # 7. Fetch Updated Adherence & User State
    state_resp = client.get("/api/user/state", headers=headers)
    assert state_resp.status_code == 200
    state_data = state_resp.json()
    assert state_data["adherence_score"] == 0.33
    assert state_data["has_completed_onboarding"] is True

    # 8. Logout
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "success"

    # Invalid token access fails after logout
    fail_resp = client.get("/api/user/state", headers=headers)
    assert fail_resp.status_code == 401


def test_flow_2_symptoms_health_and_today_schedule():
    app.dependency_overrides.clear()
    username = f"e2e_user_flow2_{time.time()}"
    password = "e2e_password_456"

    # Register & get headers
    reg_resp = client.post("/api/auth/register", json={"username": username, "password": password})
    token = reg_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload Symptoms & Wearable Telemetry
    health_payload = {
        "telemetry": {"hrv_ms": 32.0, "resting_hr": 68.0, "sleep_hours": 5.0, "body_temp_c": 38.5},
        "symptoms": ["Active fever", "Fatigue"]
    }
    health_resp = client.post("/api/health/telemetry", json=health_payload, headers=headers)
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "success"

    # 2. Analyze Dosha & Profile
    profile_resp = client.get("/api/user/profile", headers=headers)
    assert profile_resp.status_code == 200
    prof_data = profile_resp.json()
    assert prof_data["dosha_profile"]["vikriti_flags"]["has_fever"] is True
    assert prof_data["dosha_profile"]["vikriti_flags"]["vata_aggravated"] is True

    # 3. Generate Schedule (fever override must strip Abhyanga)
    gen_payload = {
        "user_id": "current",
        "context": {
            "season": "Winter",
            "weather": "Cold",
            "temperature_c": 10.0,
            "calendar_events": [],
            "self_report_symptoms": ["Active fever"]
        },
        "wearable_telemetry_7d": {"body_temp_c": 38.5}
    }
    gen_resp = client.post("/api/schedule/generate", json=gen_payload, headers=headers)
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()

    # Safety assertion: Abhyanga stripped due to fever
    morning_names = [p["name"].lower() for p in gen_data["schedule"]["morning_block"]]
    assert not any("abhyanga" in name for name in morning_names)

    # 4. Retrieve Today's Schedule
    today_resp = client.get("/api/schedule/today", headers=headers)
    assert today_resp.status_code == 200
    today_data = today_resp.json()
    assert "schedule" in today_data
    assert today_data["schedule"] is not None

    # 5. Direct Knowledge Search
    kb_resp = client.get("/api/knowledge/search?q=Dinacharya", headers=headers)
    assert kb_resp.status_code == 200
    assert "results" in kb_resp.json()
