import logging
from openai import OpenAI
from src.config import (
    CUSTOM_LLM_BASE_URL,
    CUSTOM_LLM_API_KEY,
    PUTER_BASE_URL,
    PUTER_API_KEY,
    GEMINI_BASE_URL,
    GEMINI_API_KEY,
    LLM_PROVIDER
)

logger = logging.getLogger(__name__)

def build_llm_client(
    provider: str = LLM_PROVIDER,
    custom_base_url: str = CUSTOM_LLM_BASE_URL,
    custom_api_key: str = CUSTOM_LLM_API_KEY,
    gemini_base_url: str = GEMINI_BASE_URL,
    gemini_api_key: str = GEMINI_API_KEY,
    puter_base_url: str = PUTER_BASE_URL,
    puter_api_key: str = PUTER_API_KEY,
    timeout: float = 60.0
) -> OpenAI:
    """
    Factory function to construct an OpenAI API-compatible client.
    Supports Google AI Studio (Gemini), Custom LLMs, Puter AI, and standard OpenAI endpoints.
    """
    provider_clean = (provider or "").strip().lower()

    if provider_clean in ("gemini", "google", "google_ai_studio"):
        logger.info(f"Initializing Google AI Studio (Gemini) Client pointing to: {gemini_base_url}")
        return OpenAI(
            base_url=gemini_base_url,
            api_key=gemini_api_key or "invalid_key",
            timeout=timeout
        )
    elif provider_clean in ("custom_llm", "custom", "our_llm", "nvidia", "vllm", "ollama"):
        logger.info(f"Initializing Custom LLM Client pointing to: {custom_base_url}")
        return OpenAI(
            base_url=custom_base_url,
            api_key=custom_api_key,
            timeout=timeout
        )
    elif provider_clean == "puter":
        logger.info(f"Initializing Puter AI Client pointing to: {puter_base_url}")
        return OpenAI(
            base_url=puter_base_url,
            api_key=puter_api_key,
            timeout=timeout
        )
    else:
        logger.info(f"Initializing LLM Client for '{provider_clean}' with base URL: {custom_base_url}")
        return OpenAI(
            base_url=custom_base_url,
            api_key=custom_api_key,
            timeout=timeout
        )
