# GarmentChatbot

A COMP4431 group project for finding T-shirt design references using text, images and conversational refinements. The active application is the browser frontend plus FastAPI backend in this release. The earlier Gradio/mock prototype is **not included**.

**Integration status:** the completed application is integrated on a feature branch, retaining all **1,993 existing root-level catalog JPEGs without relocation or duplication**. Model weights, Qdrant data and private credentials are external dependencies; Hosting is not complete. Existing credential exposure in Git history requires owner rotation/remediation. See [integration report](docs/INTEGRATION_REPORT.md).

## Features and stack

- Text, image and image-plus-text retrieval with unified Auto / Exact / Similar controls.
- FashionCLIP embeddings, structured Qdrant filters and an OpenAI-compatible LLM for planning/attribute extraction.
- Bounded full conversational history, persistent image-reference embeddings in browser localStorage, refinements and non-repeating pagination.
- Natural-language result counts from 1 to 8, four-card carousel pages and product details.
- Browser speech recognition, manual speech synthesis and opt-in automatic replies for voice submissions.

Stack: HTML/CSS/JavaScript ES modules; FastAPI, Pydantic, Uvicorn; PyTorch, Transformers, sentence-transformers (MiniLM), NumPy, Pillow; Qdrant client; OpenAI-compatible SDK. No frontend build step or JavaScript dependencies.

```text
Frontend → FastAPI → LLM planning + FashionCLIP → Qdrant → structured products
                         Product JPEGs ← root data/images → /images
```

## Structure

```text
frontend/             Active website and Node unit tests
backend/api.py        HTTP entry point; backend/chatbot.py is agent/CLI
backend/src/          Retrieval, extraction, state, upload and ingestion helpers
backend/SKILL.md      Required runtime instructions, not optional documentation
backend/data/         Current product lists and required runtime schema
data/images/tshirt/   Existing repository JPEGs (preserved, not duplicated)
evaluation/           Saved study, anonymized human labels and reproduction scripts
docs/                 Handover, architecture, deployment, assets and release evidence
.env.example          Template; private configuration belongs in backend/.env
```

## Local setup

Commands assume your shell starts in this release directory. Use Python 3.12 (development runtime: 3.12.14) and Node 24 (development runtime: 24.22.1). Other platforms/versions have not been validated. Do not use the original Gradio requirements or copy a developer virtual environment.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-api-test.txt
cp .env.example backend/.env
```

Fill in **your own approved private values** in `backend/.env`; do not commit it. The template defaults to a compatible provider via POE_API + POE_URL + OPENAI_MODEL. For standard SDK defaults, remove/unset POE_API and POE_URL, and set OPENAI_API_KEY instead; empty strings are not the same as unset variables. You do not need both key styles. Configure QDRANT_URL, QDRANT_COLLECTION and, if required by that server, QDRANT_API. Set CLIP_MODEL to the model used for ingestion. The saved evaluation used `patrickjohncyh/fashion-clip`; current collection compatibility must be confirmed by its owner.

The existing catalog files are retained under root `data/images/`; confirm hosting/distribution authorization. Before full use, supply a compatible populated Qdrant collection, private configuration and approved FashionCLIP/MiniLM model downloads or cache. No new dataset download or copy was used for this integration. See [dataset assets](docs/DATASET_ASSETS.md) and [tested versions](docs/TESTED_VERSIONS.md). Requirements are preserved, not a validated cross-platform lock.

### Start the two development services

```sh
# Terminal 1, from the release root (activate your environment first)
cd backend
uvicorn api:app --reload --host 127.0.0.1 --port 8001

# Terminal 2, from the release root
python3 -m http.server 8000 --bind 127.0.0.1 --directory frontend
```

Open http://127.0.0.1:8000/. `frontend/config.js` contains the public API base URL; `CORS_ORIGINS` configures the backend allowlist. Never put keys in JavaScript. CLI: from `backend/`, run `python chatbot.py`.

```sh
curl http://127.0.0.1:8001/api/health
```

Health is liveness only. It can return 200 with no credentials, model or catalog JPEGs. The existing JPEGs are served from root data/images; missing product images return 404 and no placeholder products are invented. These development commands are not a production deployment configuration.

## Isolated tests

From release root:

```sh
node --test frontend/*.test.js
cd backend
CLIP_MODEL=patrickjohncyh/fashion-clip PYTHONPATH=.:tests python -B -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count test_unified_modes test_repository_layout
```

The nonsecret CLIP_MODEL value lets offline reference validators construct test data; no weights are downloaded by the isolated suites. Install both requirements files in your environment. The lightweight API-test requirements alone do not supply all current imports. Do not substitute live smoke scripts for unit tests.

Integrated-branch tests: **103 frontend + 160 backend passed** using the existing development Python packages/Node runtime, not a newly installed environment. The static-image test now creates an owned temporary 2×2 JPEG; no catalog asset is needed. Models/LLM are mocked; some tests use in-memory Qdrant, not the hosted collection. Four additional layout tests check catalog hashes, real HTTP serving and path resolution. See [validation evidence](docs/INTEGRATION_REPORT.md).

## Evaluation

The saved study has ten primary queries and three additional image-v1 runs, with 57 human relevance labels. In this release only, the project owner's explicit T2 zero-result confirmation is recorded; all existing relevance labels and ranked results are preserved. Reviewers are pseudonymized. Fixed-denominator mean P@5 is **0.6600 across all 10 primary queries**; result-set fill rate is 80%. Image ablation remains v1 **0.7333**, v2 **0.6667** over three references. This small study does not show universal improvement or validate every later unified-mode combination.

```sh
# From release root; writes only evaluation metric CSVs, no model/provider calls
python evaluation/calculate_metrics.py
```

See [evaluation report](evaluation/EVALUATION_REPORT.md) and [reproduction notes](evaluation/README.md). Live retrieval is not run automatically and may incur cost; use a new output directory and obtain authorization.

## Limitations and handover

Model-derived attributes are imperfect and similarity scores are not relevance probabilities. Narrow exact queries may return fewer products. The 2,000-record asset lists reference only 1,993 available JPEGs; IDs 357–363 are missing. The existing public catalog remains unchanged; redistribution/hosting rights and project licensing still need owner review.

Conversations are browser-origin-local, with no account/backend persistence or cross-device sync. Original uploads/thumbnails are not persisted; stored compatible embeddings support continuation. Browser speech depends on permissions, voices, browser/service compatibility and HTTPS in hosting. Real microphone/audio acceptance on the final host is pending. Production memory, latency, access controls, rate limits, origins and platform are not yet validated or configured.

[Hosting handover](docs/HANDOVER.md) · [Architecture](docs/ARCHITECTURE.md) · [Deployment notes](docs/DEPLOYMENT_NOTES.md) · [Integration differences](docs/INTEGRATION_REPORT.md)

## Contributors

**Placeholder — replace only with approved member names and student IDs.** No identities are invented in this release.
