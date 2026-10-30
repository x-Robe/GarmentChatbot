> Historical clean-release staging evidence. The current integrated repository retains its original Git history and root catalog. For current checks, paths, source differences and access blocker, read [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md).

# Release-only Changes and Exclusions

The original workspace is untouched. Source files were copied from an explicit allowlist; no whole-repository copy-and-delete operation was used. No Git metadata, populated .env, Credentials, venv/cache, catalog image or model weight was copied. No Git repository was initialized inside the release.

## Runtime code

All 39 checked frontend runtime/tests + backend api.py/chatbot.py/SKILL.md/src modules are byte-identical to their original sources. No FashionCLIP, filters, ranking, extraction prompts, SKILL instructions, modes or voice behavior was redesigned. src/extract_embeding.py retains its exact name. Ingestion helpers, six selected validation scripts and CSV/JSON conversion tools remain for reproducibility; running them is not a deployment prerequisite or authorization to write Qdrant.

## Intentional differences

- evaluation/run_evaluation.py: only backend import/image ROOT and its command docstring adjusted for root-level evaluation/ beside backend/. No retrieval algorithm/exclusion policy changed.
- backend/tests/test_api.py: static-image/CORS test uses an owned ephemeral 2x2 JPEG mounted on the actual static route. The first release test run had 155 passing/1 failing because a catalog image was absent; after making the fixture asset-independent all 156 pass. No product image is bundled to make a test pass.
- evaluation/annotations.csv: reviewer pseudonym only; all 57 keys, relevance values and notes preserved. Identity mapping is not shipped.
- evaluation/queries.csv: T2 reviewed_by acknowledges the explicit project-owner confirmation. No personal name was invented. metrics/summary were recomputed using the existing calculator; ablation data and ranked outputs remain identical.
- evaluation report/failure documentation: T2 completed, primary mean 0.6600/10 queries, reviewer privacy and reproduction paths clarified. This does not claim a new live evaluation.
- selected historical validation Markdown: personal absolute paths removed, identities pseudonymized where applicable, omitted images/links labeled, and original-stage evidence boundaries made explicit. Fresh release test logs are separate.
- new README, environment template, ignore rules, handover/architecture/deployment/assets/version notes and this checklist/manifest: documentation and packaging only.

## Copied files with changed final hashes

- `backend/API.md`
- `backend/tests/test_api.py`
- `evaluation/EVALUATION_REPORT.md`
- `evaluation/queries.csv`
- `evaluation/metrics.csv`
- `evaluation/summary.csv`
- `evaluation/failure_cases.md`
- `evaluation/run_evaluation.py`
- `evaluation/annotations.csv`
- `docs/validation/UNIFIED_SEARCH_MODES.md`
- `docs/validation/FRONTEND_UI_CLEANUP.md`
- `docs/validation/FULL_CONTEXT_PAGINATION.md`
- `docs/validation/PERSISTENT_IMAGE_CONTEXT.md`
- `docs/validation/DYNAMIC_RESULT_COUNT.md`
- `docs/validation/VOICE_VALIDATION.md`

Full before/after hashes and original relative paths are in RELEASE_FILE_MANIFEST.json.

## Excluded

Both .git histories; .env/Credentials; .venv and all bytecode/caches/IDE/OS metadata; local model weights/HF cache; 1,993 catalog JPEGs pending rights review; large base64 galleries, private screenshots/raw debug results and obsolete stage reports; old Gradio app.py/ui/services/demo assets/requirements; unused legacy models/fashion_clip.py; sample_products.json; import-time live smoke tests. Their original files were not deleted.

Included anonymized annotations preserve evidence without publishing the original reviewer identity. No nonempty annotation notes existed in the source snapshot. Catalog path/hash metadata is provided for authorized provisioning only; image rights are still unresolved. No original audit reports containing developer machine paths were copied wholesale.
