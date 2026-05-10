# Task 2 — Measure Overlap Intensity

## Summary Statistics

| Statistic | Value |
|-----------|-------|
| Total (patent_id, focal_term) pairs | 94 |
| Unique patents | 53 |
| Unique focal term strings | 56 |
| Mean focal terms per patent | 1.77 |
| Median focal terms per patent | 1.00 |
| Std Dev | 1.55 |
| Min | 1 focal term(s) |
| Max | 9 focal terms |
| Patents with exactly 1 focal term | 35 (66.0%) |
| Patents with 2+ focal terms | 18 (34.0%) |
| Patents with 5+ focal terms | 3 (5.7%) |

## Interpretation

The 53 patents in this sample share on average **1.77 focal terms** with their cited scientific papers (median = 1), giving **94 unique (patent_id, focal_term) pairs** across **56 distinct terms**.

The distribution is **strongly right-skewed**: most patents share only a single focal term with cited literature, while a small number show broader terminological overlap.

## Examples

- Patent **10000538** (min = 1 focal term): 'amount'
- Patent **10000537** (typical = 3 focal terms): 'sequence', 'transport', 'sugar'
- Patent **10005908** (max = 9 focal terms): 'streptavidin', 'avidin', 'biological', 'protein', 'molecule', 'cell', 'biotin', 'complex', 'bond'
