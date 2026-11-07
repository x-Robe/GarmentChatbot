# Deployment Notes — Not Deployed

No hosting platform, domain, TLS setup, container, CI, authentication system or production process manager has been selected or implemented here. The README commands are local development commands.

## Provisioning requirements

- Build a compatible Python 3.12 environment with backend/requirements.txt plus test dependencies when testing. PyTorch/Transformers/sentence-transformers are significant dependencies; OS/CPU/GPU wheels and versions must be validated on the chosen platform. Known development versions are in TESTED_VERSIONS.md; this is not a lock.
- Download/provision the approved FashionCLIP and MiniLM tokenizer/config/weights. The original cache held approximately 581 MiB and 87 MiB respectively; these file sizes are **not** measured process memory. No weights/cache/venv are bundled. Existing catalog JPEGs remain tracked at repository root. Cold starts include imports, model loading and client setup. CPU is supported by current code; CUDA is used when available. No throughput, RAM or latency guarantees are provided. Benchmark before choosing worker counts; processes duplicate model memory and each has a serializing lock.
- Provision compatible Qdrant vectors, metadata and indexes or arrange owner-approved access to the existing collection. No database snapshot is included. Ingestion scripts write collections and are not automatic startup steps.
- Supply authorized catalog files to data/images/ at the paths in DATASET_ASSETS.md. Qdrant does not store JPEG binaries. The API mounts repository-root data/images through src/asset_paths.py; the existing catalog supplies it. No backend catalog copy or placeholder is required. Missing files return 404.

## Configuration and secrets

Populate backend/.env privately from the root template, or inject actual environment variables. Do not put secrets in frontend/config.js or bake them into public images/logs. Use either the compatible-provider POE_API/POE_URL path or remove those variables and use OPENAI_API_KEY/default base URL. Set the matching model and collection; placeholders are not working service settings. Only set valid optional HF tokens. Offline download flags require already-complete cache.

Past credentials in the old repository must be revoked/rotated and old history exposure separately remediated before public release. This clean directory does not cure existing remotes/forks/clones. No key validity or remote-publicity check was performed.

## Browser and networking

Set frontend/config.js API_BASE_URL to the actual reachable HTTPS API origin; no build-time environment injection exists. Set CORS_ORIGINS to explicit frontend origins and restart the API. Avoid mixed-content HTTP API/images from an HTTPS page. TLS and microphone permissions must work in the intended browser. Speech APIs/voices vary and recognition may depend on a browser-operated online service; actual voice acceptance remains to be run on the final host.

Private Qdrant connectivity and LLM compatible Responses/structured-tool support must be tested using newly authorized credentials. Backend egress may need model-hosting access. No ports/domains/platform are invented as production values.

## Operations and readiness

The current public API has no authentication, rate limiting or account isolation. CORS is not access control. Decide access policies, per-user/API quotas, paid-provider spending limits, logs/retention, request timeouts and monitoring before exposing it. Request content may include private user text/images, so avoid logging them unnecessarily. The existing upload limits do not provide a complete abuse-control layer.

GET /api/health checks process liveness without loading models or querying services. HTTP 200 does not prove catalog completeness, provider access, model readiness or Qdrant health. Production readiness and failure handling should be separately designed/approved. No live search smoke was performed for this release.

History/reference embeddings live in browser-origin localStorage, not server persistence; no cross-device synchronization, accounts or migration exists. New origins/ports have separate storage and saved absolute image URLs are not rewritten automatically. Original upload previews are not retained after refresh; do not introduce original-image storage merely to restore thumbnails.

## Before declaring Hosting complete

Verify clean dependency installation, authorized assets/cache, secrets and external services; run isolated tests, then approved E2E text/image/mixed/all-mode/refinement/pagination checks. Test refresh continuation and actual mic/speaker under HTTPS. Measure cold/warm latency and memory/concurrency. Document the chosen platform, production startup, TLS/origins, recovery and access/cost controls. None of these remaining production validations is claimed by the staging checks.
