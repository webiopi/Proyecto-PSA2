"""Motor de plantillas Jinja2 y utilidades de respuesta."""
from typing import Optional
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import BASE_DIR, settings
from .services.inventory import alertas_medicamento

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals["alertas"] = alertas_medicamento
templates.env.globals["app_name"] = settings.APP_NAME
templates.env.globals["dias_alerta"] = settings.DIAS_ALERTA_CADUCIDAD


def render(request: Request, _plantilla: str, user=None, status_code: int = 200, **ctx):
    ctx["user"] = user
    ctx["msg"] = (request.query_params.get("msg") or "")[:200]
    ctx["msg_tipo"] = "error" if request.query_params.get("t") == "error" else "ok"
    return templates.TemplateResponse(request, _plantilla, ctx, status_code=status_code)


def redirigir(url: str, msg: Optional[str] = None, tipo: str = "ok") -> RedirectResponse:
    """Redirección 303 (POST → GET) con mensaje flash en la query string."""
    if msg:
        url += ("&" if "?" in url else "?") + urlencode({"msg": msg, "t": tipo})
    return RedirectResponse(url, status_code=303)
