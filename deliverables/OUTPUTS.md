# Pipeline Outputs & Visualizations

This document explains every file produced by the three-task pipeline that links patents to their cited scientific literature via shared *focal terms*, and then measures how semantically related the two contexts are.

---

## Overview

The pipeline runs in three stages:

| Script | Task | Description |
|---|---|---|
| `01_focal_terms.py` | Task 1 | Extract focal terms — terms appearing in both a patent and its cited papers |
| `02_analysis_focterms.py` | Task 2 | Analyse the distribution of focal terms across patents |
| `03_semantic_contexts.py` | Task 3 | Embed and compare the semantic context of each focal term in patent vs. paper |

---

## Task 1 — Focal Terms (`01_focal_terms.py`)

### What is a focal term?

A focal term is a named entity/label that appears **both** in a patent and in at least one scientific paper cited by that patent. It is identified by:

1. Taking all GliNER-extracted terms from the patent (`Pat` parquet).
2. Taking all GliNER-extracted terms from the linked PubMed papers (`Pmed` parquet), using the patent–PMID link table (`Link` parquet).
3. Keeping only terms present in both sets for the same `patent_id`.

### Output file

| File | Description |
|---|---|
| `output/focal_terms_full.parquet` | One row per `(patent_id, focal_term)` combination, with frequency counts |

**Columns:**

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | string | Unique patent identifier |
| `focal_term` | string | The shared term |
| `freq_in_patent` | int | How many times the term appears in the patent |
| `freq_in_cited_papers` | int | How many times the term appears across all papers cited by that patent |

---

## Task 2 — Focal Term Analysis (`02_analysis_focterms.py`)

Analyses how focal terms are distributed across patents, and which terms are most/least common globally.

### Output files

#### `output/focal_term_counts_per_patent_full.csv`
One row per patent. Contains `patent_id` and `num_focal_terms` (the number of distinct focal terms for that patent).

#### `output/task2_summary_stats_full.csv`
Descriptive statistics over `num_focal_terms`:

| Statistic | Value |
|---|---|
| Mean | 8.85 |
| Median | 6.0 |
| Std | 8.66 |
| Min | 1 |
| Max | 158 |
| N patents | 474,011 |
| N with exactly 1 focal term | 50,352 |
| % with exactly 1 focal term | 10.6% |

The distribution is right-skewed: most patents share a small number of terms with their cited literature, but a minority overlap very broadly. The median of 6 focal terms per patent reflects the typical patent–paper relationship.

#### `output/task2_top_patent_examples_full.csv`
The 10 patents with the highest focal-term overlap:

| patent_id | num_focal_terms |
|---|---|
| 10493296 | 158 |
| 11505782 | 144 |
| 7111346 | 122 |
| 8206901 | 118 |
| 9109248 | 117 |
| 9821114 | 111 |
| 11065306 | 110 |
| 7666598 | 108 |
| 9679115 | 108 |
| 8389222 | 107 |

These are likely highly specialised biomedical/pharmaceutical patents that reference a dense body of scientific literature.

#### `output/most_used_focal_terms_full.csv`
Top 20 focal terms by total frequency across all patents:

| Focal term | Frequency |
|---|---|
| method | 92,363 |
| cell | 61,388 |
| protein | 44,343 |
| human | 43,944 |
| effective | 37,710 |
| system | 36,647 |
| sequence | 32,576 |
| treatment | 29,180 |
| time | 28,895 |
| compound | 28,163 |
| surface | 27,163 |
| patient | 25,058 |
| different | 25,025 |
| disease | 24,148 |
| activity | 23,935 |
| group | 23,769 |
| cancer | 23,342 |
| tissue | 23,261 |
| antibody | 23,164 |
| expression | 22,942 |

High-frequency terms (`method`, `cell`, `protein`) are generic biomedical vocabulary. More specific terms (`cancer`, `antibody`, `expression`) reveal the predominantly life-sciences character of the dataset.

#### `output/least_used_focal_terms_full.csv`
20 focal terms that appear in only a single patent–paper pair (frequency = 1). Examples: `intralaminar`, `alkylate`, `harmonicity`, `hydroxylammonium`, `mycovirus`. These are highly specific technical terms that link exactly one patent to its literature.

---

### Visualization

#### `visualizations/histogram_focal_terms_full.png`

A histogram of the number of focal terms per patent (x-axis: number of focal terms, y-axis: number of patents). Dashed vertical lines mark the **mean (8.85)** and **median (6.0)**.

Key observations:
- The distribution is heavily right-skewed.
- The bulk of patents cluster between 1–20 focal terms.
- A long tail extends to 158, representing patents with exceptionally broad scientific grounding.
- The gap between mean and median confirms the skew: a small number of high-overlap patents pull the mean upward.

---

## Task 3 — Semantic Context Similarity (`03_semantic_contexts.py`)

Measures how semantically similar the *context* of each focal term is between the patent and the cited papers, using sentence embeddings.

### How it works

For each `(patent_id, focal_term)` pair (sampled: N = 20,000):

1. **Patent context**: all other GliNER terms extracted from the patent, excluding the focal term itself. Concatenated into a string: `"<focal_term> <term1> <term2> ..."`.
2. **Paper context**: all GliNER terms from the cited papers that also contain the focal term, excluding the focal term itself.
3. Both strings are encoded with **`all-MiniLM-L6-v2`** (sentence-transformers).
4. **Cosine similarity** between the two normalized embeddings is computed. Values range from −1 (opposite) to 1 (identical).

A high cosine similarity means the focal term is used in a similar conceptual neighbourhood in both the patent and the cited paper. A low similarity suggests the term is borrowed across different disciplinary contexts.

### Output files

#### `output/task3_contexts_sample.parquet`
Intermediate file. One row per sampled `(patent_id, focal_term)` with the raw context term lists before embedding.

| Column | Description |
|---|---|
| `patent_id` | Patent identifier |
| `focal_term` | The focal term |
| `patent_context` | List of co-occurring terms from the patent |
| `paper_context` | List of co-occurring terms from cited papers |

#### `output/task3_cosine_similarity_sample.parquet` / `.csv`
Main results table. One row per `(patent_id, focal_term)` pair.

| Column | Description |
|---|---|
| `patent_id` | Patent identifier |
| `focal_term` | The focal term |
| `patent_context_text` | Full concatenated patent context string fed to the model |
| `paper_context_text` | Full concatenated paper context string fed to the model |
| `cosine_similarity` | Cosine similarity score (float32) |

#### `output/task3_similarity_summary_sample.csv`
Descriptive statistics over cosine similarity scores (N = 20,000 pairs):

| Statistic | Value |
|---|---|
| Mean | 0.467 |
| Median | 0.477 |
| Std | 0.141 |
| Min | −0.127 |
| Max | 0.866 |
| N pairs | 20,000 |

The mean/median are close (~0.47), indicating a roughly symmetric distribution centred in the moderate-similarity range. The standard deviation of 0.14 shows meaningful variation — some focal terms are used in very similar contexts across patents and papers, others are not.

#### `output/task3_high_similarity_examples_sample.csv`
Top 20 `(patent_id, focal_term)` pairs by cosine similarity. These represent cases where the focal term is embedded in nearly identical conceptual contexts in both the patent and its cited literature — strong evidence of direct knowledge transfer.

#### `output/task3_low_similarity_examples_sample.csv`
Bottom 20 pairs by cosine similarity. These cases have near-zero or negative similarity, suggesting the shared term is used in quite different contexts — possibly a generic term that happens to appear in both but carries different meaning.

---

### Visualization

#### `visualizations/task3_cosine_similarity_distribution_sample.png`

A histogram of cosine similarity scores (x-axis: cosine similarity, y-axis: number of focal-term pairs). Dashed vertical lines mark the **mean (0.467)** and **median (0.477)**.

Key observations:
- The distribution is approximately bell-shaped, centred around 0.45–0.50.
- Very few pairs score above 0.80 (near-identical contexts) or below 0.10 (unrelated contexts).
- The slight left tail (including a small number of negative values) corresponds to cases where patent and paper use the same term in genuinely different semantic environments.
- Overall, the moderate average similarity (~0.47) suggests that patent–literature knowledge transfer is real but partial: patents do not simply copy scientific framing; they adapt terminology to an applied/technical context.

---

## File Map

```
output/
├── focal_terms_full.parquet              # Task 1: core focal term table
├── focal_term_counts_per_patent_full.csv # Task 2: focal terms per patent
├── task2_summary_stats_full.csv          # Task 2: distribution statistics
├── task2_top_patent_examples_full.csv    # Task 2: patents with most overlap
├── most_used_focal_terms_full.csv        # Task 2: top 20 global terms
├── least_used_focal_terms_full.csv       # Task 2: bottom 20 global terms
├── task3_contexts_sample.parquet         # Task 3: context term lists (sample)
├── task3_cosine_similarity_sample.parquet# Task 3: similarity scores + context texts
├── task3_cosine_similarity_sample.csv    # Task 3: same, CSV format
├── task3_similarity_summary_sample.csv   # Task 3: similarity statistics
├── task3_high_similarity_examples_sample.csv  # Task 3: top-20 similar pairs
└── task3_low_similarity_examples_sample.csv   # Task 3: bottom-20 similar pairs

visualizations/
├── histogram_focal_terms_full.png        # Task 2: focal term count distribution
└── task3_cosine_similarity_distribution_sample.png  # Task 3: similarity distribution
```
