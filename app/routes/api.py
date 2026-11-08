"""Endpoints de integración: webhook de Telegram y análisis con Ollama."""
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_roles
from ..models import ROL_ADMIN, ROL_FARMACEUTICO
from ..services import ollama, telegram_bot

router = APIRouter(prefix="/api")


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """Recibe updates de Telegram y responde con el stock consultado en la BD."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, "Telegram no está configurado (TELEGRAM_BOT_TOKEN).")
    esperado = settings.TELEGRAM_WEBHOOK_SECRET
    if not esperado or not hmac.compare_digest(x_telegram_bot_api_secret_token, esperado):
        raise HTTPException(403, "Secret token inválido.")
    update = await request.json()
    try:
        await telegram_bot.responder_update(update)
    except Exception:  # noqa: BLE001 - evitar reintentos infinitos de Telegram
        telegram_bot.log.exception("Error respondiendo al webhook")
    return {"ok": True}


@router.post("/ai/analisis")
async def analisis_ia(
    db: Session = Depends(get_db),
    user=Depends(require_roles(ROL_ADMIN, ROL_FARMACEUTICO)),
):
    """Envía caducidades próximas y stock crítico a Ollama y devuelve sugerencias de compra."""
    try:
        return await ollama.analizar_inventario(db)
    except ollama.OllamaError as exc:
        return JSONResponse({"detail": exc.mensaje}, status_code=exc.status)
