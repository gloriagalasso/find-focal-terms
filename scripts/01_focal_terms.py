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
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (patent × pmid level) ===")
print(f"Polars version: {pl.__version__}")

if FINAL_PATH.exists():
    FINAL_PATH.unlink()

t0_all = time.time()

# =========================
# STEP 1: Build lazy query — each file scanned exactly once
# =========================
print("\nStep 1: Building query plan...")
t0 = time.time()

pat_terms = (
    pl.scan_parquet(PAT_PATH)
    .select(["patent_id", "term"])
    .filter(pl.col("term").is_not_null())
    .group_by(["patent_id", "term"])
    .agg(pl.len().alias("freq_in_patent"))
)

links = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid")
        .cast(pl.String)
        .str.extract(r"(\d+)$", 1)
        .cast(pl.Int64)
        .alias("pmid_num")
    )
    .filter(pl.col("pmid_num").is_not_null())
    .select(["patent_id", pl.col("pmid_num").alias("pmid")])
    .unique()
)

pmed_terms = (
    pl.scan_parquet(PMED_PATH)
    .select([pl.col("pmid").cast(pl.Int64), "term"])
    .filter(pl.col("term").is_not_null())
    .group_by(["pmid", "term"])
    .agg(pl.len().alias("freq_in_paper"))
)

print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 2: Join and stream result to disk
# =========================
print("\nStep 2: Computing focal terms (streaming)...")
t0 = time.time()

focal = (
    links
    .join(pmed_terms, on="pmid", how="inner")
    .join(pat_terms, on=["patent_id", "term"], how="inner")
    .group_by(["patent_id", "term"])
    .agg([
        pl.col("freq_in_patent").first(),
        pl.col("freq_in_paper").sum().alias("freq_in_cited_papers"),
    ])
    .rename({"term": "focal_term"})
)

focal.sink_parquet(FINAL_PATH)

print(f"  Final output saved to: {FINAL_PATH}")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 3: Print summary statistics
# =========================
print("\nStep 3: Computing summary statistics...")
t0 = time.time()

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
print(f"Done in {elapsed(t0)}")

# =========================
# STEP 4: Export JSON summary
# =========================
print("\nStep 4: Exporting JSON summary...")
t0 = time.time()

stats_row = stats.to_dicts()[0]
json_path = OUT_DIR / "focal_terms_full.json"
json_path.write_text(json.dumps({
    "n_rows":        int(stats_row["n_rows"]),
    "n_patents":     int(stats_row["n_patents"]),
    "n_focal_terms": int(stats_row["n_focal_terms"]),
}, indent=2))
print(f"  JSON summary saved to: {json_path}")
print(f"  Done in {elapsed(t0)}")

print(f"\n{'='*60}")
print(f"TASK 1 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"{'='*60}")
