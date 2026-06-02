import time
from fastapi.testclient import TestClient
from main import app
from src.models import DoshaProfile, DoshaVector, UserContext
from src.planning.agent import DinacharyaPlannerAgent
from src.planning.tools import check_calendar_conflicts

client = TestClient(app)


def test_calendar_conflicts_tool():
    """Verify that the calendar conflict checker identifies overlapping morning slots."""
    events = ["9:00 AM Client Meeting", "12:00 PM Team Lunch"]
    assert check_calendar_conflicts(events, "09:00 - 09:20") is True
    assert check_calendar_conflicts(events, "12:00 - 12:45") is False # Only morning check active in stub
    assert check_calendar_conflicts(events, "06:00 - 06:15") is False


def test_planning_agent_generate():
    """Verify that the planning agent compiles the LangGraph workflow and outputs a schedule."""
    profile = DoshaProfile(
        user_id="user_test_99",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        timestamp=time.time()
    )
    context = UserContext(
        season="Winter (Hemanta)",
        weather="Cold and dry",
        temperature_c=14.0,
        calendar_events=["09:00 - 10:00 Morning Call"],
        self_report_symptoms=[]
    )
    
    planner = DinacharyaPlannerAgent()
    schedule = planner.generate(
        user_id="user_test_99",
        profile=profile,
        context=context,
        adherence_score=0.9,
        complexity="Moderate"
    )
    
    assert schedule.user_id == "user_test_99"
    assert len(schedule.morning_block) > 0
    assert len(schedule.midday_block) > 0
    assert len(schedule.evening_block) > 0


def test_api_root():
    """Verify that the root endpoint serves our beautiful SPA portal."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Dinacharya AI" in response.text



def test_api_schedule_generation_flow():
    """Verify end-to-end schedule generation endpoint, including stubs, planning, and safety checks."""
    payload = {
        "user_id": "test_mobile_user_01",
        "questionnaire_responses": {
            "skin": "My skin is extremely dry and cracks easily",
            "sleep": "I have light sleep and wake up easily by sounds"
        },
        "wearable_telemetry_7d": {
            "hrv_ms": 35.0,        # Low HRV
            "resting_hr": 68.0,
            "sleep_hours": 5.4,     # Low sleep duration -> will aggravate Vata
            "body_temp_c": 38.5     # Fever detected -> will strip Abhyanga
        },
        "context": {
            "season": "Winter",
            "weather": "Dry wind",
            "temperature_c": 12.0,
            "calendar_events": ["09:00 AM Standup Meeting"],
            "self_report_symptoms": ["Active fever", "Fatigue"]
        }
    }
    
    response = client.post("/api/schedule/generate", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert "schedule" in data
    assert "dosha_profile" in data
    assert "behavioral_nudge" in data
    
    # Verify that Perception flagged the imbalances
    assert data["dosha_profile"]["vikriti_flags"]["vata_aggravated"] is True
    assert data["dosha_profile"]["vikriti_flags"]["has_fever"] is True
    
    # Verify that Safety stripped Abhyanga/Nasya due to fever override
    morning_block = data["schedule"]["morning_block"]
    for p in morning_block:
        assert "abhyanga" not in p["name"].lower()
        assert "nasya" not in p["name"].lower()


def test_api_adherence_log_closed_loop():
    """Verify that logging low adherence dynamically shifts routine complexity down to Anchor Habits."""
    payload = {
        "user_id": "test_mobile_user_01",
        "completed_practices": ["Wake up call"],
        "recommended_practices": ["Wake up call", "Abhyanga", "Lunch", "Dinner", "Meditation"]
    }
    # Adherence count: 1 / 5 = 0.20 -> triggers "Anchor Habits" complexity
    response = client.post("/api/adherence/log", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["adherence_score"] == 0.20
    assert data["next_complexity_level"] == "Anchor Habits"
    assert "focus on the essentials" in data["behavioral_nudge"]["title"].lower()
