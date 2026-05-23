import polars as pl
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent
OUT_DIR = BASE / "output"

FOCAL_PATH = OUT_DIR / "focal_terms_full.parquet"

counts = (
    pl.scan_parquet(FOCAL_PATH)
    .group_by("patent_id")
    .agg(pl.col("focal_term").n_unique().alias("num_focal_terms"))
    .sort("patent_id")
    .collect()
)

values = counts["num_focal_terms"].to_numpy()

summary = pl.DataFrame({
    "statistic": ["mean", "median", "std", "min", "max", "n_patents", "n_exactly_1", "pct_exactly_1"],
    "value": [
        float(values.mean()),
        float(np.median(values)),
        float(values.std()),
        float(values.min()),
        float(values.max()),
        float(len(counts)),
        float((counts["num_focal_terms"] == 1).sum()),
        float((counts["num_focal_terms"] == 1).sum() / len(counts) * 100),
    ],
})

counts.write_csv(OUT_DIR / "focal_term_counts_per_patent_full.csv")
summary.write_csv(OUT_DIR / "task2_summary_stats_full.csv")

print(summary)

import matplotlib.pyplot as plt

# Create visualizations folder
VIZ_DIR = BASE / "visualizations"
VIZ_DIR.mkdir(parents=True, exist_ok=True)

# Histogram
plt.figure(figsize=(10, 6))

bins = range(
    int(values.min()),
    min(int(values.max()) + 2, 200)
)

plt.hist(
    values,
    bins=bins,
    edgecolor="black",
)

plt.axvline(values.mean(), linestyle="--", label=f"Mean = {values.mean():.2f}")
plt.axvline(np.median(values), linestyle="--", label=f"Median = {np.median(values):.2f}")

plt.title("Distribution of Focal Terms per Patent")
plt.xlabel("Number of Focal Terms")
plt.ylabel("Number of Patents")
plt.legend()

plt.tight_layout()

plt.savefig(
    VIZ_DIR / "histogram_focal_terms_full.png",
    dpi=300,
)

plt.close()

print(f"Saved histogram to {VIZ_DIR}")

# ─────────────────────────────────────────────
# Example patents with strongest overlap
# ─────────────────────────────────────────────

top_examples = (
    counts
    .sort("num_focal_terms", descending=True)
    .head(10)
)

top_examples.write_csv(
    OUT_DIR / "task2_top_patent_examples_full.csv"
)

print("\nTop 10 patents by focal-term overlap:")
print(top_examples)

# ─────────────────────────────────────────────
# Most and least frequent focal terms
# ─────────────────────────────────────────────

term_counts = (
    pl.scan_parquet(FOCAL_PATH)
    .group_by("focal_term")
    .agg(pl.len().alias("frequency"))
    .collect()
)

most_used = (
    term_counts
    .sort("frequency", descending=True)
    .head(20)
)

least_used = (
    term_counts
    .sort("frequency")
    .head(20)
)

most_used.write_csv(
    OUT_DIR / "most_used_focal_terms_full.csv"
)

least_used.write_csv(
    OUT_DIR / "least_used_focal_terms_full.csv"
)

print("\nMost used focal terms:")
print(most_used)

print("\nLeast used focal terms:")
print(least_used)