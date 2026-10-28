"""
Automated unit & integration tests for AI Reasoning Engine Live SSE Streaming endpoint (/api/chat/stream).
Verifies:
1. Unauthenticated requests are rejected (401).
2. Authenticated streaming produces text/event-stream content.
3. SSE events include structured live trace events ('type': 'trace') and a terminal 'final_response' event.
4. Timings and tool execution metadata are captured and streamed to the client without dropping data.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app, get_current_user
import src.database.db as db


@pytest.fixture(autouse=True)
def init_test_db(tmp_path):
    test_db = tmp_path / "test_stream.db"
    with patch.object(db, "DB_PATH", str(test_db)):
        db.init_db()
        yield


def test_chat_stream_unauthorized():
    client = TestClient(app)
    response = client.post("/api/chat/stream", json={"message": "Hello"})
    assert response.status_code == 401


def test_chat_stream_mocked_llm_execution():
    test_user_id = db.create_user("stream_test_user", "TestPass123!")
    app.dependency_overrides[get_current_user] = lambda: test_user_id
    client = TestClient(app)

    from src.llm_gateway import LLMResponse
    fake_chat_response = LLMResponse(
        content="Here is your Ayurvedic guidance for the morning.",
        model_used="mock-reasoning-model",
        is_fallback=False
    )

    def fake_execute_tool_loop(*args, **kwargs):
        on_event = kwargs.get("on_event")
        trace_events = kwargs.get("trace_events")
        evt1 = {"type": "trace", "stage": "tool_call_start", "tool": "review_schedule_adherence"}
        evt2 = {"type": "trace", "stage": "tool_call_result", "tool": "review_schedule_adherence", "duration_ms": 12.5}
        if on_event:
            on_event(evt1)
            on_event(evt2)
        if trace_events is not None:
            trace_events.extend([evt1, evt2])
        return fake_chat_response

    with patch("src.llm_gateway.LLMGateway.execute_tool_loop", side_effect=fake_execute_tool_loop):
        resp = client.post("/api/chat/stream", json={"message": "Can I do Pranayama earlier?"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        events = []
        raw_lines = resp.text.split("\n\n")
        for chunk in raw_lines:
            chunk = chunk.strip()
            if chunk.startswith("data: "):
                payload = json.loads(chunk[6:])
                events.append(payload)

        # Must have at least trace events and the final_response event
        trace_stages = [e.get("stage") for e in events if e.get("type") == "trace"]
        assert "query_received" in trace_stages
        assert "rag_retrieval_complete" in trace_stages
        assert "tool_call_start" in trace_stages
        assert "tool_call_result" in trace_stages

        final_events = [e for e in events if e.get("type") == "final_response"]
        assert len(final_events) == 1
        final_payload = final_events[0]
        assert "Here is your Ayurvedic guidance" in final_payload["response"]
        assert final_payload["timings"]["model_used"] == "mock-reasoning-model"

    app.dependency_overrides.clear()
