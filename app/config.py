import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    # Yandex OAuth
    YANDEX_CLIENT_ID = os.environ.get("YANDEX_CLIENT_ID", "0de36ceb221b49cf837c240e54c073a0")
    YANDEX_CLIENT_SECRET = os.environ.get("YANDEX_CLIENT_SECRET", "17838e34081d48d1b7d0b3f346b53332")
    YANDEX_REDIRECT_URI = os.environ.get("YANDEX_REDIRECT_URI", "https://razgon.roborumba.com/auth/callback")
    
    # AI Agent (async agent API)
    AGENT_API_URL = os.environ.get("AGENT_API_URL", "https://api-k6pryiwyuq-as.a.run.app/v1/messages")
    AGENT_RAZGON_TOKEN = os.environ.get("AGENT_RAZGON_TOKEN", "13447af28a494d674a17a0b65b0d86915bbf5809805d9b1615fac82208eb405e")
    AGENT_CALLBACK_BASE = os.environ.get("AGENT_CALLBACK_BASE", "https://razgon.roborumba.com")
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///razgon.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
