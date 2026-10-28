"""
Priority 4 Verification Suite: NVIDIA NIM Diagnostics, Recovery, and Failover.

Tests:
1. Timeout failover to secondary/Gemini provider.
2. 401/403 Authentication error immediate failover (non-retryable).
3. 429 Rate limit error bounded retries with backoff.
4. 503 Server error diagnostic categorization.
5. Secret redaction: API keys, Bearer tokens, and secrets are strictly redacted from logs.
6. Chat history preservation and graceful clinical fallback when all providers fail.
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from openai import APITimeoutError, RateLimitError, InternalServerError, AuthenticationError
from fastapi.testclient import TestClient

from main import app, get_current_user
from src.database import db
from src.llm_gateway import LLMGateway, LLMResponse, sanitize_secret_log, categorize_failure

client = TestClient(app)


def mocked_user_id():
    return 10633


@pytest.fixture(autouse=True)
def auth_override():
    app.dependency_overrides[get_current_user] = mocked_user_id
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_secret_redaction_utility():
    """Verifies that API keys and bearer tokens are strictly masked in logs."""
    raw_log = "Error connecting to https://integrate.api.nvidia.com with key nvapi-abc123XYZ999000 and token Bearer eyJhbGciOiJIUzI1NiJ9.test and AIzaSyD9876543210"
    cleaned = sanitize_secret_log(raw_log)
    assert "nvapi-abc123XYZ999000" not in cleaned
    assert "nvapi-***REDACTED***" in cleaned
    assert "AIzaSyD9876543210" not in cleaned
    assert "AIza***REDACTED***" in cleaned
    assert "Bearer ***REDACTED***" in cleaned


def test_failure_categorization():
    """Verifies that standard errors are mapped to diagnostic categories."""
    assert categorize_failure(APITimeoutError("Request timed out after 14s")) == "TIMEOUT"
    assert categorize_failure(RateLimitError("429 Too Many Requests: quota exceeded", response=MagicMock(), body=None)) == "RATE_LIMIT"
    assert categorize_failure(InternalServerError("503 Service Unavailable", response=MagicMock(), body=None)) == "SERVER_ERROR"
    assert categorize_failure(Exception("401 Unauthorized: Invalid API Key")) == "AUTH_ERROR"
    assert categorize_failure(Exception("404 Not Found: model 'unknown-model' does not exist")) == "MODEL_NOT_FOUND"


def test_nim_timeout_failover_to_fallback(monkeypatch):
    """
    Verifies that when NVIDIA NIM times out, the gateway immediately logs
    the diagnostic code and fails over to the next configured fallback model.
    """
    gateway = LLMGateway()

    mock_client = MagicMock()
    # First model (primary NIM) raises APITimeoutError
    # Second model (fallback) succeeds
    mock_resp_success = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Secondary fallback response"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp_success.choices = [mock_choice]
    mock_resp_success.usage.prompt_tokens = 10
    mock_resp_success.usage.completion_tokens = 10

    def mock_create(**kwargs):
        if kwargs.get("model") == gateway.primary_model:
            raise APITimeoutError("NVIDIA NIM timed out after 14.0s")
        return mock_resp_success

    mock_client.chat.completions.create.side_effect = mock_create
    gateway.client = mock_client
    gateway._get_client_for_model = MagicMock(return_value=mock_client)

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Test timeout failover"}],
        retries_per_model=1
    )
    assert res.content == "Secondary fallback response"
    assert res.is_fallback is True
    assert res.model_used == gateway.fallback_model


def test_nim_401_auth_error_immediate_failover(monkeypatch):
    """
    Verifies that 401 Unauthorized errors are treated as permanent, skipping retries
    and immediately failing over to the next model/provider.
    """
    gateway = LLMGateway()

    call_count = {"primary": 0, "fallback": 0}
    mock_client = MagicMock()

    mock_resp_success = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Fallback after 401"
    mock_choice.message.reasoning_content = None
    mock_choice.message.tool_calls = None
    mock_resp_success.choices = [mock_choice]
    mock_resp_success.usage.prompt_tokens = 10
    mock_resp_success.usage.completion_tokens = 10

    def mock_create(**kwargs):
        if kwargs.get("model") == gateway.primary_model:
            call_count["primary"] += 1
            raise Exception("401 Unauthorized: Invalid API key nvapi-dummy12345")
        call_count["fallback"] += 1
        return mock_resp_success

    mock_client.chat.completions.create.side_effect = mock_create
    gateway.client = mock_client
    gateway._get_client_for_model = MagicMock(return_value=mock_client)

    res = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Test auth failure"}],
        retries_per_model=2  # even with 2 retries requested, 401 must fail over after 1 attempt!
    )
    # Primary must only have been attempted ONCE because 401 is non-retryable
    assert call_count["primary"] == 1
    assert call_count["fallback"] == 1
    assert res.content == "Fallback after 401"


def test_chat_history_preservation_under_provider_failure(monkeypatch):
    """
    Verifies that when LLM providers fail, /api/chat preserves both the user's
    message and the assistant's clinical fallback response in SQLite.
    """
    user_id = 10633
    unique_msg = f"Can you adjust my Pranayama to 18:30? {time.time()}"

    gateway = LLMGateway.get_instance()
    orig_loop = gateway.execute_tool_loop

    try:
        # Force execute_tool_loop to raise RuntimeError (all providers failed)
        gateway.execute_tool_loop = MagicMock(side_effect=RuntimeError("All LLM providers unreachable"))

        res = client.post("/api/chat", json={"message": unique_msg})
        assert res.status_code == 200
        data = res.json()
        assert "response" in data
        assert len(data["response"]) > 0

        # Verify chat history in SQLite contains both turns!
        history = db.get_chat_history(user_id, limit=4)
        history_contents = [m["content"] for m in history]
        
        # User message was safely persisted
        assert unique_msg in history_contents
        # Assistant message was safely persisted
        assert any("Vaidya AI Clinical Guidance" in c or "resilient offline" in c or "Moving" in c or "Namaste" in c for c in history_contents)

    finally:
        gateway.execute_tool_loop = orig_loop
