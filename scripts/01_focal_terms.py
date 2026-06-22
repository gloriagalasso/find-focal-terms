import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

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
FINAL_PATH = OUT_DIR / "focal_terms_full.parquet"

def elapsed(t0):
    """Format elapsed time as 'Xm' or 'Xs' for readability."""
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (fully streaming) ===")
print(f"Polars version: {pl.__version__}")

if FINAL_PATH.exists():
    FINAL_PATH.unlink()

t0_all = time.time()

# =========================
# FULLY LAZY PIPELINE
# =========================
# Nothing is collected into memory here — all three DataFrames are lazy
# scan references. sink_parquet triggers Polars' streaming engine, which
# processes data in row-group chunks and never loads all files simultaneously.
# This avoids the OOM that occurs when the 700MB compressed PAT file
# (several GB uncompressed) is collected into RAM.

print("\nStep 1: Building lazy scan for link table...")
link_lazy = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid")
        .cast(pl.String)
        .str.extract(r"(\d+)$", 1)  # Extract trailing numeric part from URL or plain ID
        .cast(pl.Int64)
        .alias("pmid")
    )
    .filter(pl.col("pmid").is_not_null())
    .select("patent_id", "pmid")
    .unique()
)

print("Step 2: Building lazy scan for PubMed terms...")
pmed_lazy = (
    pl.scan_parquet(PMED_PATH)
    .select(pl.col("pmid").cast(pl.Int64), "term")
    .filter(pl.col("pmid").is_not_null())
    .filter(pl.col("term").is_not_null())
    .group_by("pmid", "term")
    .agg(pl.len().alias("freq_in_cited_paper"))
)

print("Step 3: Building lazy scan for patent terms...")
pat_lazy = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id", "term")
    .filter(pl.col("term").is_not_null())
    .group_by("patent_id", "term")
    .agg(pl.len().alias("freq_in_patent"))
)

# =========================
# STEP 4: Stream the join to disk
# =========================
# Join order:
#   link × pmed → (patent_id, pmid, term, freq_in_paper)   [papers cited by each patent]
#   × pat       → keep only terms that ALSO appear in the patent  [focal terms]
#
# sink_parquet uses Polars' partitioned streaming engine: data is hashed by
# join key and processed partition-by-partition, so peak RAM stays bounded.
#
# IMPORTANT: group_by + agg is NOT supported before sink_parquet in the
# streaming engine — it requires a full in-memory hash map and causes
# cancellation. So we split into two steps:
#   4a) Stream the join (join + select only) into a temp file WITH pmid
#   4b) Aggregate the smaller temp file to sum freq_in_cited_paper across PMIDs

TEMP_PATH = OUT_DIR / "focal_terms_with_pmid_tmp.parquet"
if TEMP_PATH.exists():
    TEMP_PATH.unlink()

print("\nStep 4a: Streaming three-way join to temp file (join only, no aggregation)...")
t0 = time.time()

(
    link_lazy
    .join(pmed_lazy, on="pmid", how="inner")
    .join(pat_lazy, on=["patent_id", "term"], how="inner")
    .rename({"term": "focal_term"})
    .select("patent_id", "pmid", "focal_term", "freq_in_patent", "freq_in_cited_paper")
    .sink_parquet(TEMP_PATH)
)

print(f"  Temp file written | {elapsed(t0)}")

# Step 4b: Aggregate across PMIDs — sum freq_in_cited_paper per (patent_id, focal_term).
# The temp file is much smaller than the raw inputs, so this collect is safe.
print("\nStep 4b: Aggregating across PMIDs...")
t0 = time.time()

(
    pl.scan_parquet(TEMP_PATH)
    .group_by("patent_id", "focal_term")
    .agg(
        pl.first("freq_in_patent"),
        pl.sum("freq_in_cited_paper"),
    )
    .sink_parquet(FINAL_PATH)
)

TEMP_PATH.unlink(missing_ok=True)
print(f"  Saved to: {FINAL_PATH} | {elapsed(t0)}")

# =========================
# STEP 5: Summary statistics (small aggregation on the output file)
# =========================
print("\nStep 5: Computing summary statistics...")
t0 = time.time()

# n_pmids is computed from the link table (pmid is no longer in the output file)
n_pmids_val = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid").cast(pl.String).str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("pmid")
    )
    .filter(pl.col("pmid").is_not_null())
    .select(pl.col("pmid").n_unique())
    .collect()
    .item()
)

stats = (
    pl.scan_parquet(FINAL_PATH)
    .select([
        pl.len().alias("n_rows"),
        pl.col("patent_id").n_unique().alias("n_patents"),
        pl.col("focal_term").n_unique().alias("n_focal_terms"),
    ])
    .collect()
)

print(stats)
print(f"  n_pmids (from link table): {n_pmids_val:,}")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 6: Export JSON summary
# =========================
print("\nStep 6: Exporting JSON summary...")
stats_row = stats.to_dicts()[0]
json_path = OUT_DIR / "focal_terms_full.json"
json_path.write_text(json.dumps({
    "n_rows":        int(stats_row["n_rows"]),
    "n_patents":     int(stats_row["n_patents"]),
    "n_pmids":       int(n_pmids_val),
    "n_focal_terms": int(stats_row["n_focal_terms"]),
}, indent=2))
print(f"  Saved to: {json_path}")

print(f"\n{'='*60}")
print(f"TASK 1 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"{'='*60}")
