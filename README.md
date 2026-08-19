# Matilde.IA — Asistente de materiales

Asistente de la [Mercería Matilde](https://www.merceriamatilde.com) (Paraná, Entre Ríos). Interpreta un proyecto de costura/tejido (texto + foto) y recomienda materiales **solo del catálogo propio**.

## Links

| Recurso | URL |
|---------|-----|
| App en vivo | https://ia.merceriamatilde.com |
| API IA | https://ia-api.merceriamatilde.com/health |
| Catálogo | https://www.merceriamatilde.com |
| Frontend | https://github.com/merceriamatilde-ops/mmatilde-frontend |
| API .NET | https://github.com/merceriamatilde-ops/mmatilde-backend |

## Cómo funciona

1. El cliente describe el proyecto y puede adjuntar una foto.
2. FastAPI arma el prompt (reglas aprendidas + catálogo) y llama a **Gemini 2.5 Flash**.
3. Si falta un dato que **no se infiere de la foto**, pregunta con chips (incluida la opción «No sé»).
4. Si el cliente salta, igual recomienda con `completitud: aproximada`.
5. Los términos de búsqueda se cruzan con productos reales vía `api.merceriamatilde.com`.
6. La dueña valida en el backoffice (bien/mal) y puede crear reglas por palabra clave.

Memoria persistente: Postgres (`ia_consultas`, `ia_reglas_aprendidas`, `ia_ejemplos`) en la API .NET.

## Stack

- Python 3 + FastAPI + LangChain (`ChatGoogleGenerativeAI`)
- Gemini 2.5 Flash (JSON)
- Catálogo y aprendizaje: API .NET + PostgreSQL
- Front: React (mismo repo de frontend, subdominio `ia.`)

## Local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# .env: GEMINI_API_KEY, CATALOG_API_URL=http://localhost:5015/api
python main.py
```

Health: `http://127.0.0.1:8000/health`

## Seguridad

- `GEMINI_API_KEY` solo en `.env` / `/etc/mmatilde/ia.env` (no en git)
- CORS acotado a los orígenes de Matilde
- Productos sugeridos salen del catálogo; no se inventan SKUs
