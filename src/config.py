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

# Provider Selection
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").lower()

# Default AI Model based on provider
if LLM_PROVIDER == "nvidia":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-oss-20b")
else:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-3.5-turbo")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

def validate_config(strict: bool = False) -> Dict[str, Any]:
    """
    Validates application configuration and detects missing or placeholder secrets.
    Returns validation status dictionary.
    """
    issues = []
    if LLM_PROVIDER == "nvidia":
        if not NVIDIA_API_KEY or NVIDIA_API_KEY in ("placeholder_key", "your_nvidia_api_key_here"):
            issues.append("NVIDIA_API_KEY is empty or contains a documentation placeholder.")
    elif LLM_PROVIDER == "puter":
        if not PUTER_API_KEY or PUTER_API_KEY in ("placeholder_token", "your_puter_api_key_here"):
            issues.append("PUTER_API_KEY is empty or contains a documentation placeholder.")

    status = {
        "valid": len(issues) == 0,
        "provider": LLM_PROVIDER,
        "default_model": DEFAULT_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "issues": issues
    }

    if not status["valid"]:
        for issue in issues:
            logger.warning(f"[Config Validation Warning] {issue} Deterministic fallbacks will be used.")
        if strict:
            raise ValueError(f"Configuration validation failed: {issues}")

    return status
