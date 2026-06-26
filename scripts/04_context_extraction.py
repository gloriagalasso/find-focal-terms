import os
os.environ.setdefault("POLARS_MAX_THREADS", "4")

import re
import time
import json
from pathlib import Path
import polars as pl

# =========================
# CONFIGURATION
# =========================
BASE     = Path(__file__).parent
DATA_DIR = BASE.parent / "data"
OUT_DIR  = BASE.parent / "output"
OUT_DIR.mkdir(exist_ok=True)

FOCAL_PATH    = DATA_DIR / "outcomes_01_focal_terms_full.parquet"
LINK_PATH     = DATA_DIR / "FullSampleGloria_Link_PmidOa_16042026.parquet"
ABSTRACT_PATH = DATA_DIR / "A04_Abstract_filtered.parquet"
CLAIMS_PATHS  = sorted(DATA_DIR.glob("C15_claims_*.parquet"))

CONTEXT_ABSTRACT_PATH = OUT_DIR / "context_abstracts.parquet"
CONTEXT_CLAIMS_PATH   = OUT_DIR / "context_claims.parquet"

SAMPLE_SIZE = int(os.environ.get("SAMPLE_SIZE", "0"))

def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"


def extract_sentence_window(text: str, term: str, window: int = 1) -> str | None:
    """Extract the sentence containing `term` plus `window` sentences before/after."""
    if not text or not term:
        return None
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    term_lower = term.lower()
    for i, sent in enumerate(sentences):
        if term_lower in sent.lower():
            start = max(0, i - window)
            end = min(len(sentences), i + window + 1)
            return " ".join(sentences[start:end])
    return None


print("=== TASK 4: Context Extraction ===")
t0_all = time.time()

# =========================
# STEP 1: Load focal terms
# =========================
print("\nStep 1: Loading focal terms...")
t0 = time.time()

focal = pl.read_parquet(FOCAL_PATH)
if SAMPLE_SIZE > 0:
    focal = focal.head(SAMPLE_SIZE)
    print(f"  SAMPLE MODE: using {SAMPLE_SIZE} rows")

print(f"  {len(focal):,} focal term rows | {elapsed(t0)}")

# =========================
# STEP 2: Build patent_id → PMID mapping
# =========================
print("\nStep 2: Building patent-PMID mapping...")
t0 = time.time()

patent_ids_needed = set(focal["patent_id"].unique().to_list())

link = (
    pl.scan_parquet(LINK_PATH)
    .filter(pl.col("patent_id").is_in(patent_ids_needed))
    .filter(pl.col("pmid").is_not_null())
    .with_columns(
        pl.col("pmid").cast(pl.String).str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("pmid_int")
    )
    .filter(pl.col("pmid_int").is_not_null())
    .select("patent_id", "pmid_int")
    .unique()
    .collect()
)

print(f"  {len(link):,} patent-PMID pairs | {elapsed(t0)}")

# =========================
# STEP 3: Extract context from abstracts
# =========================
print("\nStep 3: Extracting context from abstracts...")
t0 = time.time()

focal_with_pmid = (
    focal.select("patent_id", "focal_term")
    .join(link, on="patent_id", how="inner")
)
print(f"  {len(focal_with_pmid):,} (patent, term, pmid) triples to search")

pmids_needed = set(focal_with_pmid["pmid_int"].unique().to_list())

abstract_map: dict[int, str] = {}
abstracts = (
    pl.scan_parquet(ABSTRACT_PATH)
    .filter(pl.col("PMID").is_in(pmids_needed))
    .filter(pl.col("AbstractText").is_not_null())
    .select("PMID", "AbstractText")
    .collect()
)
for row in abstracts.iter_rows(named=True):
    abstract_map[row["PMID"]] = row["AbstractText"]
del abstracts

print(f"  {len(abstract_map):,} abstracts loaded")

results_abstract = []
for row in focal_with_pmid.iter_rows(named=True):
    text = abstract_map.get(row["pmid_int"])
    if not text:
        continue
    context = extract_sentence_window(text, row["focal_term"])
    if context:
        results_abstract.append({
            "patent_id": row["patent_id"],
            "focal_term": row["focal_term"],
            "pmid": row["pmid_int"],
            "context": context,
            "source": "abstract",
        })

df_abstract = pl.DataFrame(results_abstract)
df_abstract.write_parquet(CONTEXT_ABSTRACT_PATH)
print(f"  {len(df_abstract):,} abstract contexts extracted | {elapsed(t0)}")

del focal_with_pmid, abstract_map, results_abstract

# =========================
# STEP 4: Extract context from patent claims
# =========================
print("\nStep 4: Extracting context from patent claims...")
t0 = time.time()

focal_terms_by_patent: dict[str, list[str]] = {}
for row in focal.select("patent_id", "focal_term").unique().iter_rows(named=True):
    focal_terms_by_patent.setdefault(row["patent_id"], []).append(row["focal_term"])

results_claims = []

# Process one claims file at a time, never holding all in memory
for p in CLAIMS_PATHS:
    print(f"  Processing {p.name}...")
    claims = (
        pl.scan_parquet(p)
        .filter(pl.col("patent_id").is_in(patent_ids_needed))
        .select("patent_id", "claim_text")
        .collect()
    )

    for row in claims.iter_rows(named=True):
        terms = focal_terms_by_patent.get(row["patent_id"])
        if not terms:
            continue
        claim_lower = row["claim_text"].lower()
        for term in terms:
            if term.lower() in claim_lower:
                results_claims.append({
                    "patent_id": row["patent_id"],
                    "focal_term": term,
                    "context": row["claim_text"],
                    "source": "claims",
                })

    del claims
    print(f"    done, {len(results_claims):,} matches so far")

df_claims = pl.DataFrame(results_claims)
df_claims.write_parquet(CONTEXT_CLAIMS_PATH)
print(f"  {len(df_claims):,} claim contexts extracted | {elapsed(t0)}")

# =========================
# STEP 5: Summary
# =========================
print(f"\n{'='*60}")
print(f"TASK 4 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"  Abstract contexts: {len(df_abstract):,} → {CONTEXT_ABSTRACT_PATH}")
print(f"  Claims contexts:   {len(df_claims):,} → {CONTEXT_CLAIMS_PATH}")
print(f"{'='*60}")

stats = {
    "abstract_contexts": len(df_abstract),
    "claims_contexts": len(df_claims),
    "focal_terms_input": len(focal),
    "sample_size": SAMPLE_SIZE if SAMPLE_SIZE > 0 else "full",
}
(OUT_DIR / "context_extraction.json").write_text(json.dumps(stats, indent=2))
