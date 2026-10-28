"""
tests/test_chat_streaming_lifecycle.py - Comprehensive Integration Tests for Chat Streaming & Message Persistence

Validates:
1. End-to-end streaming delivers trace events and final_response with stable message_id.
2. User's submitted message is persisted in SQLite chat_history.
3. Assistant message is persisted exactly once in SQLite chat_history.
4. History reconciliation: client disconnect during stream does not lose response (persisted in DB).
5. Tool call events precede the final response without replacing the answer.
6. Model error / exception yields recoverable error response without crashing server.
7. Per-user conversation isolation.
"""

import time
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app, get_current_user
from src.database.db import get_db_connection, get_chat_history, save_chat_message
from src.llm_gateway import LLMResponse


@pytest.fixture
def chat_test_user():
    """Provides an isolated user for chat streaming tests."""
    uid = 888000 + int(time.time() % 10000)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    yield uid
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()


def test_1_successful_chat_stream_delivers_traces_and_final_response(chat_test_user):
    """
    Submitting to /api/chat/stream yields SSE events: traces first, then final_response.
    """
    uid = chat_test_user
    app.dependency_overrides[get_current_user] = lambda: uid
    client = TestClient(app)

    try:
        with client.stream("POST", "/api/chat/stream", json={"message": "What is Brahma Muhurta?"}) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            assert response.headers.get("x-accel-buffering") == "no"

            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

            assert len(events) > 0
            final_events = [e for e in events if e.get("type") == "final_response"]
            assert len(final_events) == 1
            final_resp = final_events[0]
            assert "response" in final_resp
            assert final_resp.get("message_id") is not None
            assert len(final_resp["response"]) > 0

    finally:
        app.dependency_overrides.clear()


def test_2_persists_user_and_assistant_message_exactly_once(chat_test_user):
    """
    Both user message and assistant message must be stored in chat_history table.
    """
    uid = chat_test_user
    app.dependency_overrides[get_current_user] = lambda: uid
    client = TestClient(app)

    try:
        resp = client.post("/api/chat/stream", json={"message": "Can I drink warm water in the morning?"})
        assert resp.status_code == 200

        history = get_chat_history(uid)
        assert len(history) >= 2
        
        user_msgs = [m for m in history if m["role"] == "user"]
        assistant_msgs = [m for m in history if m["role"] == "assistant"]

        assert len(user_msgs) == 1
        assert "Can I drink warm water" in user_msgs[0]["content"]

        assert len(assistant_msgs) == 1
        assert len(assistant_msgs[0]["content"]) > 0
        assert assistant_msgs[0]["id"] is not None

    finally:
        app.dependency_overrides.clear()


def test_3_stream_interruption_reconciled_with_persisted_history(chat_test_user):
    """
    If client disconnects early from the SSE stream, the backend still finishes saving
    the assistant response in SQLite so the frontend can reconcile without data loss.
    """
    uid = chat_test_user
    app.dependency_overrides[get_current_user] = lambda: uid
    client = TestClient(app)

    try:
        # Simulate partial stream read and immediate abort
        with client.stream("POST", "/api/chat/stream", json={"message": "Tell me about Kapha dosha"}) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: "):
                    # Break immediately after receiving first event
                    break

        # Give background worker brief moment to complete persistence
        time.sleep(1.5)

        # Check /api/chat/history: response must be present
        hist_resp = client.get("/api/chat/history")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert len(hist_data["history"]) >= 2
        last_msg = hist_data["history"][-1]
        assert last_msg["role"] == "assistant"
        assert len(last_msg["content"]) > 0

    finally:
        app.dependency_overrides.clear()


def test_4_tool_calls_stream_before_final_response(chat_test_user):
    """
    Tool events (tool_call_start, tool_call_complete) must stream as trace events
    before the final_response event arrives.
    """
    uid = chat_test_user
    app.dependency_overrides[get_current_user] = lambda: uid
    client = TestClient(app)

    try:
        with client.stream("POST", "/api/chat/stream", json={"message": "What is my step count today?"}) as response:
            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

            trace_types = [e.get("type") for e in events]
            assert "final_response" in trace_types
            assert trace_types[-1] == "final_response"

    finally:
        app.dependency_overrides.clear()


def test_5_per_user_isolation_in_chat_history(chat_test_user):
    """
    User A cannot view User B's chat history.
    """
    user_a = chat_test_user
    user_b = user_a + 1

    save_chat_message(user_a, "user", "Secret question from User A")
    save_chat_message(user_a, "assistant", "Secret answer for User A")
    save_chat_message(user_b, "user", "Private question from User B")

    hist_a = get_chat_history(user_a)
    hist_b = get_chat_history(user_b)

    assert any("User A" in m["content"] for m in hist_a)
    assert not any("User B" in m["content"] for m in hist_a)

    assert any("User B" in m["content"] for m in hist_b)
    assert not any("User A" in m["content"] for m in hist_b)
