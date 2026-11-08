"""Configuración centralizada (variables de entorno / .env)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _cargar_secret_key() -> str:
    """Usa SECRET_KEY del entorno o genera una persistente en data/.secret_key."""
    desde_env = os.getenv("SECRET_KEY", "").strip()
    if desde_env:
        return desde_env
    ruta = DATA_DIR / ".secret_key"
    if ruta.exists():
        return ruta.read_text().strip()
    clave = secrets.token_urlsafe(48)
    ruta.write_text(clave)
    try:
        ruta.chmod(0o600)
    except OSError:
        pass
    return clave


def _lista_enteros(valor: str):
    return {int(x) for x in valor.split(",") if x.strip().lstrip("-").isdigit()}


class Settings:
    APP_NAME = "SIFARH"
    SECRET_KEY = _cargar_secret_key()
    JWT_ALGORITHM = "HS256"
    TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "480"))
    COOKIE_NAME = "access_token"
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'farmacia.db'}")
    DIAS_ALERTA_CADUCIDAD = int(os.getenv("DIAS_ALERTA_CADUCIDAD", "90"))

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_MODE = os.getenv("TELEGRAM_MODE", "polling").strip().lower()
    TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    TELEGRAM_ALLOWED_CHAT_IDS = _lista_enteros(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", ""))

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))


settings = Settings()
