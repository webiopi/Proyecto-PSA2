"""Punto de entrada FastAPI."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import BASE_DIR, settings
from .database import Base, engine
from .deps import NotAuthenticated
from .routes import api, auth, inventory, orders, reports, search, users
from .services import telegram_bot
from .templating import render

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sifarh")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    tarea = None
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_MODE == "polling":
        tarea = asyncio.create_task(telegram_bot.polling_worker())
    elif settings.TELEGRAM_BOT_TOKEN:
        log.info("Telegram en modo webhook: configura setWebhook hacia /api/telegram/webhook")
    yield
    if tarea:
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

for modulo in (auth, reports, inventory, orders, search, users, api):
    app.include_router(modulo.router)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if not request.url.path.startswith("/static"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(NotAuthenticated)
async def no_autenticado(request: Request, exc: NotAuthenticated):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "No autenticado"}, status_code=401)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.COOKIE_NAME)
    return resp


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exc)
    titulos = {403: "Acceso denegado", 404: "Página no encontrada"}
    return render(
        request, "error.html", status_code=exc.status_code,
        codigo=exc.status_code, titulo=titulos.get(exc.status_code, "Error"), detalle=exc.detail,
    )
