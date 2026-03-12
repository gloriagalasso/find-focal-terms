# Methodological Note

## Task 1 — Identify Focal Terms

**Goal:** Find terms that appear in both a patent and its cited scientific papers ("focal terms").

**Steps:**

1. **Load patent terms** from `SampleGloria_Pat_GlinerLabels.parquet` (`patent_id`, `term`). Group by `(patent_id, term)` and count occurrences → `freq_in_patent`.

2. **Clean the link table** from `SampleGloria_Link_PmidOa.parquet`. Drop rows without a PMID, extract the numeric ID from the URL via regex (`(\d+)$`), yielding clean `(patent_id, pmid)` pairs.

3. **Load paper terms** from `SampleGloria_Pmed_GlinerLabels.parquet` (`pmid`, `term`). Merge with the cleaned link table to attach `patent_id` to each paper term. Group by `(patent_id, pmid, term)` → `freq_in_cited_paper`.

4. **Identify focal terms** by inner-joining patent terms and cited paper terms on `(patent_id, term)`. Any term present in both is a focal term. Aggregate across PMIDs, summing `freq_in_cited_paper`.

**Output:** `output_dataset/focal_terms.parquet` — 790 `(patent_id, focal_term)` pairs across 101 patents.

---

## Task 2 — Measure Overlap Intensity

**Goal:** Quantify how many focal terms each patent shares with its cited papers and describe the distribution.

**Steps:**

1. Load `focal_terms.parquet` and count unique focal terms per patent via `groupby("patent_id")["focal_term"].nunique()`.

2. Compute summary statistics (mean, median, std, min, max, quartiles) over the per-patent counts.

3. Visualise the distribution with a histogram and a KDE density plot, marking mean and median.

**Output:** `task2_report.md`, `visualizations/histogram_focal_terms.png`, `visualizations/density_focal_terms.png`.

---

## Task 3 — Semantic Context Comparison

**Goal:** Assess whether focal terms are used in similar or different semantic contexts in patents vs. scientific papers.

**Steps:**

1. **Build contexts** from `focal_term_context.parquet`. For each `(patent_id, focal_term)`:
   - *Patent context*: all other terms in the patent (excluding the focal term).
   - *Paper context*: union of all terms across the relevant cited PMIDs (excluding the focal term).

2. **Serialise to sentences.** Each context becomes a single string: `"<focal_term> <term_1> <term_2> ..."`, producing two parallel lists — `patent_sentences` and `paper_sentences` — where index `i` corresponds to the same focal term in both.

3. **Generate embeddings** using `sentence-transformers/all-MiniLM-L6-v2`. Both lists are encoded with `model.encode(...)`, yielding `patent_embeddings` and `paper_embeddings` of shape `(790, 384)`.

4. **Compute cosine similarity** row-wise between `patent_embeddings[i]` and `paper_embeddings[i]` using `cosine_similarity(...).diagonal()`. The score is stored back in `focal_term_contexts['cosine_similarity']`.

5. **Analyse results**: compute summary statistics and plot a histogram with mean, median, and ±1 std lines. Inspect the top 5 and bottom 5 scoring focal terms to illustrate semantic alignment and divergence.

**Output:** `task3_report.md`, `output_dataset/focal_term_context.parquet`.
