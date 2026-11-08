"""Integración con Telegram: responde con el stock actual consultando la BD.

Dos modos (TELEGRAM_MODE):
  * polling: un worker asyncio consulta getUpdates (no requiere URL pública).
  * webhook: Telegram llama a POST /api/telegram/webhook.
"""
import asyncio
import logging
from typing import Optional

import httpx

from ..config import settings
from ..database import SessionLocal
from . import inventory as inv

log = logging.getLogger("telegram")

AYUDA = (
    "Bot de inventario farmacéutico.\n\n"
    "Escribe el nombre, principio activo o lote de un medicamento para ver su stock.\n\n"
    "Comandos:\n"
    "/stock <texto> – buscar medicamento\n"
    "/criticos – medicamentos bajo el stock mínimo\n"
    "/caducan – medicamentos caducados o próximos a caducar\n"
    "/ayuda – esta ayuda"
)


def _linea(m) -> str:
    alertas = inv.alertas_medicamento(m)
    marca = ("\n   ⚠ " + ", ".join(a.label for a in alertas)) if alertas else ""
    return (
        "• %s (%s)\n   Lote %s | Stock: %d (mín %d, máx %d) | Caduca: %s%s"
        % (m.nombre, m.principio_activo, m.lote, m.stock_actual, m.stock_minimo, m.stock_maximo,
           m.fecha_caducidad.strftime("%d/%m/%Y"), marca)
    )


def _formatear(titulo: str, meds, total: int) -> str:
    if not meds:
        return "%s\nSin resultados." % titulo
    texto = "%s (%d)\n\n%s" % (titulo, total, "\n".join(_linea(m) for m in meds))
    if total > len(meds):
        texto += "\n\n…y %d más. Afina tu búsqueda." % (total - len(meds))
    return texto


def procesar_mensaje(texto: str, chat_id: Optional[int] = None) -> str:
    """Convierte un mensaje entrante en la respuesta de texto (síncrono, usa la BD)."""
    texto = (texto or "").strip()
    if not texto:
        return AYUDA
    cmd, arg = "", texto
    if texto.startswith("/"):
        cmd, _, arg = texto.partition(" ")
        cmd = cmd.split("@")[0].lower()
        arg = arg.strip()

    if cmd in ("/start", "/ayuda", "/help"):
        extra = "\n\nTu chat_id: %s" % chat_id if chat_id is not None else ""
        return AYUDA + extra

    with SessionLocal() as db:
        if cmd == "/criticos":
            meds = inv.listar_stock_critico(db, limite=15)
            return _formatear("Stock crítico", meds, inv.resumen(db)["stock_critico"])
        if cmd == "/caducan":
            meds = inv.listar_riesgo_caducidad(db, limite=15)
            total = inv.resumen(db)["por_caducar"] + inv.resumen(db)["caducados"]
            return _formatear("Caducados o por caducar", meds, total)
        if cmd in ("", "/stock"):
            if not arg:
                return "Indica qué medicamento buscar. Ej: /stock paracetamol"
            if len(arg) > 100:
                return "El texto de búsqueda es demasiado largo."
            meds, total = inv.buscar_texto(db, arg, limite=8)
            return _formatear("Resultados para «%s»" % arg, meds, total)
    return "Comando no reconocido. Usa /ayuda."


def chat_autorizado(chat_id: Optional[int]) -> bool:
    permitidos = settings.TELEGRAM_ALLOWED_CHAT_IDS
    return not permitidos or chat_id in permitidos


async def _api(client: httpx.AsyncClient, metodo: str, **payload):
    r = await client.post(
        "https://api.telegram.org/bot%s/%s" % (settings.TELEGRAM_BOT_TOKEN, metodo), json=payload
    )
    r.raise_for_status()
    return r.json()


async def responder_update(update: dict, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Procesa un update de Telegram y envía la respuesta. Devuelve el texto enviado."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return None
    chat_id = msg["chat"]["id"]
    if not chat_autorizado(chat_id):
        respuesta = "No autorizado. Tu chat_id es %s; pide al administrador que lo habilite." % chat_id
    else:
        respuesta = await asyncio.to_thread(procesar_mensaje, msg["text"], chat_id)

    propio = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        await _api(client, "sendMessage", chat_id=chat_id, text=respuesta[:4000])
    finally:
        if propio:
            await client.aclose()
    return respuesta


async def polling_worker() -> None:
    """Bucle de long-polling contra getUpdates."""
    log.info("Worker de Telegram (polling) iniciado")
    offset = None
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            await _api(client, "deleteWebhook")  # getUpdates falla si hay un webhook activo
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo limpiar el webhook: %s", exc)
        while True:
            try:
                data = await _api(client, "getUpdates", timeout=30, offset=offset,
                                  allowed_updates=["message", "edited_message"])
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        await responder_update(upd, client)
                    except Exception:  # noqa: BLE001
                        log.exception("Error procesando update")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("Error en getUpdates (%s); reintentando en 5 s", exc)
                await asyncio.sleep(5)
