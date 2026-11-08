"""Hash de contraseñas (PBKDF2, stdlib), JWT y limitador de intentos de login."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import jwt

from .config import settings

_ITERACIONES = 390_000


def hash_password(password: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sal), _ITERACIONES)
    return f"pbkdf2_sha256${_ITERACIONES}${sal}${h.hex()}"


def verify_password(password: str, almacenado: str) -> bool:
    try:
        _, iters, sal, esperado = almacenado.split("$")
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sal), int(iters))
        return hmac.compare_digest(h.hex(), esperado)
    except (ValueError, AttributeError):
        return False


# Hash ficticio para igualar tiempos cuando el usuario no existe.
_HASH_DUMMY = hash_password("dummy-password")


def verify_dummy(password: str) -> None:
    verify_password(password, _HASH_DUMMY)


def crear_token(user_id: int) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decodificar_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


class LimitadorLogin:
    """Bloquea temporalmente tras N fallos consecutivos (en memoria, por IP+usuario)."""

    def __init__(self, max_fallos: int = 5, bloqueo_seg: int = 300):
        self.max_fallos = max_fallos
        self.bloqueo_seg = bloqueo_seg
        self._fallos: Dict[Tuple[str, str], Tuple[int, float]] = {}

    def bloqueado(self, clave: Tuple[str, str]) -> bool:
        n, ts = self._fallos.get(clave, (0, 0.0))
        if n >= self.max_fallos:
            if time.time() - ts < self.bloqueo_seg:
                return True
            self._fallos.pop(clave, None)
        return False

    def fallo(self, clave: Tuple[str, str]) -> None:
        n, _ = self._fallos.get(clave, (0, 0.0))
        self._fallos[clave] = (n + 1, time.time())

    def exito(self, clave: Tuple[str, str]) -> None:
        self._fallos.pop(clave, None)


limitador_login = LimitadorLogin()
