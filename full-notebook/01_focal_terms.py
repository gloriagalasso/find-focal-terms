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
TMP_DIR = OUT_DIR / "tmp_focal_batches"
TMP_DIR.mkdir(exist_ok=True)

def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"

print("=== TASK 1: Focal Terms (patent × pmid level), batched version ===")
print(f"Polars version: {pl.__version__}")
print(f"Batch size: 5000")

if FINAL_PATH.exists():
    FINAL_PATH.unlink()

already_done = set(TMP_DIR.glob("focal_batch_*.parquet"))
print(f"Resuming: {len(already_done)} existing batch file(s) will be kept.")

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
BATCH_SIZE = 5000

for batch_idx, start in enumerate(range(0, n_patents, BATCH_SIZE), start=1):
    t0 = time.time()

    batch_ids = patent_ids[start:start + BATCH_SIZE]
    batch_df = pl.DataFrame({"patent_id": batch_ids})

    out_path = TMP_DIR / f"focal_batch_{batch_idx:05d}.parquet"

    if out_path in already_done:
        batch_files.append(out_path)
        print(f"\nBatch {batch_idx} | skipped (already done)")
        continue

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
        del pat_terms, batch_df
        gc.collect()
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

    # Per-paper term frequencies for linked PMIDs only: (pmid, term, freq_in_paper)
    pmed_terms = (
        pl.scan_parquet(PMED_PATH)
        .select([
            pl.col("pmid").cast(pl.Int64),
            "term"
        ])
        .filter(pl.col("term").is_not_null())
        .join(pmids.lazy(), on="pmid", how="inner")
        .group_by(["pmid", "term"])
        .agg(pl.len().alias("freq_in_paper"))
        .collect()
    )

    if pmed_terms.height == 0:
        print("  No paper terms, skipping.")
        del pat_terms, links, pmids, pmed_terms, batch_df
        gc.collect()
        continue

    # Focal terms at (patent_id, pmid, term) level:
    # links ⋈ pmed_terms on pmid  →  expand to patent×paper×term triples
    # then ⋈ pat_terms on (patent_id, term)  →  keep only terms that also appear in the patent
    focal = (
        links
        .join(pmed_terms, on="pmid", how="inner")
        .join(pat_terms, on=["patent_id", "term"], how="inner")
        .select(["patent_id", "pmid", "term", "freq_in_patent", "freq_in_paper"])
        .rename({"term": "focal_term"})
    )

    if focal.height > 0:
        focal.write_parquet(out_path)
        batch_files.append(out_path)
        print(f"  Saved {focal.height:,} focal rows")
    else:
        print("  No focal terms in this batch.")

    del batch_df, pat_terms, links, pmids, pmed_terms, focal
    gc.collect()

    print(f"  Done in {elapsed(t0)}")

# =========================
# 3. Combine batch files
# =========================
print("\nCombining batch files...")

if not batch_files:
    print("No focal terms found. Writing empty parquet.")

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
        pl.col("pmid").n_unique().alias("n_pmids"),
        pl.col("focal_term").n_unique().alias("n_focal_terms"),
    ])
    .collect()
)

print("\n=== Task 1 summary ===")
print(stats)

print(f"\nTask 1 finished in {elapsed(t0_all)}")
