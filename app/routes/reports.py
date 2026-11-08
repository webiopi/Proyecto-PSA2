"""Dashboard de reportería y exportación a CSV."""
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import ROL_ADMIN, ROL_FARMACEUTICO, ROL_MEDICO, Medicamento
from ..services import inventory as inv
from ..services import orders
from ..templating import render

router = APIRouter()


@router.get("/")
def raiz():
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    resumen = inv.resumen(db)
    sanos = max(resumen["total"] - resumen["con_alertas"], 0)
    pct_sanos = round(100 * sanos / resumen["total"]) if resumen["total"] else 0
    return render(
        request, "dashboard.html", user,
        resumen=resumen, pct_sanos=pct_sanos,
        caducan=inv.listar_riesgo_caducidad(db, limite=8),
        criticos=inv.listar_stock_critico(db, limite=8),
        puede_exportar=user.rol in (ROL_ADMIN, ROL_FARMACEUTICO),
        ordenes=orders.listar(db, medico_id=user.id if user.rol == ROL_MEDICO else None, limite=15),
    )


@router.get("/reportes/exportar.csv")
def exportar_csv(
    tipo: str = "todo", db: Session = Depends(get_db),
    user=Depends(require_roles(ROL_ADMIN, ROL_FARMACEUTICO)),
):
    if tipo == "ordenes":
        contenido = "\ufeff" + orders.generar_csv(orders.listar(db))
        return Response(
            contenido, media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="ordenes_compra_%s.csv"' % date.today().isoformat()},
        )
    if tipo == "caducar":
        meds = inv.listar_riesgo_caducidad(db)
    elif tipo == "critico":
        meds = inv.listar_stock_critico(db)
    else:
        tipo = "todo"
        meds = list(db.scalars(select(Medicamento).order_by(Medicamento.nombre, Medicamento.fecha_caducidad)).all())
    contenido = "\ufeff" + inv.generar_csv(meds)  # BOM para que Excel respete UTF-8
    nombre = "inventario_%s_%s.csv" % (tipo, date.today().isoformat())
    return Response(
        contenido, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="%s"' % nombre},
    )
