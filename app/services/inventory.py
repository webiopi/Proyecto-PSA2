"""Lógica de negocio del inventario: alertas, búsqueda, resumen, validación y CSV."""
import csv
import io
from collections import namedtuple
from datetime import date, timedelta
from math import ceil
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Medicamento

Alerta = namedtuple("Alerta", "code label css")

ESTADOS_FILTRO = {
    "": "Todos",
    "alerta": "Con alguna alerta",
    "bajo_minimo": "Bajo el mínimo",
    "sobre_maximo": "Sobre el máximo",
    "por_caducar": "Caduca en ≤ %d días" % settings.DIAS_ALERTA_CADUCIDAD,
    "caducado": "Caducados",
}


def alertas_medicamento(m: Medicamento, ref: Optional[date] = None) -> List[Alerta]:
    """Alertas visuales aplicables a un medicamento."""
    ref = ref or date.today()
    out = []
    if m.fecha_caducidad < ref:
        out.append(Alerta("caducado", "Caducado", "danger"))
    elif (m.fecha_caducidad - ref).days <= settings.DIAS_ALERTA_CADUCIDAD:
        out.append(Alerta("por_caducar", "Caduca en %d d" % (m.fecha_caducidad - ref).days, "danger"))
    if m.stock_actual < m.stock_minimo:
        out.append(Alerta("bajo_minimo", "Bajo mínimo", "danger"))
    if m.stock_actual > m.stock_maximo:
        out.append(Alerta("sobre_maximo", "Sobre máximo", "over"))
    return out


def condiciones(ref: Optional[date] = None) -> Dict[str, object]:
    """Condiciones SQL equivalentes a las alertas."""
    ref = ref or date.today()
    limite = ref + timedelta(days=settings.DIAS_ALERTA_CADUCIDAD)
    c = {
        "bajo_minimo": Medicamento.stock_actual < Medicamento.stock_minimo,
        "sobre_maximo": Medicamento.stock_actual > Medicamento.stock_maximo,
        "caducado": Medicamento.fecha_caducidad < ref,
        "por_caducar": and_(Medicamento.fecha_caducidad >= ref, Medicamento.fecha_caducidad <= limite),
    }
    c["alerta"] = or_(*c.values())
    # Caducados o a punto de caducar
    c["riesgo_caducidad"] = Medicamento.fecha_caducidad <= limite
    return c


def _like(termino: str) -> str:
    esc = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + esc + "%"


def buscar(
    db: Session,
    nombre: str = "",
    principio: str = "",
    lote: str = "",
    estado: str = "",
    page: int = 1,
    per_page: int = 10,
) -> dict:
    stmt = select(Medicamento)
    if nombre:
        stmt = stmt.where(Medicamento.nombre.ilike(_like(nombre), escape="\\"))
    if principio:
        stmt = stmt.where(Medicamento.principio_activo.ilike(_like(principio), escape="\\"))
    if lote:
        stmt = stmt.where(Medicamento.lote.ilike(_like(lote), escape="\\"))
    if estado in ESTADOS_FILTRO and estado:
        stmt = stmt.where(condiciones()[estado])

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pages = max(1, ceil(total / per_page))
    page = min(max(page, 1), pages)
    items = db.scalars(
        stmt.order_by(Medicamento.nombre, Medicamento.fecha_caducidad)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return {"items": items, "total": total, "page": page, "pages": pages, "per_page": per_page}


def resumen(db: Session) -> dict:
    c = condiciones()

    def contar(cond=None) -> int:
        stmt = select(func.count()).select_from(Medicamento)
        if cond is not None:
            stmt = stmt.where(cond)
        return db.scalar(stmt) or 0

    return {
        "total": contar(),
        "por_caducar": contar(c["por_caducar"]),
        "caducados": contar(c["caducado"]),
        "stock_critico": contar(c["bajo_minimo"]),
        "sobre_maximo": contar(c["sobre_maximo"]),
        "con_alertas": contar(c["alerta"]),
    }


def listar_riesgo_caducidad(db: Session, limite: Optional[int] = None) -> List[Medicamento]:
    stmt = select(Medicamento).where(condiciones()["riesgo_caducidad"]).order_by(Medicamento.fecha_caducidad)
    if limite:
        stmt = stmt.limit(limite)
    return list(db.scalars(stmt).all())


def listar_stock_critico(db: Session, limite: Optional[int] = None) -> List[Medicamento]:
    stmt = (
        select(Medicamento)
        .where(condiciones()["bajo_minimo"])
        .order_by(Medicamento.stock_actual - Medicamento.stock_minimo, Medicamento.nombre)
    )
    if limite:
        stmt = stmt.limit(limite)
    return list(db.scalars(stmt).all())


def buscar_texto(db: Session, termino: str, limite: int = 10) -> Tuple[List[Medicamento], int]:
    """Búsqueda libre en nombre, principio activo o lote (usada por Telegram)."""
    patron = _like(termino)
    cond = or_(
        Medicamento.nombre.ilike(patron, escape="\\"),
        Medicamento.principio_activo.ilike(patron, escape="\\"),
        Medicamento.lote.ilike(patron, escape="\\"),
    )
    total = db.scalar(select(func.count()).select_from(Medicamento).where(cond)) or 0
    items = db.scalars(
        select(Medicamento).where(cond).order_by(Medicamento.nombre, Medicamento.fecha_caducidad).limit(limite)
    ).all()
    return list(items), total


# ----------------------------------------------------------------------------- validación

_CAMPOS_TEXTO = (("nombre", "Nombre", 150), ("principio_activo", "Principio activo", 150), ("lote", "Lote", 50))
_CAMPOS_NUM = (("stock_actual", "Stock actual"), ("stock_minimo", "Stock mínimo"), ("stock_maximo", "Stock máximo"))
_MAX_STOCK = 10_000_000


def validar_medicamento(form: dict) -> Tuple[dict, List[str]]:
    datos: dict = {}
    errores: List[str] = []
    for campo, etiqueta, maxlen in _CAMPOS_TEXTO:
        v = (form.get(campo) or "").strip()
        if not v:
            errores.append("%s es obligatorio." % etiqueta)
        elif len(v) > maxlen:
            errores.append("%s no puede superar %d caracteres." % (etiqueta, maxlen))
        datos[campo] = v
    try:
        datos["fecha_caducidad"] = date.fromisoformat((form.get("fecha_caducidad") or "").strip())
    except ValueError:
        errores.append("La fecha de caducidad no es válida.")
    for campo, etiqueta in _CAMPOS_NUM:
        try:
            n = int((form.get(campo) or "").strip())
            if n < 0 or n > _MAX_STOCK:
                raise ValueError
            datos[campo] = n
        except ValueError:
            errores.append("%s debe ser un entero entre 0 y %d." % (etiqueta, _MAX_STOCK))
    if "stock_minimo" in datos and "stock_maximo" in datos and datos["stock_minimo"] > datos["stock_maximo"]:
        errores.append("El stock mínimo no puede ser mayor que el máximo.")
    return datos, errores


def existe_duplicado(db: Session, nombre: str, lote: str, excluir_id: Optional[int] = None) -> bool:
    stmt = select(Medicamento.id).where(
        func.lower(Medicamento.nombre) == nombre.lower(), func.lower(Medicamento.lote) == lote.lower()
    )
    if excluir_id is not None:
        stmt = stmt.where(Medicamento.id != excluir_id)
    return db.scalar(stmt) is not None


# ----------------------------------------------------------------------------- CSV

def _seguro(valor: str) -> str:
    """Neutraliza inyección de fórmulas al abrir el CSV en Excel/LibreOffice."""
    return "'" + valor if valor and valor[0] in "=+-@\t\r" else valor


def generar_csv(meds: List[Medicamento]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Nombre", "Principio activo", "Lote", "Fecha caducidad",
                "Stock actual", "Stock mínimo", "Stock máximo", "Alertas"])
    for m in meds:
        w.writerow([
            m.id, _seguro(m.nombre), _seguro(m.principio_activo), _seguro(m.lote),
            m.fecha_caducidad.isoformat(), m.stock_actual, m.stock_minimo, m.stock_maximo,
            "; ".join(a.label for a in alertas_medicamento(m)) or "OK",
        ])
    return buf.getvalue()
