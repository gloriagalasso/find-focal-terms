#!/usr/bin/env python3
"""
Task 1 — Focal Terms Pipeline  (production-style)
===================================================
Memory-efficient processing for 100M+ row datasets using Polars lazy execution.

Stages
------
  0  Clean link file              → data/intermediate/link_clean_16042026.parquet
  1  Patent term frequencies      → data/intermediate/pat_term_counts_16042026.parquet
  2  PubMed term counts           → data/intermediate/pmed_term_counts_16042026.parquet
       (cited PMIDs only, counted per pmid+term before any patent join)
  3  Cited-paper freqs per patent → data/intermediate/cited_term_counts_16042026.parquet
  4  Focal terms (inner join)     → output/focal_terms_16042026.parquet

Run
---
  python pipeline_focal_terms.py
"""

import time
from pathlib import Path
from typing import Optional

import polars as pl

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT  = Path("/Users/gloria/Desktop/Hiwi")
DATA  = ROOT / "data" / "raw"
INTER = ROOT / "data" / "intermediate"
OUT   = ROOT / "output"

PAT_FILE  = DATA / "FullSampleGloria_Pat_GlinerLabels_16042026.parquet"
PMED_FILE = DATA / "FullSampleGloria_Pmed_GlinerLabels_16042026.parquet"
LINK_FILE = DATA / "FullSampleGloria_Link_PmidOa_16042026.parquet"

LINK_CLEAN_PATH   = INTER / "link_clean_16042026.parquet"
PAT_COUNTS_PATH   = INTER / "pat_term_counts_16042026.parquet"
PMED_COUNTS_PATH  = INTER / "pmed_term_counts_16042026.parquet"
CITED_COUNTS_PATH = INTER / "cited_term_counts_16042026.parquet"
FOCAL_TERMS_PATH  = OUT   / "focal_terms_16042026.parquet"

# ── Helpers ────────────────────────────────────────────────────────────────────
def _log(stage: str, msg: str, t0: Optional[float] = None) -> None:
    elapsed = f"  ({time.perf_counter() - t0:.1f}s)" if t0 is not None else ""
    print(f"[{time.strftime('%H:%M:%S')}] [{stage}] {msg}{elapsed}", flush=True)

def _normalize_term() -> pl.Expr:
    return pl.col("term").str.to_lowercase().str.strip_chars()

def _collect(lf: pl.LazyFrame) -> pl.DataFrame:
    """Collect with streaming when available, fall back to standard collect."""
    try:
        return lf.collect(engine="streaming")   # Polars >= 1.0
    except Exception:
        return lf.collect()

# ── Stage 0: Clean link ────────────────────────────────────────────────────────
def stage0_clean_link() -> None:
    t0 = time.perf_counter()
    _log("S0", "Loading and cleaning link file…")

    link_clean = (
        pl.scan_parquet(LINK_FILE).select(["patent_id", "pmid"])
        .filter(pl.col("pmid").is_not_null())
        .with_columns(
            pl.col("pmid").str.extract(r"(\d+)$").cast(pl.Int32, strict=False)
        )
        .filter(pl.col("pmid").is_not_null())
        .collect()                              # link is just ID pairs — load fully
    )
    link_clean.write_parquet(LINK_CLEAN_PATH)

    n_patents = link_clean["patent_id"].n_unique()
    n_pmids   = link_clean["pmid"].n_unique()
    _log("S0", f"link_clean {link_clean.shape}  |  {n_patents:,} patents  |  {n_pmids:,} PMIDs", t0)


# ── Stage 1: Patent term frequencies ──────────────────────────────────────────
def stage1_patent_term_counts() -> None:
    t0 = time.perf_counter()
    _log("S1", "Computing patent term frequencies (120M+ rows, lazy+streaming)…")

    _collect(
        pl.scan_parquet(PAT_FILE).select(["patent_id", "term"])
        .with_columns(_normalize_term())
        .filter(pl.col("term").is_not_null() & (pl.col("term") != ""))
        .group_by(["patent_id", "term"])
        .agg(pl.len().alias("freq_in_patent"))
    ).write_parquet(PAT_COUNTS_PATH)

    n = pl.scan_parquet(PAT_COUNTS_PATH).select(pl.len()).collect().item()
    _log("S1", f"pat_term_counts  →  {n:,} rows  →  {PAT_COUNTS_PATH.name}", t0)


# ── Stage 2: PubMed term counts (cited PMIDs only) ────────────────────────────
def stage2_pmed_term_counts() -> None:
    t0 = time.perf_counter()

    cited_pmids_lf = pl.scan_parquet(LINK_CLEAN_PATH).select("pmid").unique()
    n_cited = cited_pmids_lf.select(pl.len()).collect().item()
    _log("S2", f"Filtering PubMed to {n_cited:,} cited PMIDs, then counting per (pmid, term)…")

    # Key optimisation: count first (per pmid+term), join to patents later
    _collect(
        pl.scan_parquet(PMED_FILE).select(["pmid", "term"])
        .join(cited_pmids_lf, on="pmid", how="inner")   # filter to cited PMIDs only
        .with_columns(_normalize_term())
        .filter(pl.col("term").is_not_null() & (pl.col("term") != ""))
        .group_by(["pmid", "term"])
        .agg(pl.len().alias("freq_in_pmid"))
    ).write_parquet(PMED_COUNTS_PATH)

    n = pl.scan_parquet(PMED_COUNTS_PATH).select(pl.len()).collect().item()
    _log("S2", f"pmed_term_counts  →  {n:,} rows  →  {PMED_COUNTS_PATH.name}", t0)


# ── Stage 3: Cited-paper term frequencies per patent (chunked) ────────────────
def stage3_cited_term_counts(chunk_size: int = 50_000) -> None:
    """
    The naive join (link × pmed_term_counts) produces ~284M intermediate rows
    and blocks memory.  Instead we split the 870K unique patents into small
    batches and process each batch independently.  Patent-id sets are disjoint
    across batches, so the final step is a plain concatenation — no re-aggregation.
    """
    t0 = time.perf_counter()

    pmed_counts = pl.read_parquet(PMED_COUNTS_PATH)   # ~1 GB, kept for all chunks
    link_clean  = pl.read_parquet(LINK_CLEAN_PATH)

    patent_ids = link_clean["patent_id"].unique().shuffle(seed=42).to_list()
    n_chunks   = (len(patent_ids) + chunk_size - 1) // chunk_size
    _log("S3", f"Processing {len(patent_ids):,} patents in {n_chunks} chunks "
               f"of {chunk_size:,}…")

    chunk_paths: list[Path] = []
    for i, start in enumerate(range(0, len(patent_ids), chunk_size)):
        batch        = patent_ids[start : start + chunk_size]
        chunk_path   = INTER / f"_cited_chunk_{i:04d}.parquet"

        (
            link_clean
            .filter(pl.col("patent_id").is_in(batch))
            .join(pmed_counts, on="pmid", how="inner")
            .group_by(["patent_id", "term"])
            .agg(pl.col("freq_in_pmid").sum().alias("freq_in_cited"))
            .write_parquet(chunk_path)
        )
        chunk_paths.append(chunk_path)

        if (i + 1) % 5 == 0 or (i + 1) == n_chunks:
            _log("S3", f"  chunk {i+1}/{n_chunks}  "
                       f"({time.perf_counter() - t0:.0f}s elapsed)")

    # Patent-ids are disjoint across chunks → plain concat, no re-aggregation
    pl.concat([pl.read_parquet(p) for p in chunk_paths]).write_parquet(CITED_COUNTS_PATH)
    for p in chunk_paths:
        p.unlink()

    n = pl.scan_parquet(CITED_COUNTS_PATH).select(pl.len()).collect().item()
    _log("S3", f"cited_term_counts  →  {n:,} rows  →  {CITED_COUNTS_PATH.name}", t0)


# ── Stage 4: Focal terms ───────────────────────────────────────────────────────
def stage4_focal_terms() -> None:
    t0 = time.perf_counter()
    _log("S4", "Inner join patent × cited term counts to get focal terms…")

    focal_terms = (
        pl.scan_parquet(PAT_COUNTS_PATH)
        .join(pl.scan_parquet(CITED_COUNTS_PATH), on=["patent_id", "term"], how="inner")
        .rename({"term": "focal_terms"})
        .collect()
    )
    focal_terms.write_parquet(FOCAL_TERMS_PATH)

    _log("S4", f"focal_terms  →  {focal_terms.shape}  →  {FOCAL_TERMS_PATH.name}", t0)
    _log("S4", f"Unique patents    : {focal_terms['patent_id'].n_unique():,}")
    _log("S4", f"Unique focal terms: {focal_terms['focal_terms'].n_unique():,}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    INTER.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    t_total = time.perf_counter()
    _log("START", f"Polars {pl.__version__}")

    # S0–S2 already completed — comment them back in for a full re-run
    # stage0_clean_link()
    # stage1_patent_term_counts()
    # stage2_pmed_term_counts()
    stage3_cited_term_counts()
    stage4_focal_terms()

    _log("DONE", f"Total elapsed: {time.perf_counter() - t_total:.1f}s")


if __name__ == "__main__":
    main()
