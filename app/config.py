import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    # Yandex OAuth
    YANDEX_CLIENT_ID = os.environ.get("YANDEX_CLIENT_ID", "0de36ceb221b49cf837c240e54c073a0")
    YANDEX_CLIENT_SECRET = os.environ.get("YANDEX_CLIENT_SECRET", "17838e34081d48d1b7d0b3f346b53332")
    YANDEX_REDIRECT_URI = os.environ.get("YANDEX_REDIRECT_URI", "https://razgon.roborumba.com/auth/callback")
    
    # AI Agent (OpenAI-compatible)
    AGENT_API_URL = os.environ.get("AGENT_API_URL", "http://localhost:8001/v1/chat/completions")
    AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "placeholder")
    AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-4")
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///razgon.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
