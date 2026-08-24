import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Google AI Studio / Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_KEY", "")))
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Puter AI Configuration
PUTER_BASE_URL = os.getenv("PUTER_BASE_URL", "https://api.puter.com/puterai/openai/v1/")
PUTER_API_KEY = os.getenv("PUTER_API_KEY", "placeholder_token")

# Custom / Local LLM Configuration (Replacing NVIDIA NIM)
CUSTOM_LLM_BASE_URL = os.getenv("CUSTOM_LLM_BASE_URL", os.getenv("NVIDIA_BASE_URL", "http://localhost:8000/v1"))
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", os.getenv("NVIDIA_API_KEY", "custom-llm-key"))
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL", "custom-ayurveda-llm")

# Provider Selection: Default to "gemini" if API key present or configured, else "custom_llm"
_env_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
if _env_provider:
    LLM_PROVIDER = _env_provider
elif GEMINI_API_KEY:
    LLM_PROVIDER = "gemini"
else:
    LLM_PROVIDER = "custom_llm"

# Default AI Model based on provider
if LLM_PROVIDER in ("gemini", "google", "google_ai_studio"):
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", GEMINI_MODEL)
elif LLM_PROVIDER in ("custom_llm", "custom", "our_llm"):
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", CUSTOM_LLM_MODEL)
elif LLM_PROVIDER == "nvidia":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "meta/llama-3.1-70b-instruct")
else:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
