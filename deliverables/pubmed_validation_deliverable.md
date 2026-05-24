# PubMed GLiNER Validation Against NER Benchmarks — Deliverable

**Notebook:** `notebooks/pubmed_validation.ipynb`
**Date:** 2026-05-24
**Author:** Gloria Galasso

---

## 1. Objective

This validation task evaluates how well **GLiNER** extracts biomedical entity mentions from PubMed abstracts, by comparing GLiNER-extracted terms against three established biomedical NER benchmark datasets. Unlike the patent-side validation, no human annotation was required — the benchmark datasets provide ground truth directly.

---

## 2. Data Sources

| Source | File / Location | Description |
|--------|----------------|-------------|
| GLiNER PubMed labels | `data/raw/FullSampleGloria_Pmed_GlinerLabels_16042026.parquet` | 207M rows, one per (pmid, term); 881,341 unique PMIDs |
| BC5CDR | `data/CDR_Data/CDR.Corpus.v010516/` | Chemical and disease mentions in PubMed abstracts; 1500 PMIDs |
| BioRED | `data/BioRED/BioRED/` | 6 entity types (chemicals, diseases, genes, variants, organisms, cell lines); 600 PMIDs |
| NCBI Disease | `data/NCBIdisease/` | Disease name recognition; 793 PMIDs |

BioRED was downloaded from `https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip`. NCBI Disease was downloaded from `https://www.ncbi.nlm.nih.gov/CBBresearch/Dogan/DISEASE/`. All three benchmarks are in PubTator format.

---

## 3. Process

### Step 1 — Parse benchmark datasets

All three benchmark datasets were parsed from PubTator format into a dictionary `{pmid: [(mention, entity_type), ...]}`. Only the entity mention (column 4) and entity type (column 5) were extracted; character offsets were ignored. Mentions were lowercased and stripped of whitespace.

### Step 2 — Find overlapping PMIDs

The set of GLiNER PMIDs was intersected with each benchmark's PMIDs separately. This identified the articles present in both datasets — the only articles where a comparison is possible.

| Benchmark | Benchmark PMIDs | Overlapping with GLiNER | Overlap % |
|-----------|----------------|------------------------|-----------|
| BC5CDR | 1500 | 46 | 3.1% |
| BioRED | 600 | 48 | 8.0% |
| NCBI Disease | 793 | 0 | 0.0% |

The NCBI Disease corpus could not be evaluated: its PMIDs cover very old articles (PMID range 23,402–10,987,655, roughly pre-2000) that are almost absent from the GLiNER sample. Of the 881,341 GLiNER PMIDs, only 1,533 fall within that PMID range, and none coincide with the 792 specific NCBI Disease PMIDs.

### Step 3 — Filter GLiNER data

The 207M-row GLiNER file was loaded and immediately filtered to only the ~90 overlapping PMIDs (yielding ~21,000 rows), before building the `{pmid: set(terms)}` dictionary. This avoids running an expensive groupby on the full dataset.

### Step 4 — Match GLiNER terms against ground truth

For each overlapping PMID, GLiNER terms were compared against the deduplicated ground truth mentions using two criteria:

- **Exact match**: the GT mention equals a GLiNER term (e.g. GT `"headache"` = GLiNER `"headache"`)
- **Partial match**: a GLiNER term is a substring of the GT mention, or vice versa (e.g. GT `"nitric oxide"` partially matched by GLiNER `"nitric"`)

### Step 5 — Compute metrics

For each PMID and then aggregated across all PMIDs:

- **Recall** = fraction of GT mentions covered by GLiNER (exact or partial)
- **Precision** = fraction of GLiNER terms that match at least one GT mention
- **F1** = harmonic mean of precision and recall
- Both **micro** (mention-weighted) and **macro** (article-weighted) averages were computed

---

## 4. Results

### BC5CDR (46 overlapping PMIDs)

| Metric | Value |
|--------|-------|
| GT mentions (deduplicated) | 449 |
| Exact matches | 196 |
| Partial matches | 155 |
| Missed | 98 |
| GLiNER terms total | 2061 |
| GLiNER terms matching ≥1 GT entity | 420 |
| **Micro Precision** | **0.204** |
| **Micro Recall** | **0.782** |
| **Micro F1** | **0.323** |
| Macro Precision | 0.207 |
| Macro Recall | 0.790 |
| Macro F1 | 0.318 |

### BioRED (48 overlapping PMIDs)

| Metric | Value |
|--------|-------|
| GT mentions (deduplicated) | 768 |
| Exact matches | 190 |
| Partial matches | 239 |
| Missed | 339 |
| GLiNER terms total | 2304 |
| GLiNER terms matching ≥1 GT entity | 467 |
| **Micro Precision** | **0.203** |
| **Micro Recall** | **0.559** |
| **Micro F1** | **0.297** |
| Macro Precision | 0.228 |
| Macro Recall | 0.552 |
| Macro F1 | 0.309 |

### BioRED — Recall by Entity Type

| Entity Type | Exact | Partial | Missed | Total | Recall |
|-------------|-------|---------|--------|-------|--------|
| DiseaseOrPhenotypicFeature | 66 | 97 | 48 | 211 | 0.773 |
| ChemicalEntity | 66 | 30 | 40 | 136 | 0.706 |
| OrganismTaxon | 28 | 14 | 43 | 85 | 0.494 |
| GeneOrGeneProduct | 28 | 76 | 152 | 256 | 0.406 |
| SequenceVariant | 2 | 22 | 39 | 63 | 0.381 |
| CellLine | 0 | 0 | 17 | 17 | 0.000 |

---

## 5. Findings

### Finding 1 — Recall is lower than in the patent validation

GLiNER achieved recall of 0.782 (BC5CDR) and 0.559 (BioRED), compared to 0.99 on patent claims. The difference comes from the nature of the entities: biomedical entity names are longer, multi-word phrases (e.g. *glyceryl trinitrate*, *tension-type headache*, *VEGF receptor*), while patent claim terms tend to be shorter and more standalone. GLiNER fragments multi-word biomedical entities into single-word tokens that only partially cover the ground truth span.

### Finding 2 — Precision is similarly low (~0.20)

Only about 20% of GLiNER terms match a benchmark entity. The remaining 80% are generic tokens — prepositions, numbers, and common words like *after*, *study*, *significantly* — that are not biomedical entities. This is consistent with the patent finding (precision = 0.27). A minimum term-length filter and a biomedical stop-list would substantially raise precision without harming recall.

### Finding 3 — Partial matching is needed to get a fair recall estimate

GLiNER tends to extract single words rather than full multi-word entity names. For example, the GT entity `"nitric oxide"` gets captured as just `"nitric"`. Without partial matching, recall would drop from 0.782 to roughly 0.44 for BC5CDR. Partial matching — counting a GT entity as found if at least one of its component words appears in GLiNER — gives a fairer picture of actual coverage.

### Finding 4 — Recall varies strongly by entity type

Diseases and chemicals are better covered (0.71–0.77) because their surface forms are shorter and more common. Genes, variants, and cell lines are poorly covered (0.00–0.41) because their names are highly specialised laboratory codes (e.g. *HeLa*, *MCF-7*, *rs12345*) or long compound identifiers that GLiNER never emits as single tokens.

### Finding 5 — Top missed entities reveal systematic gaps

**BC5CDR missed:** multi-token drug names (*glyceryl trinitrate*, *6-OHDA*, *cyproterone acetate*) and short abbreviations (*FA*, *GTN*, *TDP*, *CHF*) that GLiNER either fragments or ignores.

**BioRED missed:** organism mentions (*patients*, *mice*, *rats*) — surprisingly absent from the GLiNER PubMed term set, suggesting they were filtered upstream as too generic by the pipeline. Also gene symbols (*VEGF*, *NF-κB*, *GLUT2*) and cell lines (*HEK293*, *HeLa*).

---

## 6. Comparison with Patent Validation

| Setting | Precision | Recall | F1 |
|---------|-----------|--------|-----|
| Patents (human annotation, claims only) | 0.27 | 0.99 | 0.42 |
| BC5CDR benchmark (chemicals + diseases) | 0.20 | 0.78 | 0.32 |
| BioRED benchmark (6 entity types) | 0.20 | 0.56 | 0.30 |

The overall pattern is consistent across both domains: **GLiNER is a high-extraction, noisy first-pass tagger**. Precision is low in both settings because the pipeline does not filter generic tokens. Recall is high for patents but lower for PubMed because biomedical entity names are harder to capture as single tokens.

---

## 7. Output Files

| File | Location | Description |
|------|----------|-------------|
| `bc5cdr_per_pmid.csv` | `output/pubmed_validation/` | Per-PMID evaluation table for BC5CDR |
| `biored_per_pmid.csv` | `output/pubmed_validation/` | Per-PMID evaluation table for BioRED |
| `biored_by_entity_type.csv` | `output/pubmed_validation/` | BioRED recall broken down by entity type |
| `benchmark_summary.csv` | `output/pubmed_validation/` | Aggregate metrics for all three benchmarks |
| `metrics_and_match_distribution.png` | `visualizations/pubmed_validation/` | Micro metrics bar chart + match distribution |
| `per_pmid_recall_distribution.png` | `visualizations/pubmed_validation/` | Per-document recall histograms |
| `biored_recall_by_entity_type.png` | `visualizations/pubmed_validation/` | BioRED recall by entity type |
| `top_missed_entities.png` | `visualizations/pubmed_validation/` | Top missed GT entities (BC5CDR and BioRED) |
