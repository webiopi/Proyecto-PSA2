"""Órdenes de compra: creación por el médico, confirmación/rechazo por el farmacéutico."""
import csv
import io
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    ESTADO_CONFIRMADA, ESTADO_PENDIENTE, ESTADO_RECHAZADA, Medicamento, OrdenCompra, OrdenItem, Usuario,
)

MAX_CANTIDAD = 100_000
MAX_ITEMS = 50


def crear_orden(db: Session, medico: Usuario, items: list, notas: str = "") -> Tuple[Optional[OrdenCompra], List[str]]:
    """Valida y crea una orden pendiente. `items`: [{medicamento_id, cantidad}]."""
    errores: List[str] = []
    if not isinstance(items, list) or not items:
        return None, ["Agrega al menos un medicamento al pedido."]
    if len(items) > MAX_ITEMS:
        return None, ["Un pedido no puede superar %d medicamentos." % MAX_ITEMS]

    acumulado = {}
    for it in items:
        try:
            mid, cant = int(it.get("medicamento_id")), int(it.get("cantidad"))
        except (TypeError, ValueError, AttributeError):
            return None, ["Datos de pedido inválidos."]
        if cant < 1 or cant > MAX_CANTIDAD:
            return None, ["La cantidad debe estar entre 1 y %d." % MAX_CANTIDAD]
        acumulado[mid] = acumulado.get(mid, 0) + cant

    meds = {m.id: m for m in db.scalars(select(Medicamento).where(Medicamento.id.in_(list(acumulado)))).all()}
    for mid, cant in acumulado.items():
        m = meds.get(mid)
        if m is None:
            errores.append("El medicamento #%d ya no existe." % mid)
        elif cant > m.stock_actual:
            errores.append("«%s» (lote %s): solicitas %d y hay %d en stock." % (m.nombre, m.lote, cant, m.stock_actual))
    if errores:
        return None, errores

    orden = OrdenCompra(medico_id=medico.id, notas=(notas or "").strip()[:300])
    orden.items = [OrdenItem(medicamento_id=mid, cantidad=cant) for mid, cant in acumulado.items()]
    db.add(orden)
    db.commit()
    return orden, []


def _cargar(db: Session, orden_id: int) -> Optional[OrdenCompra]:
    return db.scalars(
        select(OrdenCompra).where(OrdenCompra.id == orden_id)
        .options(selectinload(OrdenCompra.items).selectinload(OrdenItem.medicamento))
    ).first()


def confirmar_orden(db: Session, orden_id: int, farmaceutico: Usuario) -> List[str]:
    """Confirma la orden y rebaja el stock de forma atómica. Devuelve errores (vacío si OK)."""
    orden = _cargar(db, orden_id)
    if orden is None:
        return ["La orden no existe."]
    if orden.estado != ESTADO_PENDIENTE:
        return ["La orden #%d ya fue %s." % (orden.id, orden.estado.lower())]
    errores = []
    for it in orden.items:
        m = it.medicamento
        if it.cantidad > m.stock_actual:
            errores.append("Stock insuficiente de «%s» (lote %s): pide %d, hay %d."
                           % (m.nombre, m.lote, it.cantidad, m.stock_actual))
    if errores:
        return errores
    for it in orden.items:
        it.medicamento.stock_actual -= it.cantidad
    orden.estado = ESTADO_CONFIRMADA
    orden.resuelto_por_id = farmaceutico.id
    orden.resuelto_en = datetime.utcnow()
    db.commit()
    return []


def rechazar_orden(db: Session, orden_id: int, farmaceutico: Usuario) -> List[str]:
    orden = db.get(OrdenCompra, orden_id)
    if orden is None:
        return ["La orden no existe."]
    if orden.estado != ESTADO_PENDIENTE:
        return ["La orden #%d ya fue %s." % (orden.id, orden.estado.lower())]
    orden.estado = ESTADO_RECHAZADA
    orden.resuelto_por_id = farmaceutico.id
    orden.resuelto_en = datetime.utcnow()
    db.commit()
    return []


def listar(db: Session, medico_id: Optional[int] = None, estado: Optional[str] = None,
           limite: Optional[int] = None) -> List[OrdenCompra]:
    stmt = (
        select(OrdenCompra)
        .options(selectinload(OrdenCompra.items).selectinload(OrdenItem.medicamento),
                 selectinload(OrdenCompra.medico), selectinload(OrdenCompra.resuelto_por))
        .order_by(OrdenCompra.creado_en.desc(), OrdenCompra.id.desc())
    )
    if medico_id is not None:
        stmt = stmt.where(OrdenCompra.medico_id == medico_id)
    if estado:
        stmt = stmt.where(OrdenCompra.estado == estado)
    if limite:
        stmt = stmt.limit(limite)
    return list(db.scalars(stmt).all())


def contar_pendientes(db: Session) -> int:
    return len(db.scalars(select(OrdenCompra.id).where(OrdenCompra.estado == ESTADO_PENDIENTE)).all())


def _neutralizar(v: str) -> str:
    """Evita inyección de fórmulas al abrir el CSV en Excel."""
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def generar_csv(ordenes: List[OrdenCompra]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Orden", "Fecha", "Médico", "Estado", "Medicamento", "Lote", "Cantidad", "Resuelta por", "Fecha resolución"])
    for o in ordenes:
        for it in o.items:
            w.writerow([
                o.id, o.creado_en.strftime("%Y-%m-%d %H:%M"), _neutralizar(o.medico.nombre), o.estado,
                _neutralizar(it.medicamento.nombre), _neutralizar(it.medicamento.lote), it.cantidad,
                _neutralizar(o.resuelto_por.nombre) if o.resuelto_por else "",
                o.resuelto_en.strftime("%Y-%m-%d %H:%M") if o.resuelto_en else "",
            ])
    return buf.getvalue()
