"""Términos de búsqueda del catálogo: normalización, sinónimos y variantes."""
from __future__ import annotations

import re
import unicodedata

STOP_WORDS = frozenset({
    "para", "con", "sin", "del", "de", "la", "el", "los", "las", "una", "uno", "por",
    "mas", "muy", "que", "como", "tipo", "aprox", "aproximado",
})

TOKEN_ALIASES: dict[str, str] = {
    "semigorda": "semigruesa",
    "semigroso": "semigruesa",
    "semigrueso": "semigruesa",
    "semi-fina": "semifina",
    "semi fina": "semifina",
    "acrilica": "acrilico",
    "agujas": "aguja",
    "tejedora": "tejedor",
    "tejedoras": "tejedor",
    "lanas": "lana",
    "hilos": "hilo",
    "guatas": "guata",
    "cierres": "cierre",
    "botones": "boton",
    "botón": "boton",
    "elastico": "elastico",
    "elástico": "elastico",
    "elásticos": "elastico",
}

SYNONYM_EXPANSION: dict[str, list[str]] = {
    "semigruesa": ["semigorda", "gruesa", "grueso"],
    "semifina": ["fina", "fino"],
    "lana": ["ovillo", "madeja"],
    "hilo": ["ovillo", "madeja"],
    "aguja": ["tejedor", "circular"],
    "crochet": ["croche", "ganchillo"],
    "algodon": ["algodón"],
    "acrilico": ["acrílico", "sintetica", "sintética"],
    "guata": ["relleno", "volumen"],
    "cierre": ["zipper", "cremallera"],
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_query(query: str) -> str:
    text = _strip_accents(query.strip().lower())
    text = re.sub(r"[-_/\\.,;:+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _canonical_token(token: str) -> str:
    normalized = normalize_query(token)
    return TOKEN_ALIASES.get(normalized, normalized)


def expand_search_terms(query: str) -> list[str]:
    normalized = normalize_query(query)
    if len(normalized) < 3:
        return []

    tokens: set[str] = set()
    visited: set[str] = set()

    def add_token(token: str | None) -> None:
        if not token:
            return
        canon = _canonical_token(token)
        if len(canon) < 3 or canon in STOP_WORDS:
            return
        if canon in visited:
            return
        visited.add(canon)
        tokens.add(canon)
        if canon.endswith("s") and len(canon) > 4:
            tokens.add(canon[:-1])
        for syn in SYNONYM_EXPANSION.get(canon, []):
            add_token(syn)

    add_token(normalized)
    for part in normalized.split():
        add_token(part)

    return [t for t in tokens if len(t) >= 3 and t not in STOP_WORDS]
