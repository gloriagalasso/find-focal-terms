import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import gc
import json
import time
from pathlib import Path
import polars as pl

# =========================
# CONFIGURATION
# =========================
BASE     = Path(__file__).parent
DATA_DIR = BASE.parent / "data"

PAT_PATH  = DATA_DIR / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
LINK_PATH = DATA_DIR / "FullSampleGloria_Link_PmidOa_16042026.parquet"
PMED_PATH = DATA_DIR / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"

OUT_DIR    = BASE.parent / "output"
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR    = OUT_DIR / "tmp_focal_batches"
TMP_DIR.mkdir(exist_ok=True)
FINAL_PATH = OUT_DIR / "focal_terms_full.parquet"

BATCH_SIZE = 5000  # Process patents in batches to control memory usage

def elapsed(t0):
    """Format elapsed time as 'Xm' or 'Xs' for readability."""
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (patent × pmid level), batched version ===")
print(f"Polars version: {pl.__version__}")
print(f"Batch size: {BATCH_SIZE:,}")

# Clean up previous output if exists
if FINAL_PATH.exists():
    FINAL_PATH.unlink()

# Check for resumable batches (useful for reruns)
already_done = set(TMP_DIR.glob("focal_batch_*.parquet"))
print(f"Resuming: {len(already_done)} existing batch file(s) will be kept.")

t0_all = time.time()

# =========================
# STEP 1: Load all unique patent IDs
# =========================
print("\nStep 1: Loading unique patent IDs from patent file...")
t0 = time.time()

patent_ids = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id")
    .unique()
    .collect()
    ["patent_id"]
    .to_list()
)

n_patents = len(patent_ids)
print(f"  Found {n_patents:,} unique patents")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 2: Process patents in batches
# =========================
# Each batch:
#   1. Load patent terms for patents in this batch
#   2. Load patent-PMID links for patents in this batch
#   3. Load PubMed terms for only those PMIDs
#   4. Join: patent_terms × links × pmed_terms
#   5. Save as intermediate parquet file
# This approach keeps memory bounded: we only hold 1 batch's worth of data at a time

print("\nStep 2: Processing patents in batches...")
batch_files = []

for batch_idx, start in enumerate(range(0, n_patents, BATCH_SIZE), start=1):
    t0 = time.time()
    end = min(start + BATCH_SIZE, n_patents)
    batch_ids = patent_ids[start:end]
    batch_df = pl.DataFrame({"patent_id": batch_ids})

    out_path = TMP_DIR / f"focal_batch_{batch_idx:05d}.parquet"

    # Skip if already processed in a previous run
    if out_path in already_done:
        batch_files.append(out_path)
        print(f"\nBatch {batch_idx} | patents {start:,}–{end:,} | SKIPPED (already done)")
        continue

    print(f"\nBatch {batch_idx} | patents {start:,}–{end:,}")

    # ─────────────────────────────────────────────────────────────────
    # 2a. Load patent terms for this batch
    # ─────────────────────────────────────────────────────────────────
    # For each (patent_id, term) pair in this batch, count how many times
    # the term appears in that patent (freq_in_patent).
    pat_terms = (
        pl.scan_parquet(PAT_PATH)
        .select(["patent_id", "term"])
        .filter(pl.col("term").is_not_null())
        .join(batch_df.lazy(), on="patent_id", how="inner")
        .group_by(["patent_id", "term"])
        .agg(pl.len().alias("freq_in_patent"))
        .collect()
    )

    if pat_terms.height == 0:
        print("  → No patent terms found, skipping batch.")
        del pat_terms, batch_df
        gc.collect()
        continue

    # ─────────────────────────────────────────────────────────────────
    # 2b. Load patent-PMID links for this batch
    # ─────────────────────────────────────────────────────────────────
    # Extract all unique (patent_id, pmid) pairs for patents in this batch.
    # PMID values are strings like "12345ABC" — extract just the numeric part.
    links = (
        pl.scan_parquet(LINK_PATH)
        .filter(pl.col("pmid").is_not_null())
        .with_columns(
            pl.col("pmid")
            .cast(pl.String)
            .str.extract(r"(\d+)$", 1)  # Extract trailing digits
            .cast(pl.Int64)
            .alias("pmid_num")
        )
        .filter(pl.col("pmid_num").is_not_null())
        .select(["patent_id", pl.col("pmid_num").alias("pmid")])
        .join(batch_df.lazy(), on="patent_id", how="inner")
        .unique()
        .collect()
    )

    if links.height == 0:
        print("  → No patent-PMID links found, skipping batch.")
        del pat_terms, links, batch_df
        gc.collect()
        continue

    # ─────────────────────────────────────────────────────────────────
    # 2c. Load PubMed terms for only the PMIDs linked to this batch
    # ─────────────────────────────────────────────────────────────────
    # For each (pmid, term) pair linked to a patent in this batch, count
    # how many times the term appears in that paper (freq_in_paper).
    # By filtering to only relevant PMIDs first, we avoid scanning all ~207M rows.
    pmids = links.select("pmid").unique()

    pmed_terms = (
        pl.scan_parquet(PMED_PATH)
        .select([pl.col("pmid").cast(pl.Int64), "term"])
        .filter(pl.col("term").is_not_null())
        .join(pmids.lazy(), on="pmid", how="inner")  # Filter to relevant PMIDs
        .group_by(["pmid", "term"])
        .agg(pl.len().alias("freq_in_paper"))
        .collect()
    )

    if pmed_terms.height == 0:
        print("  → No PubMed terms found, skipping batch.")
        del pat_terms, links, pmids, pmed_terms, batch_df
        gc.collect()
        continue

    # ─────────────────────────────────────────────────────────────────
    # 2d. Join patent terms, links, and paper terms to find focal terms
    # ─────────────────────────────────────────────────────────────────
    # Focal term = a term that appears in:
    #   - the patent (freq_in_patent)
    #   - a cited paper (freq_in_paper)
    # We keep only the intersection: terms in both.
    focal = (
        links
        .join(pmed_terms, on="pmid", how="inner")  # Match terms to papers
        .join(pat_terms, on=["patent_id", "term"], how="inner")  # Match terms to patents
        .select(["patent_id", "pmid", "term", "freq_in_patent", "freq_in_paper"])
        .rename({"term": "focal_term"})
    )

    if focal.height > 0:
        focal.write_parquet(out_path)
        batch_files.append(out_path)
        print(f"  → Saved {focal.height:,} focal term occurrences")
    else:
        print("  → No focal terms in this batch.")

    del batch_df, pat_terms, links, pmids, pmed_terms, focal
    gc.collect()

    print(f"  Batch done in {elapsed(t0)}")

# =========================
# STEP 3: Combine all batch files into one
# =========================
print("\nStep 3: Combining all batch files...")
t0 = time.time()

if not batch_files:
    print("  No focal terms found across all batches. Writing empty parquet.")
    schema = {
        "patent_id":      pl.String,
        "pmid":           pl.Int64,
        "focal_term":     pl.String,
        "freq_in_patent": pl.UInt32,
        "freq_in_paper":  pl.UInt32,
    }
    empty = pl.DataFrame(schema=schema)
    empty.write_parquet(FINAL_PATH)
else:
    # Read all batch files, remove duplicates (in case of reruns), and write final output
    (
        pl.scan_parquet([str(p) for p in batch_files])
        .unique()
        .sink_parquet(FINAL_PATH)
    )

print(f"  Final output saved to: {FINAL_PATH}")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 4: Print summary statistics
# =========================
print("\nStep 4: Computing summary statistics...")
t0 = time.time()

stats = (
    pl.scan_parquet(FINAL_PATH)
    .select([
        pl.len().alias("n_rows"),
        pl.col("patent_id").n_unique().alias("n_patents"),
        pl.col("pmid").n_unique().alias("n_pmids"),
        pl.col("focal_term").n_unique().alias("n_focal_terms"),
    ])
    .collect()
)

print(stats)
print(f"Done in {elapsed(t0)}")

# =========================
# STEP 5: Export JSON summary
# =========================
print("\nStep 5: Exporting JSON summary...")
t0 = time.time()

stats_row = stats.to_dicts()[0]
json_path = OUT_DIR / "focal_terms_full.json"
json_path.write_text(json.dumps({
    "n_rows":        int(stats_row["n_rows"]),
    "n_patents":     int(stats_row["n_patents"]),
    "n_pmids":       int(stats_row["n_pmids"]),
    "n_focal_terms": int(stats_row["n_focal_terms"]),
}, indent=2))
print(f"  JSON summary saved to: {json_path}")
print(f"  Done in {elapsed(t0)}")

print(f"\n{'='*60}")
print(f"TASK 1 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"{'='*60}")
