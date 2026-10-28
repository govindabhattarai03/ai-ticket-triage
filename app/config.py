"""Settings read from environment variables (or a local `.env` file).

The API key is never written in the code, so it can never leak to GitHub.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Which LLM to use: "gemini", "ollama" or "fake" (offline, no key needed)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "fake")

# Gemini (free key from https://aistudio.google.com)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# Ollama (runs a model locally, see https://ollama.com)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# How many times to ask the LLM again when its answer is not valid
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# Where tickets are stored (a single SQLite file). ":memory:" = temporary, used by tests.
DATABASE_PATH = os.getenv("DATABASE_PATH", "tickets.db")