import os
import re
import json
import base64
import hashlib
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts import SYSTEM_PROMPT
from learned_rules import (
    extraer_texto_busqueda,
    obtener_contexto_aprendizaje,
    formatear_bloque_reglas,
    formatear_bloque_ejemplos,
    registrar_consulta,
)
from models import (
    ConsultaResponse,
    ResumenProyecto,
    ProgresoConsulta,
    Pregunta,
    OpcionPregunta,
    ResultadoEstimacion,
    Insumo,
)
from catalog import sugerir_productos

app = FastAPI(title="Matilde IA - Asistente de Materiales")

_cors_env = os.getenv("CORS_ORIGINS", "").strip()
_cors_origins = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else [
        "http://localhost:5173",
        "http://ia.localhost:5173",
        "http://127.0.0.1:5173",
        "https://www.merceriamatilde.com",
        "https://ia.merceriamatilde.com",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https?://([\w-]+\.)?localhost(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="Servicio de IA no configurado")
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.3,
            google_api_key=api_key,
            response_mime_type="application/json",
        )
    return _llm

MAX_IMAGE_BYTES = 4 * 1024 * 1024


@app.get("/")
def read_root():
    return {"status": "ok", "service": "matilde-ia"}


@app.get("/health")
def health():
    return {"status": "ok", "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))}


def _slugify_option(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower().strip())
    return slug.strip("_") or "opcion"


def _parse_ia_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _build_context_message(contexto: dict) -> str:
    parts = ["CONTEXTO DEL CLIENTE:"]

    desc = contexto.get("descripcion_inicial", "").strip()
    if desc:
        parts.append(f"- Descripción del proyecto: {desc}")

    respuestas = contexto.get("respuestas", [])
    if respuestas:
        parts.append("- Respuestas confirmadas:")
        for r in respuestas:
            parts.append(f"  · {r.get('pregunta', r.get('id', ''))}: {r.get('respuesta', '')}")

    notas = contexto.get("notas_adicionales", [])
    if notas:
        parts.append("- Notas adicionales del cliente (leelas y usalas, no repreguntes lo que ya dijo):")
        for n in notas:
            parts.append(f"  · {n}")

    paso = int(contexto.get("paso_refinamiento", 0))
    if paso > 0:
        parts.append(f"- Pantallas de detalle ya completadas: {paso}")

    if contexto.get("acepta_aproximado"):
        parts.append(
            "- IMPORTANTE: El cliente quiere ver recomendaciones YA, aunque falten datos. "
            "Respondé con estado 'listo', completitud 'aproximada', varias alternativas de "
            "insumos y distintos termino_busqueda para mostrar opciones del catálogo."
        )

    if len(parts) == 1:
        parts.append("- El cliente aún no describió el proyecto.")

    return "\n".join(parts)


def _normalize_preguntas(preguntas_raw: list) -> list[Pregunta]:
    preguntas: list[Pregunta] = []
    for p in preguntas_raw[:2]:
        opciones_raw = p.get("opciones", [])
        opciones: list[OpcionPregunta] = []
        for i, opt in enumerate(opciones_raw[:6]):
            if isinstance(opt, str):
                opciones.append(OpcionPregunta(id=f"opt_{i}", label=opt))
            elif isinstance(opt, dict):
                label = opt.get("label") or opt.get("texto") or str(opt)
                opt_id = opt.get("id") or _slugify_option(label)
                opciones.append(OpcionPregunta(id=opt_id, label=label))
        if p.get("pregunta") and opciones:
            preguntas.append(
                Pregunta(
                    id=p.get("id") or _slugify_option(p["pregunta"]),
                    pregunta=p["pregunta"],
                    opciones=opciones,
                )
            )
    return preguntas


def _safe_str(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _normalize_resultado(data: dict) -> ResultadoEstimacion | None:
    resultado_raw = data.get("resultado")
    if not resultado_raw or not isinstance(resultado_raw, dict):
        return None

    insumos: list[Insumo] = []
    for item in resultado_raw.get("insumos") or []:
        if isinstance(item, str):
            desc = item.strip()
            if desc:
                insumos.append(Insumo(descripcion=desc, termino_busqueda=desc[:40]))
        elif isinstance(item, dict):
            desc = _safe_str(item.get("descripcion"))
            termino = _safe_str(item.get("termino_busqueda"), desc[:40] if desc else "")
            if desc:
                insumos.append(Insumo(descripcion=desc, termino_busqueda=termino or desc[:40]))

    if not insumos:
        return None

    tecnica = _safe_str(
        resultado_raw.get("tecnica_detectada")
        or (data.get("resumen") or {}).get("tecnica"),
        "No especificada",
    )

    completitud = resultado_raw.get("completitud", "exacta")
    if completitud not in ("exacta", "aproximada"):
        completitud = "aproximada" if len(insumos) > 3 else "exacta"

    chequeos_raw = resultado_raw.get("chequeos") or []
    if isinstance(chequeos_raw, str):
        chequeos = [chequeos_raw] if chequeos_raw.strip() else []
    else:
        chequeos = [str(c).strip() for c in chequeos_raw if c]

    supuestos_raw = resultado_raw.get("supuestos") or []
    if isinstance(supuestos_raw, str):
        supuestos = [supuestos_raw] if supuestos_raw.strip() else []
    else:
        supuestos = [str(s).strip() for s in supuestos_raw if s]

    if not chequeos:
        chequeos = ["catálogo propio", "rango de cantidad", "destinatario"]

    return ResultadoEstimacion(
        tecnica_detectada=tecnica,
        insumos=insumos,
        nota=_safe_str(resultado_raw.get("nota")),
        completitud=completitud,
        supuestos=supuestos,
        chequeos=chequeos,
    )


def _normalize_progreso(data: dict, estado: str) -> ProgresoConsulta:
    raw = data.get("progreso") or {}
    confirmado = [str(c).strip() for c in (raw.get("confirmado") or []) if c]
    falta = [str(f).strip() for f in (raw.get("falta") or []) if f]

    if estado == "listo":
        return ProgresoConsulta(confirmado=confirmado, falta=[], pasos_restantes=0, ultimo_paso=True)

    pasos = raw.get("pasos_restantes")
    try:
        pasos_restantes = max(1, min(3, int(pasos))) if pasos is not None else max(1, len(falta))
    except (TypeError, ValueError):
        pasos_restantes = max(1, len(falta)) if falta else 1

    ultimo_paso = bool(raw.get("ultimo_paso", False))

    return ProgresoConsulta(
        confirmado=confirmado,
        falta=falta,
        pasos_restantes=pasos_restantes,
        ultimo_paso=ultimo_paso,
    )


@app.post("/api/consulta", response_model=ConsultaResponse)
async def consulta_proyecto(
    contexto: str = Form("{}"),
    imagen: UploadFile | None = File(None),
):
    try:
        contexto_data = json.loads(contexto)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Contexto inválido")

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    texto_busqueda = extraer_texto_busqueda(contexto_data)
    ctx_aprendizaje = await obtener_contexto_aprendizaje(texto_busqueda)
    bloque_extra = formatear_bloque_reglas(ctx_aprendizaje.get("reglas") or [])
    bloque_extra += formatear_bloque_ejemplos(ctx_aprendizaje.get("ejemplos") or [])
    if bloque_extra:
        messages[0] = SystemMessage(content=SYSTEM_PROMPT + bloque_extra)

    content: list[dict] = [{"type": "text", "text": _build_context_message(contexto_data)}]

    if imagen:
        image_bytes = await imagen.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="La imagen es muy pesada. Probá con otra foto más chica.",
            )
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        mime = imagen.content_type or "image/jpeg"
        content.append(
            {"type": "image_url", "image_url": f"data:{mime};base64,{encoded}"}
        )
        content[0]["text"] += "\n\n(El cliente adjuntó una foto de referencia — usala para inferir técnica, colores y tipo de proyecto.)"

    messages.append(HumanMessage(content=content))

    try:
        response = get_llm().invoke(messages)
        ia_data = _parse_ia_json(response.content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="No pudimos interpretar la respuesta de la IA. Intentá de nuevo.",
        )
    except Exception as e:
        err = str(e)
        print(f"[gemini] Error: {e}")
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    "La asistente está muy solicitada en este momento (límite diario de consultas). "
                    "Probá de nuevo en unos minutos o escribinos por WhatsApp y te ayudamos."
                ),
            )
        raise HTTPException(status_code=502, detail="Error al consultar la IA")

    estado = ia_data.get("estado", "preguntando")
    if estado not in ("preguntando", "listo"):
        estado = "listo" if ia_data.get("resultado") else "preguntando"

    resumen_raw = ia_data.get("resumen") or {}
    resumen = ResumenProyecto(
        proyecto=_safe_str(resumen_raw.get("proyecto")),
        tecnica=_safe_str(resumen_raw.get("tecnica")) or None,
        detalles=[d for d in (resumen_raw.get("detalles") or []) if d],
    )

    preguntas = [] if estado == "listo" else _normalize_preguntas(ia_data.get("preguntas") or [])
    resultado = _normalize_resultado(ia_data) if estado == "listo" else None
    progreso = _normalize_progreso(ia_data, estado)

    if estado == "listo" and not resultado:
        estado = "preguntando"
        progreso = _normalize_progreso({**ia_data, "estado": "preguntando"}, "preguntando")
        if not progreso.falta:
            progreso.falta = ["Un poco más de detalle sobre tamaño y material"]
        mensaje = _safe_str(
            ia_data.get("mensaje"),
            "Necesito un poco más de información para calcular los materiales.",
        )
    else:
        mensaje = _safe_str(
            ia_data.get("mensaje"),
            "¡Listo! Te dejé el detalle de materiales y productos sugeridos."
            if estado == "listo"
            else "Contame un poco más para afinar la recomendación.",
        )

    if estado == "preguntando" and not preguntas and progreso.falta:
        mensaje = mensaje or "Necesitamos confirmar algunos datos más para calcular los materiales."

    productos = []
    if resultado:
        productos = await sugerir_productos(
            resultado.insumos,
            aproximada=resultado.completitud == "aproximada",
        )

        resultado_dict = resultado.model_dump()
        productos_json = json.dumps([p.model_dump() for p in productos], ensure_ascii=False)
        idem_key = hashlib.sha256(
            (contexto + json.dumps(resultado_dict, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        await registrar_consulta(
            proyecto=resumen.proyecto or "Sin título",
            tecnica=resultado.tecnica_detectada,
            contexto_json=contexto,
            resultado_json=json.dumps(resultado_dict, ensure_ascii=False),
            productos_json=productos_json,
            idempotency_key=idem_key,
        )

    return ConsultaResponse(
        estado=estado,
        mensaje=mensaje,
        progreso=progreso,
        resumen=resumen,
        preguntas=preguntas,
        resultado=resultado,
        productos_sugeridos=productos,
    )


# Compatibilidad con integraciones anteriores
@app.post("/api/chat")
async def chat_legacy(
    historial: str = Form("[]"),
    mensaje_nuevo: str = Form(""),
    imagen: UploadFile | None = File(None),
):
    try:
        history = json.loads(historial)
    except json.JSONDecodeError:
        history = []

    descripcion = mensaje_nuevo.strip()
    if not descripcion and history:
        for msg in reversed(history):
            if msg.get("role") == "user" and msg.get("content"):
                descripcion = msg["content"]
                break

    contexto = json.dumps({
        "descripcion_inicial": descripcion,
        "respuestas": [],
        "notas_adicionales": [],
    })

    result = await consulta_proyecto(contexto=contexto, imagen=imagen)

    if result.estado == "listo" and result.resultado:
        return {
            "tipo": "resultado_final",
            "tecnica_detectada": result.resultado.tecnica_detectada,
            "insumos_teoricos": [i.descripcion for i in result.resultado.insumos],
            "sugerencias_catalogo": [p.model_dump() for p in result.productos_sugeridos],
        }

    opciones_txt = ""
    if result.preguntas:
        opts = [o.label for o in result.preguntas[0].opciones[:4]]
        opciones_txt = f" Podés elegir: {', '.join(opts)}."

    return {
        "tipo": "mensaje",
        "mensaje": result.mensaje + opciones_txt,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
