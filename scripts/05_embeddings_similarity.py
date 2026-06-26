import os
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import gc
import time
import json
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from transformers import AutoTokenizer, AutoModel

# =========================
# CONFIGURATION
# =========================
BASE     = Path(__file__).parent
DATA_DIR = BASE.parent / "data"
OUT_DIR  = BASE.parent / "output"
OUT_DIR.mkdir(exist_ok=True)

CONTEXT_ABSTRACT_PATH = OUT_DIR / "context_abstracts.parquet"
CONTEXT_CLAIMS_PATH   = OUT_DIR / "context_claims.parquet"

MODELS = {
    "pubmedbert": "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
    "biolord":    "FremyCompany/BioLORD-2023-C",
}

MODEL_KEY   = os.environ.get("MODEL", "pubmedbert").lower()
MODEL_NAME  = MODELS[MODEL_KEY]
MODEL_TAG   = MODEL_KEY

SIMILARITY_PATH = OUT_DIR / f"similarity_scores_{MODEL_TAG}.parquet"
AGGREGATE_PATH  = OUT_DIR / f"similarity_aggregate_{MODEL_TAG}.parquet"

BATCH_SIZE  = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
SAMPLE_SIZE = int(os.environ.get("SAMPLE_SIZE", "0"))
DEVICE      = "cuda" if torch.cuda.is_available() else "cpu"


def elapsed(t0):
    s = time.time() - t0
    return f"{s/60:.1f}m" if s >= 60 else f"{s:.1f}s"


def load_model(model_name):
    print(f"  Loading model: {model_name} on {DEVICE}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(DEVICE)
    model.eval()
    return tokenizer, model


@torch.no_grad()
def encode_texts(texts: list[str], tokenizer, model) -> np.ndarray:
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(DEVICE)
        outputs = model(**encoded)
        # Mean pooling (masked to ignore padding tokens)
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        summed = (outputs.last_hidden_state * mask).sum(dim=1)
        embs = (summed / mask.sum(dim=1)).cpu().numpy()
        all_embeddings.append(embs)
        del encoded, outputs, mask, summed
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
    return np.vstack(all_embeddings)


print(f"=== TASK 5: Embeddings & Pairwise Similarity ({MODEL_TAG}) ===")
t0_all = time.time()

# =========================
# STEP 1: Load model
# =========================
print(f"\nStep 1: Loading {MODEL_TAG}...")
t0 = time.time()
tokenizer, model = load_model(MODEL_NAME)
print(f"  Model loaded | {elapsed(t0)}")

# =========================
# STEP 2: Load context data
# =========================
print("\nStep 2: Loading context data...")
t0 = time.time()

abstracts = pl.read_parquet(CONTEXT_ABSTRACT_PATH)
claims = pl.read_parquet(CONTEXT_CLAIMS_PATH)

if SAMPLE_SIZE > 0:
    abstracts = abstracts.head(SAMPLE_SIZE)
    claims_patents = set(abstracts["patent_id"].unique().to_list())
    claims = claims.filter(pl.col("patent_id").is_in(claims_patents))
    print(f"  SAMPLE MODE: {SAMPLE_SIZE} abstract rows")

print(f"  {len(abstracts):,} abstract contexts, {len(claims):,} claim contexts | {elapsed(t0)}")

# =========================
# STEP 3: Embed claim contexts (patent side)
# =========================
print("\nStep 3: Embedding patent claim contexts...")
t0 = time.time()

claim_texts = claims["context"].to_list()
claim_embeddings = encode_texts(claim_texts, tokenizer, model)
del claim_texts
gc.collect()

claims = claims.with_columns(
    pl.Series("emb_idx", list(range(len(claims))))
)
claim_emb_by_key: dict[tuple[str, str], np.ndarray] = {}
for row in claims.iter_rows(named=True):
    key = (row["patent_id"], row["focal_term"])
    claim_emb_by_key[key] = claim_embeddings[row["emb_idx"]]

del claim_embeddings, claims
gc.collect()

print(f"  {len(claim_emb_by_key):,} unique (patent, term) claim embeddings | {elapsed(t0)}")

# =========================
# STEP 4: Embed abstract contexts (paper side)
# =========================
print("\nStep 4: Embedding abstract contexts...")
t0 = time.time()

abstract_texts = abstracts["context"].to_list()
abstract_embeddings = encode_texts(abstract_texts, tokenizer, model)
del abstract_texts, tokenizer, model
gc.collect()
if DEVICE == "cuda":
    torch.cuda.empty_cache()

print(f"  {len(abstract_embeddings):,} abstract embeddings | {elapsed(t0)}")

# =========================
# STEP 5: Pairwise cosine similarity
# =========================
print("\nStep 5: Computing pairwise similarities...")
t0 = time.time()

SIMILARITY_SCHEMA = pa.schema([
    ("patent_id", pa.string()),
    ("focal_term", pa.string()),
    ("pmid", pa.int64()),
    ("cosine_similarity", pa.float32()),
])

writer = pq.ParquetWriter(SIMILARITY_PATH, SIMILARITY_SCHEMA)
buffer = []
n_pairs = 0
n_matched = 0

for i, row in enumerate(abstracts.iter_rows(named=True)):
    key = (row["patent_id"], row["focal_term"])
    claim_emb = claim_emb_by_key.get(key)
    if claim_emb is None:
        continue

    abs_emb = abstract_embeddings[i]
    cos_sim = float(
        np.dot(claim_emb, abs_emb)
        / (np.linalg.norm(claim_emb) * np.linalg.norm(abs_emb) + 1e-8)
    )

    buffer.append({
        "patent_id": row["patent_id"],
        "focal_term": row["focal_term"],
        "pmid": row["pmid"],
        "cosine_similarity": cos_sim,
    })
    n_matched += 1

    if len(buffer) >= 50_000:
        table = pa.table(
            {col: [r[col] for r in buffer] for col in SIMILARITY_SCHEMA.names},
            schema=SIMILARITY_SCHEMA,
        )
        writer.write_table(table)
        del table
        n_pairs += len(buffer)
        buffer.clear()

if buffer:
    table = pa.table(
        {col: [r[col] for r in buffer] for col in SIMILARITY_SCHEMA.names},
        schema=SIMILARITY_SCHEMA,
    )
    writer.write_table(table)
    n_pairs += len(buffer)
    buffer.clear()
    del table

writer.close()
del abstract_embeddings, claim_emb_by_key, abstracts
gc.collect()

print(f"  {n_pairs:,} pairwise similarities computed | {elapsed(t0)}")

# =========================
# STEP 6: Aggregate metrics per (patent_id, focal_term)
# =========================
print("\nStep 6: Computing aggregate similarity metrics...")
t0 = time.time()

sim_df = pl.read_parquet(SIMILARITY_PATH)

agg = (
    sim_df
    .group_by("patent_id", "focal_term")
    .agg(
        pl.col("cosine_similarity").mean().alias("sim_mean"),
        pl.col("cosine_similarity").median().alias("sim_median"),
        pl.col("cosine_similarity").max().alias("sim_max"),
        pl.col("cosine_similarity").min().alias("sim_min"),
        pl.col("cosine_similarity").std().alias("sim_std"),
        pl.col("cosine_similarity").count().alias("n_papers"),
    )
)

agg.write_parquet(AGGREGATE_PATH)
print(f"  {len(agg):,} (patent, term) groups | {elapsed(t0)}")

del sim_df
gc.collect()

# =========================
# STEP 7: Summary
# =========================
print(f"\n{'='*60}")
print(f"TASK 5 COMPLETE | Total time: {elapsed(t0_all)}")
print(f"  Pairwise similarities: {n_pairs:,} → {SIMILARITY_PATH}")
print(f"  Aggregate metrics:     {len(agg):,} → {AGGREGATE_PATH}")
print(f"{'='*60}")

stats = {
    "model": MODEL_NAME,
    "device": DEVICE,
    "pairwise_similarities": n_pairs,
    "aggregate_groups": len(agg),
    "sample_size": SAMPLE_SIZE if SAMPLE_SIZE > 0 else "full",
}
(OUT_DIR / f"embeddings_similarity_{MODEL_TAG}.json").write_text(json.dumps(stats, indent=2))
