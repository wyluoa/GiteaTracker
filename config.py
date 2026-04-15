"""
Application configuration.

Reads from environment variables, with sensible defaults for local development.
For production, set these via .env file or shell environment.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present (for local dev)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # Database
    DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "gitea_tracker.db"))

    # Attachments
    ATTACHMENT_DIR = os.environ.get(
        "ATTACHMENT_DIR", str(BASE_DIR / "data" / "attachments")
    )
    ATTACHMENT_MAX_MB = int(os.environ.get("ATTACHMENT_MAX_MB", "5"))
    ATTACHMENT_MAX_PER_ENTRY = 3
    ATTACHMENT_ALLOWED_EXT = {"png", "jpg", "jpeg", "pdf"}

    # Session
    SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "24"))
    PERMANENT_SESSION_LIFETIME = SESSION_HOURS * 3600

    # Server
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))

    # Reverse proxy path prefix (e.g. "/GiteaTracker")
    # Set in .env — NOT read from system environment variables.
    BASE_URL = os.environ.get("BASE_URL", "")


def get_config():
    return Config
