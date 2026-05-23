import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import gc
import time
from pathlib import Path

import numpy as np
import polars as pl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"
VIZ_DIR = BASE / "visualizations"

OUT_DIR.mkdir(exist_ok=True)
VIZ_DIR.mkdir(exist_ok=True)

PAT_PATH = BASE / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
LINK_PATH = BASE / "FullSampleGloria_Link_PmidOa_16042026.parquet"
PMED_PATH = BASE / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"
FOCAL_PATH = OUT_DIR / "focal_terms_full.parquet"

CONTEXT_PATH = OUT_DIR / "task3_contexts_sample.parquet"
RESULT_PATH = OUT_DIR / "task3_cosine_similarity_sample.parquet"


# ============================================================
# PARAMETERS
# ============================================================

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Safer settings
N_SAMPLE = 20000
CHUNK_SIZE = 256
ENCODE_BATCH = 32

print("Task 3 — Semantic Context Comparison SAMPLE")
print(f"N_SAMPLE: {N_SAMPLE:,}")
print(f"CHUNK_SIZE: {CHUNK_SIZE}")
print(f"ENCODE_BATCH: {ENCODE_BATCH}")


# ============================================================
# 1. SAMPLE FOCAL PAIRS
# ============================================================

print("\nStep 1/6: Sampling focal pairs...")

focal_pairs = (
    pl.scan_parquet(FOCAL_PATH)
    .select("patent_id", "focal_term")
    .unique()
    .sort("patent_id", "focal_term")
    .limit(N_SAMPLE)
    .collect()
)

print(f"Sampled focal pairs: {len(focal_pairs):,}")
print(f"RAM focal_pairs: {focal_pairs.estimated_size('mb'):.2f} MB")


# ============================================================
# 2. GET ONLY RELEVANT PATENT IDS
# ============================================================

sample_patents = focal_pairs.select("patent_id").unique()

print(f"Sample patents: {len(sample_patents):,}")


# ============================================================
# 3. CLEAN LINKS ONLY FOR SAMPLE PATENTS
# ============================================================

print("\nStep 2/6: Preparing links for sampled patents...")

link_clean = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid")
        .str.extract(r"(\d+)$", 1)
        .cast(pl.Int64)
        .alias("pmid")
    )
    .filter(pl.col("pmid").is_not_null())
    .select("patent_id", "pmid")
    .join(sample_patents.lazy(), on="patent_id", how="inner")
    .unique()
    .collect()
)

print(f"Relevant links: {len(link_clean):,}")
print(f"RAM link_clean: {link_clean.estimated_size('mb'):.2f} MB")


# ============================================================
# 4. PATENT CONTEXTS ONLY FOR SAMPLE
# ============================================================

print("\nStep 3/6: Building patent contexts...")

patent_context = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id", "term")
    .join(sample_patents.lazy(), on="patent_id", how="inner")
    .join(focal_pairs.lazy(), on="patent_id", how="inner")
    .filter(pl.col("term") != pl.col("focal_term"))
    .group_by("patent_id", "focal_term")
    .agg(
        pl.col("term")
        .unique()
        .alias("patent_context")
    )
    .collect()
)

print(f"Patent contexts: {len(patent_context):,}")
print(f"RAM patent_context: {patent_context.estimated_size('mb'):.2f} MB")


# ============================================================
# 5. PUBMED TERMS ONLY FOR RELEVANT PMIDS
# ============================================================

print("\nStep 4/6: Loading PubMed terms only for relevant PMIDs...")

relevant_pmids = link_clean.select("pmid").unique()

pmed_terms = (
    pl.scan_parquet(PMED_PATH)
    .select(
        pl.col("pmid").cast(pl.Int64),
        pl.col("term")
    )
    .join(relevant_pmids.lazy(), on="pmid", how="inner")
    .collect()
)

print(f"Relevant PubMed term rows: {len(pmed_terms):,}")
print(f"RAM pmed_terms: {pmed_terms.estimated_size('mb'):.2f} MB")


# ============================================================
# 6. PAPER CONTEXTS
# ============================================================

print("\nStep 5/6: Building cited-paper contexts...")

paper_context = (
    focal_pairs
    .lazy()
    .join(link_clean.lazy(), on="patent_id", how="inner")
    .join(
        pmed_terms.lazy().rename({"term": "focal_term"}),
        on=["pmid", "focal_term"],
        how="inner"
    )
    .select("patent_id", "focal_term", "pmid")
    .unique()
    .join(pmed_terms.lazy(), on="pmid", how="inner")
    .filter(pl.col("term") != pl.col("focal_term"))
    .group_by("patent_id", "focal_term")
    .agg(
        pl.col("term")
        .unique()
        .alias("paper_context")
    )
    .collect()
)

print(f"Paper contexts: {len(paper_context):,}")
print(f"RAM paper_context: {paper_context.estimated_size('mb'):.2f} MB")

del link_clean, pmed_terms, relevant_pmids, sample_patents
gc.collect()


# ============================================================
# 7. COMBINE CONTEXTS
# ============================================================

print("\nCombining contexts...")

contexts = (
    focal_pairs
    .join(patent_context, on=["patent_id", "focal_term"], how="left")
    .join(paper_context, on=["patent_id", "focal_term"], how="left")
)

contexts = contexts.with_columns(
    pl.col("patent_context").fill_null([]),
    pl.col("paper_context").fill_null([]),
)

contexts.write_parquet(CONTEXT_PATH)

print(f"Saved context file: {CONTEXT_PATH}")
print(f"Context rows: {len(contexts):,}")
print(f"RAM contexts: {contexts.estimated_size('mb'):.2f} MB")

del focal_pairs, patent_context, paper_context
gc.collect()


# ============================================================
# 8. EMBEDDING SIMILARITY
# ============================================================

print("\nStep 6/6: Encoding contexts and computing cosine similarity...")

model = SentenceTransformer(MODEL_NAME, device="cpu")

all_patent_ids = []
all_focal_terms = []
all_patent_texts = []
all_paper_texts = []
all_similarities = []

start_time = time.time()
total_rows = len(contexts)

for start in range(0, total_rows, CHUNK_SIZE):
    end = min(start + CHUNK_SIZE, total_rows)
    chunk = contexts.slice(start, CHUNK_SIZE)

    patent_texts = []
    paper_texts = []

    for row in chunk.iter_rows(named=True):
        focal_term = row["focal_term"]

        patent_terms = row["patent_context"] or []
        paper_terms = row["paper_context"] or []

        patent_text = focal_term + " " + " ".join(patent_terms)
        paper_text = focal_term + " " + " ".join(paper_terms)

        patent_texts.append(patent_text)
        paper_texts.append(paper_text)

    patent_emb = model.encode(
        patent_texts,
        batch_size=ENCODE_BATCH,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    paper_emb = model.encode(
        paper_texts,
        batch_size=ENCODE_BATCH,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    similarities = (patent_emb * paper_emb).sum(axis=1).astype(np.float32)

    all_patent_ids.extend(chunk["patent_id"].to_list())
    all_focal_terms.extend(chunk["focal_term"].to_list())
    all_patent_texts.extend(patent_texts)
    all_paper_texts.extend(paper_texts)
    all_similarities.extend(similarities.tolist())

    del chunk, patent_texts, paper_texts, patent_emb, paper_emb, similarities
    gc.collect()

    elapsed = time.time() - start_time
    done = end
    pct = done / total_rows * 100
    rate = done / max(elapsed, 1)
    eta = (total_rows - done) / max(rate, 1)

    print(
        f"Processed {done:,}/{total_rows:,} "
        f"({pct:.1f}%) | ETA {eta / 60:.1f} min"
    )


# ============================================================
# 9. SAVE RESULTS
# ============================================================

results = pl.DataFrame({
    "patent_id": all_patent_ids,
    "focal_term": all_focal_terms,
    "patent_context_text": all_patent_texts,
    "paper_context_text": all_paper_texts,
    "cosine_similarity": all_similarities,
})

results.write_parquet(RESULT_PATH)
results.write_csv(OUT_DIR / "task3_cosine_similarity_sample.csv")

print(f"\nSaved results: {RESULT_PATH}")


# ============================================================
# 10. SUMMARY
# ============================================================

sim = results["cosine_similarity"].to_numpy()

summary = pl.DataFrame({
    "statistic": ["mean", "median", "std", "min", "max", "n_pairs"],
    "value": [
        float(sim.mean()),
        float(np.median(sim)),
        float(sim.std()),
        float(sim.min()),
        float(sim.max()),
        float(len(sim)),
    ],
})

summary.write_csv(OUT_DIR / "task3_similarity_summary_sample.csv")

print("\nSimilarity summary:")
print(summary)


# ============================================================
# 11. HIGH / LOW EXAMPLES
# ============================================================

high_examples = (
    results
    .sort("cosine_similarity", descending=True)
    .head(20)
)

low_examples = (
    results
    .sort("cosine_similarity")
    .head(20)
)

high_examples.write_csv(OUT_DIR / "task3_high_similarity_examples_sample.csv")
low_examples.write_csv(OUT_DIR / "task3_low_similarity_examples_sample.csv")

print("\nHigh similarity examples:")
print(high_examples.select("patent_id", "focal_term", "cosine_similarity").head(10))

print("\nLow similarity examples:")
print(low_examples.select("patent_id", "focal_term", "cosine_similarity").head(10))


# ============================================================
# 12. PLOT
# ============================================================

plt.figure(figsize=(10, 6))

plt.hist(
    sim,
    bins=60,
    edgecolor="black"
)

plt.axvline(sim.mean(), linestyle="--", label=f"Mean = {sim.mean():.3f}")
plt.axvline(np.median(sim), linestyle="--", label=f"Median = {np.median(sim):.3f}")

plt.title("Semantic Similarity Between Patent and Scientific Contexts — Sample")
plt.xlabel("Cosine Similarity")
plt.ylabel("Number of focal-term pairs")
plt.legend()
plt.tight_layout()

plt.savefig(VIZ_DIR / "task3_cosine_similarity_distribution_sample.png", dpi=300)
plt.close()

print(f"\nSaved plot: {VIZ_DIR / 'task3_cosine_similarity_distribution_sample.png'}")

print("\nTask 3 sample complete.")