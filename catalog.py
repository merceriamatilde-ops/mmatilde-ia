import os
import httpx
from models import Insumo, ProductoSugerido
from search_terms import expand_search_terms, normalize_query

CATALOG_API_URL = os.getenv("CATALOG_API_URL", "http://localhost:5015/api")
MAX_PRODUCTOS = int(os.getenv("CATALOG_MAX_SUGERENCIAS", "30"))
PER_INSUMO = int(os.getenv("CATALOG_PER_INSUMO", "8"))


async def _buscar_api(termino: str, limit: int) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{CATALOG_API_URL}/catalogo/buscar",
                params={"q": termino, "limit": limit},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"[catalog] Error buscando '{termino}': {e}")
    return []


async def buscar_productos(termino: str, limit: int = 20) -> list[dict]:
    termino = termino.strip()
    if len(termino) < 3:
        return []

    candidatos = expand_search_terms(termino)
    if not candidatos:
        candidatos = [normalize_query(termino)]

    # Frase completa primero, luego tokens de más específicos a más cortos
    orden = [termino.strip(), normalize_query(termino)]
    orden.extend(sorted(candidatos, key=len, reverse=True))
    vistos_query: set[str] = set()
    vistos_id: set[int] = set()
    resultados: list[dict] = []

    for q in orden:
        q = q.strip()
        if len(q) < 3 or q in vistos_query:
            continue
        vistos_query.add(q)
        productos = await _buscar_api(q, limit)
        for prod in productos:
            prod_id = prod.get("id")
            if prod_id is None or prod_id in vistos_id:
                continue
            vistos_id.add(prod_id)
            resultados.append(prod)
            if len(resultados) >= limit:
                return resultados

    return resultados


async def sugerir_productos(insumos: list[Insumo], aproximada: bool = False) -> list[ProductoSugerido]:
    vistos: set[int] = set()
    sugerencias: list[ProductoSugerido] = []
    por_insumo = PER_INSUMO if aproximada else max(6, PER_INSUMO - 2)
    max_total = 36 if aproximada else MAX_PRODUCTOS

    for insumo in insumos:
        productos = await buscar_productos(insumo.termino_busqueda, limit=por_insumo + 4)
        for prod in productos[:por_insumo]:
            prod_id = prod.get("id")
            if prod_id is None or prod_id in vistos:
                continue
            vistos.add(prod_id)
            sugerencias.append(
                ProductoSugerido(
                    id=prod_id,
                    slug=prod.get("slug", ""),
                    nombre=prod.get("nombre", ""),
                    categoria=prod.get("categoria", ""),
                    imagen_url=prod.get("imagenUrl"),
                    termino_relacionado=insumo.termino_busqueda,
                )
            )
            if len(sugerencias) >= max_total:
                return sugerencias

    return sugerencias
