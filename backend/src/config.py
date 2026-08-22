import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Puter AI Configuration
PUTER_BASE_URL = os.getenv("PUTER_BASE_URL", "https://api.puter.com/puterai/openai/v1/")
PUTER_API_KEY = os.getenv("PUTER_API_KEY", "placeholder_token")

# Custom / Local LLM Configuration (Replacing NVIDIA NIM)
CUSTOM_LLM_BASE_URL = os.getenv("CUSTOM_LLM_BASE_URL", os.getenv("NVIDIA_BASE_URL", "http://localhost:8000/v1"))
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", os.getenv("NVIDIA_API_KEY", "custom-llm-key"))
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL", "custom-ayurveda-llm")

# Provider Selection: Default to our own created LLM ("custom_llm")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "custom_llm").lower()

# Default AI Model based on provider
if LLM_PROVIDER in ("custom_llm", "custom", "our_llm"):
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", CUSTOM_LLM_MODEL)
elif LLM_PROVIDER == "nvidia":
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "meta/llama-3.1-70b-instruct")
else:
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
