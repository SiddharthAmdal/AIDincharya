import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Puter AI Configuration
PUTER_BASE_URL = os.getenv("PUTER_BASE_URL", "https://api.puter.com/puterai/openai/v1/")
PUTER_API_KEY = os.getenv("PUTER_API_KEY", "placeholder_token")

# NVIDIA NIM Configuration
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "placeholder_key")

# Gemini and OpenRouter Configuration
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_API_KEYS = [key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()]
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

# Provider Selection
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").lower()

# Default AI Model based on provider
if LLM_PROVIDER == "nvidia":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "meta/llama-3.1-70b-instruct")
elif LLM_PROVIDER == "gemini":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
else:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
