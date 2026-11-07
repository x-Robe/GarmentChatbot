# GarmentChatbot — Human Relevance Evaluation and Ablation

**Release-copy update (2026-10-30):** all 57 supplied relevance labels are preserved; reviewer identities are pseudonymized. The project owner explicitly confirmed T2's zero-result set in the release task. queries.csv records project-owner-confirmation, with provenance in README.md. No original workspace files or live retrieval runs were changed.

## Setup and metric

The saved real study used the configured 1,993-point Qdrant collection, patrickjohncyh/fashion-clip and local catalog references. It includes four text, three image and three image-plus-text primary queries, each requesting five results, plus three additional image-v1 baseline runs. The 13 runs returned 57 ranked rows / 45 unique products; primary cases account for 42 rows. Query wording, modes, criteria and reference paths are in queries.csv. Ranked scores/attributes are real outputs, not ground truth.

The three image references are plain white garment 941, black graphic garment 635 and multi-garment image 442. Source-product point IDs were excluded in both arms' retrieval and candidate counts. run_manifest.json stores hashes, exclusions and filter diagnostics, without credentials or raw reference embeddings. Original live retrieval was not rerun during release preparation.

Human labels determine relevance using the recorded rubric. Model scores/inferred metadata are not labels. Precision@5 uses a fixed denominator of five, including underfilled queries. A zero-result query needs an explicit human acknowledgement; T2 now has that acknowledgement from the project owner's release instruction. Its P@5 is 0.0000; no nonexistent product annotations were added.

## Primary results

| Query | Input / mode | Returned | Human P@5 |
|---|---|---:|---:|
| T1 | Black T-shirts / Auto | 5 | 1.0000 |
| T2 | White graphic short-sleeve T-shirts / Auto | 0 | 0.0000 |
| T3 | Japanese streetwear graphic T-shirts / Similar | 5 | 0.8000 |
| T4 | Red striped long-sleeve T-shirts / Exact | 2 | 0.2000 |
| I1 | Plain white reference 941 / v2 | 5 | 1.0000 |
| I2 | Black graphic reference 635 / v2 | 5 | 1.0000 |
| I3 | Multi-garment reference 442 / v2 | 5 | 0.0000 |
| M1 | Reference 941 + make it black | 5 | 1.0000 |
| M2 | Reference 941 + make it long sleeve | 5 | 1.0000 |
| M3 | Reference 635 + make it plain | 5 | 0.6000 |

Mean human P@5 is **0.6600 across all 10 primary queries (10/10 complete)**, recomputed with the existing calculator. Eight of ten returned five products: **80% fill rate**, not accuracy. Previously 0.7333 covered only nine cases; it must not be compared as a retrieval improvement/degradation because only acknowledgement coverage changed. T2/T4 were not padded or silently relaxed.

## Controlled image ablation

Each pair uses the same reference, cached image vector, collection, source exclusion, requested count and relevance criterion. v1 is pure image-vector retrieval; v2 uses the existing attribute-guided candidate/relaxation policy with unchanged cosine ranking. The saved historical arms are not every newer unified image mode.

| Query | v1 P@5 | v2 P@5 | v2 − v1 | Shared products | Same ordered top five |
|---|---:|---:|---:|---:|---|
| I1 / 941 | 1.0000 | 1.0000 | 0.0000 | 5 | Yes |
| I2 / 635 | 1.0000 | 1.0000 | 0.0000 | 5 | Yes |
| I3 / 442 | 0.2000 | 0.0000 | -0.2000 | 0 | No |

Both returned five in each image case. Mean image P@5 remains **v1 0.7333 / v2 0.6667**, paired difference -0.0667. These outputs and relevance values are unchanged. Two pairs are equal, one multi-garment case is worse; three examples do not establish general superiority or statistical significance.

## Failure analysis and limitations

See failure_cases.md for saved evidence and unimplemented hypotheses. I3's multi-garment metadata may describe the composition instead of the rubric's foreground garment. M3 can return visible logos under plain metadata. Compound requirements T2/T4 underfill; T2's confirmed empty result does not prove the catalog has no visually relevant products. These causal explanations remain hypotheses rather than independent ground truth.

The ten-query sample is small and purposive, labels are subjective and a single reviewer does not establish inter-rater reliability. Near-duplicate catalog items may remain despite source exclusion. Model-derived attributes are imperfect. Saved services/model/collection state are not frozen, so later live rankings may differ. The study evaluates retrieval, not speech quality, deployment readiness, production latency or all newer unified-mode combinations. No tuning/new ranking was justified or implemented by this release update.

## Reproducibility and evidence boundaries

Run `python evaluation/calculate_metrics.py` from release root to recompute saved CSVs without external services. See README.md in this directory for optional future live runs/new output directories and gallery generation after authorized asset provisioning. Existing root-level catalog JPEGs are preserved in this integration; old galleries are omitted. Unchanged source/reference paths resolve under repository-root data/images.

The original study report recorded 138 backend / 48 frontend regression tests at its time. The latest release-copy isolated run separately passed **160 backend / 103 frontend** using existing development packages; it is not a fresh install or new live evaluation. Historical real API/browser evidence is in ../docs/validation/. Real hosting voice hardware and full E2E checks remain unverified.

Preserved artifacts: queries, results, runs, run_manifest, 57 pseudonymized annotations, metrics, summary, ablation, failure analysis and both reproduction scripts. Relevance labels/notes and all ranked rows remain unchanged. T2 acknowledgement and identity minimization are explicitly documented; no fake reviewer name, generated product labels or new retrieval evidence was introduced.
