import os
os.environ.setdefault("POLARS_MAX_THREADS", "2")

import gc
import re
import time
import json
from pathlib import Path
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

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
CHUNK_SIZE  = 50_000

ABSTRACT_SCHEMA = pa.schema([
    ("patent_id", pa.string()),
    ("focal_term", pa.string()),
    ("pmid", pa.int64()),
    ("context", pa.string()),
    ("source", pa.string()),
])
CLAIMS_SCHEMA = pa.schema([
    ("patent_id", pa.string()),
    ("focal_term", pa.string()),
    ("claim_number", pa.int32()),
    ("context", pa.string()),
    ("source", pa.string()),
])


def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"


def extract_sentence_window(text: str, term: str, window: int = 1) -> str | None:
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


def flush_to_parquet(writer, results, schema):
    if not results:
        return
    table = pa.table({col: [r[col] for r in results] for col in schema.names}, schema=schema)
    writer.write_table(table)
    del table


print("=== TASK 4: Context Extraction ===")
t0_all = time.time()

# =========================
# STEP 1: Load focal terms (only needed columns)
# =========================
print("\nStep 1: Loading focal terms...")
t0 = time.time()

focal = pl.read_parquet(FOCAL_PATH, columns=["patent_id", "focal_term"])
if SAMPLE_SIZE > 0:
    focal = focal.head(SAMPLE_SIZE)
    print(f"  SAMPLE MODE: using {SAMPLE_SIZE} rows")

print(f"  {len(focal):,} focal term rows | {elapsed(t0)}")

# Build patent_id → [focal_terms] dict, then free the dataframe
focal_terms_by_patent: dict[str, list[str]] = {}
for row in focal.unique().iter_rows(named=True):
    focal_terms_by_patent.setdefault(row["patent_id"], []).append(row["focal_term"])

patent_ids_needed = set(focal_terms_by_patent.keys())
n_focal = len(focal)
del focal
gc.collect()

print(f"  {len(patent_ids_needed):,} unique patents")

# =========================
# STEP 2: Build patent_id → PMID mapping
# =========================
print("\nStep 2: Building patent-PMID mapping...")
t0 = time.time()

pmids_by_patent: dict[str, list[int]] = {}
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
for row in link.iter_rows(named=True):
    pmids_by_patent.setdefault(row["patent_id"], []).append(row["pmid_int"])
del link
gc.collect()

all_pmids = set()
for pmid_list in pmids_by_patent.values():
    all_pmids.update(pmid_list)

print(f"  {len(pmids_by_patent):,} patents with PMIDs, {len(all_pmids):,} unique PMIDs | {elapsed(t0)}")

# =========================
# STEP 3: Extract context from abstracts (streamed to disk)
# =========================
print("\nStep 3: Extracting context from abstracts...")
t0 = time.time()

abstract_map: dict[int, str] = {}
abstracts = (
    pl.scan_parquet(ABSTRACT_PATH)
    .filter(pl.col("PMID").is_in(all_pmids))
    .filter(pl.col("AbstractText").is_not_null())
    .select("PMID", "AbstractText")
    .collect()
)
for row in abstracts.iter_rows(named=True):
    abstract_map[row["PMID"]] = row["AbstractText"]
del abstracts, all_pmids
gc.collect()
print(f"  {len(abstract_map):,} abstracts loaded")

count_abstract = 0
writer_abs = pq.ParquetWriter(CONTEXT_ABSTRACT_PATH, ABSTRACT_SCHEMA)
buffer = []

for patent_id, terms in focal_terms_by_patent.items():
    pmids = pmids_by_patent.get(patent_id)
    if not pmids:
        continue
    for pmid in pmids:
        text = abstract_map.get(pmid)
        if not text:
            continue
        for term in terms:
            context = extract_sentence_window(text, term)
            if context:
                buffer.append({
                    "patent_id": patent_id,
                    "focal_term": term,
                    "pmid": pmid,
                    "context": context,
                    "source": "abstract",
                })
    if len(buffer) >= CHUNK_SIZE:
        flush_to_parquet(writer_abs, buffer, ABSTRACT_SCHEMA)
        count_abstract += len(buffer)
        buffer.clear()

flush_to_parquet(writer_abs, buffer, ABSTRACT_SCHEMA)
count_abstract += len(buffer)
buffer.clear()
writer_abs.close()

del abstract_map, pmids_by_patent
gc.collect()

print(f"  {count_abstract:,} abstract contexts extracted | {elapsed(t0)}")

# =========================
# STEP 4: Extract context from patent claims (streamed to disk)
# =========================
print("\nStep 4: Extracting context from patent claims...")
t0 = time.time()

# Keep only the longest claim per (patent_id, focal_term)
best_claim: dict[tuple[str, str], tuple[str, int]] = {}

for p in CLAIMS_PATHS:
    print(f"  Processing {p.name}...")
    claims = (
        pl.scan_parquet(p)
        .filter(pl.col("patent_id").is_in(patent_ids_needed))
        .select("patent_id", "claim_text", "claim_number")
        .collect()
    )

    for row in claims.iter_rows(named=True):
        terms = focal_terms_by_patent.get(row["patent_id"])
        if not terms:
            continue
        claim_lower = row["claim_text"].lower()
        for term in terms:
            if term.lower() in claim_lower:
                key = (row["patent_id"], term)
                prev = best_claim.get(key)
                if prev is None or len(row["claim_text"]) > len(prev[0]):
                    best_claim[key] = (row["claim_text"], row["claim_number"])

    del claims
    gc.collect()
    print(f"    done, {len(best_claim):,} unique (patent, term) pairs so far")

count_claims = 0
writer_cl = pq.ParquetWriter(CONTEXT_CLAIMS_PATH, CLAIMS_SCHEMA)
buffer = []

for (patent_id, focal_term), (context, claim_number) in best_claim.items():
    buffer.append({
        "patent_id": patent_id,
        "focal_term": focal_term,
        "claim_number": claim_number,
        "context": context,
        "source": "claims",
    })
    if len(buffer) >= CHUNK_SIZE:
        flush_to_parquet(writer_cl, buffer, CLAIMS_SCHEMA)
        count_claims += len(buffer)
        buffer.clear()

flush_to_parquet(writer_cl, buffer, CLAIMS_SCHEMA)
count_claims += len(buffer)
buffer.clear()
writer_cl.close()
del best_claim
gc.collect()

print(f"  {count_claims:,} claim contexts (one per patent-term) | {elapsed(t0)}")

# =========================
# STEP 5: Summary
# =========================
print(f"\n{'='*60}")
print(f"TASK 4 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"  Abstract contexts: {count_abstract:,} → {CONTEXT_ABSTRACT_PATH}")
print(f"  Claims contexts:   {count_claims:,} → {CONTEXT_CLAIMS_PATH}")
print(f"{'='*60}")

stats = {
    "abstract_contexts": count_abstract,
    "claims_contexts": count_claims,
    "focal_terms_input": n_focal,
    "sample_size": SAMPLE_SIZE if SAMPLE_SIZE > 0 else "full",
}
(OUT_DIR / "context_extraction.json").write_text(json.dumps(stats, indent=2))
