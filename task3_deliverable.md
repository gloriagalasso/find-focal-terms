# Task 3 — Semantic Comparison Results

## Quantitative Similarity Measure

Cosine similarity was computed between the patent-context embedding and the paper-context embedding for each focal term. Scores range from -1 to 1, where 1 means identical context and 0 means unrelated.

| Statistic | Value |
|---|---|
| Mean | 0.441 |
| Median | 0.443 |
| Std Dev | 0.140 |
| Min | -0.008 |
| Max | 0.843 |

## Distribution Plot

![Histogram of Cosine Similarity](visualizations/cosine_similarity_distribution.png)

The distribution is approximately bell-shaped and centred around 0.44, indicating moderate semantic alignment between patent and paper usage on average. The std of 0.14 shows meaningful variation across focal terms. Some are used in very similar contexts, others in quite different ones.

---

## Cosine Similarity per Focal Term

| Patent ID | Focal Term | Cosine Similarity |
|---|---|---|
| 7662783 | alpha | 0.363 |
| 7662783 | antagonist | 0.353 |
| 7662783 | cell | 0.337 |
| 7662783 | collagen | 0.365 |
| 7662783 | colon | 0.374 |
| 7662783 | effect | 0.258 |
| 7662783 | effective | 0.324 |
| 7662783 | growth | 0.378 |
| 7662783 | lung | 0.350 |
| 7662783 | melanoma | 0.370 |
| 7662783 | peptide | 0.392 |
| 7662783 | proliferation | 0.390 |
| 7662783 | sequence | 0.147 |
| 7662783 | skin | 0.348 |
| 7662783 | treatment | 0.369 |
| 7662783 | tumor | 0.372 |
| 7700783 | agent | 0.173 |
| 7700783 | hydroxyl | 0.276 |
| 7704363 | and | 0.285 |
| 7704363 | concentration | 0.433 |
| 7704363 | maximum | 0.292 |
| 7704363 | presence | 0.360 |
| 7723513 | bis | 0.536 |
| 7723513 | copper | 0.565 |
| 7723513 | coupling | 0.572 |
| 7723513 | dichloromethane | 0.421 |
| 7723513 | dipyrrinato | 0.552 |
| 7723513 | metal | 0.546 |
| 7723513 | palladium | 0.587 |
| 7723513 | reaction | 0.558 |
| 7723513 | solvent | 0.398 |
| 7723513 | toluene | 0.582 |
| 7723513 | zinc | 0.594 |
| 7741269 | exendin-4 | 0.379 |
| 7741269 | peptide | 0.294 |
| 7741269 | sequence | 0.255 |
| 7741269 | treatment | 0.268 |
| 7749408 | room | 0.340 |
| 7754703 | aryl | 0.256 |
| 7754703 | compound | 0.147 |
| 7754703 | group | 0.024 |
| 7754703 | phosphate | 0.101 |
| 7754703 | phosphonate | 0.265 |
| 7754860 | hormone | 0.418 |
| 7754860 | mg | 0.427 |
| 7754860 | recombinant | 0.409 |
| 7754909 | solution | 0.349 |
| 7766658 | diagnosis | 0.470 |
| 7766658 | disease | 0.452 |
| 7766658 | drug | 0.336 |
