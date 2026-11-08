"""Login, registro y cierre de sesión."""
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import ROL_ADMIN, ROL_FARMACEUTICO, ROL_MEDICO, Usuario
from ..security import (crear_token, hash_password, verify_dummy,
                        verify_password)
# Bloqueo por intentos fallidos desactivado temporalmente.
# Para reactivarlo: importar `limitador_login` y descomentar las líneas marcadas con [LIMITADOR].
from ..templating import redirigir, render

router = APIRouter()

RE_USUARIO = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
ROLES_AUTOREGISTRO = (ROL_FARMACEUTICO, ROL_MEDICO)


def validar_alta(nombre: str, usuario: str, password: str) -> list:
    errores = []
    if not 2 <= len(nombre) <= 100:
        errores.append("El nombre debe tener entre 2 y 100 caracteres.")
    if not RE_USUARIO.match(usuario):
        errores.append("El usuario debe tener 3-32 caracteres (letras, números, . _ -).")
    if not 8 <= len(password) <= 128:
        errores.append("La contraseña debe tener entre 8 y 128 caracteres.")
    return errores


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Usuario)) == 0:
        return redirigir("/registro")
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, usuario: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    usuario = usuario.strip()
    # [LIMITADOR] clave = (request.client.host if request.client else "?", usuario.lower())
    # [LIMITADOR] if limitador_login.bloqueado(clave):
    # [LIMITADOR]     return render(request, "login.html", status_code=429,
    # [LIMITADOR]                   error="Demasiados intentos fallidos. Espera 5 minutos.", usuario=usuario)

    user = db.scalar(select(Usuario).where(func.lower(Usuario.usuario) == usuario.lower()))
    if user is None:
        verify_dummy(password)
    if user is None or not verify_password(password, user.password_hash):
        # [LIMITADOR] limitador_login.fallo(clave)
        return render(request, "login.html", status_code=401, error="Usuario o contraseña incorrectos.",
                      usuario=usuario)
    if not user.aprobado:
        return render(request, "login.html", status_code=403, usuario=usuario,
                      error="Tu cuenta está pendiente de aprobación por un administrador.")

    # [LIMITADOR] limitador_login.exito(clave)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(
        settings.COOKIE_NAME, crear_token(user.id),
        max_age=settings.TOKEN_EXPIRE_MINUTES * 60,
        httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
    )
    return resp


@router.get("/registro")
def registro_form(request: Request, db: Session = Depends(get_db)):
    primero = db.scalar(select(func.count()).select_from(Usuario)) == 0
    return render(request, "registro.html", primero=primero, roles=ROLES_AUTOREGISTRO)


@router.post("/registro")
def registro(
    request: Request,
    nombre: str = Form(""),
    usuario: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
    rol: str = Form(ROL_MEDICO),
    db: Session = Depends(get_db),
):
    primero = db.scalar(select(func.count()).select_from(Usuario)) == 0
    nombre, usuario = nombre.strip(), usuario.strip()
    errores = validar_alta(nombre, usuario, password)
    if password != password2:
        errores.append("Las contraseñas no coinciden.")
    if not primero and rol not in ROLES_AUTOREGISTRO:
        errores.append("Rol no válido.")
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.usuario) == usuario.lower())):
        errores.append("Ese nombre de usuario ya existe.")
    if errores:
        return render(request, "registro.html", status_code=400, primero=primero, roles=ROLES_AUTOREGISTRO,
                      errores=errores, nombre=nombre, usuario=usuario, rol=rol)

    # El primer usuario es Admin y queda aprobado; el resto queda pendiente y nunca puede ser Admin.
    db.add(Usuario(
        nombre=nombre, usuario=usuario, password_hash=hash_password(password),
        rol=ROL_ADMIN if primero else rol, aprobado=primero,
    ))
    db.commit()
    if primero:
        return redirigir("/login", "Administrador creado. Inicia sesión.")
    return redirigir("/login", "Registro enviado. Un administrador debe aprobar tu cuenta.")


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.COOKIE_NAME)
    return resp
