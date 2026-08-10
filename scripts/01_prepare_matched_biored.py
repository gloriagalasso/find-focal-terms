"""
Build the matched BioRED <-> GLiNER (PubMed) dataset.

- Parses BioRED PubTator files (Train/Dev/Test) into per-document
  {pmid, text, entities:[(start,end,text,type)]}.
- Loads FullSampleGloria_Pmed_GlinerLabels.parquet, restricted to pmids
  that also appear in BioRED.
- For each GLiNER term of a matched pmid, recovers a character span by
  locating the FIRST case-insensitive occurrence of that term string in
  the document text (title + " " + abstract, the standard PubTator
  offset convention). GLiNER's output here is a bag of terms per
  document with no position/occurrence info, so "first occurrence" is
  the simplest deterministic, reproducible recovery rule; documented
  explicitly per instructions.md. Terms not found verbatim in the text
  (e.g. due to GLiNER-side normalization) are kept but flagged
  text_not_found=True and excluded from span matching.

Writes:
  scripts/matched_biored.json  -- list of per-document records
"""
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

BASE = Path("/Users/vincenzomula/Documents/hiwi_gloria")
BIORED_ZIP = BASE / "benchmarks_extractors/biored/BIORED.zip"
GLINER_PARQUET = BASE / "FullSampleGloria_Pmed_GlinerLabels.parquet"
OUT = BASE / "scripts/matched_biored.json"

PUBTATOR_SPLITS = ["BioRED/Train.PubTator", "BioRED/Dev.PubTator", "BioRED/Test.PubTator"]


def parse_pubtator(raw: str, split_name: str):
    """Parse a PubTator-format string into {pmid: {text, entities, split}}."""
    docs = {}
    lines = raw.splitlines()
    i = 0
    n = len(lines)
    title_re = re.compile(r"^(\d+)\|t\|(.*)$")
    abs_re = re.compile(r"^(\d+)\|a\|(.*)$")
    ann_re = re.compile(r"^(\d+)\t(\d+)\t(\d+)\t(.*?)\t([^\t]+)\t(.*)$")

    while i < n:
        line = lines[i]
        m = title_re.match(line)
        if not m:
            i += 1
            continue
        pmid, title = m.group(1), m.group(2)
        i += 1
        abstract = ""
        if i < n:
            m2 = abs_re.match(lines[i])
            if m2 and m2.group(1) == pmid:
                abstract = m2.group(2)
                i += 1
        text = title + " " + abstract
        entities = []
        while i < n and lines[i].strip() != "":
            am = ann_re.match(lines[i])
            if am and am.group(1) == pmid:
                start, end, ent_text, ent_type = (
                    int(am.group(2)),
                    int(am.group(3)),
                    am.group(4),
                    am.group(5),
                )
                # skip relation lines (CID-style, no numeric offsets) - ann_re already requires numeric start/end
                entities.append(
                    {"start": start, "end": end, "text": ent_text, "type": ent_type}
                )
            i += 1
        # skip blank line separator
        while i < n and lines[i].strip() == "":
            i += 1
        docs[pmid] = {"pmid": pmid, "text": text, "entities": entities, "split": split_name}
    return docs


def load_biored():
    z = zipfile.ZipFile(BIORED_ZIP)
    all_docs = {}
    for split in PUBTATOR_SPLITS:
        raw = z.read(split).decode("utf-8", errors="ignore")
        split_name = split.split("/")[1].replace(".PubTator", "")
        docs = parse_pubtator(raw, split_name)
        all_docs.update(docs)
    return all_docs


def find_first_occurrence(term: str, text: str):
    idx = text.lower().find(term.lower())
    if idx == -1:
        return None
    return idx, idx + len(term)


def main():
    print("Parsing BioRED PubTator files...")
    biored_docs = load_biored()
    print(f"  BioRED total docs (train+dev+test): {len(biored_docs)}")

    print("Loading GLiNER PubMed parquet (pmid, term columns only)...")
    gliner = pd.read_parquet(GLINER_PARQUET, columns=["pmid", "term"])
    gliner["pmid"] = gliner["pmid"].astype(str)

    biored_pmids = set(biored_docs.keys())
    matched_pmids = sorted(biored_pmids & set(gliner["pmid"].unique()), key=int)
    print(f"  BioRED pmids: {len(biored_pmids)}")
    print(f"  GLiNER unique pmids: {gliner['pmid'].nunique()}")
    print(f"  Matched pmids: {len(matched_pmids)}")

    gliner_matched = gliner[gliner["pmid"].isin(matched_pmids)]
    terms_by_pmid = gliner_matched.groupby("pmid")["term"].apply(
        lambda s: sorted(set(s.tolist()))
    )

    records = []
    n_terms_total = 0
    n_terms_found = 0
    for pmid in matched_pmids:
        doc = biored_docs[pmid]
        terms = terms_by_pmid.get(pmid, [])
        pred_spans = []
        for term in terms:
            n_terms_total += 1
            occ = find_first_occurrence(term, doc["text"])
            if occ is None:
                pred_spans.append(
                    {"term": term, "start": None, "end": None, "text_not_found": True}
                )
            else:
                n_terms_found += 1
                start, end = occ
                pred_spans.append(
                    {
                        "term": term,
                        "start": start,
                        "end": end,
                        "text_not_found": False,
                        "matched_text": doc["text"][start:end],
                    }
                )
        records.append(
            {
                "pmid": pmid,
                "split": doc["split"],
                "text": doc["text"],
                "gold_entities": doc["entities"],
                "gliner_terms": pred_spans,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(records, f)

    print(f"  GLiNER terms total (matched docs): {n_terms_total}")
    print(f"  GLiNER terms located via first-occurrence text search: {n_terms_found} "
          f"({n_terms_found / n_terms_total:.1%})")
    print(f"  GLiNER terms NOT found verbatim in text: {n_terms_total - n_terms_found}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
