import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Puter AI Configuration
PUTER_BASE_URL = os.getenv("PUTER_BASE_URL", "https://api.puter.com/puterai/openai/v1/")
PUTER_API_KEY = os.getenv("PUTER_API_KEY", os.getenv("OPENAI_API_KEY", "placeholder_token"))

# Default AI Model (Puter AI supports various models)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

# FastAPI Configurations
APP_NAME = "Ayurvedic Dinacharya Automation API"
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
