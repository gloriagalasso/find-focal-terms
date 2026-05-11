Please update `task_1_2_3_16042026.ipynb` so that it reproduces the same methodology from Tasks 1, 2, and 3, but using the new FullSampleGloria datasets.

Important:
The files are large, so for now use only the first 5,000 rows from each dataset for testing/debugging.

Use these input datasets:

* `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Link_PmidOa_16042026.parquet`
* `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Pat_GlinerLabels_16042026.parquet`
* `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Pmed_GlinerLabels_16042026.parquet`

Save CSV/parquet outputs to:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs`

Save PNG visualizations to:

`/Users/gloria/Desktop/Hiwi/visualizations/fullsample_visualizations`

Create these folders if they do not exist.

Goal:
Reproduce the same logic of Task 1, Task 2, and Task 3 in one notebook, changing only the input datasets and output paths.

## Task 1 — Identify Focal Terms

Goal:
Find terms that appear both in a patent and in its cited scientific papers.

Steps:

1. Load the first 5,000 rows of the patent GLiNER labels dataset:
   `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Pat_GlinerLabels_16042026.parquet`

2. Keep at least:

   * `patent_id`
   * `term`

3. Group by:

   * `patent_id`
   * `term`

   and count occurrences as:

   * `freq_in_patent`

4. Load the first 5,000 rows of the patent–PMID/OA link dataset:
   `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Link_PmidOa_16042026.parquet`

5. Clean the link table:

   * drop rows without PMID/OA information
   * extract numeric PMID from URL or PMID field using regex `(\d+)$`
   * create clean `(patent_id, pmid)` pairs
   * remove duplicate `(patent_id, pmid)` pairs

6. Load the first 5,000 rows of the PubMed GLiNER labels dataset:
   `/Users/gloria/Desktop/Hiwi/data/raw/FullSampleGloria_Pmed_GlinerLabels_16042026.parquet`

7. Keep at least:

   * `pmid`
   * `term`

8. Join paper terms with the cleaned link table to attach `patent_id`.

9. Group cited paper terms by:

   * `patent_id`
   * `term`

   and count/sum occurrences as:

   * `freq_in_cited_papers`

10. Identify focal terms by inner-joining patent terms and cited paper terms on:

* `patent_id`
* `term`

11. Save focal terms as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/focal_terms_fullsample_5000.parquet`

Also save a CSV version:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/focal_terms_fullsample_5000.csv`

12. Print sanity checks:

* number of patent rows loaded
* number of link rows loaded
* number of paper rows loaded
* number of unique patents in patent terms
* number of unique PMIDs in link table
* number of unique PMIDs in paper terms
* number of cleaned patent–PMID links
* number of focal terms
* number of unique patents with focal terms
* number of unique focal terms

## Task 2 — Measure Overlap Intensity

Goal:
Measure how many focal terms each patent shares with its cited scientific papers.

Steps:

1. Load/use the focal terms from Task 1.

2. Count unique focal terms per patent:

   * group by `patent_id`
   * count unique `focal_term`

3. Compute summary statistics:

   * mean
   * median
   * standard deviation
   * min
   * max
   * number of patents
   * percentage of patents with exactly 1 focal term

4. Save the per-patent focal-term counts as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/focal_term_counts_per_patent_fullsample_5000.csv`

5. Create visualizations:

   * histogram of focal terms per patent
   * density/KDE plot of focal terms per patent

6. Save visualizations as:

`/Users/gloria/Desktop/Hiwi/visualizations/fullsample_visualizations/histogram_focal_terms_fullsample_5000.png`

`/Users/gloria/Desktop/Hiwi/visualizations/fullsample_visualizations/density_focal_terms_fullsample_5000.png`

7. Print and save summary statistics as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/task2_summary_stats_fullsample_5000.csv`

## Task 3 — Semantic Context Comparison

Goal:
Assess whether focal terms are used in similar or different semantic contexts in patents versus cited scientific papers.

Steps:

1. Use focal terms from Task 1.

2. Map each `(patent_id, focal_term)` to the cited PMIDs that contain that focal term.

3. Build contexts for each `(patent_id, focal_term)`:

Patent context:

* all other terms in the same patent
* exclude the focal term itself

Paper context:

* all other terms from cited PMIDs that contain the focal term
* exclude the focal term itself

4. Serialize contexts into strings:

Patent context sentence:
`<focal_term> <patent_context_term_1> <patent_context_term_2> ...`

Paper context sentence:
`<focal_term> <paper_context_term_1> <paper_context_term_2> ...`

The focal term should be prepended once to anchor the embedding.

5. Generate embeddings using:

`sentence-transformers/all-MiniLM-L6-v2`

Use a reasonable batch size, for example:
`batch_size=256`

6. Compute row-wise cosine similarity between patent-context embeddings and paper-context embeddings.

7. Save context table as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/focal_term_context_fullsample_5000.parquet`

and CSV:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/focal_term_context_fullsample_5000.csv`

8. Save cosine similarity results as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/cosine_similarity_results_fullsample_5000.parquet`

and CSV:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/cosine_similarity_results_fullsample_5000.csv`

9. Create visualization:

   * histogram/density plot of cosine similarity scores

Save as:

`/Users/gloria/Desktop/Hiwi/visualizations/fullsample_visualizations/cosine_similarity_distribution_fullsample_5000.png`

10. Print and save cosine similarity summary statistics:

* mean
* median
* standard deviation
* min
* max

Save as:

`/Users/gloria/Desktop/Hiwi/output/fullsample_outputs/task3_cosine_summary_stats_fullsample_5000.csv`

## General notebook requirements

1. Keep the notebook clean and structured with markdown sections:

   * Imports and paths
   * Data loading
   * Task 1: focal terms
   * Task 2: overlap intensity
   * Task 3: semantic context comparison
   * Final summary

2. Use clear intermediate sanity checks after each join/filter/grouping.

3. Add comments explaining each step.

4. Do not change the methodology except where needed to handle the new larger datasets or column names.

5. If a column name differs from the previous notebooks, inspect and adapt the code safely.

6. If the first 5,000 rows produce zero focal terms because the sampled rows do not overlap, print a clear warning and explain that this may be due to row slicing rather than pipeline failure.

7. The purpose is to verify the pipeline on the FullSampleGloria datasets before scaling to the full files.
