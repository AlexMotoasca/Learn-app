# python
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

class Config:
    # App / Flask secrets
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key")

    # Database: prefer DATABASE_URL from env (Postgres), otherwise use a local sqlite file for dev
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # create a sqlite file next to the project for local development
        base_dir = os.path.abspath(os.path.dirname(__file__))
        sqlite_path = os.path.join(base_dir, "uplearn.db")
        # Windows path fix for SQLAlchemy sqlite URI
        sqlite_uri = f"sqlite:///{sqlite_path.replace('\\', '/')}"
        SQLALCHEMY_DATABASE_URI = sqlite_uri
    else:
        SQLALCHEMY_DATABASE_URI = database_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OpenAI (optional)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Ollama / local LLM settings (defaults to Qwen 2.5 14B)
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))
