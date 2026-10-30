# Saved Evaluation and Reproduction

This directory contains a saved real retrieval snapshot, not newly rerun retrieval. The project instruction explicitly confirms T2's zero products; queries.csv now records that acknowledgement as project-owner-confirmation. All 57 original relevance values, keys/order and notes are preserved; reviewer identity is pseudonymized as reviewer-01. The identity mapping is deliberately not included. This is data minimization for release, not a claim that someone re-annotated the products.

From release root:

```sh
python evaluation/calculate_metrics.py
```

This uses Python stdlib and writes only metrics.csv, summary.csv and ablation.csv. Current primary mean P@5 is 0.6600 over 10/10 cases; T2 is 0/5. Image-v1/v2 means remain 0.7333/0.6667 over three references. No labels are generated or filled in by model inference.

An optional future live run requires authorized catalog assets, the original-compatible services/model, and approval for external/possibly paid calls:

```sh
# Do not run until authorized and fully provisioned; choose a fresh output directory
python evaluation/run_evaluation.py --run-live --output evaluation/run_2
```

The release-only ROOT adjustment points this script at ../backend for imports and image_path resolution. It refuses to overwrite existing run artifacts. API/search source and study algorithms are unchanged. Existing dataset images are preserved at repository-root data/images; old debug/annotation galleries are omitted. To generate a gallery from the existing snapshot with the existing catalog (confirm asset rights before hosting) (no model query):

```sh
python -c "import sys; from pathlib import Path; sys.path.insert(0,'evaluation'); from run_evaluation import gallery; from calculate_metrics import read_csv; p=Path('evaluation').resolve(); gallery(p,read_csv(p/'queries.csv'),read_csv(p/'results.csv'),read_csv(p/'runs.csv'))"
```

Without the corresponding product/reference images the gallery generator correctly fails rather than inventing content. Review data/identity/image publication rights before any future export. The final study predates full unified-mode evaluation and must not be presented as validation of every later feature.
