import logging
import os
from itertools import cycle
from typing import Any, Iterable
from types import SimpleNamespace

from openai import OpenAI

logger = logging.getLogger("DinacharyaLLM")


def _is_retryable_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403, 408, 409, 429} or status_code is not None and status_code >= 500:
        return True

    message = str(error).lower()
    return any(term in message for term in ("rate limit", "quota", "too many requests", "timed out"))


class RotatingLLMClient:
    """Expose an OpenAI-compatible client while rotating hosted free-tier providers."""

    def __init__(self, clients: Iterable[tuple[str, OpenAI]], models: dict[str, str]):
        self._clients = list(clients)
        self._models = models
        self._client_cycle = cycle(range(len(self._clients)))
        self._next_client_index = next(self._client_cycle) if self._clients else 0

        if not self._clients:
            raise ValueError("No LLM clients are configured.")

        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        errors = []
        start_index = self._next_client_index

        for offset in range(len(self._clients)):
            index = (start_index + offset) % len(self._clients)
            provider, client = self._clients[index]
            request = dict(kwargs)
            request["model"] = self._models.get(provider, kwargs.get("model"))

            try:
                response = client.chat.completions.create(**request)
                self._next_client_index = (index + 1) % len(self._clients)
                return response
            except Exception as error:
                errors.append(f"{provider}: {error}")
                if not _is_retryable_error(error):
                    raise
                logger.warning("LLM request failed on %s; trying the next provider: %s", provider, error)

        raise RuntimeError("All configured LLM providers failed: " + " | ".join(errors))


def build_llm_client(
    provider: str,
    default_model: str,
    gemini_base_url: str,
    gemini_api_keys: list[str],
    openrouter_base_url: str,
    openrouter_api_key: str,
    openrouter_model: str,
    puter_base_url: str,
    puter_api_key: str,
    nvidia_base_url: str,
    nvidia_api_key: str,
) -> RotatingLLMClient | OpenAI:
    if provider == "nvidia":
        return OpenAI(base_url=nvidia_base_url, api_key=nvidia_api_key, timeout=60.0)

    if provider == "puter":
        return OpenAI(base_url=puter_base_url, api_key=puter_api_key, timeout=60.0)

    if provider == "gemini":
        clients = [
            ("gemini", OpenAI(base_url=gemini_base_url, api_key=api_key, timeout=60.0))
            for api_key in gemini_api_keys
        ]
        if openrouter_api_key:
            clients.append(("openrouter", OpenAI(base_url=openrouter_base_url, api_key=openrouter_api_key, timeout=60.0)))
        models = {"gemini": default_model, "openrouter": openrouter_model}
        return RotatingLLMClient(clients, models)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def configured_gemini_keys() -> list[str]:
    return [key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()]