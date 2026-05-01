import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    # Yandex OAuth
    YANDEX_CLIENT_ID = os.environ.get("YANDEX_CLIENT_ID", "placeholder")
    YANDEX_CLIENT_SECRET = os.environ.get("YANDEX_CLIENT_SECRET", "placeholder")
    YANDEX_REDIRECT_URI = os.environ.get("YANDEX_REDIRECT_URI", "http://localhost:5000/auth/callback")
    
    # AI Agent (OpenAI-compatible)
    AGENT_API_URL = os.environ.get("AGENT_API_URL", "http://localhost:8001/v1/chat/completions")
    AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "placeholder")
    AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-4")
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///razgon.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
