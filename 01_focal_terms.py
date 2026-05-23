import os
os.environ.setdefault("POLARS_MAX_THREADS", "2")

import gc
import time
from pathlib import Path
import polars as pl

# =========================
# SETTINGS
# =========================
BATCH_SIZE = 2000   # lower if RAM rises too much, e.g. 1000 or 500

BASE = Path(__file__).parent

PAT_PATH  = BASE / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
LINK_PATH = BASE / "FullSampleGloria_Link_PmidOa_16042026.parquet"
PMED_PATH = BASE / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"

OUT_DIR = BASE / "output"
TMP_DIR = OUT_DIR / "tmp_focal_batches"
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

FINAL_PATH = OUT_DIR / "focal_terms_full.parquet"


def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"


print("=== TASK 1: Focal Terms, batched version ===")
print(f"Polars version: {pl.__version__}")
print(f"Batch size: {BATCH_SIZE}")

# Remove old partial files
for f in TMP_DIR.glob("focal_batch_*.parquet"):
    f.unlink()

if FINAL_PATH.exists():
    FINAL_PATH.unlink()

t0_all = time.time()

# =========================
# 1. Get all patent IDs
# =========================
print("Loading unique patent IDs...")

patent_ids = (
    pl.scan_parquet(PAT_PATH)
    .select("patent_id")
    .unique()
    .collect()
    ["patent_id"]
    .to_list()
)

n_patents = len(patent_ids)
print(f"Total unique patents: {n_patents:,}")

# =========================
# 2. Process patent batches
# =========================
batch_files = []

for batch_idx, start in enumerate(range(0, n_patents, BATCH_SIZE), start=1):
    t0 = time.time()

    batch_ids = patent_ids[start:start + BATCH_SIZE]
    batch_df = pl.DataFrame({"patent_id": batch_ids})

    out_path = TMP_DIR / f"focal_batch_{batch_idx:05d}.parquet"

    print(
        f"\nBatch {batch_idx} | patents {start:,}–{min(start+BATCH_SIZE, n_patents):,}"
    )

    # Patent terms in this batch
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
        print("  No patent terms, skipping.")
        continue

    # Links for patents in this batch
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
        .select([
            "patent_id",
            pl.col("pmid_num").alias("pmid")
        ])
        .join(batch_df.lazy(), on="patent_id", how="inner")
        .unique()
        .collect()
    )

    if links.height == 0:
        print("  No PMID links, skipping.")
        del pat_terms, links, batch_df
        gc.collect()
        continue

    pmids = links.select("pmid").unique()

    # Paper terms only for linked PMIDs
    pmed_terms = (
        pl.scan_parquet(PMED_PATH)
        .select([
            pl.col("pmid").cast(pl.Int64),
            "term"
        ])
        .filter(pl.col("term").is_not_null())
        .join(pmids.lazy(), on="pmid", how="inner")
        .collect()
    )

    if pmed_terms.height == 0:
        print("  No paper terms, skipping.")
        del pat_terms, links, pmids, pmed_terms, batch_df
        gc.collect()
        continue

    # Count terms in cited papers for this batch only
    cited_counts = (
        links
        .join(pmed_terms, on="pmid", how="inner")
        .group_by(["patent_id", "term"])
        .agg(pl.len().alias("freq_in_cited_papers"))
    )

    # Focal terms = terms appearing both in patent and cited papers
    focal = (
        pat_terms
        .join(cited_counts, on=["patent_id", "term"], how="inner")
        .rename({"term": "focal_term"})
    )

    if focal.height > 0:
        focal.write_parquet(out_path)
        batch_files.append(out_path)
        print(f"  Saved {focal.height:,} focal rows")
    else:
        print("  No focal terms in this batch.")

    del batch_df, pat_terms, links, pmids, pmed_terms, cited_counts, focal
    gc.collect()

    print(f"  Done in {elapsed(t0)}")

# =========================
# 3. Combine batch files
# =========================
print("\nCombining batch files...")

if not batch_files:
    print("No focal terms found. Writing empty parquet.")

    empty = pl.DataFrame({
        "patent_id": [],
        "focal_term": [],
        "freq_in_patent": [],
        "freq_in_cited_papers": [],
    })

    empty.write_parquet(FINAL_PATH)

else:
    (
        pl.scan_parquet([str(p) for p in batch_files])
        .unique()
        .sink_parquet(FINAL_PATH)
    )

print(f"Final saved file: {FINAL_PATH}")

# =========================
# 4. Summary
# =========================
stats = (
    pl.scan_parquet(FINAL_PATH)
    .select([
        pl.len().alias("n_rows"),
        pl.col("patent_id").n_unique().alias("n_patents"),
        pl.col("focal_term").n_unique().alias("n_focal_terms"),
    ])
    .collect()
)

print("\n=== Task 1 summary ===")
print(stats)

print(f"\nTask 1 finished in {elapsed(t0_all)}")