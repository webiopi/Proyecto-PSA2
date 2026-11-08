"""Integración con Ollama: análisis y sugerencias de compra en lenguaje natural."""
import json
from datetime import date
from typing import List

import httpx
from sqlalchemy import select

from ..config import settings
from ..models import Medicamento
from . import inventory as inv


class OllamaError(Exception):
    def __init__(self, mensaje: str, status: int = 502):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def _fila(m: Medicamento) -> str:
    return "- %s (%s), lote %s, caduca %s, stock %d (mín %d, máx %d)" % (
        m.nombre, m.principio_activo, m.lote, m.fecha_caducidad.isoformat(),
        m.stock_actual, m.stock_minimo, m.stock_maximo,
    )


def construir_prompt(caducan: List[Medicamento], criticos: List[Medicamento]) -> str:
    hoy = date.today().isoformat()
    partes = [
        "Eres un asistente de farmacia hospitalaria. Fecha de hoy: %s." % hoy,
        "Analiza los datos de inventario y responde en español, de forma breve y accionable: "
        "(1) prioridades, (2) sugerencia de compra con cantidades aproximadas "
        "(lleva cada producto hacia su stock máximo sin superarlo), "
        "(3) acciones para lotes próximos a caducar (rotación, devolución, uso prioritario). "
        "No inventes datos que no aparezcan abajo.",
        "",
        "MEDICAMENTOS CADUCADOS O PRÓXIMOS A CADUCAR (≤ %d días):" % settings.DIAS_ALERTA_CADUCIDAD,
        "\n".join(_fila(m) for m in caducan) or "(ninguno)",
        "",
        "MEDICAMENTOS CON STOCK CRÍTICO (bajo el mínimo):",
        "\n".join(_fila(m) for m in criticos) or "(ninguno)",
    ]
    return "\n".join(partes)


async def generar(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
            r = await client.post(
                settings.OLLAMA_URL,
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
    except httpx.ConnectError:
        raise OllamaError("No se pudo conectar con Ollama en %s. ¿Está en ejecución?" % settings.OLLAMA_URL, 503)
    except httpx.TimeoutException:
        raise OllamaError("Ollama tardó demasiado en responder.", 504)
    except httpx.HTTPError as exc:
        raise OllamaError("Error de red al contactar con Ollama: %s" % exc, 502)

    if r.status_code != 200:
        detalle = ""
        try:
            detalle = r.json().get("error", "")
        except ValueError:
            pass
        if r.status_code == 404:
            raise OllamaError("El modelo «%s» no está instalado en Ollama (ejecuta: ollama pull %s). %s"
                              % (settings.OLLAMA_MODEL, settings.OLLAMA_MODEL, detalle), 502)
        raise OllamaError("Ollama respondió %d. %s" % (r.status_code, detalle), 502)
    try:
        return r.json()["response"].strip()
    except (ValueError, KeyError):
        raise OllamaError("Respuesta inesperada de Ollama.", 502)


async def analizar_inventario(db) -> dict:
    caducan = inv.listar_riesgo_caducidad(db, limite=50)
    criticos = inv.listar_stock_critico(db, limite=50)
    if not caducan and not criticos:
        return {
            "modelo": None,
            "analisis": "No hay medicamentos caducados, próximos a caducar ni con stock crítico. "
                        "No se requieren acciones.",
            "caducan": 0,
            "criticos": 0,
        }
    texto = await generar(construir_prompt(caducan, criticos))
    return {"modelo": settings.OLLAMA_MODEL, "analisis": texto, "caducan": len(caducan), "criticos": len(criticos)}


def _extraer_json(texto: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta del modelo (tolera texto/markdown alrededor)."""
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini == -1 or fin <= ini:
        return {}
    try:
        data = json.loads(texto[ini:fin + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def sugerir_medicamentos(db, dolencia: str) -> dict:
    """Sugiere medicamentos del inventario disponible para una dolencia descrita por el médico."""
    disponibles = list(db.scalars(
        select(Medicamento).where(Medicamento.stock_actual > 0, Medicamento.fecha_caducidad >= date.today())
        .order_by(Medicamento.nombre).limit(150)
    ).all())
    if not disponibles:
        return {"modelo": None, "explicacion": "No hay medicamentos con stock disponible.", "sugeridos": []}
    catalogo = "\n".join(
        "%d | %s | %s | stock %d" % (m.id, m.nombre, m.principio_activo, m.stock_actual) for m in disponibles
    )
    prompt = "\n".join([
        "Eres un asistente de farmacia hospitalaria que apoya a un médico. No sustituyes su criterio clínico.",
        "Dolencia o síntoma indicado por el médico: «%s»" % dolencia,
        "",
        "Del siguiente catálogo (formato: id | nombre | principio activo | stock) elige SOLO medicamentos "
        "que existan en la lista y sean pertinentes (máximo 5):",
        catalogo,
        "",
        'Responde ÚNICAMENTE con JSON válido: {"ids": [<ids del catálogo>], "explicacion": "<una o dos frases en español>"}',
    ])
    data = _extraer_json(await generar(prompt))
    por_id = {m.id: m for m in disponibles}
    ids = []
    for v in data.get("ids", []) if isinstance(data.get("ids"), list) else []:
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if i in por_id and i not in ids:
            ids.append(i)
    explicacion = data.get("explicacion") if isinstance(data.get("explicacion"), str) else ""
    if not ids and not explicacion:
        explicacion = "El modelo no devolvió sugerencias utilizables. Intenta describir la dolencia con más detalle."
    return {
        "modelo": settings.OLLAMA_MODEL,
        "explicacion": explicacion.strip()[:600],
        "sugeridos": [medicamento_json(por_id[i]) for i in ids[:5]],
    }


def medicamento_json(m: Medicamento) -> dict:
    return {
        "id": m.id, "nombre": m.nombre, "principio_activo": m.principio_activo, "lote": m.lote,
        "caducidad": m.fecha_caducidad.strftime("%d/%m/%Y"), "stock": m.stock_actual,
    }
