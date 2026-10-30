# Observed retrieval failure cases

Evidence: saved `results.csv`, `runs.csv`, `run_manifest.json` and local dataset images. The assistant visually inspected all 45 unique retrieved products. These qualitative observations are **not human relevance annotations**; all 57 labels were subsequently supplied by human reviewer reviewer-01 on 2026-10-30. The detailed causal interpretations below remain hypotheses; T2 zero-result acknowledgement is now recorded from the project owner’s release instruction. The replacement labels resolve the earlier I2 annotation discrepancy. No proposed improvement was implemented.

## 1. Multi-garment composition changes the filtering target (I3)

- **Input:** `442.jpg`, showing a muted-green plain foreground T-shirt with white/red garments behind it.
- **Expected:** Under the criterion specified before retrieval, match the foreground green plain short-sleeve garment, not the entire multipack.
- **Observed:** v1 ranks product 83 first, a visually similar plain muted-green shirt. v2 returns 684, 720, 191, 260 and 439, with zero overlap with v1. The recorded v2 filters are multicolor and colorblock. Examples include a black/green multipack (684), a colorblocked shirt (720), and graphic garments (191 and 260). Product 83 carries green/plain metadata and does not satisfy these filters.
- **Likely cause (hypothesis):** Global image analysis conflates the colors of several separate garments with a single multicolor/colorblocked garment. The diagnostics establish the selected filters, but do not prove the internal cause of the classifier prediction.
- **Future proposal:** Evaluate user-selected foreground crops before attribute inference. This is a proposed experiment, not a production change.

## 2. “Make it plain” still returns prominent logos (M3)

- **Input:** Graphic reference `635.jpg` plus `make it plain`.
- **Expected:** No prominent graphic or logo, while retaining the dark short-sleeve appearance where possible.
- **Observed:** Results are 447, 620, 569, 111 and 773. Rank 2 (620) has a large central Reebok logo; rank 3 (569) has visible Champion branding. Both stored pattern lists contain `logo print` and `plain`. The actual mandatory override is `patterns: [plain]`.
- **Likely cause:** Nonexclusive metadata allows logo-bearing products to satisfy the existing plain filter. The co-labeling is observed; whether it arose from ambiguous annotation criteria or model error remains a hypothesis.
- **Future proposal:** Audit the plain-versus-logo labeling criteria against a small human-reviewed sample before considering ingestion changes.

## 3. Compound text requirements underfill the requested set (T2 and T4)

- **Input:** Five white graphic short-sleeve T-shirts (T2); five red striped long-sleeve T-shirts (T4).
- **Expected:** Five matching products if available, without relaxing explicit requirements silently.
- **Observed:** T2 returns zero; T4 returns only products 1940 and 636. These are successful search executions, not infrastructure errors. T4 product 636 additionally has an ambiguous purple/burgundy sports-top appearance with sleeve stripes; its payload includes red, striped and long sleeve. A human must judge it against the red-dominant criterion.
- **Likely cause (hypothesis):** Sparse intersections of catalog attributes and imperfect metadata can reduce coverage. The saved trace does not establish the precise cause of T2's zero results. Zero retrieval does not prove that no visually suitable item exists in the catalog.
- **Future proposal:** Manually audit a small catalog sample for these compound requirements and explain shortages to users; do not automatically weaken their requirements.
