# Hosting Teammate Handover

## Completed and included

This release includes the current sibling browser frontend and FastAPI backend together. Text/image/mixed modes, LLM planning, FashionCLIP retrieval, structured filters, localStorage history/image vectors, refinements, pagination, 1–8 counts, voice controls and product UI are implemented. Hosting has not been performed. Prompts, retrieval algorithms, ranking and frontend are unchanged from the final release. Only repository/catalog path plumbing and integration-specific tests/documentation were added; see INTEGRATION_REPORT.md.

Start with [README](../README.md). Active modules:

| File | Responsibility |
|---|---|
| frontend/app.js | UI orchestration and common typed/voice submission path |
| frontend/search.js + config.js | HTTP contracts and public API origin |
| frontend/state.js + context.js | localStorage, reference compatibility, full bounded text history |
| frontend/presentation.js + products.js | legacy-image display normalization, carousel/details |
| frontend/voice.js | Browser recognition/synthesis lifecycle; no server audio pipeline |
| backend/api.py | Validation, CORS, bounded uploads/JSON, shared lazy backend, image mount |
| backend/chatbot.py + SKILL.md | LLM plan validation, domain policy, mode overrides, tool dispatch, result selection |
| backend/src/product_search.py | Qdrant metadata/vector queries, paging and image routing |
| backend/src/extract_embeding.py | Actual FashionCLIP encoder; retain the existing spelling |
| backend/src/zero_shot_classifier.py + hybrid_image_search.py | Image attribute labels and current candidate policy |
| backend/src/query_attribute_extractor.py | Structured LLM text attributes / explicit image overrides |
| backend/src/search_state.py + image_reference.py | Validated client-supplied active search and reference embeddings |
| backend/src/result_count.py + conversation_context.py | Count limits and bounded server-side history |
| backend/src/image_upload.py + json_size_limit.py | Request and decoded-image limits |
| backend/src/image_messages.py | Image result prose |
| backend/src/ingest_product.py + qdrant_connection.py | Offline collection creation/upsert; NOT startup tasks |
| evaluation/ | Preserved rankings, pseudonymized labels and offline metric calculation |

## Configuration and service dependencies

Private configuration belongs in **backend/.env**; root `.env.example` is only a template. Use POE_API/POE_URL for the approved compatible provider or remove both and use OPENAI_API_KEY with SDK defaults. OPENAI_MODEL, QDRANT_URL, QDRANT_COLLECTION and matching CLIP_MODEL must be supplied; QDRANT_API is required only for authenticated servers. HF_TOKEN is optional when authorized/public download does not need it. CORS and bounded history have documented defaults. Do not populate two conflicting key styles or leave POE_URL empty when expecting SDK defaults.

FashionClipEmbedder uses AutoProcessor/AutoModel.from_pretrained(CLIP_MODEL), chooses CUDA when available otherwise CPU. ProductSearch also initializes `sentence-transformers/all-MiniLM-L6-v2`. Both sets of weights/tokenizers/config must be obtainable on the host. No local cache or virtual environment is included. Offline flags work only after cache provisioning.

The evaluation manifest identifies the historical collection/model, not an exported database or a supplied credential. Ask the collection owner for the approved endpoint/key and whether to reuse a populated collection. Preserve 512-dimensional compatible vectors, cosine collection setup and actual payload types: product_id, image_url/path and supported colors/patterns/neckline/sleeve/style/buttons/category metadata. Review current indexes: historical integer product_id payload vs keyword index has an existing pagination fallback; do not assume a new collection has been provisioned or migration is approved.

Qdrant stores vectors/payloads, not the actual JPEG files. `/images` serves data/images, so the host must separately receive authorized assets at their relative paths. [Asset manifest and instructions](DATASET_ASSETS.md) list all 1,993 known files/hashes and seven missing records. Do not publish images merely because an asset manifest exists.

## Tests and what remains unverified

The release directory itself passed **103 frontend / 160 backend isolated tests**. Models/LLM are mocked and local Qdrant fixtures are in-memory. The available existing Python packages were reused for these checks; a new dependency installation was not attempted. An initial backend test failure revealed a catalog dependency; the release test now generates a temporary JPEG and passes the same static-serving/CORS assertions.

A separate release-only server imports successfully and serves `/api/health` without initializing the agent. This does not verify real Qdrant/provider/model/image readiness. No paid-provider or hosted-Qdrant query, ingestion, catalog upload or new browser E2E run was performed for this staging task. Historical real API/browser observations are retained as stage-specific engineering evidence under validation/; historical counts are not current rerun counts.

Saved evaluation metrics were recomputed offline: T2 acknowledged from the project owner's task instruction, primary mean P@5 0.6600/10 queries. The 57 relevance labels/notes and all ranked results remain unchanged; identity fields alone were pseudonymized. T2's reviewed_by is project-owner-confirmation, deliberately not an invented personal name or claim that the original named reviewer was re-interviewed. Image v1/v2 ablation values are unchanged. See ../evaluation/README.md.

Still unverified: clean-environment dependency resolution, catalog/model download rights and provisioning, live access using rotated keys, full E2E on the host, production memory/latency/concurrency, and real microphone/speaker behavior in the final HTTPS browser.

## Hosting actions remaining

1. Resolve credential exposure and public-release blockers below.
2. Choose hosting, build the Python environment, provision authorized model cache/images and compatible Qdrant.
3. Set secrets privately, configure frontend API_BASE_URL and explicit backend CORS origins, provide HTTPS and microphone permissions.
4. Decide access control, rate limits, spending limits, monitoring, timeouts and readiness checks. The app currently has no authentication or backend history database.
5. Validate all modes, image continuation after refresh, text searches, pagination and browser voice on the target host.

Each process has its own lazy models/client and a lock serializes its search calls. More workers duplicate model memory; no measured production sizing is supplied. localStorage is per origin; changing domain/port does not migrate history or rewrite saved absolute product-image URLs. Keep dataset paths stable. See [deployment notes](DEPLOYMENT_NOTES.md).

## Files generally not to change for hosting

Do not casually edit SKILL.md, FashionCLIP embeddings, zero-shot labels, extraction prompts, filters, ranking, mode behavior, reference schema or evaluation labels. Hosting should primarily configure secrets, service origins, model/cache/assets and operations. Any behavior change needs separate review/tests.

## Critical: old GitHub secrets are unresolved

The previous repository history contains exposed credentials. Owners must revoke/rotate old Qdrant, model-hosting and LLM-provider credentials as applicable. A clean copy does **not** erase existing GitHub history; old clones/forks may retain commits. Reusing the previous remote/history requires an explicit separate remediation decision. Current-tree credentials/populated .env were removed, but the original repository history is deliberately retained and still contains past exposures. No history rewriting or push has been performed. **Do not treat this branch as remediation of historical exposure.** Also confirm source/project license, asset-manifest/metadata redistribution and any remaining personal-data publication approval.

## Current repository integration

The original catalog remains at repository-root data/images/tshirt, not backend/data/images. backend/src/asset_paths.py resolves unchanged Qdrant data/images/... paths from repository root and all other relative file inputs from backend root. API StaticFiles mounts the same real root once, retaining /images/tshirt/... URLs. No image symlink or duplicate directory is used. Ingestion, image-query and evaluation/validation file helpers share this compatibility convention; algorithms and payloads are unchanged. The backend schema and SKILL stay under backend.

The integrated branch has 263 passing automated checks (103 frontend + 160 backend). Real browser image-component checks used saved evaluation products and real root JPEGs, not live retrieval. Current connected GitHub account has pull=true/push=false; collaborator-permission detail request also returned 403. No push or PR can be claimed. Have the owner grant Write access or have an authorized teammate fetch the validated local feature branch; see INTEGRATION_REPORT.md.

Optional legacy validation scripts may write generated diagnostics into backend/validation (placeholder included; outputs ignored). Some historical hybrid script defaults reference omitted Gradio demo assets: pass explicit existing catalog image arguments instead. These scripts are not startup tasks or authorization for live provider calls.
