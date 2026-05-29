import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import time
from pathlib import Path
import polars as pl

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

print("=== TASK 1: Focal Terms (single-pass lazy join) ===")
print(f"Polars version: {pl.__version__}")

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

print("Running lazy join pipeline...")

(
    pat_terms
    .join(links, on="patent_id", how="inner")
    .join(pmed_terms, on=["pmid", "term"], how="inner")
    .select(["patent_id", "pmid", "term", "freq_in_patent", "freq_in_paper"])
    .rename({"term": "focal_term"})
    .unique()
    .sink_parquet(FINAL_PATH)
)

print(f"Saved: {FINAL_PATH}")

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

print("\n=== Task 1 summary ===")
print(stats)
print(f"\nTask 1 finished in {elapsed(t0)}")
