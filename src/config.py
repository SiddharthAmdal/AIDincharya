import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger("AiDincharyaConfig")

# Puter AI Configuration
PUTER_BASE_URL = os.getenv("PUTER_BASE_URL", "https://api.puter.com/puterai/openai/v1/")
PUTER_API_KEY = os.getenv("PUTER_API_KEY", "")

# NVIDIA NIM Configuration
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# Gemini (Google AI Studio) and OpenRouter Configuration
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_raw_gemini_keys = [key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()]
if GEMINI_API_KEY and GEMINI_API_KEY not in _raw_gemini_keys:
    _raw_gemini_keys.insert(0, GEMINI_API_KEY)
GEMINI_API_KEYS = _raw_gemini_keys
if not GEMINI_API_KEY and GEMINI_API_KEYS:
    GEMINI_API_KEY = GEMINI_API_KEYS[0]

# High-rate-limit Google AI Studio model (Gemini 3.5 Flash-Lite has the highest RPM/TPM/RPD allowance)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
THIRD_FALLBACK_MODEL = os.getenv("THIRD_FALLBACK_MODEL", GEMINI_MODEL)

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

# Provider Selection
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").lower()

# Default AI Model based on provider
if LLM_PROVIDER == "nvidia":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-oss-20b")
elif LLM_PROVIDER == "gemini":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.5-flash-lite")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gemini-3.1-flash-lite")
else:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-3.5-turbo")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")


def is_valid_gemini_key(key: str) -> bool:
    """Returns True if the provided Gemini API key is non-empty and not a placeholder."""
    if not key or not key.strip():
        return False
    return key.strip() not in (
        "placeholder_key",
        "your_gemini_api_key_here",
        "your_google_ai_studio_key_here",
        "GEMINI_API_KEY",
    )


def get_valid_gemini_keys() -> list[str]:
    """Returns all configured non-placeholder Gemini API keys (checking env dynamically as well)."""
    env_single = os.getenv("GEMINI_API_KEY", "").strip()
    env_multi = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    combined = []
    for k in [env_single] + env_multi + list(GEMINI_API_KEYS):
        if is_valid_gemini_key(k) and k not in combined:
            combined.append(k)
    return combined


def validate_config(strict: bool = False) -> Dict[str, Any]:
    """
    Validates application configuration and detects missing or placeholder secrets.
    Returns validation status dictionary.
    """
    issues = []
    if LLM_PROVIDER == "nvidia":
        if not NVIDIA_API_KEY or NVIDIA_API_KEY in ("placeholder_key", "your_nvidia_api_key_here"):
            issues.append("NVIDIA_API_KEY is empty or contains a documentation placeholder.")
    elif LLM_PROVIDER == "gemini":
        if not get_valid_gemini_keys():
            issues.append("GEMINI_API_KEY is empty or contains a documentation placeholder.")
    elif LLM_PROVIDER == "puter":
        if not PUTER_API_KEY or PUTER_API_KEY in ("placeholder_token", "your_puter_api_key_here"):
            issues.append("PUTER_API_KEY is empty or contains a documentation placeholder.")

    status = {
        "valid": len(issues) == 0,
        "provider": LLM_PROVIDER,
        "default_model": DEFAULT_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "third_fallback_model": THIRD_FALLBACK_MODEL,
        "gemini_fallback_configured": len(get_valid_gemini_keys()) > 0,
        "issues": issues
    }

    if not status["valid"]:
        for issue in issues:
            logger.warning(f"[Config Validation Warning] {issue} Deterministic fallbacks will be used.")
        if strict:
            raise ValueError(f"Configuration validation failed: {issues}")

    return status
