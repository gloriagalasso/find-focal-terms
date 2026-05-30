import json
import polars as pl
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

# =========================
# CONFIGURATION
# =========================
BASE    = Path(__file__).parent
OUT_DIR = BASE.parent / "output"
VIZ_DIR = BASE.parent / "visualizations"

FOCAL_PATH = OUT_DIR / "focal_terms_full.parquet"

VIZ_DIR.mkdir(parents=True, exist_ok=True)

print("=== TASK 2: Focal Terms Analysis ===\n")

# =========================
# STEP 1: Load focal terms and compute per-patent statistics
# =========================
print("Step 1: Computing focal terms per patent...")

# For each patent, count how many unique focal terms it has.
# A patent with many focal terms has broader overlap with cited papers.
counts = (
    pl.scan_parquet(FOCAL_PATH)
    .group_by("patent_id")
    .agg(pl.col("focal_term").n_unique().alias("num_focal_terms"))
    .sort("patent_id")
    .collect()
)

values = counts["num_focal_terms"].to_numpy()
print(f"  Computed for {len(counts):,} patents")
print(f"  Range: {int(values.min())} to {int(values.max())} focal terms per patent\n")

# =========================
# STEP 2: Compute summary statistics
# =========================
print("Step 2: Computing summary statistics...")

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

counts.write_parquet(OUT_DIR / "focal_term_counts_per_patent_full.parquet")

print(summary)
print()

# =========================
# STEP 3: Visualize distribution
# =========================
print("Step 3: Creating histogram of focal terms per patent...")

plt.figure(figsize=(10, 6))

# Use bins from min to max, capped at 200 for readability
bins = range(
    int(values.min()),
    min(int(values.max()) + 2, 200)
)

plt.hist(
    values,
    bins=bins,
    edgecolor="black",
    color="steelblue",
    alpha=0.7,
)

# Add lines for mean and median
plt.axvline(values.mean(), linestyle="--", linewidth=2, color="red", label=f"Mean = {values.mean():.2f}")
plt.axvline(np.median(values), linestyle="--", linewidth=2, color="orange", label=f"Median = {np.median(values):.2f}")

plt.title("Distribution of Focal Terms per Patent", fontsize=14, fontweight="bold")
plt.xlabel("Number of Focal Terms", fontsize=12)
plt.ylabel("Number of Patents", fontsize=12)
plt.legend()
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()

plt.savefig(VIZ_DIR / "histogram_focal_terms_full.png", dpi=300)
plt.close()

print(f"  Saved: {VIZ_DIR / 'histogram_focal_terms_full.png'}\n")

# =========================
# STEP 4: Find patents with strongest overlap
# =========================
print("Step 4: Identifying top 10 patents by focal-term overlap...")

top_examples = (
    counts
    .sort("num_focal_terms", descending=True)
    .head(10)
)


print("Top 10 patents by focal-term overlap:")
print(top_examples)
print()

# =========================
# STEP 5: Analyze focal term frequencies
# =========================
print("Step 5: Computing focal term frequencies...")

# Count how many patents each focal term appears in.
# A frequently appearing term has broad relevance across patents and papers.
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

term_counts.write_parquet(OUT_DIR / "term_frequency_full.parquet")

print("Most frequent focal terms (top 20):")
print(most_used)
print()

print("Least frequent focal terms (bottom 20):")
print(least_used)
print()

# =========================
# STEP 6: Export JSON summary
# =========================
print("Step 6: Exporting JSON summary...")

summary_row = summary.to_dicts()
json_path = OUT_DIR / "task2_analysis.json"
json_path.write_text(json.dumps({
    "summary_stats":   {r["statistic"]: r["value"] for r in summary_row},
    "top_10_patents":  top_examples.to_dicts(),
    "most_used_terms": most_used.to_dicts(),
    "least_used_terms": least_used.to_dicts(),
}, indent=2))
print(f"  JSON summary saved to: {json_path}\n")

print("=" * 60)
print("TASK 2 COMPLETE")
print("=" * 60)
