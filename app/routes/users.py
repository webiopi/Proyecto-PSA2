"""Administración de usuarios (solo Admin)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..models import ROL_ADMIN, ROLES, Usuario
from ..security import hash_password
from ..templating import redirigir, render
from .auth import validar_alta

router = APIRouter(prefix="/usuarios")
solo_admin = require_roles(ROL_ADMIN)


def _listar(db: Session):
    return db.scalars(select(Usuario).order_by(Usuario.aprobado, Usuario.creado_en.desc())).all()


def _otro_admin_activo(db: Session, excluir_id: int) -> bool:
    return db.scalar(
        select(func.count()).select_from(Usuario)
        .where(Usuario.rol == ROL_ADMIN, Usuario.aprobado.is_(True), Usuario.id != excluir_id)
    ) > 0


def _get_or_404(db: Session, uid: int) -> Usuario:
    u = db.get(Usuario, uid)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado.")
    return u


@router.get("")
def listado(request: Request, db: Session = Depends(get_db), user=Depends(solo_admin)):
    return render(request, "usuarios.html", user, usuarios=_listar(db), roles=ROLES, errores=[], valores={})


@router.post("/crear")
def crear(
    request: Request,
    nombre: str = Form(""), usuario: str = Form(""), password: str = Form(""), rol: str = Form(""),
    db: Session = Depends(get_db), user=Depends(solo_admin),
):
    nombre, usuario = nombre.strip(), usuario.strip()
    errores = validar_alta(nombre, usuario, password)
    if rol not in ROLES:
        errores.append("Rol no válido.")
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.usuario) == usuario.lower())):
        errores.append("Ese nombre de usuario ya existe.")
    if errores:
        return render(request, "usuarios.html", user, status_code=400, usuarios=_listar(db), roles=ROLES,
                      errores=errores, valores={"nombre": nombre, "usuario": usuario, "rol": rol})
    db.add(Usuario(nombre=nombre, usuario=usuario, rol=rol, password_hash=hash_password(password), aprobado=True))
    db.commit()
    return redirigir("/usuarios", "Usuario creado.")


@router.post("/{uid}/aprobar")
def aprobar(uid: int, db: Session = Depends(get_db), user=Depends(solo_admin)):
    u = _get_or_404(db, uid)
    u.aprobado = True
    db.commit()
    return redirigir("/usuarios", "Cuenta de %s aprobada." % u.usuario)


@router.post("/{uid}/suspender")
def suspender(uid: int, db: Session = Depends(get_db), user=Depends(solo_admin)):
    u = _get_or_404(db, uid)
    if u.id == user.id:
        return redirigir("/usuarios", "No puedes suspender tu propia cuenta.", "error")
    if u.rol == ROL_ADMIN and not _otro_admin_activo(db, u.id):
        return redirigir("/usuarios", "Debe quedar al menos un administrador activo.", "error")
    u.aprobado = False
    db.commit()
    return redirigir("/usuarios", "Cuenta de %s suspendida." % u.usuario)


@router.post("/{uid}/eliminar")
def eliminar(uid: int, db: Session = Depends(get_db), user=Depends(solo_admin)):
    u = _get_or_404(db, uid)
    if u.id == user.id:
        return redirigir("/usuarios", "No puedes eliminar tu propia cuenta.", "error")
    if u.rol == ROL_ADMIN and not _otro_admin_activo(db, u.id):
        return redirigir("/usuarios", "Debe quedar al menos un administrador activo.", "error")
    db.delete(u)
    db.commit()
    return redirigir("/usuarios", "Usuario eliminado.")
