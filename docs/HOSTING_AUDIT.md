# Deployment readiness audit — 2026-11-07

Audited upstream commit `cfb2f657f7bbcb7f01ae6ebc4574e4a26e8c65bd` in an independent clone. Existing local development folders are untouched. No deployment, push, cloud mutation or credential reuse is authorized by this audit.

## Findings before changes

- Entry point: `cd backend && uvicorn api:app --host 0.0.0.0 --port "$PORT" --workers 1`. Keep repository-root `data/images` available; Render root directory must remain repository root.
- Python 3.12; existing requirements are unpinned. Documented development versions are historical evidence, not a clean Linux installation or lock. CPU inference supported; multiple workers duplicate model memory.
- API process is lazy, although Python imports include NumPy/Pillow. FashionCLIP initializes on first search; MiniLM is imported and may initialize on attribute extraction, not unconditionally during ProductSearch construction (older handover overstates this). Hugging Face cache must be available; historical caches ~668 MiB combined are disk sizes, not RAM measurements. Catalog ~361 MiB; allow several GiB build/runtime disk for Python, Torch and caches. RAM still needs measurement.
- 1,993 catalog JPEGs retained; original metadata has seven known missing IDs 357–363. Root catalog mount/path helpers already support production layout.
- Frontend uses absolute API origin from config.js; current value `https://garmentchatbot.onrender.com` exists in source but ownership/reachability is unverified. Firebase selects `garmentchatbot`, publishes `frontend`, and currently publishes tests/docs as well. Project permissions are unverified.
- CORS defaults to development localhost origins; production needs explicit Firebase origins. HTTPS API is already configured in source, but a configured URL is not deployment evidence.
- Liveness `/api/health` does not load models or verify dependencies. No readiness endpoint or rate limit. Agent LLM timeout exists (30s, no retries); extractor and Qdrant lack explicit bounded settings.
- Qdrant unnamed 512-dimensional cosine collection expected for the historical FashionCLIP model. Model identity, live dimension, payload/index compatibility and populated count are unverified. No ingestion is permitted.
- LLM uses OpenAI-compatible Responses/structured tools; endpoint/model/key must support the actual application requests. No live provider request has been made.
- `.gitignore` repeats backend/.env and then explicitly unignores it. `backend/.env` is tracked. All credentials there and historically exposed Qdrant, HF and provider credentials require owner rotation; values are never reported or reused.

## Redacted current-tree scan

Heuristic scan findings below report locations only, may include false positives, and are not a guarantee of absence. No credential values are printed. Full Git history remains unremediated.

- `backend/.env:8`
- `backend/src/ingest_product.py:60`
- `backend/src/ingest_product.py:76`
- `backend/src/product_search.py:193`

Environment names present in tracked configuration: `POE_API`, `POE_URL`, `OPENAI_MODEL`, `QDRANT_URL`, `QDRANT_API`, `QDRANT_COLLECTION`, `CLIP_MODEL`, `HF_TOKEN`, `CORS_ORIGINS`, `MAX_CONTEXT_MESSAGES`, `MAX_CONTEXT_CHARS`, `PRODUCT_FILE`, `BATCH_SIZE`.

## Redacted history scan

Scanned text files across all eight locally fetched reachable commits for provider/HF/JWT patterns. Findings report paths and categories only (heuristic, not exhaustive):

- `.env`: model-host-token
- `.env`: provider-key
- `.env`: qdrant-token
- `Credentials/qdrant`: qdrant-token
- `backend/.env`: model-host-token
- `backend/.env`: provider-key
- `backend/.env`: qdrant-token

Revoke all potentially exposed Qdrant, HF and LLM provider keys regardless of whether a pattern matches. No history was rewritten.
