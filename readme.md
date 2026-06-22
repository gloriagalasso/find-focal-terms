# Methodological Note

## Task 1 — Identify Focal Terms

**Goal:** Find terms that appear in both a patent and its cited scientific papers ("focal terms").

**Steps:**

1. **Load patent terms** from `data/raw/v1/SampleGloria_Pat_GlinerLabels.parquet` (`patent_id`, `term`). Group by `(patent_id, term)` and count occurrences → `freq_in_patent`.

2. **Clean the link table** from `data/raw/v1/SampleGloria_Link_PmidOa.parquet`. Drop rows without a PMID, extract the numeric ID from the URL via regex (`(\d+)$`), yielding clean `(patent_id, pmid)` pairs.

3. **Load paper terms** from `data/raw/v1/SampleGloria_Pmed_GlinerLabels.parquet` (`pmid`, `term`). Merge with the cleaned link table to attach `patent_id` to each paper term. Group by `(patent_id, pmid, term)` → `freq_in_cited_paper`.

4. **Identify focal terms** by inner-joining patent terms and cited paper terms on `(patent_id, term)`. Any term present in both is a focal term. Aggregate across PMIDs, summing `freq_in_cited_paper`.

**Output:** `output/v1/focal_terms.parquet` — 790 `(patent_id, focal_term)` pairs across 101 patents.

---

## Task 1 (20260323) — Identify Focal Terms

**Goal:** Same as Task 1, applied to the full 20260323 dataset.

**Steps:**

1. **Load patent terms** from `data/raw/v2_20260323/SampleGloria_Pat_GlinerLabels_20260323.parquet`. Group by `(patent_id, term)` → `freq_in_patent`.

2. **Clean the link table** from `data/raw/v2_20260323/SampleGloria_Link_PmidOa_20260323.parquet`. Drop duplicate `(patent_id, pmid)` rows that arise from multiple matching sources.

3. **Load paper terms** from `data/raw/v2_20260323/SampleGloria_Pmed_GlinerLabels_20260323.parquet`. Merge with the cleaned link table to attach `patent_id`. Group by `(patent_id, term)` → `freq_in_cited_papers`.

4. **Identify focal terms** by inner-joining patent terms and cited paper terms on `(patent_id, term)`.

**Output:** `output/v2_20260323/focal_terms_20260323.parquet` — 19,145 `(patent_id, focal_term)` pairs across 14,237 patents and 4,611 unique focal terms.

---

## Task 2 — Measure Overlap Intensity

**Goal:** Quantify how many focal terms each patent shares with its cited papers and describe the distribution.

**Steps:**

1. Load `focal_terms.parquet` and count unique focal terms per patent via `groupby("patent_id")["focal_term"].nunique()`.

2. Compute summary statistics (mean 7.82, median 6.00, std 6.83, min 1, max 30) over the per-patent counts.

3. Visualise the distribution with a histogram and a KDE density plot, marking mean and median.

**Output:** `deliverables/task2_deliverable.md`, `visualizations/v1/histogram_focal_terms.png`, `visualizations/v1/density_focal_terms.png`.

---

## Task 2 (20260323) — Measure Overlap Intensity

**Goal:** Same as Task 2, applied to the full 20260323 dataset.

**Steps:**

1. Load `focal_terms_20260323.parquet` and count unique focal terms per patent.

2. Compute summary statistics (mean 1.34, median 1.00, std 0.82, min 1, max 17). 77.5% of patents have exactly 1 focal term.

3. Visualise the distribution with a histogram and a KDE density plot.

**Output:** `visualizations/v2_20260323/histogram_focal_terms_20260323.png`, `visualizations/v2_20260323/density_focal_terms_20260323.png`.

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

**Output:** `deliverables/task3_deliverable.md`, `output/v1/focal_term_context.parquet`, `output/v1/cosine_similarity_results.parquet`, `visualizations/v1/cosine_similarity_distribution.png`.

---

## Task 3 (20260323) — Semantic Context Comparison

**Goal:** Same as Task 3, applied to the full 20260323 dataset.

**Steps:**

1–4. Same methodology as Task 3, using `focal_terms_20260323.parquet` and the `_20260323` raw files. Encoding uses `batch_size=256`. Output shape: `(19145, 384)`.

5. **Compute cosine similarity.** Summary statistics: mean 0.375, median 0.379, std 0.128, min -0.109, max 0.795.

**Output:** `deliverables/task3_20260323_deliverable.md`, `output/v2_20260323/cosine_similarity_results_20260323.parquet`, `visualizations/v2_20260323/cosine_similarity_distribution_20260323.png`.

---

## Task 1 (v3 Full Sample) — Identify Focal Terms

**Goal:** Same as Tasks 1/1b, applied to the full v3 dataset (16 April 2026).

**Data:**
- `FullSampleGloria_Pat_GlinerLabels_16042026.parquet` (~120M rows)
- `FullSampleGloria_Link_PmidOa_16042026.parquet` (~27M rows)
- `FullSampleGloria_Pmed_GlinerLabels_16042026.parquet` (~207M rows)

All data stored on Cloudflare R2 (too large for GitHub or local execution).

**Steps:**

1. **Lazy scan** all three parquet files without loading into memory. Patent terms grouped by `(patent_id, term)` → `freq_in_patent`. PubMed terms grouped by `(pmid, term)` → `freq_in_cited_paper`. Link table cleaned (numeric PMID extraction).

2. **Stream a three-way join** via Polars `sink_parquet`: links × PubMed terms × patent terms. Only terms present in both the patent and a cited paper survive the inner joins (= focal terms). Written to a temporary file with per-PMID granularity.

3. **Aggregate** the temporary file: group by `(patent_id, focal_term)`, keep `freq_in_patent`, sum `freq_in_cited_paper` across all PMIDs → final output.

**Why streaming:** The raw files exceed available RAM (~350M+ rows, several GB uncompressed). The previous batched approach (5,000 patents per batch, 256 batches) re-scanned the full parquet files for every batch. The streaming approach performs a single pass using Polars' partitioned streaming engine, keeping peak memory bounded.

**Output columns:** `patent_id`, `focal_term`, `freq_in_patent`, `freq_in_cited_papers`.

**Output:** `output/v3_16042026/outcomes_01_focal_terms_full.parquet` — 474,011 patents.

**Infrastructure:** GitHub Actions (`ubuntu-latest`, 7 GB RAM) + Cloudflare R2 storage. Workflow: `.github/workflows/01_focal_terms.yml`.

---

## Task 2 (v3 Full Sample) — Measure Overlap Intensity

**Goal:** Same as Tasks 2/2b, applied to the v3 full dataset.

**Key results:** mean 8.85 focal terms per patent, median 6.0, std 8.66, min 1, max 158. 10.6% of patents have exactly 1 focal term.

**Output:** `output/v3_16042026/outcomes_02_analysis_full.json`.

---

## Task 3 (v3 Full Sample) — Semantic Context Comparison

**Goal:** Same as Tasks 3/3b, applied to the v3 full dataset.

**Steps:** Same methodology as Task 3. Contexts built from term lists, embedded with `sentence-transformers/all-MiniLM-L6-v2`. 20,000 focal-term pairs sampled for tractable computation.

**Key results:** mean cosine similarity 0.466, median 0.477, std 0.141. 43% of pairs above 0.5 (similar context), 4.1% below 0.2 (very different context), 0.1% negative.

**Output:** `output/v3_16042026/outcomes_03_similarity_full.parquet`, `outcomes_03_contexts_full.parquet`, `outcomes_03_semantic_summary_full.json`, `task3_deliverable.json`.

---

## PubMed Validation — GLiNER vs. NER Benchmarks

**Goal:** Evaluate how well GLiNER extracts biomedical entity mentions from PubMed abstracts, by matching GLiNER-extracted terms against three established NER benchmark datasets (BC5CDR, BioRED, NCBI Disease) on shared PMIDs. No human annotation required — ground truth comes from the benchmarks.

**Data source (re-run):** Initial analysis used a random PubMed sample (`data/raw/v3_16042026/FullSampleGloria_Pmed_GlinerLabels_16042026.parquet`, 207M rows, 881k PMIDs) and found only 3–8% PMID overlap with the benchmarks and 0% for NCBI Disease (which covers pre-2000 articles). The analysis was re-run using a dedicated JSON (`data/raw/pubmed_validation/specialized_pubmed_samples_with_entities.json`) which contains GLiNER labels run specifically on all benchmark PMIDs, achieving 100% coverage across all three corpora.

**Steps:**

1. **Parse benchmarks** from PubTator format into `{pmid: [(mention, entity_type), ...]}` dictionaries. All three benchmarks (BC5CDR: 1500 PMIDs, BioRED: 600 PMIDs, NCBI Disease: 792 PMIDs) were parsed.

2. **Load GLiNER labels from the dedicated JSON.** Each entry in the JSON represents one article and contains sentence-level entity extractions with text, label, confidence score, and character offsets. Entity texts are lowercased and collected into a set per PMID. For BioRED, where some PMIDs appear across multiple splits (train/dev/test), terms from all splits are merged.

3. **Match terms** using exact match (GLiNER term == GT mention) and partial match (one appears as whole words inside the other, using regex lookarounds to handle chemical names with brackets). Compute precision, recall, and F1 at both micro and macro level.

**Key results:**

| Benchmark | PMIDs | GT Mentions | Micro Precision | Micro Recall | Micro F1 |
|-----------|-------|-------------|-----------------|--------------|----------|
| BC5CDR | 1,500 | 12,614 | 0.163 | 0.985 | 0.280 |
| BioRED | 600 | 9,421 | 0.240 | 0.984 | 0.386 |
| NCBI Disease | 792 | 3,864 | 0.105 | 0.986 | 0.189 |

BioRED recall by entity type: OrganismTaxon (0.991) > GeneOrGeneProduct (0.990) > ChemicalEntity (0.987) > Disease (0.980) > SequenceVariant (0.977) > CellLine (0.880). The earlier recall gradient (CellLine = 0.00 at 17 annotations) has flattened at full scale (92 annotations).

**Main findings:** GLiNER achieves near-perfect recall (~0.985) across all three benchmarks, matching the patent validation result (0.99). The earlier lower recall (0.56–0.78) was a sampling artefact from low PMID overlap, not a genuine domain difference. Precision is low (0.10–0.24) because GLiNER extracts all entity types while each benchmark annotates only a subset. NCBI Disease precision (0.105) is lowest as it is a disease-only corpus. Partial matches account for 28–52% of all matched mentions, with NCBI Disease having the highest partial-match share (52%) because older disease names tend to be long multi-word constructions. The finding is consistent with patent validation: GLiNER is a near-complete recall extractor that benefits from downstream precision filtering.

**Output:** `output/validation/pubmed_validation/` (5 CSVs: `benchmark_summary.csv`, `bc5cdr_per_pmid.csv`, `biored_per_pmid.csv`, `ncbi_per_pmid.csv`, `biored_by_entity_type.csv`), `visualizations/validation/pubmed_validation/` (4 plots).

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

**Output:** `deliverables/patent_claim_validation_deliverable.md`, `visualizations/validation/validation_visualizations/` (4 plots), `output/validation/validation_outputs/` (2 CSVs), `data/annotation/` (evaluation tables).
