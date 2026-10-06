"""Loads settings from the .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hiring_ai")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1")
# "localhost" is first tried over IPv6 on Windows, which Ollama does not listen on: every connection then waits
# ~2 seconds before falling back. Using 127.0.0.1 directly avoids that delay on every AI call.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").replace("://localhost", "://127.0.0.1")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
# The secret key that signs the sign-in tokens (services/security.py). Keep it private: anyone who knows it
# could make their own tokens. Changing it signs everybody out.
JWT_SECRET = os.getenv("JWT_SECRET", "")

APP_NAME = "Hiring AI Assistant"
