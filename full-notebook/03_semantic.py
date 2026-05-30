import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import gc
import json
import time
from pathlib import Path

import numpy as np
import polars as pl
import matplotlib
matplotlib.use("Agg")  # Use non-interactive backend for server environments
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer

# =========================
# CONFIGURATION
# =========================
BASE     = Path(__file__).parent
OUT_DIR  = BASE.parent / "output"
VIZ_DIR  = BASE.parent / "visualizations"
DATA_DIR = BASE.parent / "data"

OUT_DIR.mkdir(exist_ok=True)
VIZ_DIR.mkdir(exist_ok=True)

PAT_PATH    = DATA_DIR / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
LINK_PATH   = DATA_DIR / "FullSampleGloria_Link_PmidOa_16042026.parquet"
PMED_PATH   = DATA_DIR / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"
FOCAL_PATH  = OUT_DIR / "focal_terms_full.parquet"

CONTEXT_PATH = OUT_DIR / "task3_contexts_sample.parquet"
RESULT_PATH  = OUT_DIR / "task3_cosine_similarity_sample.parquet"

# Semantic embedding model
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Processing parameters
N_SAMPLE = 20000      # Sample 20k focal pairs for semantic analysis (reduces computation)
CHUNK_SIZE = 256      # Process 256 pairs at a time to manage memory
ENCODE_BATCH = 32     # Batch size for transformer embeddings

def elapsed(t0):
    """Format elapsed time as 'Xm' or 'Xs' for readability."""
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 3: Semantic Context Comparison ===")
print(f"Sample size: {N_SAMPLE:,} focal pairs")
print(f"Embedding model: {MODEL_NAME}")
print(f"Chunk size: {CHUNK_SIZE} | Batch size: {ENCODE_BATCH}\n")

t0_all = time.time()

# =========================
# STEP 1: Sample focal pairs
# =========================
print("Step 1: Sampling focal pairs...")
t0 = time.time()

# Load a sample of (patent_id, focal_term) pairs.
# We take a sample because encoding all pairs would be too slow;
# 20k pairs is enough for representative statistics.
focal_pairs = (
    pl.scan_parquet(FOCAL_PATH)
    .select("patent_id", "focal_term")
    .unique()
    .sort("patent_id", "focal_term")
    .limit(N_SAMPLE)
    .collect()
)

print(f"  Sampled {len(focal_pairs):,} unique (patent, term) pairs")
print(f"  RAM usage: {focal_pairs.estimated_size('mb'):.2f} MB")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 2: Get relevant patent-PMID links
# =========================
print("Step 2: Loading patent-PMID links for sampled patents...")
t0 = time.time()

sample_patents = focal_pairs.select("patent_id").unique()

# Extract patent-PMID links for only the patents in our sample.
# PMID values are strings like "12345ABC" — extract just the numeric part.
link_clean = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid")
        .cast(pl.String)
        .str.extract(r"(\d+)$", 1)  # Extract trailing digits
        .cast(pl.Int64)
        .alias("pmid")
    )
    .filter(pl.col("pmid").is_not_null())
    .select("patent_id", "pmid")
    .join(sample_patents.lazy(), on="patent_id", how="inner")
    .unique()
    .collect()
)

print(f"  Found {len(link_clean):,} patent-PMID links")
print(f"  RAM usage: {link_clean.estimated_size('mb'):.2f} MB")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 3: Build patent contexts
# =========================
print("Step 3: Building patent term contexts...")
t0 = time.time()

# For each (patent, focal_term) pair, collect all OTHER terms in that patent.
# These "context terms" help us understand the semantic field around the focal term.
patent_context = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id", "term")
    .join(sample_patents.lazy(), on="patent_id", how="inner")
    .join(focal_pairs.lazy(), on="patent_id", how="inner")
    .filter(pl.col("term") != pl.col("focal_term"))  # Exclude the focal term itself
    .group_by("patent_id", "focal_term")
    .agg(
        pl.col("term")
        .unique()
        .alias("patent_context")
    )
    .collect()
)

print(f"  Built context for {len(patent_context):,} (patent, focal_term) pairs")
print(f"  RAM usage: {patent_context.estimated_size('mb'):.2f} MB")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 4: Load relevant PubMed terms
# =========================
print("Step 4: Loading PubMed terms for cited papers...")
t0 = time.time()

relevant_pmids = link_clean.select("pmid").unique()

# Load PubMed terms, but only for papers cited by patents in our sample.
pmed_terms = (
    pl.scan_parquet(PMED_PATH)
    .select([
        pl.col("pmid").cast(pl.Int64),
        pl.col("term")
    ])
    .join(relevant_pmids.lazy(), on="pmid", how="inner")
    .collect()
)

print(f"  Loaded {len(pmed_terms):,} PubMed term rows")
print(f"  RAM usage: {pmed_terms.estimated_size('mb'):.2f} MB")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 5: Build paper contexts
# =========================
print("Step 5: Building cited-paper term contexts...")
t0 = time.time()

# For each (patent, focal_term) pair, collect all OTHER terms in papers that cite that term.
# This lets us compare what terms appear alongside the focal term in scientific papers.
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
    .filter(pl.col("term") != pl.col("focal_term"))  # Exclude focal term
    .group_by("patent_id", "focal_term")
    .agg(
        pl.col("term")
        .unique()
        .alias("paper_context")
    )
    .collect()
)

print(f"  Built context for {len(paper_context):,} (patent, focal_term) pairs")
print(f"  RAM usage: {paper_context.estimated_size('mb'):.2f} MB")
print(f"  Done in {elapsed(t0)}\n")

del link_clean, pmed_terms, relevant_pmids, sample_patents
gc.collect()

# =========================
# STEP 6: Combine contexts
# =========================
print("Step 6: Combining patent and paper contexts...")
t0 = time.time()

# Merge patent contexts and paper contexts into a single table.
# Left join ensures we keep all focal pairs even if context is missing.
contexts = (
    focal_pairs
    .join(patent_context, on=["patent_id", "focal_term"], how="left")
    .join(paper_context, on=["patent_id", "focal_term"], how="left")
)

# Fill missing contexts with empty lists
contexts = contexts.with_columns(
    pl.col("patent_context").fill_null([]),
    pl.col("paper_context").fill_null([]),
)

contexts.write_parquet(CONTEXT_PATH)

print(f"  Combined {len(contexts):,} pairs with patent + paper contexts")
print(f"  Saved to: {CONTEXT_PATH}")
print(f"  Done in {elapsed(t0)}\n")

del focal_pairs, patent_context, paper_context
gc.collect()

# =========================
# STEP 7: Encode contexts and compute cosine similarity
# =========================
print("Step 7: Encoding contexts with transformer model...")
t0 = time.time()

# Load the sentence transformer model
model = SentenceTransformer(MODEL_NAME, device="cpu")

# Track results as we process chunks
all_patent_ids = []
all_focal_terms = []
all_patent_texts = []
all_paper_texts = []
all_similarities = []

total_rows = len(contexts)

# Process contexts in chunks to manage memory
for start in range(0, total_rows, CHUNK_SIZE):
    end = min(start + CHUNK_SIZE, total_rows)
    chunk = contexts.slice(start, CHUNK_SIZE)

    patent_texts = []
    paper_texts = []

    # For each pair, construct text strings:
    # - patent_text = focal_term + " " + other patent terms
    # - paper_text = focal_term + " " + other paper terms
    # This creates a representation of the semantic context around the focal term.
    for row in chunk.iter_rows(named=True):
        focal_term = row["focal_term"]
        patent_terms = row["patent_context"] or []
        paper_terms = row["paper_context"] or []

        patent_text = focal_term + " " + " ".join(patent_terms)
        paper_text = focal_term + " " + " ".join(paper_terms)

        patent_texts.append(patent_text)
        paper_texts.append(paper_text)

    # Encode both context strings using the transformer
    patent_emb = model.encode(
        patent_texts,
        batch_size=ENCODE_BATCH,
        show_progress_bar=False,
        normalize_embeddings=True,  # Normalize so cosine similarity is in [-1, 1]
    )

    paper_emb = model.encode(
        paper_texts,
        batch_size=ENCODE_BATCH,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    # Cosine similarity = dot product of normalized vectors
    similarities = (patent_emb * paper_emb).sum(axis=1).astype(np.float32)

    # Accumulate results
    all_patent_ids.extend(chunk["patent_id"].to_list())
    all_focal_terms.extend(chunk["focal_term"].to_list())
    all_patent_texts.extend(patent_texts)
    all_paper_texts.extend(paper_texts)
    all_similarities.extend(similarities.tolist())

    del chunk, patent_texts, paper_texts, patent_emb, paper_emb, similarities
    gc.collect()

    # Progress indicator
    done = end
    pct = done / total_rows * 100
    elapsed_so_far = time.time() - t0
    rate = done / max(elapsed_so_far, 1)
    eta = (total_rows - done) / max(rate, 1)

    print(f"  Processed {done:,}/{total_rows:,} ({pct:.1f}%) | ETA {eta / 60:.1f} min")

print(f"Done in {elapsed(t0)}\n")

# =========================
# STEP 8: Save similarity results
# =========================
print("Step 8: Saving results...")
t0 = time.time()

# Compile all results into a single dataframe
results = pl.DataFrame({
    "patent_id": all_patent_ids,
    "focal_term": all_focal_terms,
    "patent_context_text": all_patent_texts,
    "paper_context_text": all_paper_texts,
    "cosine_similarity": all_similarities,
})

results.write_parquet(RESULT_PATH)
results.write_csv(OUT_DIR / "task3_cosine_similarity_sample.csv")

print(f"  Saved results to: {RESULT_PATH}")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 9: Compute and display summary statistics
# =========================
print("Step 9: Computing similarity statistics...")
t0 = time.time()

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

print(summary)
print(f"Done in {elapsed(t0)}\n")

# =========================
# STEP 10: Identify high and low similarity examples
# =========================
print("Step 10: Finding example pairs with high and low similarity...")
t0 = time.time()

# High similarity = semantic context is very similar between patent and papers
# Low similarity = semantic context is quite different between patent and papers
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

print(f"  Found 20 high-similarity and 20 low-similarity examples")
print("\nHigh similarity examples (focal term context most similar):")
print(high_examples.select("patent_id", "focal_term", "cosine_similarity").head(10))

print("\nLow similarity examples (focal term context most different):")
print(low_examples.select("patent_id", "focal_term", "cosine_similarity").head(10))
print(f"Done in {elapsed(t0)}\n")

# =========================
# STEP 11: Export JSON summary
# =========================
print("Step 11: Exporting JSON summary...")
t0 = time.time()

json_path = OUT_DIR / "task3_semantic_summary.json"
json_path.write_text(json.dumps({
    "summary_stats": {r["statistic"]: r["value"] for r in summary.to_dicts()},
    "high_similarity_examples": (
        high_examples
        .select("patent_id", "focal_term", "cosine_similarity")
        .to_dicts()
    ),
    "low_similarity_examples": (
        low_examples
        .select("patent_id", "focal_term", "cosine_similarity")
        .to_dicts()
    ),
}, indent=2))
print(f"  JSON summary saved to: {json_path}")
print(f"  Done in {elapsed(t0)}\n")

# =========================
# STEP 12: Visualize similarity distribution
# =========================
print("Step 12: Creating similarity distribution plot...")
t0 = time.time()

plt.figure(figsize=(10, 6))

plt.hist(
    sim,
    bins=60,
    edgecolor="black",
    color="steelblue",
    alpha=0.7,
)

plt.axvline(sim.mean(), linestyle="--", linewidth=2, color="red", label=f"Mean = {sim.mean():.3f}")
plt.axvline(np.median(sim), linestyle="--", linewidth=2, color="orange", label=f"Median = {np.median(sim):.3f}")

plt.title("Semantic Similarity Between Patent and Cited Paper Contexts", fontsize=14, fontweight="bold")
plt.xlabel("Cosine Similarity", fontsize=12)
plt.ylabel("Number of focal-term pairs", fontsize=12)
plt.legend()
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()

plt.savefig(VIZ_DIR / "task3_cosine_similarity_distribution_sample.png", dpi=300)
plt.close()

print(f"  Saved plot to: {VIZ_DIR / 'task3_cosine_similarity_distribution_sample.png'}")
print(f"Done in {elapsed(t0)}\n")

# =========================
# SUMMARY
# =========================
print("=" * 60)
print(f"TASK 3 COMPLETE | Total time: {elapsed(t0_all)}")
print("=" * 60)
