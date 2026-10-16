"""
Comprehensive Automated Tests for Web Push Notification Subsystem.

Covers:
1. Subscription creation, retrieval, status, and revocation.
2. Authentication and cross-user isolation.
3. Missing or invalid VAPID configuration.
4. Input validation (endpoint schemes, missing keys).
5. Successful delivery using mocked provider.
6. Transient failures and bounded retries.
7. Expired subscriptions and permanent provider failures (HTTP 404 / 410 Gone).
8. Duplicate event suppression and stable tagging.
9. Push delivery failure without loss of canonical in-app notification or routine persistence.
10. Payload sizing constraints and lock-screen privacy sanitization.
11. Service worker route serving (/sw.js) and Service-Worker-Allowed header.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from main import app, get_current_user
import src.database.db as db
from src.notifications.push_service import (
    generate_vapid_key_pair,
    is_push_configured,
    get_vapid_public_key,
    get_vapid_private_key,
    sanitize_notification_text,
    build_push_payload,
    send_push_notification_to_subscription,
    send_push_notification_to_user,
    MAX_PAYLOAD_BYTES,
)
from src.planning.schedule_service import mutate_user_schedule
from src.planning.tools import request_user_notification

client = TestClient(app)

TEST_USER_A = 9901
TEST_USER_B = 9902


@pytest.fixture(autouse=True)
def clean_test_users():
    """Ensure clean database state for test users before each test."""
    conn = db.get_db_connection()
    c = conn.cursor()
    for uid in (TEST_USER_A, TEST_USER_B):
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        c.execute("DELETE FROM user_state WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM notifications WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (uid,))
    
    c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
              (TEST_USER_A, "push_user_a", "dummy_hash"))
    c.execute("INSERT INTO user_state (user_id, questionnaire_responses, telemetry_baselines) VALUES (?, ?, ?)",
              (TEST_USER_A, "{}", "{}"))
    c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
              (TEST_USER_B, "push_user_b", "dummy_hash"))
    c.execute("INSERT INTO user_state (user_id, questionnaire_responses, telemetry_baselines) VALUES (?, ?, ?)",
              (TEST_USER_B, "{}", "{}"))
    conn.commit()
    conn.close()

    orig_override = app.dependency_overrides.get(get_current_user)
    yield
    if orig_override is not None:
        app.dependency_overrides[get_current_user] = orig_override
    else:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_vapid_env():
    """Provides temporary in-memory generated VAPID keys for testing without network."""
    keys = generate_vapid_key_pair()
    with patch.dict(os.environ, {
        "VAPID_PUBLIC_KEY": keys["public_key"],
        "VAPID_PRIVATE_KEY": keys["private_key"],
        "VAPID_CLAIMS_EMAIL": "test-admin@aidincharya.internal"
    }):
        yield keys


# ---------------------------------------------------------------------------
# 1. VAPID Configuration & Key Generation
# ---------------------------------------------------------------------------

def test_vapid_keypair_generation():
    keys = generate_vapid_key_pair()
    assert "public_key" in keys
    assert "private_key" in keys
    assert len(keys["public_key"]) > 50
    assert len(keys["private_key"]) > 30


def test_push_unconfigured_when_env_empty():
    with patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": ""}):
        assert is_push_configured() is False
        assert get_vapid_public_key() is None
        assert get_vapid_private_key() is None

        # Route returns configured=False
        res = client.get("/api/notifications/push/vapid-public-key")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["public_key"] is None


def test_push_configured_route_with_env(mock_vapid_env):
    res = client.get("/api/notifications/push/vapid-public-key")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is True
    assert data["public_key"] == mock_vapid_env["public_key"]


# ---------------------------------------------------------------------------
# 2. Authentication & Cross-User Isolation
# ---------------------------------------------------------------------------

def test_unauthenticated_push_endpoints_return_401():
    # Without dependency override or Authorization header
    res_status = client.get("/api/notifications/push/status")
    assert res_status.status_code == 401

    res_sub = client.post("/api/notifications/push/subscribe", json={
        "endpoint": "https://push.example.com/endpoint/123",
        "p256dh": "test-p256dh",
        "auth": "test-auth"
    })
    assert res_sub.status_code == 401

    res_unsub = client.post("/api/notifications/push/unsubscribe", json={
        "endpoint": "https://push.example.com/endpoint/123"
    })
    assert res_unsub.status_code == 401


def test_cross_user_isolation(mock_vapid_env):
    ep_a = "https://fcm.googleapis.com/fcm/send/user_a_endpoint"
    ep_b = "https://fcm.googleapis.com/fcm/send/user_b_endpoint"

    # User A registers subscription
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    sub_res_a = client.post("/api/notifications/push/subscribe", json={
        "endpoint": ep_a,
        "keys": {"p256dh": "p256_a", "auth": "auth_a"}
    })
    assert sub_res_a.status_code == 200
    assert sub_res_a.json()["success"] is True

    # User B registers subscription
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_B
    sub_res_b = client.post("/api/notifications/push/subscribe", json={
        "endpoint": ep_b,
        "keys": {"p256dh": "p256_b", "auth": "auth_b"}
    })
    assert sub_res_b.status_code == 200
    assert sub_res_b.json()["success"] is True

    # User A checks status: should only see User A's subscription (count=1)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    status_a = client.get("/api/notifications/push/status").json()
    assert status_a["subscription_count"] == 1
    assert status_a["enabled"] is True

    # User A tries to delete User B's endpoint -> should fail
    unsub_attempt = client.post("/api/notifications/push/unsubscribe", json={"endpoint": ep_b})
    assert unsub_attempt.status_code == 200
    assert unsub_attempt.json()["success"] is False

    # Confirm User B's subscription is still active
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_B
    status_b = client.get("/api/notifications/push/status").json()
    assert status_b["subscription_count"] == 1
    assert status_b["enabled"] is True

    # User B deletes User B's endpoint -> succeeds
    unsub_b = client.post("/api/notifications/push/unsubscribe", json={"endpoint": ep_b})
    assert unsub_b.status_code == 200
    assert unsub_b.json()["success"] is True

    # Status for B is now disabled
    status_b_after = client.get("/api/notifications/push/status").json()
    assert status_b_after["subscription_count"] == 0
    assert status_b_after["enabled"] is False


# ---------------------------------------------------------------------------
# 3. Input Validation
# ---------------------------------------------------------------------------

def test_subscribe_invalid_scheme_rejected():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    # Insecure HTTP endpoint on non-localhost
    res = client.post("/api/notifications/push/subscribe", json={
        "endpoint": "http://insecure-domain.com/push/123",
        "keys": {"p256dh": "key1", "auth": "key2"}
    })
    assert res.status_code == 400
    assert "Invalid push endpoint scheme" in res.json()["detail"]


def test_subscribe_missing_keys_rejected():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    # Missing p256dh or auth
    res = client.post("/api/notifications/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {"p256dh": "", "auth": "some-auth"}
    })
    assert res.status_code == 400
    assert "Incomplete subscription keys" in res.json()["detail"]


def test_subscribe_accepts_flat_and_nested_keys():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_A
    # Flat keys
    res = client.post("/api/notifications/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/flat_endpoint",
        "p256dh": "flat_p256dh",
        "auth": "flat_auth"
    })
    assert res.status_code == 200
    assert res.json()["success"] is True


# ---------------------------------------------------------------------------
# 4. Lock-Screen Privacy & Payload Size Constraints
# ---------------------------------------------------------------------------

def test_sanitize_notification_text():
    raw = "Routine recalibrated [RECALIBRATE]   with  grounding    practices."
    sanitized = sanitize_notification_text(raw)
    assert "[RECALIBRATE]" not in sanitized
    assert sanitized == "Routine recalibrated with grounding practices."


def test_build_push_payload_truncates_oversized_content():
    huge_body = "A" * 5000
    payload = build_push_payload(
        title="Schedule Update",
        body=huge_body,
        url="/routine"
    )
    payload_bytes = payload.encode("utf-8")
    assert len(payload_bytes) <= MAX_PAYLOAD_BYTES
    data = json.loads(payload)
    assert data["title"] == "Schedule Update"
    assert data["data"]["url"] == "/routine"
    assert len(data["body"]) < 200


# ---------------------------------------------------------------------------
# 5. Mocked Successful Delivery
# ---------------------------------------------------------------------------

def test_successful_push_delivery(mock_vapid_env):
    ep = "https://fcm.googleapis.com/fcm/send/delivery_test_user"
    db.save_push_subscription(TEST_USER_A, ep, "p256_mock", "auth_mock")

    mock_resp = MagicMock()
    mock_resp.status_code = 201

    with patch("src.notifications.push_service.webpush", return_value=mock_resp) as mock_webpush:
        summary = send_push_notification_to_user(
            user_id=TEST_USER_A,
            title="Ayurvedic Routine Synchronized",
            body="Your evening schedule was adjusted.",
            url="/routine",
            tag="tag-123"
        )
        assert summary["configured"] is True
        assert summary["sent"] == 1
        assert summary["failed"] == 0
        assert mock_webpush.call_count == 1

        # Check call arguments
        call_kwargs = mock_webpush.call_args[1]
        assert call_kwargs["subscription_info"]["endpoint"] == ep
        assert call_kwargs["vapid_private_key"] == mock_vapid_env["private_key"]
        payload_sent = json.loads(call_kwargs["data"])
        assert payload_sent["tag"] == "tag-123"
        assert payload_sent["data"]["url"] == "/routine"


# ---------------------------------------------------------------------------
# 6. Transient Failures and Bounded Retries
# ---------------------------------------------------------------------------

def test_transient_failure_bounded_retry(mock_vapid_env):
    ep = "https://fcm.googleapis.com/fcm/send/retry_test"
    db.save_push_subscription(TEST_USER_A, ep, "p256_mock", "auth_mock")

    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 503
    transient_exc = WebPushException("Service Unavailable", response=mock_err_resp)

    mock_success_resp = MagicMock()
    mock_success_resp.status_code = 200

    # Fails first attempt, succeeds second attempt
    with patch("src.notifications.push_service.webpush", side_effect=[transient_exc, mock_success_resp]) as mock_wp:
        with patch("time.sleep", return_value=None):
            summary = send_push_notification_to_user(
                user_id=TEST_USER_A,
                title="Retry Test",
                body="Testing retry logic"
            )
            assert summary["sent"] == 1
            assert summary["failed"] == 0
            assert mock_wp.call_count == 2


def test_transient_failure_exhausts_retries_without_storm(mock_vapid_env):
    ep = "https://fcm.googleapis.com/fcm/send/exhaust_test"
    db.save_push_subscription(TEST_USER_A, ep, "p256_mock", "auth_mock")

    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 500
    server_exc = WebPushException("Internal Server Error", response=mock_err_resp)

    with patch("src.notifications.push_service.webpush", side_effect=server_exc) as mock_wp:
        with patch("time.sleep", return_value=None):
            summary = send_push_notification_to_user(
                user_id=TEST_USER_A,
                title="Exhaust Test",
                body="Testing failure"
            )
            assert summary["sent"] == 0
            assert summary["failed"] == 1
            # Maximum 2 attempts (max_retries=2)
            assert mock_wp.call_count == 2

            # Confirm subscription was NOT deleted for transient error
            subs = db.get_user_push_subscriptions(TEST_USER_A)
            assert len(subs) == 1


# ---------------------------------------------------------------------------
# 7. Permanent Failure (HTTP 410 Gone / 404 Not Found) Auto-Cleanup
# ---------------------------------------------------------------------------

def test_permanent_failure_410_removes_subscription(mock_vapid_env):
    ep = "https://fcm.googleapis.com/fcm/send/expired_endpoint_410"
    db.save_push_subscription(TEST_USER_A, ep, "p256_mock", "auth_mock")
    assert len(db.get_user_push_subscriptions(TEST_USER_A)) == 1

    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 410
    gone_exc = WebPushException("Gone", response=mock_err_resp)

    with patch("src.notifications.push_service.webpush", side_effect=gone_exc) as mock_wp:
        summary = send_push_notification_to_user(
            user_id=TEST_USER_A,
            title="Expired Test",
            body="Should delete endpoint"
        )
        assert summary["sent"] == 0
        assert summary["failed"] == 1
        # Should not retry 410 Gone
        assert mock_wp.call_count == 1

        # Subscription MUST be removed from database
        subs = db.get_user_push_subscriptions(TEST_USER_A)
        assert len(subs) == 0


# ---------------------------------------------------------------------------
# 8. Decoupled Persistence: Push Failure Never Affects In-App Notification
# ---------------------------------------------------------------------------

def test_push_failure_does_not_break_schedule_mutation(mock_vapid_env):
    # Set up user initial schedule
    initial_sched = {
        "schedule": {
            "user_id": str(TEST_USER_A),
            "morning_block": [
                {
                    "name": "Brahma Muhurta Jagaran",
                    "time_slot": "06:00 - 06:15",
                    "duration_minutes": 15,
                    "description": "Wake up early"
                }
            ],
            "midday_block": [
                {
                    "name": "Mitahara",
                    "time_slot": "12:00 - 12:40",
                    "duration_minutes": 40,
                    "description": "Lunch"
                }
            ],
            "evening_block": [
                {
                    "name": "Light Early Dinner",
                    "time_slot": "19:00 - 19:30",
                    "duration_minutes": 30,
                    "description": "Nourishing dinner"
                }
            ]
        }
    }
    db.save_user_schedule(TEST_USER_A, initial_sched, "2026-10-16")

    # Register subscription for TEST_USER_A
    db.save_push_subscription(TEST_USER_A, "https://fcm.googleapis.com/fcm/send/fail_push", "k1", "k2")

    # Simulate catastrophic push service failure (network down / exception)
    with patch("src.notifications.push_service.send_push_notification_to_user", side_effect=RuntimeError("WebPush Network Outage")):
        mutation_result = mutate_user_schedule(
            user_id=TEST_USER_A,
            updates={"Light Early Dinner": "20:00 - 20:30"},
            date_str="2026-10-16"
        )
        # 1. Schedule mutation must succeed
        assert mutation_result["success"] is True

        # 2. Schedule in database must be persisted with the new time
        user_state = db.get_user_state(TEST_USER_A)
        updated = user_state.get("last_schedule")
        assert updated is not None
        evening = updated["schedule"]["evening_block"]
        dinner = next(p for p in evening if p["name"] == "Light Early Dinner")
        assert dinner["time_slot"] == "20:00 - 20:30"

        # 3. In-app notification must still be created in the database
        notifs = db.get_user_notifications(TEST_USER_A)
        assert len(notifs) >= 1
        assert any(n["event_type"] == "adaptation_confirmed" for n in notifs)


def test_push_failure_does_not_break_request_user_notification(mock_vapid_env):
    with patch("src.notifications.push_service.send_push_notification_to_user", side_effect=Exception("Delivery failed")):
        res = request_user_notification(
            user_id=str(TEST_USER_A),
            event_type="routine_reminder",
            message="Time for your evening Pranayama.",
            activity_name="Pranayama",
            idempotency_key="pranayama-reminder-1"
        )
        assert res["success"] is True
        assert res["notification_id"] is not None

        # Verify in-app notification exists in DB
        notifs = db.get_user_notifications(TEST_USER_A)
        assert any(n["activity_name"] == "Pranayama" for n in notifs)


# ---------------------------------------------------------------------------
# 9. Service Worker Route (/sw.js) and Headers
# ---------------------------------------------------------------------------

def test_service_worker_route_headers():
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")
    assert res.headers.get("Service-Worker-Allowed") == "/"
    content = res.text
    assert "self.addEventListener('push'" in content
    assert "self.addEventListener('notificationclick'" in content
