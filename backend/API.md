# Garment chat API

From this directory (Python 3.10+):

```sh
python -m pip install -r requirements.txt
uvicorn api:app --reload --host 127.0.0.1 --port 8001
```

The existing `.env`, provider, model and Qdrant settings are reused. No credentials
belong in frontend config. `python chatbot.py` still works and now defaults to Auto.
In this development environment the existing HF token is expired; prefix the
command with `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` to load the same public model
anonymously, without modifying model configuration.

## Contract

- `GET /api/health`: `{"status":"ok"}`, cheap process liveness, no model loading.
- `POST /api/chat`: `{"query":"Korean style t-shirt","mode":"auto"}`.
- Query must be a nonblank string. Modes: `auto` (default), `exact`, `similar`.
  Legacy `default` is normalized to `auto`, including direct agent/CLI calls.

Response (product entries below are omitted for brevity, not invented):

```json
{
  "text": "I found 8 visually similar designs for inspiration.",
  "closing_text": "...",
  "response_id": "...",
  "intent": "search",
  "resolved_query": "Korean style t-shirt",
  "search_strategy": "similar",
  "products": [],
  "search_results": {"exact": [], "similar": []}
}
```

`text` remains the backwards-compatible intro/answer. `closing_text` is a separate
1–2 sentence message after the cards, empty for no results/non-search. The frontend
never splits model prose. `intent` is search/informational/unrelated/clarification;
`search_strategy` is exact/similar/both/none. `none` means no retrieval was requested.
Strategy records the selected plan even when a branch fails or returns zero.

`products` is the authoritative, selected display list (0–8). Entries preserve
ProductSearch's point_id, product_id, similarity_score, image_path, attributes and
label_matches, plus copied match_type. `search_results` preserves raw successful
candidate results by actual tool; it may include duplicates/trimmed candidates.
Do not render or summarize candidate lists as extra cards.

## Routing and domain policy

The same existing LLM makes a required `plan_request` tool call with intent, route
and resolved query; malformed plans fail closed without product search. No chain-of-thought
is requested or returned. SKILL.md supplies semantic intent examples, not keyword
blacklists. Auto selects Exact for concrete supported attributes, Similar for
open-ended aesthetics, Both for constraints plus inspiration.

The application validates the plan and forces a manual Exact/Similar selection,
even if the planner returns another route. It dispatches existing extraction once
and the existing search tools once per selected branch. Search limits are set by
code, not the LLM. Both is an intentional route, never an implicit fallback.
Self-contained query text is preserved; dependent queries use the resolved
meaning. Extracted attributes use the existing normalization unchanged. No supported attributes means no unrestricted Exact query.
Similar has no exact filters. FashionCLIP, embeddings, Qdrant, filters, dataset and
each search's ranking implementation are untouched.

Informational fashion questions go to a short answer with no extraction or search.
Clearly unrelated requests get a concise application-generated domain refusal:
no extraction, Qdrant call or general-purpose answer generation. Semantic LLM
classification is not a formal guarantee against all adversarial/ambiguous inputs.
Each backend request remains stateless; the caller may supply the bounded text context described below.

## Deterministic selection

1. Exact: only existing filtered results; no score cutoff or filler, preserve order.
2. Similar: retain the original ranked prefix while score >= 85% of the first
   numeric score. Stop at a lower score, nonpositive score or nonfinite score.
   Missing scores alone are not evidence to reject. No sorting or new retrieval.
3. Deduplicate Exact first, using product_id then point_id; normalize identifiers
   to strings in separate namespaces. Exact wins. No-ID entries are not guessed.
4. Both: reserve min(2, distinct eligible Similar count) of 8 slots for Similar.
   Fill remaining slots with Exact; if Exact has fewer, Similar gets the remaining
   capacity. If no distinct Similar survives, Exact can use all 8. No filler and
   no new searches to meet the allocation.

Five real semantic queries were audited before choosing the 85% rule. Scores in
rank order (same query prompt/embedding/Qdrant, filters={}, limit=8):

| Query | Top eight scores |
|---|---|
| Korean style t-shirt | .3700, .3403, .3399, .3398, .3356, .3335, .3333, .3325 |
| Japanese streetwear | .3657, .3540, .3539, .3498, .3481, .3473, .3420, .3419 |
| white minimalist t-shirt | .3634, .3534, .3523, .3509, .3490, .3485, .3470, .3450 |
| cyberpunk oversized t-shirt | .3652, .3634, .3600, .3524, .3483, .3483, .3482, .3463 |
| vintage graphic t-shirt | .3450, .3397, .3394, .3382, .3329, .3327, .3320, .3315 |

Observed top-to-tail drop is 3.9–10.1%. A 15% relative drop leaves a conservative
margin and retains all five valid broad searches. This is a provisional tail rule,
not a calibrated relevance probability. With no labeled relevance evidence we do
not impose an absolute CLIP cutoff: uniformly weak positive scores can still pass.
Do not misrepresent this rule as a guarantee of semantic quality. Narrow Exact
queries naturally return fewer results. Automated fixtures cover clear score-tail
trimming and zero/nonfinite scores without paid calls.

The intro count is constructed from `products`. Only selected attributes (no raw
candidates, IDs or scores) reach the final LLM writer for the closing. Informational
answers and closings use structured JSON, following the Responses structured-output
and function-calling contracts; the same compatible provider is retained.
References: [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses),
[function calling](https://developers.openai.com/api/docs/guides/function-calling).

## Errors, reuse and CORS

One lazy GarmentAgent per process, protected by a lock. Health/validation need no
model. HTTP 422: safe validation JSON. HTTP 503: incomplete config/initialization.
HTTP 502: escaped agent/provider or invalid structured response. Error responses
never include exception text, credentials or traces. Individual search-tool errors
are caught: successful branches remain, failed branches stay empty, prose explains
partial/unavailable search. Only exception class is logged, not its message.

Explicit localhost/127.0.0.1 origins on ports 3000, 5173 and 8000. Change
comma-separated `CORS_ORIGINS` and restart. GET/POST, Content-Type, no credentials.

## Images

Integrated layout: `src/asset_paths.py` mounts repository-root `data/images/`, not `backend/data/images/`. Unchanged Qdrant paths `data/images/tshirt/<id>.jpg` resolve against repository root, with unchanged `/images/tshirt/...` public URLs. The existing catalog is not duplicated; schema/SKILL remain backend-relative.

Unchanged: only data/images is mounted at `/images`. API adds copied root-relative
image_url to all three product lists. Frontend resolves it against API_BASE_URL.
Existing image_path stays unchanged. Invalid/outside-root/symlink-escaping paths
get null; missing files return 404. Repository and secrets are not served.

## Checks

```sh
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:8001/api/chat -H 'Content-Type: application/json' \
  -d '{"query":"Korean style t-shirt","mode":"auto"}'
python -m unittest discover -s tests -p test_api.py -v
python -m unittest discover -s tests -p test_chatbot_results.py -v
python -m unittest discover -s tests -p test_extraction_robustness.py -v
```

These targeted tests mock model/tool boundaries; other legacy test scripts may
contact external services. See AUTO_VALIDATION.md for this change's real E2E audit.


## Lightweight conversation context

Optional request extension (old query/mode-only callers still work):

```json
{
  "query": "make them darker",
  "mode": "auto",
  "context": [
    {"role": "user", "text": "show me Japanese streetwear t-shirts"},
    {"role": "assistant", "text": "Here are some relaxed designs for inspiration."}
  ]
}
```

The frontend builds the full normal textual history in the active chat, bounded
by 200 messages, 60,000 total characters and 10,000 per message by default. It combines
assistant text and closing_text, skips failed/interrupted/pending turns, and does
not send products, attachments, IDs or image fields. Old image markup, links,
local paths and explicit product/point metadata lines are stripped. The API rejects
extra context fields, system roles, oversized messages/windows and invalid types
with safe 422 JSON. The direct agent validates/sanitizes the same boundary.

The existing plan_request LLM call sees current_query plus untrusted recent text.
It returns intent, strategy and a standalone resolved_query; there is no added
model or extra resolution call. Dependent follow-ups inherit the recent relevant
topic; replacements such as white supersede old colors. Fresh questions/requests
stay independent. Prior fashion context cannot authorize unrelated questions or
change the interface mode. Ambiguous references produce intent clarification,
strategy none, a brief question and no retrieval.

For contextual searches, the resolved query reaches the unchanged extractor and
both existing search functions. For no-context calls and non-search intents, the
original query is retained. The additive resolved_query response field is for
inspection, not shown as conversation prose. No reasoning is returned. New request
context is snapshotted for retry; legacy retries derive it only from preceding
turns, never from themselves or later messages. New Chat starts with no context.
Old localStorage history still uses available text without requiring new fields.
There is no server-side conversation store, session database or persistent memory.

Normal intros/closings avoid implementation terminology; the intro count still
comes directly from products. Explicit system questions remain informational and
may discuss actual filters, FashionCLIP/Qdrant ranking and mode policy accurately.
Historical messages keep their originally saved wording; they are not rewritten.
The 85% selection rule, Both allocation, ranking and all retrieval code are unchanged.
See CONTEXT_VALIDATION.md for tests and real sequential browser checks.


## Image + text attribute overrides (v1)

`POST /api/image-search` accepts multipart `image`, `limit` (1–8, default 8),
and optional `query` (up to 2000 characters). Missing/blank query uses unchanged,
LLM-free Image Search v2. Text-only `/api/chat` is unchanged.

```sh
curl -s http://127.0.0.1:8001/api/image-search \
  -F 'image=@data/images/tshirt/646.jpg' \
  -F 'query=make it black and short sleeve' -F 'limit=8'
```

Mixed input reuses QueryAttributeExtractor's configured client/model via its new
`extract_image_overrides` method. It uses the actual ingestion vocabulary for
colors, patterns, neckline, sleeve, style, buttons. Explicit text replaces the
image's entire category. Across categories conditions are AND; alternatives
within one category use the existing MatchAny OR. Buttons remain Boolean.

Explicit constraints NEVER relax to meet the candidate budget. Up to two reliable
image guesses may guide the candidate pool using unchanged v2 margins and 4×limit
heuristic; only these guesses may relax. One image embedding supplies analysis
and Qdrant cosine ranking. No query-text embedding or rank fusion.

Required response fields remain `text`, `search_type: image`, `products`,
`closing_text`. Optional fields: `image_analysis` (including `filters_used`),
`text_analysis` (`intent`, `overrides`, `unsupported_text`), `resolved_attributes`,
`search_strategy`, `intent`. Resolved attributes include uncertain inherited
image guesses, NOT a claim all were filtered; `filters_used` is authoritative.

Unsupported-only/ambiguous/unrelated requests return 200 with an explanation and
empty products, without retrieval. Partial support applies supported changes and
names unapplied text. Clear no-op requests use v2. Failed parsing returns safe
502, never silently discards text. Existing upload validation remains; overlong
query returns safe 422. No vectors, raw model replies, or diagnostic trace in API.

See historical implementation/validation (stage report omitted; see ../docs/RELEASE_CHANGES.md) and real
comparison JSON (historical debug artifact omitted).


## Full text history and non-repeating text results (2026-10-23)

`POST /api/chat` keeps all prior fields and accepts optional `active_search`.
Normal `context` includes all previous conversation text (user/assistant only,
closing_text included), never product objects, images, vectors or tool traces.
The current query appears once, outside context.

The frontend defaults in `frontend/config.js::CONTEXT_LIMITS` are 200 messages,
60,000 total characters, and 10,000 per message. The backend independently uses
`MAX_CONTEXT_MESSAGES` (default 200) and `MAX_CONTEXT_CHARS` (default 60000) from
`.env`/environment; it retains recent text deterministically, including a suffix
of the oldest retained message if needed. Hard HTTP/direct-agent validation rejects
more than 1000 records or a record over 10000 characters. No summarization.

Example compact state (shown IDs are illustrative, not a new catalog):

```json
{
  "search_type": "text",
  "resolved_query": "black oversized t-shirts",
  "mode": "auto",
  "search_strategy": "exact",
  "attributes": {"category": "t-shirt", "colors": ["black"], "style": ["oversized"]},
  "shown_product_ids": ["14", "271"],
  "shown_point_ids": []
}
```

State permits only known fields and existing garment attributes; ID lists each
cap at 4096, IDs at 128 characters, query at 2000 characters. Product IDs normalize
to strings; point IDs must be Qdrant UUIDs/unsigned integers. Image state is only
`{"search_type":"image"}` (no image vector or reference binary). Backend response
models may expand defaults for this marker, but no reference data is stored.

The same plan_request call adds `relation_to_context`: new_topic, refinement,
more_results, continuation, fashion_information, out_of_domain, clarification.
Intent remains the original search/informational/unrelated/clarification schema.
IDs and filter objects are not sent to the LLM. New topic keeps the current query;
refinement resolves the query and starts fresh. More results reuses saved query,
mode, strategy AND exact attributes; no fresh extraction and no implicit mode switch.

New optional response fields: active_search, relation_to_context, has_more.
`has_more` is normally null/unknown, never guessed true from page size. It is false
only on a pagination response with empty raw retrieval branches (and an actual
exact predicate if Exact). A nonempty candidate list trimmed by the existing
Similar selection rule is not proof of exhaustion. Errors return safe 502 and
leave the client state unchanged, including partial branch failures in Both.

Product exclusion is attempted with must_not for string and integer payload IDs,
plus HasId for points, preserving positive predicates. The current hosted
collection has integer product_id payloads but only a keyword index; integer
exclusion is rejected. Without changing indexes, this implementation falls back
to server-side known-point exclusions and bounded adaptive vector queries
(8,16,...4096 maximum per branch), rejecting seen product IDs locally across all
points. It stops when enough unseen candidates exist or Qdrant returns fewer than
requested; reaching the scan budget yields an error, not false exhaustion. No
fixed Top24, full unbounded scans, vector changes, or reranking.

Only final displayed products update state. Browser storage is per conversation;
retries snapshot the prior state and failed/aborted responses don't advance it.
Historical retries cannot overwrite a newer active topic. Full request context
is recomputed from stored messages instead of duplicated in localStorage.
Legacy histories restore normally; missing text state is left null rather than
inventing filters/seen IDs. Legacy image searches can safely restore an image
marker. Legacy images without a saved reference require re-upload; new references
support the continuation endpoint below. Independent text queries still work.

See [full implementation and real validation](../docs/validation/FULL_CONTEXT_PAGINATION.md).


## Persistent image continuation (version 1)

`POST /api/image-search` retains multipart input and existing products/analysis.
Successful retrieval additionally returns `image_reference` and `active_search`:

```json
{
  "image_reference": {
    "version": 1,
    "model": "<configured CLIP_MODEL>",
    "dimension": 512,
    "embedding": ["512 finite numbers in the actual response"],
    "image_analysis": {"colors": {"label":"white", "score":0.3,
      "runner_up":"gray", "runner_up_score":0.27, "margin":0.03}}
  },
  "active_search": {"search_type":"image", "text_overrides":{},
    "effective_filters":{}, "shown_product_ids":[], "shown_point_ids":[]}
}
```

The sample above abbreviates analysis/vector for documentation only. Actual
responses contain the full vector and original six-category analysis (or empty
analysis if the existing classifier fallback was used). The original vector and
analysis remain separate from effective current filters and text overrides.
The existing upload encodes exactly once; the response reuses that vector.

`POST /api/image-search/continue` accepts JSON:

```json
{
  "query":"make it long sleeve",
  "mode":"auto",
  "context":[{"role":"user","text":"make it black"}],
  "reference_image":"the complete image_reference object from upload",
  "active_search":"the complete latest active_search object"
}
```

Replace the two descriptive strings with the actual objects. The response keeps
all chat fields and adds optional `search_type`, `continuation`, `text_overrides`,
`image_analysis`. No vector echo on continuation. The same agent plan selects
`image_refinement` / `image_more_results`, independent text search, Q&A or refusal.
Only compact text/overrides reach the LLM. Reference vectors and full predictions
are confined to validation/retrieval. No server reference cache or database.

Refinement extracts current-message changes using the existing extractor, adds
or replaces category values, and removes only explicitly requested categories.
Unmentioned values persist. Removal restores normal original-image inheritance.
A fresh refinement clears seen IDs; pagination preserves exact effective filters
and all current overrides, uses original vector ordering, excludes seen IDs via
the existing bounded fallback, and does not rerun image analysis or encoding.
Explicit requirements remain mandatory. Saved filter selection is frozen for
pagination so later pages cannot silently broaden the active search.

Validation: exact 512 finite numeric elements, nonzero unit norm within 0.001,
version 1 and exact current CLIP_MODEL match; original analysis labels, finite
scores/margins and their consistency; supported override/filter values; bounded
validated IDs. Continuation JSON is capped at 2 MiB before parsing. Invalid or
incompatible context returns safe 422/re-upload guidance; excessive body 413;
retrieval failures 502 without state advancement. Version must be bumped if
preprocessing/embedding semantics change under the same model identifier.

Browser refresh/restart and backend restart work while localStorage survives
and the model/version stays compatible. This is client-owned, untrusted state,
not authentication or a tamper-proof service. Public deployments still need HTTPS,
authentication/rate limiting as appropriate. No raw-vector logs, analytics, URLs,
permanent uploaded files, new models or new collections are introduced.

Validation report: [persistent image context](../docs/validation/PERSISTENT_IMAGE_CONTEXT.md).

## Per-request result quantity

The existing intent resolver now returns nullable `result_count` alongside
`intent`, `relation_to_context`, `resolved_query`, and `search_strategy`. No new
model or resolver call is introduced. English and Chinese explicit quantities
are separated from garment meaning; sizes, years, printed numbers, sleeve
fractions and prices are not quantities. Vague requests use the default.

`src/result_count.py` owns separate `MIN_RESULT_COUNT=1`,
`DEFAULT_RESULT_COUNT=8`, and `MAX_RESULT_COUNT=8` settings. The backend validates
integer types, asks for clarification on zero/negative counts without retrieval,
and caps positive requests above eight with an explanatory sentence.

Chat and image responses add optional `requested_count`, `effective_count`, and
`count_capped` fields. `effective_count` is the allowed result budget, **not** the
actual count: use `products.length`. Invalid nonpositive requests have
`effective_count: null`. Existing product/response fields remain intact.

```json
{"query":"Show me 7 black T-shirts.","mode":"auto"}
```

```json
{
  "requested_count": 7,
  "effective_count": 7,
  "count_capped": false,
  "resolved_query": "black T-shirts",
  "products": []
}
```

The second JSON illustrates only the new metadata, not a real search result.
All returned products still come from the existing retrieval tools. Both mode
uses one combined budget, Exact-first deduplication, and up to two distinct
Similar slots (leaving at least one Exact slot if available). Similar's existing
85% relative tail rule still applies; results need not fill the budget.

`show me N more` reuses the saved search and existing exclusion mechanism. Only
products actually returned in `products` are added to shown IDs. Quantity is
never stored in active search; an unnumbered follow-up returns to default eight.
Message-level diagnostics may be saved without changing the localStorage format.

`POST /api/image-search` retains multipart `limit` (1–8, default eight). An
explicit natural-language quantity takes precedence over that parameter; absent
a quantity, the supplied multipart limit is respected. Image + text extracts
quantity in the existing override call. `/api/image-search/continue` uses the
existing request resolver, saved embedding, effective filters and shown IDs.
No new embeddings, scoring rules or storage architecture are introduced.


## Unified multimodal modes (2026-10-30)

This section supersedes earlier image-mode restrictions above. Text routing is
unchanged. `POST /api/image-search` accepts multipart `mode=auto|exact|similar`,
defaulting to Auto when omitted. The upload still takes `image`, optional `query`
and the existing count/limit rules. `/api/image-search/continue` already accepts
JSON `mode`; it now applies it to fresh image refinements.

- Auto: existing v2 confidence/margin, candidate-pool and relaxation policy.
- Exact: same reliability margins and two-inferred-attribute cap, but without
  candidate-pool rejection or filter relaxation. Explicit text overrides win and
  remain mandatory. Empty filters produce `attributes_required` clarification
  without a Qdrant query; zero matches never trigger Similar fallback.
- Similar: image-vector retrieval with no inferred hard filters. Explicit text
  requirements remain mandatory metadata filters.

Results remain image-cosine ranked. Match labels are Exact for strict image
results and Similar otherwise; Exact is supported-attribute matching, not pixel
identity. New optional reply diagnostics are `requested_mode`, `effective_mode`
and `effective_image_strategy`. Strategies are `attribute_guided`,
`strict_attributes`, `pure_image_similarity`, `explicit_text_filtered_similarity`
and `attributes_required`. Existing `search_strategy` remains available; the new
image field is authoritative for distinguishing image retrieval policies.

`ImageActiveSearch` gains `mode` (default Auto) and optional
`effective_image_strategy`. Pagination uses these saved values plus the frozen
`effective_filters` and shown IDs, ignoring a changed current UI mode. Refinement
uses current mode, reuses the same stored embedding/original analysis, accumulates
text overrides and creates fresh shown-ID state. Old saved states lacking mode
continue as Auto with their previous frozen filters. No historical results are
rewritten and no backend image cache is added.

Example upload:

```sh
curl http://127.0.0.1:8001/api/image-search \
  -F 'image=@data/images/tshirt/941.jpg' -F 'mode=similar' \
  -F 'query=make it black' -F 'limit=5'
```

Read [validation/UNIFIED_SEARCH_MODES.md](../docs/validation/UNIFIED_SEARCH_MODES.md) for
actual request evidence. Prior v1/v2 relevance evaluation results remain versioned
and unchanged; no relevance gain is asserted for the unified selector.
