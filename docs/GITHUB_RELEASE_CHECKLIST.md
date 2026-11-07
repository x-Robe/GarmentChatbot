> Historical clean-release staging evidence. The current integrated repository retains its original Git history and root catalog. For current checks, paths, source differences and access blocker, read [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md).

# GitHub Release Readiness Checklist

Prepared 2026-10-30. **Public GitHub publication: NOT READY.** The clean source staging deliverable is prepared and validated as described below; credential exposure and owner/licensing/provisioning decisions remain. No commit, push, deployment, Git-history rewrite, credential rotation or live paid retrieval was performed.

## Location and package boundaries

The directory is named GarmentChatbot-GitHub-Release and is a sibling of the original workspace, outside both original repositories. The exact absolute delivery location is provided in the task completion message; personal machine paths are deliberately absent from these public-facing documents. Both active frontend/ and backend/ are included. No .git directory was initialized here or copied from either original repository.

Source files copied from an allowlist: **82** (some intentionally adjusted in this release). Separately authored files include root README/.gitignore/.env.example, handover/architecture/deployment/dataset/version/change notes, asset/copy manifests, evaluation reproduction notes and fresh test evidence. Final file count: **102**. Total logical size: **1,107,594 bytes (1.056 MiB)**. All files are text or the empty placeholder; no catalog/model binaries are bundled.

## Completed checks

- [x] Current browser frontend, shared typed/voice request path, all modes, image continuation, history, pagination, count and product UI source included.
- [x] Current FastAPI, agent, SKILL.md, all src modules including offline ingestion helpers, schema, product lists and selected scripts included.
- [x] Required backend/data/images/tshirt/.gitkeep preserves the static-file mount directory.
- [x] 39 checked frontend runtime/tests + backend runtime/SKILL files are byte-identical to original. No search/AI behavior changes.
- [x] Relevant isolated tests included; import-time legacy live smoke tests and Gradio mock prototype excluded.
- [x] Root ignore tested with 12 excluded and 8 trackable cases, including the schema, source and .gitkeep. Disposable Git metadata for this check was outside the release/originals; no add/commit/push.
- [x] Safe template uses real variable names, private backend/.env location and mutually alternative provider configuration. No working keys or cluster URLs copied.
- [x] Frontend tests executed from release: **103 pass, 0 fail**.
- [x] Backend isolated suite executed from release: **156 pass, 0 fail**. Initial 1-failure catalog-dependent fixture was corrected only in the copied test using an owned temporary JPEG, then full suite rerun.
- [x] All 16 backend/module imports resolve using available development dependencies; schema/SKILL/image directory present.
- [x] Temporary release-only HTTP server returned /api/health **200 / {"status":"ok"}** with agent/model still uninitialized; server stopped afterward. Original development services unchanged.
- [x] Existing calculator recomputed saved release metrics without model/service calls: primary P@5 **0.6600 (10/10)**, T2 **0.0000**. All 57 relevance values/notes/rank keys and all saved ranking/run/manifest data preserved. Image ablation remains v1 **0.7333**, v2 **0.6667**.
- [x] Reviewer identity pseudonymized; original identity mapping not included. T2 acknowledgement is explicitly project-owner-confirmation, sourced from the release task rather than an invented named reviewer.
- [x] Catalog manifest: 1,993 filename/byte/SHA-256 entries, 378,919,404 bytes of expected source assets; seven missing IDs 357–363 recorded. Zero catalog images copied.
- [x] Scan includes source/docs/CSV/JSON/logs against current + historical credential values, key/auth-URL patterns, private cluster URL, personal absolute paths, original reviewer identity, embedded base64 images, forbidden directories and unexpected large binaries: **no findings** in the final scan.
- [x] Existing original file bytes/inventory checked: **2,177 noncache/non-Git/non-venv files unchanged**. Both repositories' status, branch, HEAD, remotes and tracked-index listing unchanged.

Evidence: [frontend log](validation/frontend-tests.txt), [backend log](validation/backend-tests.txt), [release checks](validation/release-validation.json), [smoke check](validation/release-smoke.json), [security scan](validation/release-security.json), [copied-file hashes](RELEASE_FILE_MANIFEST.json), [intentional differences](RELEASE_CHANGES.md).

## Publication / hosting blockers

- [ ] Owners revoke/rotate previously exposed Qdrant/HF/provider credentials and decide remediation for the old GitHub history, clones and forks. This directory does not erase old exposure; do not reuse old history blindly.
- [ ] Team approves project/source license and public release; catalog rights and metadata/checksum-manifest publication are reviewed. No license or asset download URL is invented.
- [ ] Decide authorized catalog asset supply and provision files to backend/data/images. Product cards cannot display omitted JPEGs. Qdrant does not hold their binaries.
- [ ] Supply compatible populated Qdrant, approved model/cache and fresh private configuration. No cloud collection change/re-ingestion was performed.
- [ ] Validate a genuinely fresh environment installation/resolution and record approved dependency/model revisions; current requirements are preserved and known tested versions documented, not a verified lock.
- [ ] Hosting teammate selects platform/capacity/process strategy, configures HTTPS/API origin/CORS/secrets/assets, and implements approved access/cost controls, rate limits and monitoring. Nothing deployed.
- [ ] With assets/services and authorization, run full target-host E2E, real microphone/audio, image serving and reference persistence checks; measure memory/latency/concurrency/readiness. Liveness 200 is not readiness.
- [ ] Replace contributor placeholder only with approved names/student IDs; confirm the minimized human-label release meets team publication expectations.

## Evidence limits

The existing development Python/Node runtimes were reused; no venv, HF cache or weights were copied, and no fresh-install claim is made. Models/LLM are mocked in isolated tests; some Qdrant tests use a local in-memory fixture only. No hosted-Qdrant or paid-provider search ran during staging. Historical real API/browser reports describe their original stages, not this release check. The seven missing images, dataset rights, live service credentials and production configuration remain external dependencies.

Security scanning is evidence against checked values/patterns, not a proof that every possible unknown secret format is detectable. No remote state/token validity was queried. Source snapshot proof excludes generated caches, virtual environment and Git object internals, with both Git logical states separately compared.

## Explicit answers

| Question | Answer |
|---|---|
| Q1 Both active frontend/backend included? | Yes. |
| Q2 Real keys/populated .env/Credentials excluded? | Yes; only .env.example placeholders remain. |
| Q3 Both original Git histories excluded? | Yes; no release .git. |
| Q4 Actual runtime source/schema included? | Yes; imports and required paths checked. |
| Q5 Product images covered by an asset plan? | Yes; paths/checksums/provisioning documented, no unauthorized copies. |
| Q6 Can a teammate understand/setup from docs? | Practical README/HANDOVER supplied; isolated/source checks passed. Full setup still requires authorized assets/services/private config and a fresh-install validation. |
| Q7 Original files/branches/remotes preserved? | Yes; 2,177 file hashes/inventory and both Git states matched. |
| Q8 Tests run against release? | Yes: frontend 103, backend 156; not a fresh environment or live retrieval. |
| Q9 Anything committed/pushed/deployed? | No. |
| Q10 Ready for public GitHub publication? | No; unresolved security/rights/provisioning/approval checks above. |

## Complete final release tree

```text
GarmentChatbot-GitHub-Release/
├── backend/
│   ├── data/
│   │   ├── images/
│   │   │   └── tshirt/
│   │   │       └── .gitkeep
│   │   ├── samples/
│   │   │   └── sample_tshirt_schema.json
│   │   ├── products.csv
│   │   └── products.json
│   ├── other_tools/
│   │   ├── convert_to_json.py
│   │   └── image_metadata.py
│   ├── scripts/
│   │   ├── validate_hybrid_image_search.py
│   │   ├── validate_image_context.py
│   │   ├── validate_image_search.py
│   │   ├── validate_image_text.py
│   │   ├── validate_pagination.py
│   │   └── validate_result_count.py
│   ├── src/
│   │   ├── __init__.py
│   │   ├── conversation_context.py
│   │   ├── extract_embeding.py
│   │   ├── hybrid_image_search.py
│   │   ├── image_messages.py
│   │   ├── image_reference.py
│   │   ├── image_upload.py
│   │   ├── ingest_product.py
│   │   ├── json_size_limit.py
│   │   ├── product_search.py
│   │   ├── qdrant_connection.py
│   │   ├── query_attribute_extractor.py
│   │   ├── result_count.py
│   │   ├── search_state.py
│   │   └── zero_shot_classifier.py
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_chatbot_results.py
│   │   ├── test_extraction_robustness.py
│   │   ├── test_hybrid_image_search.py
│   │   ├── test_image_api.py
│   │   ├── test_image_context.py
│   │   ├── test_image_search.py
│   │   ├── test_image_text.py
│   │   ├── test_pagination.py
│   │   ├── test_result_count.py
│   │   └── test_unified_modes.py
│   ├── API.md
│   ├── SKILL.md
│   ├── api.py
│   ├── chatbot.py
│   ├── requirements-api-test.txt
│   └── requirements.txt
├── docs/
│   ├── validation/
│   │   ├── DYNAMIC_RESULT_COUNT.md
│   │   ├── FRONTEND_UI_CLEANUP.md
│   │   ├── FULL_CONTEXT_PAGINATION.md
│   │   ├── PERSISTENT_IMAGE_CONTEXT.md
│   │   ├── UNIFIED_SEARCH_MODES.md
│   │   ├── VOICE_VALIDATION.md
│   │   ├── backend-tests.txt
│   │   ├── frontend-tests.txt
│   │   ├── release-security.json
│   │   ├── release-smoke.json
│   │   └── release-validation.json
│   ├── ARCHITECTURE.md
│   ├── CATALOG_ASSET_MANIFEST.csv
│   ├── CATALOG_ASSET_SUMMARY.json
│   ├── DATASET_ASSETS.md
│   ├── DEPLOYMENT_NOTES.md
│   ├── GITHUB_RELEASE_CHECKLIST.md
│   ├── HANDOVER.md
│   ├── RELEASE_CHANGES.md
│   ├── RELEASE_FILE_MANIFEST.json
│   └── TESTED_VERSIONS.md
├── evaluation/
│   ├── EVALUATION_REPORT.md
│   ├── README.md
│   ├── ablation.csv
│   ├── annotations.csv
│   ├── calculate_metrics.py
│   ├── failure_cases.md
│   ├── metrics.csv
│   ├── queries.csv
│   ├── results.csv
│   ├── run_evaluation.py
│   ├── run_manifest.json
│   ├── runs.csv
│   └── summary.csv
├── frontend/
│   ├── app.js
│   ├── config.js
│   ├── context.js
│   ├── context.test.js
│   ├── image-context.test.js
│   ├── image-search.test.js
│   ├── index.html
│   ├── package.json
│   ├── pagination.test.js
│   ├── presentation.js
│   ├── presentation.test.js
│   ├── products.js
│   ├── products.test.js
│   ├── search.js
│   ├── search.test.js
│   ├── state.js
│   ├── state.test.js
│   ├── styles.css
│   ├── voice-app.test.js
│   ├── voice.js
│   └── voice.test.js
├── .env.example
├── .gitignore
└── README.md
```
