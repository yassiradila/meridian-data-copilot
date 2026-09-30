import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdf"
CHROMA_DIR = DATA_DIR / "chroma_db"

# LLM & API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Observability (LangSmith)
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "meridian-copilot")

# Database URL
DEFAULT_DB_URL = "postgresql://postgres:linuxubuntu2004@localhost:5432/stellantis_db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DB_URL

# ReAct Agent loop settings
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "4"))
