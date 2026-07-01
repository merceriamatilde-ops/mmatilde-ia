import os
import httpx
from models import Insumo, ProductoSugerido

CATALOG_API_URL = os.getenv("CATALOG_API_URL", "https://api.merceriamatilde.com/api")
MAX_PRODUCTOS = int(os.getenv("CATALOG_MAX_SUGERENCIAS", "12"))


async def buscar_productos(termino: str) -> list[dict]:
    termino = termino.strip()
    if len(termino) < 3:
        return []

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{CATALOG_API_URL}/catalogo/buscar",
                params={"q": termino},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"[catalog] Error buscando '{termino}': {e}")
    return []


async def sugerir_productos(insumos: list[Insumo], aproximada: bool = False) -> list[ProductoSugerido]:
    vistos: set[int] = set()
    sugerencias: list[ProductoSugerido] = []
    por_insumo = 4 if aproximada else 2
    max_total = 16 if aproximada else MAX_PRODUCTOS

    for insumo in insumos:
        productos = await buscar_productos(insumo.termino_busqueda)
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
