"""
POS-based error analysis of GLiNER span extraction vs. BioRED gold entities.

Input: scripts/matched_biored.json (produced by 01_prepare_matched_biored.py)
       48 BioRED documents matched to FullSampleGloria_Pmed_GlinerLabels.parquet by pmid.

Pipeline per document:
  1. POS-tag the full document text once with scispaCy (en_core_sci_md),
     so gold/predicted spans are tagged in their original sentence context
     (per instructions.md), not in isolation.
  2. Build gold spans (from BioRED annotations) and predicted spans (GLiNER
     terms located via first-occurrence text search in 01_prepare_matched_biored.py;
     terms not found verbatim in text are excluded from span matching but
     counted separately).
  3. One-to-one span matching: for every (gold, pred) pair with character-span
     overlap, compute overlap = intersection_len / union_len. Solve one-to-one
     assignment greedily: sort all overlapping pairs by score desc (ties broken
     by larger gold span, then earlier gold start, then earlier pred start),
     accept a pair if both sides are still free. This guarantees no gold entity
     or prediction is used in more than one match, and prioritizes largest
     overlap first as instructed.
  4. Classify: exact_match (identical boundaries), partial_match (overlap>0,
     boundaries differ), no_match (gold entity or prediction left unmatched).
  5. For partial matches, derive missing/added tokens and POS via scispaCy
     token spans intersected with gold/pred character ranges, and boundary
     error direction (LEFT/RIGHT/BOTH).

Outputs:
  pos_analysis_test_500.csv    -- detailed per-pair record (name kept per
                                   instructions.md template; N=48 docs here,
                                   not 500, see summary for the reported count)
  pos_analysis_test_500.json   -- same detailed records, JSON (per explicit request)
  pos_analysis_summary.json    -- all summary statistics (JSON, primary deliverable)
  pos_analysis_manual_sample.csv / .json -- ~50 random partial-match cases, random_state=42
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import spacy

BASE = Path("/Users/vincenzomula/Documents/hiwi_gloria")
MATCHED = BASE / "scripts/matched_biored.json"
OUT_CSV = BASE / "pos_analysis_test_500.csv"
OUT_JSON = BASE / "pos_analysis_test_500.json"
SUMMARY_JSON = BASE / "pos_analysis_summary.json"
MANUAL_CSV = BASE / "pos_analysis_manual_sample.csv"
MANUAL_JSON = BASE / "pos_analysis_manual_sample.json"

RANDOM_STATE = 42


def overlap_score(a_start, a_end, b_start, b_end):
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    if inter == 0:
        return 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    return inter / union


def one_to_one_match(gold_spans, pred_spans):
    """gold_spans/pred_spans: list of dicts with start/end. Returns list of
    (gold_idx, pred_idx, score) matched pairs, greedy by score desc."""
    candidates = []
    for gi, g in enumerate(gold_spans):
        for pi, p in enumerate(pred_spans):
            score = overlap_score(g["start"], g["end"], p["start"], p["end"])
            if score > 0:
                span_len = g["end"] - g["start"]
                candidates.append((score, span_len, g["start"], p["start"], gi, pi))
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2], c[3]))

    matched_gold, matched_pred = set(), set()
    pairs = []
    for score, _, _, _, gi, pi in candidates:
        if gi in matched_gold or pi in matched_pred:
            continue
        matched_gold.add(gi)
        matched_pred.add(pi)
        pairs.append((gi, pi, score))
    return pairs, matched_gold, matched_pred


def tokens_in_span(doc, start, end):
    """Return list of spaCy tokens whose char span overlaps [start,end)."""
    return [t for t in doc if t.idx < end and (t.idx + len(t.text)) > start]


def boundary_error_direction(gold_start, gold_end, pred_start, pred_end):
    left_diff = pred_start != gold_start
    right_diff = pred_end != gold_end
    if left_diff and right_diff:
        return "BOTH"
    if left_diff:
        return "LEFT"
    if right_diff:
        return "RIGHT"
    return None


def diff_tokens(gold_toks, pred_toks):
    gold_set = {(t.idx, t.text) for t in gold_toks}
    pred_set = {(t.idx, t.text) for t in pred_toks}
    missing = [t for t in gold_toks if (t.idx, t.text) not in pred_set]
    added = [t for t in pred_toks if (t.idx, t.text) not in gold_set]
    return missing, added


def missing_side(tok, pred_start, pred_end):
    """A missing (gold-only) token is LEFT if it falls before the predicted
    span's start, RIGHT if it falls at/after the predicted span's end."""
    if tok.idx < pred_start:
        return "LEFT"
    if tok.idx >= pred_end:
        return "RIGHT"
    return "MIDDLE"


def added_side(tok, gold_start, gold_end):
    """An added (prediction-only) token is LEFT if it falls before the gold
    span's start, RIGHT if it falls at/after the gold span's end."""
    if tok.idx < gold_start:
        return "LEFT"
    if tok.idx >= gold_end:
        return "RIGHT"
    return "MIDDLE"


def main():
    print("Loading spaCy en_core_sci_md ...")
    nlp = spacy.load("en_core_sci_md")

    print("Loading matched BioRED/GLiNER data ...")
    records = json.loads(MATCHED.read_text())
    print(f"  {len(records)} matched documents")

    detailed_rows = []
    n_excluded_not_found = 0
    n_gold_total = 0
    n_pred_total = 0

    match_counts = Counter()  # exact_match / partial_match / no_match(gold) / no_match(pred)

    for rec in records:
        pmid = rec["pmid"]
        text = rec["text"]
        doc = nlp(text)

        gold_spans = [
            {"start": e["start"], "end": e["end"], "text": e["text"], "label": e["type"]}
            for e in rec["gold_entities"]
        ]
        pred_all = rec["gliner_terms"]
        n_pred_total += len(pred_all)
        pred_spans = []
        for p in pred_all:
            if p["text_not_found"]:
                n_excluded_not_found += 1
                continue
            pred_spans.append({"start": p["start"], "end": p["end"], "text": p["matched_text"]})

        n_gold_total += len(gold_spans)

        pairs, matched_gold, matched_pred = one_to_one_match(gold_spans, pred_spans)

        # matched pairs: exact or partial
        for gi, pi, score in pairs:
            g, p = gold_spans[gi], pred_spans[pi]
            is_exact = g["start"] == p["start"] and g["end"] == p["end"]
            match_type = "exact_match" if is_exact else "partial_match"
            match_counts[match_type] += 1

            gold_toks = tokens_in_span(doc, g["start"], g["end"])
            pred_toks = tokens_in_span(doc, p["start"], p["end"])
            gold_pos = " ".join(t.pos_ for t in gold_toks)
            pred_pos = " ".join(t.pos_ for t in pred_toks)

            row = {
                "patent_id": pmid,  # kept as pmid; column name preserved per instructions.md template
                "pmid": pmid,
                "gold_label": g["label"],
                "predicted_label": None,
                "gold_span": g["text"],
                "predicted_span": p["text"],
                "gold_start": g["start"],
                "gold_end": g["end"],
                "pred_start": p["start"],
                "pred_end": p["end"],
                "match_type": match_type,
                "boundary_error": None,
                "missing_left": "",
                "missing_right": "",
                "added_left": "",
                "added_right": "",
                "missing_tokens": "",
                "missing_pos": "",
                "added_tokens": "",
                "added_pos": "",
                "gold_pos_pattern": gold_pos,
                "predicted_pos_pattern": pred_pos,
                "overlap_score": round(score, 4),
            }

            if match_type == "partial_match":
                missing, added = diff_tokens(gold_toks, pred_toks)
                b_err = boundary_error_direction(g["start"], g["end"], p["start"], p["end"])
                row["boundary_error"] = b_err
                row["missing_tokens"] = " ".join(t.text for t in missing)
                row["missing_pos"] = " ".join(t.pos_ for t in missing)
                row["added_tokens"] = " ".join(t.text for t in added)
                row["added_pos"] = " ".join(t.pos_ for t in added)
                row["missing_left"] = " ".join(
                    t.text for t in missing if missing_side(t, p["start"], p["end"]) == "LEFT"
                )
                row["missing_right"] = " ".join(
                    t.text for t in missing if missing_side(t, p["start"], p["end"]) == "RIGHT"
                )
                row["added_left"] = " ".join(
                    t.text for t in added if added_side(t, g["start"], g["end"]) == "LEFT"
                )
                row["added_right"] = " ".join(
                    t.text for t in added if added_side(t, g["start"], g["end"]) == "RIGHT"
                )

            detailed_rows.append(row)

        # unmatched gold -> no_match (FN)
        for gi, g in enumerate(gold_spans):
            if gi in matched_gold:
                continue
            match_counts["no_match_gold"] += 1
            gold_toks = tokens_in_span(doc, g["start"], g["end"])
            detailed_rows.append(
                {
                    "patent_id": pmid,
                    "pmid": pmid,
                    "gold_label": g["label"],
                    "predicted_label": None,
                    "gold_span": g["text"],
                    "predicted_span": None,
                    "gold_start": g["start"],
                    "gold_end": g["end"],
                    "pred_start": None,
                    "pred_end": None,
                    "match_type": "no_match",
                    "boundary_error": None,
                    "missing_left": "",
                    "missing_right": "",
                    "added_left": "",
                    "added_right": "",
                    "missing_tokens": "",
                    "missing_pos": "",
                    "added_tokens": "",
                    "added_pos": "",
                    "gold_pos_pattern": " ".join(t.pos_ for t in gold_toks),
                    "predicted_pos_pattern": "",
                    "overlap_score": 0.0,
                }
            )

        # unmatched pred -> no_match (FP)
        for pi, p in enumerate(pred_spans):
            if pi in matched_pred:
                continue
            match_counts["no_match_pred"] += 1
            pred_toks = tokens_in_span(doc, p["start"], p["end"])
            detailed_rows.append(
                {
                    "patent_id": pmid,
                    "pmid": pmid,
                    "gold_label": None,
                    "predicted_label": None,
                    "gold_span": None,
                    "predicted_span": p["text"],
                    "gold_start": None,
                    "gold_end": None,
                    "pred_start": p["start"],
                    "pred_end": p["end"],
                    "match_type": "no_match",
                    "boundary_error": None,
                    "missing_left": "",
                    "missing_right": "",
                    "added_left": "",
                    "added_right": "",
                    "missing_tokens": "",
                    "missing_pos": "",
                    "added_tokens": "",
                    "added_pos": "",
                    "gold_pos_pattern": "",
                    "predicted_pos_pattern": " ".join(t.pos_ for t in pred_toks),
                    "overlap_score": 0.0,
                }
            )

    df = pd.DataFrame(detailed_rows)
    df.to_csv(OUT_CSV, index=False)
    df.to_json(OUT_JSON, orient="records", indent=2)
    print(f"Wrote {OUT_CSV} and {OUT_JSON} ({len(df)} rows)")

    # ---------------- Summary statistics ----------------
    n_exact = match_counts["exact_match"]
    n_partial = match_counts["partial_match"]
    n_unmatched_gold = match_counts["no_match_gold"]
    n_unmatched_pred = match_counts["no_match_pred"]
    n_gold_denom = n_exact + n_partial + n_unmatched_gold
    n_pred_denom = n_exact + n_partial + n_unmatched_pred

    match_distribution = {
        "exact_match": {"count": n_exact, "pct_of_gold": round(100 * n_exact / n_gold_denom, 2)},
        "partial_match": {
            "count": n_partial,
            "pct_of_gold": round(100 * n_partial / n_gold_denom, 2),
        },
        "unmatched_gold": {
            "count": n_unmatched_gold,
            "pct_of_gold": round(100 * n_unmatched_gold / n_gold_denom, 2),
        },
        "unmatched_pred": {
            "count": n_unmatched_pred,
            "pct_of_pred": round(100 * n_unmatched_pred / n_pred_denom, 2),
        },
    }

    partial_df = df[df["match_type"] == "partial_match"]
    boundary_counts = partial_df["boundary_error"].value_counts().to_dict()
    n_partial_total = len(partial_df) if len(partial_df) else 1
    boundary_error_direction_stats = {
        k: {"count": int(v), "pct": round(100 * v / n_partial_total, 2)}
        for k, v in boundary_counts.items()
    }

    def pos_counter_from_col(colname):
        c = Counter()
        for val in partial_df[colname]:
            if val:
                c.update(val.split())
        return c

    pos_missing_all = pos_counter_from_col("missing_pos")
    left_pos_counter = Counter()
    right_pos_counter = Counter()
    for _, row in partial_df.iterrows():
        missing_tok_list = row["missing_tokens"].split() if row["missing_tokens"] else []
        missing_pos_list = row["missing_pos"].split() if row["missing_pos"] else []
        left_toks = set(row["missing_left"].split()) if row["missing_left"] else set()
        right_toks = set(row["missing_right"].split()) if row["missing_right"] else set()
        for tok, pos in zip(missing_tok_list, missing_pos_list):
            if tok in left_toks:
                left_pos_counter[pos] += 1
            elif tok in right_toks:
                right_pos_counter[pos] += 1

    total_missing = sum(pos_missing_all.values()) or 1
    pos_of_omitted_tokens = {
        "overall": {
            pos: {"count": cnt, "pct": round(100 * cnt / total_missing, 2)}
            for pos, cnt in pos_missing_all.most_common()
        },
        "left_boundary": {
            pos: cnt for pos, cnt in left_pos_counter.most_common()
        },
        "right_boundary": {
            pos: cnt for pos, cnt in right_pos_counter.most_common()
        },
    }

    transformations = Counter()
    for _, row in partial_df.iterrows():
        transformations[f"{row['gold_pos_pattern']} -> {row['predicted_pos_pattern']}"] += 1
    top_transformations = [
        {"pattern": k, "count": v} for k, v in transformations.most_common(20)
    ]

    surface_words_omitted = Counter()
    for _, row in partial_df.iterrows():
        if row["missing_tokens"]:
            surface_words_omitted.update(row["missing_tokens"].lower().split())
    top_surface_words_omitted = [
        {"word": k, "count": v} for k, v in surface_words_omitted.most_common(30)
    ]

    def prf(tp, fp, fn):
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "Precision": round(precision, 4),
            "Recall": round(recall, 4),
            "F1": round(f1, 4),
        }

    exact_tp = n_exact
    exact_fp = n_partial + n_unmatched_pred  # partial + unmatched pred are not exact TP
    exact_fn = n_partial + n_unmatched_gold
    exact_eval = prf(exact_tp, exact_fp, exact_fn)

    partial_tp = n_exact + n_partial  # one-to-one enforced upstream
    partial_fp = n_unmatched_pred
    partial_fn = n_unmatched_gold
    partial_eval = prf(partial_tp, partial_fp, partial_fn)

    summary = {
        "corpus": "BioRED (Train+Dev+Test PubTator splits)",
        "sample_size_requested": 500,
        "sample_size_used": len(records),
        "sample_note": (
            "Fewer than 500 matched documents exist between BioRED (600 docs) and "
            "FullSampleGloria_Pmed_GlinerLabels.parquet (881,341 unique pmids, a ~2.3% "
            "sample of PubMed). Only 48 pmids overlap; all 48 were used, per the "
            "instructions.md fallback rule for fewer-than-500 matched documents."
        ),
        "matching_identifier": "pmid",
        "counts": {
            "biored_total_docs": 600,
            "gliner_unique_pmids": 881341,
            "matched_docs": len(records),
        },
        "concept_label_filter": {
            "applied": False,
            "reason": (
                "FullSampleGloria_Pmed_GlinerLabels.parquet has no entity-type/label "
                "column (only pmid, term, year, term_firstYr), so CONCEPT_LABELS "
                "filtering is not applicable to the GLiNER side. BioRED gold labels "
                "are retained as-is."
            ),
        },
        "span_recovery_method": {
            "description": (
                "GLiNER predictions in FullSampleGloria_Pmed_GlinerLabels.parquet are "
                "bare term strings per pmid with no character offsets or occurrence "
                "index. For each unique GLiNER term per matched document, the first "
                "case-insensitive occurrence of that exact string in the document text "
                "(title + ' ' + abstract, standard PubTator offset convention) was used "
                "as its predicted character span. This is deterministic and reproducible "
                "but is a documented approximation: if a term occurs multiple times, only "
                "the first occurrence is used; if GLiNER's term does not appear verbatim "
                "in the text (e.g. due to normalization), it is excluded from span matching."
            ),
            "gliner_terms_total_in_matched_docs": n_pred_total,
            "gliner_terms_located_verbatim": n_pred_total - n_excluded_not_found,
            "gliner_terms_excluded_not_found": n_excluded_not_found,
            "pct_located": round(100 * (n_pred_total - n_excluded_not_found) / n_pred_total, 2),
        },
        "pos_tagging": {
            "model": "en_core_sci_md (scispaCy)",
            "context": "Full document text (title + abstract) tagged once per document; "
            "gold/predicted spans use token POS from that context, not isolated strings.",
        },
        "match_distribution": match_distribution,
        "boundary_error_direction": boundary_error_direction_stats,
        "pos_of_omitted_tokens": pos_of_omitted_tokens,
        "pos_transformation_patterns_top20": top_transformations,
        "surface_words_omitted_top30": top_surface_words_omitted,
        "evaluation": {
            "exact_match": exact_eval,
            "partial_match_one_to_one": partial_eval,
        },
    }

    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {SUMMARY_JSON}")

    # ---------------- Manual sanity-check sample ----------------
    rng = random.Random(RANDOM_STATE)
    partial_records = partial_df.to_dict("records")
    rng.shuffle(partial_records)
    manual_n = min(50, len(partial_records))
    manual_sample = partial_records[:manual_n]
    manual_out = [
        {
            "patent_id": r["pmid"],
            "gold": r["gold_span"],
            "gold_POS": r["gold_pos_pattern"],
            "prediction": r["predicted_span"],
            "prediction_POS": r["predicted_pos_pattern"],
            "missing": r["missing_tokens"],
            "missing_POS": r["missing_pos"],
            "boundary_error": r["boundary_error"],
        }
        for r in manual_sample
    ]
    pd.DataFrame(manual_out).to_csv(MANUAL_CSV, index=False)
    MANUAL_JSON.write_text(json.dumps(manual_out, indent=2))
    print(f"Wrote {MANUAL_CSV} and {MANUAL_JSON} ({manual_n} rows)")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary["match_distribution"], indent=2))
    print(json.dumps(summary["evaluation"], indent=2))


if __name__ == "__main__":
    main()
