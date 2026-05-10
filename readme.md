# Methodological Note

## Task 1 — Identify Focal Terms

**Goal:** Find terms that appear in both a patent and its cited scientific papers ("focal terms").

**Steps:**

1. **Load patent terms** from `SampleGloria_Pat_GlinerLabels.parquet` (`patent_id`, `term`). Group by `(patent_id, term)` and count occurrences → `freq_in_patent`.

2. **Clean the link table** from `SampleGloria_Link_PmidOa.parquet`. Drop rows without a PMID, extract the numeric ID from the URL via regex (`(\d+)$`), yielding clean `(patent_id, pmid)` pairs.

3. **Load paper terms** from `SampleGloria_Pmed_GlinerLabels.parquet` (`pmid`, `term`). Merge with the cleaned link table to attach `patent_id` to each paper term. Group by `(patent_id, pmid, term)` → `freq_in_cited_paper`.

4. **Identify focal terms** by inner-joining patent terms and cited paper terms on `(patent_id, term)`. Any term present in both is a focal term. Aggregate across PMIDs, summing `freq_in_cited_paper`.

**Output:** `output/focal_terms.parquet` — 790 `(patent_id, focal_term)` pairs across 101 patents.

---

## Task 1 (20260323) — Identify Focal Terms

**Goal:** Same as Task 1, applied to the full 20260323 dataset.

**Steps:**

1. **Load patent terms** from `SampleGloria_Pat_GlinerLabels_20260323.parquet`. Group by `(patent_id, term)` → `freq_in_patent`.

2. **Clean the link table** from `SampleGloria_Link_PmidOa_20260323.parquet`. Drop duplicate `(patent_id, pmid)` rows that arise from multiple matching sources.

3. **Load paper terms** from `SampleGloria_Pmed_GlinerLabels_20260323.parquet`. Merge with the cleaned link table to attach `patent_id`. Group by `(patent_id, term)` → `freq_in_cited_papers`.

4. **Identify focal terms** by inner-joining patent terms and cited paper terms on `(patent_id, term)`.

**Output:** `output/focal_terms_20260323.parquet` — 19,145 `(patent_id, focal_term)` pairs across 14,237 patents and 4,611 unique focal terms.

---

## Task 2 — Measure Overlap Intensity

**Goal:** Quantify how many focal terms each patent shares with its cited papers and describe the distribution.

**Steps:**

1. Load `focal_terms.parquet` and count unique focal terms per patent via `groupby("patent_id")["focal_term"].nunique()`.

2. Compute summary statistics (mean 7.82, median 6.00, std 6.83, min 1, max 30) over the per-patent counts.

3. Visualise the distribution with a histogram and a KDE density plot, marking mean and median.

**Output:** `deliverables/task2_deliverable.md`, `visualizations/histogram_focal_terms.png`, `visualizations/density_focal_terms.png`.

---

## Task 2 (20260323) — Measure Overlap Intensity

**Goal:** Same as Task 2, applied to the full 20260323 dataset.

**Steps:**

1. Load `focal_terms_20260323.parquet` and count unique focal terms per patent.

2. Compute summary statistics (mean 1.34, median 1.00, std 0.82, min 1, max 17). 77.5% of patents have exactly 1 focal term.

3. Visualise the distribution with a histogram and a KDE density plot.

**Output:** `visualizations/histogram_focal_terms_20260323.png`, `visualizations/density_focal_terms_20260323.png`.

---

## Task 3 — Semantic Context Comparison

**Goal:** Assess whether focal terms are used in similar or different semantic contexts in patents vs. scientific papers.

**Steps:**

1. **Map focal terms to PMIDs.** For each `(patent_id, focal_term)`, find the cited PMIDs that contain the focal term, restricting the paper context to papers that actually use the term.

2. **Build contexts.** For each `(patent_id, focal_term)`:
   - *Patent context*: all other terms in the patent (excluding the focal term itself).
   - *Paper context*: union of all terms across the relevant cited PMIDs (excluding the focal term itself).

3. **Serialise to sentences.** Each context becomes: `"<focal_term> <term_1> <term_2> ..."`. The focal term is prepended to anchor the embedding; it is excluded from the context set first to avoid appearing twice.

4. **Generate embeddings** using `sentence-transformers/all-MiniLM-L6-v2`, yielding `patent_embeddings` and `paper_embeddings` of shape `(790, 384)`.

5. **Compute cosine similarity** row-wise via `cosine_similarity(...).diagonal()`. Summary statistics: mean 0.441, median 0.443, std 0.140, min -0.008, max 0.843.

**Output:** `deliverables/task3_deliverable.md`, `output/focal_term_context.parquet`, `output/cosine_similarity_results.parquet`, `visualizations/cosine_similarity_distribution.png`.

---

## Task 3 (20260323) — Semantic Context Comparison

**Goal:** Same as Task 3, applied to the full 20260323 dataset.

**Steps:**

1–4. Same methodology as Task 3, using `focal_terms_20260323.parquet` and the `_20260323` raw files. Encoding uses `batch_size=256`. Output shape: `(19145, 384)`.

5. **Compute cosine similarity.** Summary statistics: mean 0.375, median 0.379, std 0.128, min -0.109, max 0.795.

**Output:** `deliverables/task3_20260323_deliverable.md`, `output/cosine_similarity_results_20260323.parquet`, `visualizations/cosine_similarity_distribution_20260323.png`.

---

## Validation Task — GLiNER Claim-Level Evaluation

**Goal:** Evaluate how well GLiNER extracts meaningful scientific and technical terms from patent claims, and how accurately it assigns semantic labels. This is not strict biomedical NER evaluation — the aim is to assess whether GLiNER identifies the "idea terms" that matter for the focal-term pipeline.

**Steps:**

1. **Sample 100 claims** at random (`seed=42`) from patents with `GrantedDate ≥ 2000` that appear in the GLiNER dataset. Each claim belongs to a different patent.

2. **Filter GLiNER terms to claim level.** GLiNER runs at patent level; terms were filtered to those that appear as a case-insensitive substring of the sampled `claim_text`, making the comparison fair against human annotations.

3. **Human annotation.** Each of the 100 claims was manually annotated: terms identified, approximate semantic labels assigned from the 127-label GLiNER/UMLS inventory, stored in compact format (one row per claim, semicolon-separated).

4. **Format conversion.** Human annotations converted from compact to long format (one row per term). Term normalization: lowercase, strip whitespace, collapse internal spaces.

5. **Comparison.** For each human term, a match was sought among GLiNER terms in the same `patent_id + claim_number`: exact (normalized strings identical) or partial (substring in either direction). Labels compared for matched terms.

6. **Metrics.** Precision, recall, F1, and label accuracy computed. GLiNER-only and human-only terms identified and saved.

**Key results:**

| Metric | Value |
|--------|-------|
| Human-annotated terms | 502 |
| GLiNER terms (unique per claim) | 1 848 |
| Exact matches | 246 |
| Partial matches | 250 |
| Precision | 0.27 |
| Recall | 0.99 |
| F1 | 0.42 |
| Label accuracy (matched terms) | 0.34 |

**Main findings:** GLiNER has near-perfect recall but low precision — it extracts ~3.7× more terms than humans. The 904 unmatched GLiNER terms are dominated by patent legal boilerplate (`wherein`, `method`, `claim`). Half of all matches are partial, reflecting a systematic span boundary problem. Label accuracy is low (0.34) but most confusions are between hierarchically adjacent categories (e.g. Organic Chemical ↔ Chemical).

**Output:** `deliverables/validation_deliverable.md`, `visualizations/validation_visualizations/` (4 plots), `output/validation_outputs/` (2 CSVs), `data/annotation/` (evaluation tables).
