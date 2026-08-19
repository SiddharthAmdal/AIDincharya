import requests
import json
import time

BASE_URL = "http://localhost:8000"

print("1. Registering user...")
res = requests.post(f"{BASE_URL}/api/auth/register", json={"username": "testuser_" + str(time.time()), "password": "password"})
token = res.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

print("2. Onboarding...")
requests.post(f"{BASE_URL}/api/user/questionnaire", json={"responses": {"q1": "vata", "q2": "pitta", "q3": "kapha"}}, headers=headers)

print("3. Generating schedule with fever...")
payload_fever = {
    "user_id": "current",
    "context": {"season": "Winter", "weather": "Cold", "temperature_c": 10.0, "calendar_events": [], "self_report_symptoms": []},
    "wearable_telemetry_7d": {"body_temp_c": 38.5}
}
res_sched = requests.post(f"{BASE_URL}/api/schedule/generate", json=payload_fever, headers=headers)
sched_data = res_sched.json()
print("Schedule blocks:", sched_data.get("schedule", {}).keys())

print("\n4. Triggering Chat Recalibration asking for contraindicated Abhyanga...")
res_chat = requests.post(f"{BASE_URL}/api/chat", json={"message": "I really want to do Abhyanga at 06:30 instead. Please schedule it."}, headers=headers)
chat_data = res_chat.json()
proposed = chat_data.get("proposed_schedule")

print("Chat proposed schedule:", bool(proposed))
if proposed:
    all_tasks = str(proposed).lower()
    print("Does proposed schedule contain 'abhyanga'? (If True, safety was bypassed!):", "abhyanga" in all_tasks)
    print("Tasks proposed:", [t['name'] for block in proposed.values() for t in block])
else:
    print("No schedule proposed by chat.")

print("\n5. Testing adherence logging...")
# Pick a task to complete
try:
    first_task = sched_data["schedule"]["morning_block"][0]["name"]
    requests.post(f"{BASE_URL}/api/adherence/log", json={"user_id": "current", "completed_practices": [first_task], "recommended_practices": [first_task, "Task2", "Task3", "Task4", "Task5"]}, headers=headers)
    res_state = requests.get(f"{BASE_URL}/api/user/state", headers=headers)
    print("Adherence Score after logging 1/5:", res_state.json()["adherence_score"])
except Exception as e:
    print("Could not test adherence:", e)
