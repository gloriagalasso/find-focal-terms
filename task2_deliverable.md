# Task 2 — Descriptive Statistics and Distribution of Overlap

## Summary Statistics

| Metric | Value |
|---|---|
| Total (patent_id, focal_term) pairs | 790 |
| Unique patents | 101 |
| Unique focal terms | 494 |
| Mean focal terms per patent | 7.82 |
| Median focal terms per patent | 6.00 |
| Std Dev | 6.83 |
| Min | 1 |
| 25th percentile | 3 |
| 75th percentile | 11 |
| Max | 30 |

---

## Distribution Plot

![Histogram of Focal Terms per Patent](visualizations/histogram_focal_terms.png)

The histogram shows the number of focal terms per patent. The red dashed line marks the **mean (7.82)** and the orange dashed line marks the **median (6.00)**. The gap between mean and median confirms the distribution is **right-skewed** — a few patents with many focal terms pull the mean upward.

---

## Brief Descriptive Interpretation

The 101 patents share on average **7.8 focal terms** with their cited scientific papers, totalling **790 unique (patent_id, focal_term) pairs**. The distribution is right-skewed: most patents have few focal terms, while a small number have many.

**Examples:**

| Patent ID | Focal Terms (n) | Focal Terms |
|---|---|---|
| 7749408 | 1 (min) | *"room"* |
| 7884261 | 6 (median) | *"increase", "plant", "promoter", "rice", "transgenic", "yield"* |
| 8280136 | 30 (max) | *"cardiac", "heart", "dyssynchrony", "myocardial", "device", "model", ...* |
