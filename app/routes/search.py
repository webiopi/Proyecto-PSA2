"""Consulta de inventario: buscador con filtros y paginación (todos los roles)."""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..services import inventory as inv
from ..templating import render

router = APIRouter()


@router.get("/consulta")
def consulta(
    request: Request,
    nombre: str = "", principio: str = "", lote: str = "", estado: str = "", page: int = 1,
    db: Session = Depends(get_db), user=Depends(get_current_user),
):
    nombre, principio, lote = nombre.strip()[:100], principio.strip()[:100], lote.strip()[:50]
    if estado not in inv.ESTADOS_FILTRO:
        estado = ""
    res = inv.buscar(db, nombre, principio, lote, estado, page, per_page=10)
    filtros = {"nombre": nombre, "principio": principio, "lote": lote, "estado": estado}
    base_qs = urlencode({k: v for k, v in filtros.items() if v})
    return render(request, "consulta.html", user, res=res, f=filtros, base_qs=base_qs,
                  estados=inv.ESTADOS_FILTRO)
