import time
from fastapi.testclient import TestClient
from main import app, get_current_user
from src.perception.dosha_mapper import IsolationForestAnomalyDetector, DoshaMapper
from src.perception.wearables import WearableSyncEngine
from src.behavior.notifications import NotificationScheduler
from src.evaluation.analytics import PilotEvaluationAnalytics
from src.models import DinacharyaSchedule, Practice

client = TestClient(app)

def mocked_user():
    return 1

def test_isolation_forest_anomaly_detector():
    detector = IsolationForestAnomalyDetector()
    results = detector.fit_predict([[55.0, 70.0, 7.5, 36.8], [30.0, 85.0, 4.5, 38.5]])
    assert len(results) == 2

def test_wearable_sync_parsers():
    hk_payload = {
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {"value": 34.0},
        "HKQuantityTypeIdentifierRestingHeartRate": {"value": 78.0},
        "HKCategoryTypeIdentifierSleepAnalysis": {"value": 5.2},
        "HKQuantityTypeIdentifierBodyTemperature": {"value": 38.2}
    }
    normalized = WearableSyncEngine.normalize_vendor_payload("apple_healthkit", hk_payload)
    assert normalized["hrv_ms"] == 34.0
    assert normalized["body_temp_c"] == 38.2

    gc_payload = {
        "hrv_rmssd_ms": 40.0,
        "resting_hr_bpm": 65.0,
        "sleep_duration_hours": 8.0,
        "body_temperature_celsius": 36.6
    }
    normalized_gc = WearableSyncEngine.normalize_vendor_payload("google_healthconnect", gc_payload)
    assert normalized_gc["hrv_ms"] == 40.0
    assert normalized_gc["sleep_hours"] == 8.0

def test_notification_scheduler():
    schedule = DinacharyaSchedule(
        user_id="test_user",
        adherence_score=1.0,
        routine_complexity="Moderate",
        morning_block=[
            Practice(name="Brahma Muhurta", time_slot="06:00 - 06:15", duration_minutes=15, description="Wake up", rationale="Test")
        ],
        midday_block=[],
        evening_block=[],
        timestamp=time.time()
    )
    notifs = NotificationScheduler.generate_pending_notifications(schedule, "1")
    assert len(notifs) == 1
    assert notifs[0]["practice_name"] == "Brahma Muhurta"

def test_pilot_evaluation_analytics():
    metrics = PilotEvaluationAnalytics.compute_study_metrics([1])
    assert "cohort_size" in metrics
    assert metrics["cohort_size"] == 1
    assert "average_adherence_score" in metrics

def test_api_wearable_sync_and_metrics_endpoints():
    app.dependency_overrides[get_current_user] = mocked_user
    
    # 1. Wearable Sync
    sync_resp = client.post("/api/wearables/sync", json={
        "provider": "apple_healthkit",
        "raw_payload": {
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {"value": 32.0},
            "HKQuantityTypeIdentifierRestingHeartRate": {"value": 72.0},
            "HKCategoryTypeIdentifierSleepAnalysis": {"value": 5.0},
            "HKQuantityTypeIdentifierBodyTemperature": {"value": 38.4}
        }
    })
    assert sync_resp.status_code == 200
    assert sync_resp.json()["status"] == "success"

    # 2. Metrics Endpoint
    metrics_resp = client.get("/api/evaluation/metrics")
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["cohort_size"] == 1
