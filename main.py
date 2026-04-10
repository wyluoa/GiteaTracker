"""
Entry point for the Gitea Tracker server.

Usage:
    python main.py
"""
from app import create_app
from config import Config

app = create_app()


if __name__ == "__main__":
    print(f"Starting Gitea Tracker on http://{Config.HOST}:{Config.PORT}")
    print(f"DB:          {Config.DB_PATH}")
    print(f"Attachments: {Config.ATTACHMENT_DIR}")
    print(f"Debug mode:  {Config.DEBUG}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
