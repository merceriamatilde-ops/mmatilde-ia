"""Reglas y ejemplos aprendidos — se inyectan en el prompt de Gemini (filtrados por contexto)."""

import os
import hashlib
import httpx

_CACHE_TTL_SEC = 120
_contexto_cache: dict[str, tuple[float, dict]] = {}


def _api_base() -> str:
    api_url = os.getenv("CATALOG_API_URL", "http://localhost:5015/api").rstrip("/")
    return api_url.rsplit("/api", 1)[0] + "/api"


def extraer_texto_busqueda(contexto_data: dict) -> str:
    parts: list[str] = []
    parts.append(str(contexto_data.get("descripcion_inicial", "")))
    for r in contexto_data.get("respuestas") or []:
        if isinstance(r, dict):
            parts.append(str(r.get("pregunta", "")))
            parts.append(str(r.get("respuesta", "")))
    for n in contexto_data.get("notas_adicionales") or []:
        parts.append(str(n))
    return " ".join(p.strip() for p in parts if p and str(p).strip())


async def obtener_contexto_aprendizaje(texto_busqueda: str) -> dict:
    import time

    key = hashlib.md5(texto_busqueda.encode("utf-8")).hexdigest()[:16]
    now = time.monotonic()
    cached = _contexto_cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    base = _api_base()
    params = {"q": texto_busqueda[:2000]} if texto_busqueda.strip() else {}

    vacio = {"reglas": [], "ejemplos": []}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{base}/ia/contexto-aprendizaje", params=params)
            if resp.status_code == 200:
                data = resp.json()
                _contexto_cache[key] = (now, data)
                if len(_contexto_cache) > 80:
                    oldest = min(_contexto_cache, key=lambda k: _contexto_cache[k][0])
                    _contexto_cache.pop(oldest, None)
                return data
    except Exception as e:
        print(f"[learned_rules] No se pudo cargar contexto: {e}")

    return cached[1] if cached else vacio


def formatear_bloque_reglas(reglas: list) -> str:
    if not reglas:
        return ""
    lineas = []
    for item in reglas[:8]:
        if isinstance(item, dict):
            lineas.append(f"- {item.get('regla', '')}")
        else:
            lineas.append(f"- {item}")
    if not lineas:
        return ""
    return (
        "\n\nREGLAS APRENDIDAS (solo las relevantes a este proyecto):\n"
        + "\n".join(lineas)
        + "\nAplicá cada regla SOLO si el destinatario coincide "
        "(adulto / bebé / niño / mascota). Si la regla habla de adulto y el cliente pidió bebé, IGNORALA."
        "\nPriorizalas sobre estimaciones genéricas cuando apliquen."
    )


def formatear_bloque_ejemplos(ejemplos: list) -> str:
    if not ejemplos:
        return ""
    parts = [
        "\n\nEJEMPLOS DE REFERENCIA (casos corregidos por el equipo — imitá este formato si el proyecto es similar):"
    ]
    for i, ex in enumerate(ejemplos[:3], 1):
        if not isinstance(ex, dict):
            continue
        titulo = ex.get("titulo", f"Ejemplo {i}")
        desc = ex.get("descripcion", "")
        resp = ex.get("respuestaJson", ex.get("respuesta_json", ""))
        parts.append(f"\n--- Ejemplo {i}: {titulo} ---")
        parts.append(f"Contexto: {desc}")
        if ex.get("imagenUrl"):
            parts.append("(Incluye foto de referencia en archivo interno — interpretá la prenda como en la descripción, no al azar.)")
        parts.append(f"Respuesta correcta esperada: {resp}")
    return "\n".join(parts)


async def registrar_consulta(
    proyecto: str,
    tecnica: str | None,
    contexto_json: str,
    resultado_json: str,
    productos_json: str | None,
    idempotency_key: str | None = None,
) -> None:
    base = _api_base()
    payload = {
        "proyecto": proyecto or "Sin título",
        "tecnica": tecnica,
        "contextoJson": contexto_json,
        "resultadoJson": resultado_json,
        "productosJson": productos_json,
    }
    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    url = f"{base}/ia/consultas"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                print(f"[learned_rules] Consulta guardada en BO (proyecto={proyecto[:40]!r})")
            else:
                print(
                    f"[learned_rules] Error al guardar consulta: {resp.status_code} "
                    f"url={url} body={resp.text[:300]}"
                )
    except Exception as e:
        print(f"[learned_rules] No se pudo guardar consulta en {url}: {e}")
