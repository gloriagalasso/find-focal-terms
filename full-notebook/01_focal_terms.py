import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import gc
import time
from pathlib import Path
import polars as pl

BASE     = Path(__file__).parent
DATA_DIR = BASE.parent / "data"

PAT_PATH  = DATA_DIR / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
LINK_PATH = DATA_DIR / "FullSampleGloria_Link_PmidOa_16042026.parquet"
PMED_PATH = DATA_DIR / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"

OUT_DIR = BASE.parent / "output"
OUT_DIR.mkdir(exist_ok=True)
FINAL_PATH = OUT_DIR / "focal_terms_full.parquet"

def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (memory-efficient batched join) ===")
print(f"Polars version: {pl.__version__}")

t0_all = time.time()

# Pre-filter: get all unique PMIDs from links to avoid scanning all of PMED
print("\nStep 1: Getting unique PMIDs from links...")
t0 = time.time()

pmids = (
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
    .select("pmid_num")
    .unique()
    .collect()["pmid_num"].to_list()
)

print(f"  {len(pmids):,} unique PMIDs")
print(f"  Done in {elapsed(t0)}")

# Pre-load all links (compact)
print("\nStep 2: Loading all patent-PMID links...")
t0 = time.time()

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
    .collect()
)

print(f"  {len(links):,} patent-PMID links")
print(f"  Done in {elapsed(t0)}")

# Pre-load PubMed terms for relevant PMIDs only (filter upfront)
print("\nStep 3: Loading PubMed terms for relevant PMIDs...")
t0 = time.time()

pmed_df = pl.DataFrame({"pmid": pmids})
pmed_terms = (
    pl.scan_parquet(PMED_PATH)
    .select([pl.col("pmid").cast(pl.Int64), "term"])
    .filter(pl.col("term").is_not_null())
    .join(pmed_df.lazy(), on="pmid", how="inner")
    .collect()
)

print(f"  {len(pmed_terms):,} PubMed term rows")
print(f"  Done in {elapsed(t0)}")

del pmed_df
gc.collect()

# Get unique patent IDs for batching
print("\nStep 4: Getting unique patent IDs...")
t0 = time.time()

patent_ids = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id")
    .unique()
    .join(links.select("patent_id").unique().lazy(), on="patent_id", how="inner")
    .collect()["patent_id"].to_list()
)

n_patents = len(patent_ids)
print(f"  {n_patents:,} patents with PMID links")
print(f"  Done in {elapsed(t0)}")

# Process in batches: read patent file once, join with cached links/terms
print("\nStep 5: Processing patent batches...")
batch_size = 5000
batch_files = []
tmp_dir = OUT_DIR / "tmp_focal"
tmp_dir.mkdir(exist_ok=True)

for batch_idx, start in enumerate(range(0, n_patents, batch_size), start=1):
    t0 = time.time()
    end_idx = min(start + batch_size, n_patents)
    batch_ids = patent_ids[start:end_idx]

    out_path = tmp_dir / f"batch_{batch_idx:04d}.parquet"

    print(f"\nBatch {batch_idx} | patents {start:,}–{end_idx:,}")

    # Get patent terms for this batch
    pat_terms = (
        pl.scan_parquet(PAT_PATH)
        .select(["patent_id", "term"])
        .filter(
            (pl.col("term").is_not_null())
            & (pl.col("patent_id").is_in(batch_ids))
        )
        .group_by(["patent_id", "term"])
        .agg(pl.len().alias("freq_in_patent"))
        .collect()
    )

    if pat_terms.height == 0:
        print("  No patent terms, skipping.")
        continue

    # Join: patents → links
    batch_links = links.filter(pl.col("patent_id").is_in(batch_ids))
    if batch_links.height == 0:
        print("  No links, skipping.")
        continue

    # Join: links → pmed_terms
    focal = (
        batch_links
        .lazy()
        .join(pmed_terms.lazy(), on="pmid", how="inner")
        .join(pat_terms.lazy(), on=["patent_id", "term"], how="inner")
        .select(["patent_id", "pmid", "term", "freq_in_patent", "freq_in_paper"])
        .rename({"term": "focal_term"})
        .unique()
        .collect()
    )

    if focal.height > 0:
        focal.write_parquet(out_path)
        batch_files.append(out_path)
        print(f"  {focal.height:,} focal rows → {out_path.name}")
    else:
        print("  No focal terms, skipping.")

    del pat_terms, batch_links, focal
    gc.collect()

    print(f"  Done in {elapsed(t0)}")

# Combine all batches
print("\nStep 6: Combining batch files...")
t0 = time.time()

if batch_files:
    (
        pl.scan_parquet([str(p) for p in batch_files])
        .unique()
        .sink_parquet(FINAL_PATH)
    )
    print(f"  Combined {len(batch_files)} batches")
else:
    schema = {
        "patent_id":      pl.String,
        "pmid":           pl.Int64,
        "focal_term":     pl.String,
        "freq_in_patent": pl.UInt32,
        "freq_in_paper":  pl.UInt32,
    }
    pl.DataFrame(schema=schema).write_parquet(FINAL_PATH)
    print("  No batches; wrote empty parquet")

print(f"  Saved: {FINAL_PATH}")
print(f"  Done in {elapsed(t0)}")

# Summary
print("\n=== Task 1 summary ===")
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
print(f"\nTask 1 finished in {elapsed(t0_all)}")
