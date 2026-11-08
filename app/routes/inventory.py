"""CRUD de medicamentos (escritura: Admin y Farmacéutico) y listado de gestión."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import ESTADO_PENDIENTE, ROL_ADMIN, ROL_FARMACEUTICO, ROL_MEDICO, Medicamento, OrdenItem
from ..services import inventory as inv
from ..services import orders
from ..templating import redirigir, render

router = APIRouter(prefix="/inventario")
escritura = require_roles(ROL_ADMIN, ROL_FARMACEUTICO)

CAMPOS = ("nombre", "principio_activo", "lote", "fecha_caducidad", "stock_actual", "stock_minimo", "stock_maximo")


@router.get("")
def listado(request: Request, page: int = 1, db: Session = Depends(get_db), user=Depends(get_current_user)):
    res = inv.buscar(db, page=page, per_page=15)
    puede_editar = user.rol in (ROL_ADMIN, ROL_FARMACEUTICO)
    return render(
        request, "inventario.html", user, res=res, base_qs="", puede_editar=puede_editar,
        es_medico=user.rol == ROL_MEDICO,
        ordenes_pendientes=orders.listar(db, estado=ESTADO_PENDIENTE) if puede_editar else [],
        mis_ordenes=orders.listar(db, medico_id=user.id, limite=10) if user.rol == ROL_MEDICO else [],
    )


@router.get("/nuevo")
def nuevo_form(request: Request, user=Depends(escritura)):
    return render(request, "medicamento_form.html", user, valores={}, errores=[], editando=False)


@router.post("/nuevo")
def nuevo(
    request: Request,
    nombre: str = Form(""), principio_activo: str = Form(""), lote: str = Form(""),
    fecha_caducidad: str = Form(""), stock_actual: str = Form(""),
    stock_minimo: str = Form(""), stock_maximo: str = Form(""),
    db: Session = Depends(get_db), user=Depends(escritura),
):
    valores = dict(nombre=nombre, principio_activo=principio_activo, lote=lote, fecha_caducidad=fecha_caducidad,
                   stock_actual=stock_actual, stock_minimo=stock_minimo, stock_maximo=stock_maximo)
    datos, errores = inv.validar_medicamento(valores)
    if not errores and inv.existe_duplicado(db, datos["nombre"], datos["lote"]):
        errores.append("Ya existe un medicamento con ese nombre y lote.")
    if errores:
        return render(request, "medicamento_form.html", user, status_code=400, valores=valores,
                      errores=errores, editando=False)
    try:
        db.add(Medicamento(**datos))
        db.commit()
    except IntegrityError:
        db.rollback()
        return render(request, "medicamento_form.html", user, status_code=400, valores=valores,
                      errores=["No se pudo guardar: datos duplicados o inválidos."], editando=False)
    return redirigir("/inventario", "Medicamento agregado.")


def _get_or_404(db: Session, med_id: int) -> Medicamento:
    med = db.get(Medicamento, med_id)
    if med is None:
        raise HTTPException(404, "Medicamento no encontrado.")
    return med


@router.get("/{med_id}/editar")
def editar_form(med_id: int, request: Request, db: Session = Depends(get_db), user=Depends(escritura)):
    med = _get_or_404(db, med_id)
    valores = {c: getattr(med, c) for c in CAMPOS}
    valores["fecha_caducidad"] = med.fecha_caducidad.isoformat()
    return render(request, "medicamento_form.html", user, valores=valores, errores=[], editando=True, med=med)


@router.post("/{med_id}/editar")
def editar(
    med_id: int, request: Request,
    nombre: str = Form(""), principio_activo: str = Form(""), lote: str = Form(""),
    fecha_caducidad: str = Form(""), stock_actual: str = Form(""),
    stock_minimo: str = Form(""), stock_maximo: str = Form(""),
    db: Session = Depends(get_db), user=Depends(escritura),
):
    med = _get_or_404(db, med_id)
    valores = dict(nombre=nombre, principio_activo=principio_activo, lote=lote, fecha_caducidad=fecha_caducidad,
                   stock_actual=stock_actual, stock_minimo=stock_minimo, stock_maximo=stock_maximo)
    datos, errores = inv.validar_medicamento(valores)
    if not errores and inv.existe_duplicado(db, datos["nombre"], datos["lote"], excluir_id=med.id):
        errores.append("Ya existe otro medicamento con ese nombre y lote.")
    if errores:
        return render(request, "medicamento_form.html", user, status_code=400, valores=valores,
                      errores=errores, editando=True, med=med)
    for k, v in datos.items():
        setattr(med, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return render(request, "medicamento_form.html", user, status_code=400, valores=valores,
                      errores=["No se pudo guardar: datos duplicados o inválidos."], editando=True, med=med)
    return redirigir("/inventario", "Medicamento actualizado.")


@router.post("/{med_id}/eliminar")
def eliminar(med_id: int, db: Session = Depends(get_db), user=Depends(escritura)):
    med = _get_or_404(db, med_id)
    if db.scalar(select(OrdenItem.id).where(OrdenItem.medicamento_id == med.id).limit(1)):
        return redirigir("/inventario", "No se puede eliminar: el medicamento figura en órdenes de compra.", "error")
    db.delete(med)
    db.commit()
    return redirigir("/inventario", "Medicamento eliminado.")
