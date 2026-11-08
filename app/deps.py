"""Dependencias de autenticación y autorización."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Usuario
from .security import decodificar_token


class NotAuthenticated(Exception):
    """Sin sesión válida (se traduce en redirección a /login o 401 JSON)."""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise NotAuthenticated()
    payload = decodificar_token(token)
    if not payload or not str(payload.get("sub", "")).isdigit():
        raise NotAuthenticated()
    # Se consulta la BD en cada petición: borrar/suspender a un usuario surte efecto de inmediato.
    user = db.get(Usuario, int(payload["sub"]))
    if user is None or not user.aprobado:
        raise NotAuthenticated()
    return user


def require_roles(*roles: str):
    def checker(user: Usuario = Depends(get_current_user)) -> Usuario:
        if user.rol not in roles:
            raise HTTPException(status_code=403, detail="No tienes permisos para esta acción.")
        return user

    return checker
