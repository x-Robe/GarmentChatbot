> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# Unified Auto / Exact / Similar Search Modes

Date: 2026-10-30 (Asia/Hong_Kong). Status: implemented; automated tests and real local API/browser checks completed. Voice hardware verification is not claimed.

## 1. Files changed

- Backend: `api.py`, `chatbot.py`, `src/product_search.py`, `src/hybrid_image_search.py`, `src/image_reference.py`.
- Frontend: `app.js`, `search.js`, `state.js`, `index.html` in `../../frontend/`.
- Tests: `tests/test_api.py`, `tests/test_image_context.py`, new `tests/test_unified_modes.py`; frontend `image-search.test.js`, `image-context.test.js`, `voice-app.test.js`.
- Documentation/evidence: `API.md`, `../../frontend/README.md`, this report and `unified_modes_api.json`.

No dependencies, models, classifier vocabulary, SKILL.md instructions, FashionCLIP preprocessing, Qdrant collections, ingestion, embeddings, similarity metrics or voice controller were changed. Text-specific extraction, retrieval, overrides, Both merge/ranking and quantity rules remain in place.

## 2. Final semantics

| Input | Auto | Exact | Similar |
|---|---|---|---|
| Text | Existing LLM selects Exact / Similar / Both | Existing schema metadata filters plus FashionCLIP text ranking | Existing FashionCLIP text retrieval without positive metadata filters |
| Image | Existing v2 confidence/margin, candidate-pool and relaxation policy | Strict reliable image attributes; image-vector ranking; no relaxation | Image-vector ranking without inferred hard filters |
| Image + text / image refinement | Existing v2 plus mandatory supported text requirements | Strict reliable image attributes plus mandatory text requirements | Only mandatory text requirements; no inferred hard filters |

All image paths share ProductSearch.search_by_image_embedding (historical artifact omitted). Uploads encode the image once through the existing encoder; refinements and pagination reuse the stored vector and original analysis. Optional analysis is retained even for Similar to support later mode changes; its scores never narrow Similar candidates.

Auto still calls the existing `retrieve_hybrid`; only its eligibility calculation was extracted into a shared helper, preserving the existing policy. There is no new LLM router or additional LLM request for image modes. The original override extractor and continuation planner retain their existing roles/call counts. See hybrid_image_search.py:16 (historical artifact omitted), product_search.py:544 (historical artifact omitted), and chatbot.py:269 (historical artifact omitted).

## 3. Exact, Similar and diagnostic metadata

Exact reuses the existing positive-score, valid-label/runner-up and margin rules: margin ≥0.015 for basic attributes, ≥0.04 for style. These are uncalibrated retrieval heuristics, not probabilities. It selects the strongest **up to two inferred attributes**, excluding fields explicitly overridden by text; all explicit requirements are added independently of that cap. It uses the existing six image attributes only. It does not reject a reliable constraint because candidate count is small and never relaxes these strict filters to fill a quota. Qdrant ANDs fields and uses existing MatchAny/OR within a field; buttons use Boolean equality.

No reliable image attributes and no explicit attributes → `attributes_required`, zero products, clarification asking for a requirement or switching to Similar, **no Qdrant query**. The image reference is retained for refinement. Strict filters with zero matches → an honest empty result with no automatic fallback. Exact means supported metadata matching, not pixel equality or guaranteed human visual relevance.

Similar uses no inferred image filters. Explicit supported requirements remain mandatory. Auto may relax only inferred conditions under the original v2 policy; explicit requirements are never relaxed. Unsupported-only requests do not silently run a claimed modified search. Partially supported requests apply supported conditions and explicitly say which additions were not applied.

Optional response fields:

```json
{
  "requested_mode": "exact",
  "effective_mode": "similar",
  "effective_image_strategy": "pure_image_similarity"
}
```

The example is a valid pagination response when the UI now requests Exact but the active image search was Similar. Effective strategy values are `attribute_guided`, `strict_attributes`, `pure_image_similarity`, `explicit_text_filtered_similarity`, and `attributes_required`. `image_analysis.filters_used` reports the actual final positive conditions; original/resolved attribute guesses do not mean every field was enforced. Existing `search_strategy` remains for compatibility, with Exact image results categorized/labelled Exact and other image results Similar. The new image-specific field distinguishes actual policies.

## 4. Propagation, continuation and compatibility

`/api/image-search` accepts multipart `mode=auto|exact|similar`, defaults to Auto, and still accepts `image`, optional `query`, and the existing count/limit contract (api.py:261 (historical artifact omitted)). Frontend FormData now includes mode; controls remain available with image attachments and during requests. Each upload snapshots the current selected mode, including for Retry. Cache versions were updated for the changed app, transport and state modules so old imports do not silently retain the previous upload behavior.

Image active state adds canonical `mode` and optional `effective_image_strategy`; no separate competing image-mode setting is introduced (image_reference.py:80 (historical artifact omitted)). Validators preserve embedding/model/analysis validation and mandatory conditions, reject inferred filters in Similar, and check strategy consistency. Old state without mode/strategy defaults to Auto and continues using saved effective filters. Historical product arrays and old messages are not migrated or rewritten. Old image requests without mode still use Auto; old frontend image retries fall back to Auto.

- **More results:** saved active mode, strategy and effective filters are frozen; UI mode changes do not alter that search. The original vector is reused, shown products/points are excluded using existing pagination logic, and current-request quantity applies.
- **Refinement:** current selected mode is used, explicit text overrides accumulate/correct/remove using the existing extractor, and a fresh shown-ID set is created. Original reference analysis/vector are unchanged; previous products may reappear.
- **New image:** current mode starts a fresh reference/override/pagination state; history remains intact.
- **Quantity:** existing default/max 8, invalid-count handling and cap rules are reused. Counts are per request, not sticky. There is one image retrieval policy per request, not Exact+Similar quota filling.
- **Voice:** the existing `submitMessage(text, state.mode, [], {voice:true})` path is unchanged. It forwards current mode and the saved image reference to the same continuation endpoint. Voice recognition/synthesis code itself was not changed.

The image upload's empty-Exact CTA is not allowed to invoke the text-only retry shortcut without an image. A user can refine the retained image with explicit conditions or upload/search in another mode. The existing text “Try Similar” action is retained.

## 5. Automated tests

**Backend: 156 passed, zero failures** (138 existing + 18 new parameterized mode tests). **Frontend: 98 passed, zero failures** (94 existing, updated for intentional image-mode propagation, + 4 new tests). Total: **254 passed**.

New tests cover all image-only/mixed routes; actual local-Qdrant strict/no-inferred filtering with mocked embeddings; supported text precedence; Exact zero/no-attribute handling; existing Auto policy; original-analysis immutability; one upload encoding; classifier failure; frozen mode/filter/vector/IDs on pagination; current-mode refinement; accumulated requirements and reset exclusions; count 1/3/7/above-cap; old omitted mode/state; new upload reset; frontend mode forwarding/Exact cards/history; retaining a reference on Exact clarification; and actual-app voice-to-image continuation. Mock LLM/encoder/browser tests do not establish real retrieval quality or speech accuracy.

Commands:

```sh
# From GarmentChatbot:
PYTHONPATH=.:tests .venv/bin/python -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count test_unified_modes
# From frontend:
node --test *.test.js
```

## 6. Real API validation

Fourteen HTTP requests were executed against **http://127.0.0.1:8001**, using real FashionCLIP, configured LLM calls where already required, and live Qdrant. All returned HTTP 200 and all assertions passed. Reference image: existing `data/images/tshirt/941.jpg`; image upload limit 5 except count-bearing continuation requests. No source exclusion was added, so these results can include the source product and are not an independent relevance evaluation.

A temporary read-only profiler observed actual `_query_qdrant` filter arguments and float32-vector hashes in the local API process; it did not replace functions or results. Full product IDs, real scores, attributes and Qdrant filter expressions are saved in unified_modes_api.json (historical artifact omitted). The observer process was subsequently replaced with ordinary uvicorn, and a final real Exact smoke request returned one product successfully.

| Case | Input / parent | Requested → effective mode | Effective strategy | Positive filters | Count | Actual product IDs |
|---|---|---|---|---|---:|---|
| A-old-default | 941.jpg | (omitted -> auto) → auto | attribute_guided | `{"colors": "white", "patterns": "plain"}` | 5 | 941, 816, 1467, 1411, 1503 |
| A-auto | 941.jpg | auto → auto | attribute_guided | `{"colors": "white", "patterns": "plain"}` | 5 | 941, 816, 1467, 1411, 1503 |
| A-exact | 941.jpg | exact → exact | strict_attributes | `{"colors": "white", "patterns": "plain"}` | 5 | 941, 816, 1467, 1411, 1503 |
| A-similar | 941.jpg | similar → similar | pure_image_similarity | `{}` | 5 | 941, 816, 1467, 1411, 1503 |
| B-exact-black | make it black | exact → exact | strict_attributes | `{"colors": ["black"], "patterns": "plain", "buttons": false}` | 5 | 1265, 890, 1618, 1114, 1288 |
| B-similar-black | make it black | similar → similar | explicit_text_filtered_similarity | `{"colors": ["black"]}` | 5 | 1265, 890, 1618, 1114, 1288 |
| C-auto-to-exact | make it long sleeve | exact → exact | strict_attributes | `{"sleeve": ["long sleeve"], "colors": "white", "patterns": "plain"}` | 8 | 1133, 1777, 1338, 1210, 1750, 1617, 956, 867 |
| D-similar-more | show me 3 more | exact → similar | pure_image_similarity | `{}` | 3 | 1324, 815, 1107 |
| C-black-then-similar-sleeve | make it long sleeve | similar → similar | explicit_text_filtered_similarity | `{"colors": ["black"], "sleeve": ["long sleeve"]}` | 8 | 1679, 919, 1535, 837, 1966, 1850, 1664, 1190 |
| E-auto | Show me 5 black T-shirts. | auto → auto | exact | `{"category": ["t-shirt"], "colors": ["black"]}` | 5 | 1335, 679, 1205, 1265, 1354 |
| E-exact | Show me 5 black T-shirts. | exact → exact | exact | `{"category": ["t-shirt"], "colors": ["black"]}` | 5 | 1335, 679, 1205, 1265, 1354 |
| E-similar | Show me 5 Japanese streetwear T-shirts. | similar → similar | similar | `{}` | 5 | 19, 635, 18, 542, 374 |
| E-refine | make them darker | exact → exact | exact | `{"category": ["t-shirt"], "colors": ["black"]}` | 8 | 1335, 679, 1265, 447, 773, 1618, 1205, 1288 |
| E-more | show me 3 more | similar → similar | exact | `{"category": ["t-shirt"], "colors": ["black"]}` | 3 | 829, 447, 1618 |

The first four cases returned identical top-five IDs, which is valid: Auto and Exact used white/plain predicates, whereas Similar sent **no positive filter**. Black-modification Exact and Similar also returned the same IDs, but Exact enforced black + plain + no visible buttons, while Similar enforced **black only**. The trace therefore proves behavioral differences beyond UI labels.

C-auto-to-exact used saved A-auto's image and added long sleeves under Exact. D-similar-more paginated A-similar despite UI Exact: saved mode remained Similar, filters stayed empty, quantity was 3, and overlap with the initial five products was **zero**. C-black-then-similar-sleeve retained black and added long sleeves under Similar, without extra inferred filters. All nine image cases used the **same observed vector hash**, including continuations. Index-compatibility exclusion retries can cause two Qdrant attempts on pagination; they do not relax positive conditions or change mode.

E-auto/Exact/Similar, E-refine and E-more confirmed existing text routes. E-more requested Similar but correctly retained saved Exact. These are execution/constraint checks, not human relevance labels.

## 7. Real browser validation

At **http://127.0.0.1:8000/** in the available in-app browser:

1. Existing history restored; all three mode controls remained usable after attaching a real image.
2. An initial browser attempt exposed a stale transport-module cache and used Auto. Import cache versions were corrected and the test was repeated: Exact upload then returned eight **Exact** cards and a strict-matching explanation.
3. Switching to Similar and sending “Show me 7 designs and make it black.” reused the reference and returned seven Similar products.
4. Switching the UI to Exact and sending “show me 3 more” still returned three **Similar** products. Both carousel pages of the seven prior products were inspected; the next three IDs did not overlap.
5. Carousel and product details worked, showing real black/color/sleeve/match fields.
6. Refresh restored the image reference context and previous results. “Make it long sleeve and show me 2 designs.” under Exact returned two Exact black long-sleeve results without re-uploading the image.

The earlier voice unit/integration tests remain passing, including a new mocked voice-image refinement test that verifies current mode and original reference forwarding. **No real spoken microphone transcript or audibly verified synthesized speech is claimed.** The current browser tests use actual image/text input and real backend retrieval.

## 8. Evaluation versioning and limitations

The earlier v1/v2 evaluation CSVs, annotations, gallery and report were not rerun or changed. Image Similar is related to original pure-vector v1, but explicit text filters make it a constrained variant; image Auto keeps v2; Exact is a new strict-attribute mode. No new Precision@5, relevance improvement or statistical claim is made.

Metadata can be imperfect (including multipack/foreground and logo/plain ambiguity). Strict filters may return fewer or zero results. At most two inferred attributes is a compatibility choice, not proof that other attributes are irrelevant. Explicit text values retain the existing OR-within-field semantics. Mode changes take effect on fresh image refinements/new uploads, not plain pagination. Browser-only reference persistence remains subject to localStorage capacity and model-version compatibility. Original image analysis is retained for switching modes and is not necessarily applied as a filter.

Hash verification confirmed all previously saved evaluation files, the FashionCLIP encoder, zero-shot classifier and voice controller were unchanged (17 protected files in total). No collection writes/re-ingestion or ranking/metric changes were performed.

## 9. Explicit answers

| Question | Answer |
|---|---|
| Q1. Does mode affect image-only retrieval? | **Yes**: real Auto/Exact/Similar requests and Qdrant filters verified. |
| Q2. Does mode affect image+text? | **Yes**: real Exact/Similar black modification verified; all three modes covered in automated mixed-input tests. |
| Q3. Does Similar avoid inferred hard filters? | **Yes**: empty predicates for image-only; explicit text predicates only for mixed/refined images. |
| Q4. Does Exact use strict supported constraints? | **Yes**; no reliable constraints yields explicit clarification without unrestricted retrieval. |
| Q5. Does Auto preserve original v2 by default? | **Yes**: same shared eligibility/margin/pool/relaxation policy; old omitted-mode calls match explicit Auto. |
| Q6. Are supported explicit requirements mandatory in every image mode? | **Yes**, with unsupported additions reported honestly. |
| Q7. Does pagination preserve strategy and refinement use current mode? | **Yes**, verified in local-Qdrant tests, real HTTP requests and browser flow. |
| Q8. Are text modes unchanged? | **Yes**: existing code paths and regressions preserved; real Auto/Exact/Similar/refinement/pagination passed. |
| Q9. Are FashionCLIP, collections, embeddings and ranking metrics preserved? | **Yes**; only candidate constraints/routing for new image modes changed. |
| Q10. Were real FashionCLIP/Qdrant image requests verified? | **Yes**: nine image/mixed/continuation batch cases, additional browser requests and final normal-server smoke. |
