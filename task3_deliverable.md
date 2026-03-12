# Task 3 — Semantic Comparison Results

## Quantitative Similarity Measure

Cosine similarity was computed between the patent-context embedding and the paper-context embedding for each focal term. Scores range from -1 to 1, where 1 means identical context and 0 means unrelated.

| Statistic | Value |
|---|---|
| Mean | 0.352 |
| Median | 0.357 |
| Std Dev | 0.152 |
| Min | -0.008 |
| Max | 0.843 |

## Distribution Plot

![Histogram of Cosine Similarity](visualizations/cosine_similarity_distribution.png)

The distribution is approximately bell-shaped and centred around 0.35, indicating moderate but not high semantic alignment between patent and paper usage on average. The std of 0.15 shows meaningful variation across focal terms. Some are used in very similar contexts, others in quite different ones.

---

## Examples Illustrating Similarities and Differences

### High Similarity — Focal Terms Used in Similar Contexts

| Focal Term | Patent ID | Similarity | Patent Context (sample) | Paper Context (sample) |
|---|---|---|---|---|
| `asbestos-related` | 8168398 | 0.843 | mesothelioma, presence, method, human, assaying | mesothelioma, cancer, disease, presence, asbestos |
| `asbestos` | 8168398 | 0.820 | mesothelioma, presence, method, human, assaying | mesothelioma, cancer, enzyme-linked, presence |
| `presence` | 8168398 | 0.801 | mesothelioma, assaying, concluded, increased | mesothelioma, cancer, disease, asbestos, normal |
| `cocaine` | 8084204 | 0.792 | pocket, insoluble, release, indicator, method | pocket, insoluble, binding, ligand, selective |
| `risk` | 8168398 | 0.784 | mesothelioma, presence, method, human, increased | mesothelioma, cancer, chemoprevention, decline |

**Interpretation:** These focal terms belong to narrow, domain-specific topics (e.g. asbestos-related disease diagnosis). Patents and papers share a tight vocabulary, leading to high contextual alignment.

---

### Low Similarity — Focal Terms Used in Different Contexts

| Focal Term | Patent ID | Similarity | Patent Context (sample) | Paper Context (sample) |
|---|---|---|---|---|
| `first` | 7838242 | -0.008 | bacteria, listeria, delivery, method, release | insulin, hypoglycemia, pump, long-term, risk |
| `second` | 7838242 | -0.006 | bacteria, listeria, delivery, method, release | insulin, hypoglycemia, pump, long-term, risk |
| `group` | 7790843 | 0.010 | amino acid, sequence, 1-220, 221-454, seq | brain, cortex, morphometric, cerebral, region |
| `group` | 7754703 | 0.024 | hydroxyl, aryl, carbon, fluorine, chemical | insulin, immunosuppression, release, potent |
| `less` | 8052734 | 0.032 | width, hinge, expandable, sectional, mm | brachytherapy, stenting, intimal, clinical |

**Interpretation:** Generic terms like `group`, `first`, `second`, and `less` carry very different meanings depending on context. When the patent and its cited paper belong to different sub-fields, even shared terms reflect divergent usage.
