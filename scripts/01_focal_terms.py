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
TMP_DIR    = OUT_DIR / "tmp_intermediate"
TMP_DIR.mkdir(exist_ok=True)
FINAL_PATH = OUT_DIR / "focal_terms_full.parquet"

PAT_AGG_PATH  = TMP_DIR / "pat_term_counts.parquet"
LINK_AGG_PATH = TMP_DIR / "link_clean.parquet"
PMED_AGG_PATH = TMP_DIR / "pmed_term_counts.parquet"

def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (patent × pmid level) ===")
print(f"Polars version: {pl.__version__}")

if FINAL_PATH.exists():
    FINAL_PATH.unlink()

t0_all = time.time()

# =========================
# STEP 1: Aggregate patent terms (one scan of Pat file)
# =========================
print("\nStep 1: Aggregating patent terms...")
t0 = time.time()

(
    pl.scan_parquet(PAT_PATH)
    .select(["patent_id", "term"])
    .filter(pl.col("term").is_not_null())
    .group_by(["patent_id", "term"])
    .agg(pl.len().alias("freq_in_patent"))
    .sink_parquet(PAT_AGG_PATH)
)

n_pat = pl.scan_parquet(PAT_AGG_PATH).select(pl.len()).collect().item()
print(f"  {n_pat:,} unique (patent, term) pairs")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 2: Clean links (one scan of Link file)
# =========================
print("\nStep 2: Cleaning patent-PMID links...")
t0 = time.time()

(
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
    .sink_parquet(LINK_AGG_PATH)
)

n_links = pl.scan_parquet(LINK_AGG_PATH).select(pl.len()).collect().item()
print(f"  {n_links:,} unique (patent, pmid) links")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 3: Aggregate PubMed terms (one scan of Pmed file)
# =========================
print("\nStep 3: Aggregating PubMed terms...")
t0 = time.time()

(
    pl.scan_parquet(PMED_PATH)
    .select([pl.col("pmid").cast(pl.Int64), "term"])
    .filter(pl.col("term").is_not_null())
    .group_by(["pmid", "term"])
    .agg(pl.len().alias("freq_in_paper"))
    .sink_parquet(PMED_AGG_PATH)
)

n_pmed = pl.scan_parquet(PMED_AGG_PATH).select(pl.len()).collect().item()
print(f"  {n_pmed:,} unique (pmid, term) pairs")
print(f"  Done in {elapsed(t0)}")

# =========================
# STEP 4: Join intermediates and write focal terms
# =========================
print("\nStep 4: Joining to find focal terms...")
t0 = time.time()

links = pl.scan_parquet(LINK_AGG_PATH)
pmed_terms = pl.scan_parquet(PMED_AGG_PATH)
pat_terms = pl.scan_parquet(PAT_AGG_PATH)

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
