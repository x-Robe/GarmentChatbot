# Architecture

## Transport and entry points

The build-free frontend sends JSON to POST /api/chat and POST /api/image-search/continue, and multipart image/mode/optional query to POST /api/image-search. GET /api/health is cheap liveness. GET /images/... maps only to data/images. One lazy agent/ProductSearch per process is protected by a shared lock. There is no backend account/history database.

## Text search

GarmentAgent reads backend/SKILL.md and the data/samples/sample_tshirt_schema.json. An OpenAI-compatible Responses tool call plans intent, resolved query, relation to context, strategy and requested quantity. The application validates the plan and enforces a manual Exact/Similar override for search. Auto can select Exact, Similar or Both; informational/refused/clarification paths may use no retrieval.

Structured attribute extraction is separate from product retrieval. Exact uses supported structured Qdrant metadata filters and FashionCLIP text-vector ranking without silent broadening. Similar uses FashionCLIP text embedding retrieval without exact metadata constraints. Both executes the two existing branches, deduplicates using product_id then point_id with Exact precedence, preserves each tool's order, applies the existing Similar score-prefix policy and allocates available slots without inventing filler. Retrieval scores are not probabilities.

## Image and image-plus-text

Upload decoding accepts JPEG/PNG/WebP, at most 10 MiB and 20 million pixels. The current FashionCLIP image vector and zero-shot image attributes are used. Auto retains the existing attribute-guided candidate/relaxation policy. Exact uses the existing strongest reliable inferred attributes plus mandatory supported explicit changes, with strict metadata filtering and no silent relaxation; no reliable constraints can yield clarification. Similar uses the original image vector and only explicit supported text constraints. Optional text is extracted into structured overrides, not used to generate an edited image or a new fusion model.

The response contains real products, mode/strategy diagnostics, original image analysis and a versioned 512-number normalized reference embedding. Upload Files/thumbnails are session-only; no permanent original-image upload store is added.

## History, continuation and result counts

The frontend stores conversations, products, active_search, reference_image and a local reference revision in garment.conversations.v1 localStorage. Reference vectors are not inserted into textual LLM context. A text-only image marker and user-authored modifications retain routing meaning. Saved image retries check reference revision to avoid using a replacement image silently. Incompatible references ask for re-upload.

Bounded text history includes assistant closings, excludes failed/pending/current turns and removes technical paths. Server defaults are 200 messages/60,000 characters, independently bounded; frontend has matching configurable defaults. Refinements use the current manual mode and update explicit constraints; “more” freezes the previous effective strategy/conditions even if the selector changed. Seen product/point IDs prevent repeated displayed products; the existing bounded adaptive exclusion fallback handles a known index compatibility case without reranking.

The LLM/extractor plans natural-language quantities; code validates and caps them to 1–8 (default 8). The frontend four-card carousel only pages already-returned data. A “show more” conversational request performs retrieval; carousel arrows do not.

## Voice and presentation

SpeechRecognition/webkitSpeechRecognition feeds the same selected-mode submission path as typing. Only one completed transcript is submitted; interim/cancelled sessions are not. speechSynthesis supports manual read-aloud and an opt-in Voice Mode for voice-submitted replies. Playback stops/cancels recognition appropriately; there is no automatic microphone re-listening loop. Voice state/audio is not persisted.

Attachments keep filename/size/preview metadata separate from authored text. New image-only messages have no redundant text bubble; legacy technical prefixes are removed for display only when corroborated by the original request/attachment. Products preserve real backend metadata and API image URLs. No text-to-product parsing or fictional product fields are introduced.

## External state and release scope

LLM provider, Qdrant data and model cache remain external; existing catalog JPEGs remain at repository root. Evaluation scripts reuse existing retrieval but are outside serving startup. Their release-only ROOT adjustment points to backend/; production source, prompts, FashionCLIP, ranking, filtering and mode policies are unchanged. The legacy Gradio mock application is omitted.
