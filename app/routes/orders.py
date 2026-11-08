"""Pedidos del médico (con sugerencias IA) y gestión de órdenes de compra por el farmacéutico."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..deps import require_roles
from ..models import ROL_ADMIN, ROL_FARMACEUTICO, ROL_MEDICO
from ..services import inventory as inv
from ..services import ollama
from ..services import orders
from ..templating import redirigir

router = APIRouter()
solo_medico = require_roles(ROL_MEDICO)
gestion = require_roles(ROL_ADMIN, ROL_FARMACEUTICO)


class ItemIn(BaseModel):
    medicamento_id: int
    cantidad: int


class PedidoIn(BaseModel):
    items: List[ItemIn] = Field(default_factory=list)
    notas: str = ""


class DolenciaIn(BaseModel):
    dolencia: str


@router.get("/api/ordenes/buscar")
def buscar(q: str = "", db: Session = Depends(get_db), user=Depends(solo_medico)):
    q = q.strip()[:100]
    if q:
        meds, _ = inv.buscar_texto(db, q, limite=15)
    else:
        meds = inv.buscar(db, per_page=15)["items"]
    return {"items": [ollama.medicamento_json(m) for m in meds if m.stock_actual > 0]}


@router.post("/api/ordenes/sugerir")
async def sugerir(datos: DolenciaIn, db: Session = Depends(get_db), user=Depends(solo_medico)):
    dolencia = " ".join(datos.dolencia.split())[:300]
    if len(dolencia) < 3:
        return JSONResponse({"detail": "Describe la dolencia (mínimo 3 caracteres)."}, status_code=400)
    try:
        return await ollama.sugerir_medicamentos(db, dolencia)
    except ollama.OllamaError as exc:
        return JSONResponse({"detail": exc.mensaje}, status_code=exc.status)


@router.post("/api/ordenes")
def crear(datos: PedidoIn, db: Session = Depends(get_db), user=Depends(solo_medico)):
    orden, errores = orders.crear_orden(db, user, [i.model_dump() if hasattr(i, "model_dump") else i.dict() for i in datos.items], datos.notas)
    if errores:
        return JSONResponse({"detail": " ".join(errores), "errores": errores}, status_code=400)
    return {"ok": True, "id": orden.id}


@router.post("/ordenes/{orden_id}/confirmar")
def confirmar(orden_id: int, request: Request, db: Session = Depends(get_db), user=Depends(gestion)):
    errores = orders.confirmar_orden(db, orden_id, user)
    if errores:
        return redirigir("/inventario", " ".join(errores), "error")
    return redirigir("/inventario", "Orden #%d confirmada: stock actualizado." % orden_id)


@router.post("/ordenes/{orden_id}/rechazar")
def rechazar(orden_id: int, db: Session = Depends(get_db), user=Depends(gestion)):
    errores = orders.rechazar_orden(db, orden_id, user)
    if errores:
        return redirigir("/inventario", " ".join(errores), "error")
    return redirigir("/inventario", "Orden #%d rechazada." % orden_id)
