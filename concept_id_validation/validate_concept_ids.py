#!/usr/bin/env python3
"""
Validate OMOP concept IDs from the BDCHM Priority Variables spreadsheet
against the OHDSI WebAPI (ATLAS demo instance).

Reads from Google Sheet: "DO NOT EDIT BDCHM Prioritization Information"
                worksheet: "BDCHM Priority Variables"

Looks up each concept_id via:
  GET https://atlas-demo.ohdsi.org/WebAPI/vocabulary/OHDSIEVIDNET/concept/{id}

Outputs CSV comparing source spreadsheet values to OMOP vocabulary values.
"""

import sys
import time
import pandas as pd
import requests
from pathlib import Path

# Add parent dir so we can reuse existing gsheet loader
sys.path.insert(0, str(Path(__file__).parent.parent))
from variable_documentation.generate_variable_documentation import load_gsheet_as_df

WEBAPI_BASE = "https://atlas-demo.ohdsi.org/WebAPI/vocabulary/OHDSIEVIDNET"
CONCEPT_ENDPOINT = f"{WEBAPI_BASE}/concept"

# Column mappings from the spreadsheet
COL_DOMAIN = "DOMAIN"                          # col A
COL_VAR_LABEL = "Variable (Label)"             # col F
COL_VAR_NAME = "Variable (Machine Readable Name)"  # col G
COL_CONCEPT_ID = "OMOP Standard Concept ID"    # col P
COL_VOCAB = "target_vocab_id"                  # col Q


def fetch_concept(concept_id: int) -> dict | None:
    """Fetch a single OMOP concept from the OHDSI WebAPI."""
    url = f"{CONCEPT_ENDPOINT}/{concept_id}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"  HTTP {resp.status_code} for concept_id {concept_id}")
        return None
    except requests.RequestException as e:
        print(f"  Error fetching concept_id {concept_id}: {e}")
        return None


def diff_str(src: str, omop: str) -> str:
    """Return empty string if values match (case-insensitive), else 'DIFF'."""
    if not src and not omop:
        return ""
    if (src or "").strip().lower() == (omop or "").strip().lower():
        return ""
    return "DIFF"


def main():
    print("Loading spreadsheet...")
    df = load_gsheet_as_df(
        # https://docs.google.com/spreadsheets/d/1G-AIk2m4UCDfh1OvFID3bewQXqxExeKNNmVxaswLT8E/edit?gid=2039879463#gid=2039879463
        "DO NOT EDIT BDCHM Prioritization Information",
        "BDCHM Priority Variables",
    )
    print(f"Loaded {len(df)} rows")

    # Filter to rows that have a concept_id
    has_id = df[COL_CONCEPT_ID].astype(str).str.strip().ne("")
    df = df[has_id].copy()

    # Parse concept IDs to int, skipping non-numeric
    def parse_id(val):
        try:
            return int(float(str(val).strip()))
        except (ValueError, TypeError):
            return None

    df["_concept_id"] = df[COL_CONCEPT_ID].apply(parse_id)
    bad_ids = df[df["_concept_id"].isna()]
    if len(bad_ids):
        print(f"Skipping {len(bad_ids)} rows with non-numeric concept IDs:")
        for _, row in bad_ids.iterrows():
            print(f"  {row.get(COL_VAR_LABEL, '?')}: '{row[COL_CONCEPT_ID]}'")
    df = df[df["_concept_id"].notna()].copy()
    df["_concept_id"] = df["_concept_id"].astype(int)

    # Deduplicate concept IDs for lookup (many rows may share the same ID)
    unique_ids = df["_concept_id"].unique()
    print(f"Looking up {len(unique_ids)} unique concept IDs from {len(df)} rows...")

    concept_cache: dict[int, dict | None] = {}
    for i, cid in enumerate(unique_ids):
        concept_cache[cid] = fetch_concept(cid)
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(unique_ids)} fetched...")
        time.sleep(0.1)  # be polite

    print(f"Fetched {sum(1 for v in concept_cache.values() if v is not None)}/{len(unique_ids)} concepts successfully")

    # Build output rows
    rows = []
    for _, row in df.iterrows():
        cid = row["_concept_id"]
        concept = concept_cache.get(cid)

        src_name = str(row.get(COL_VAR_LABEL, "")).strip()
        src_domain = str(row.get(COL_DOMAIN, "")).strip()
        src_vocab = str(row.get(COL_VOCAB, "")).strip()
        src_var_name = str(row.get(COL_VAR_NAME, "")).strip()

        if concept:
            omop_std = concept.get("STANDARD_CONCEPT", "")
            omop_name = concept.get("CONCEPT_NAME", "")
            omop_domain = concept.get("DOMAIN_ID", "")
            omop_vocab = concept.get("VOCABULARY_ID", "")
        else:
            omop_std = "NOT FOUND"
            omop_name = omop_domain = omop_vocab = ""

        rows.append({
            "concept_id": cid,
            "OMOP_std": omop_std,
            "src_concept_name": src_name,
            "OMOP_concept_name": omop_name,
            "name_diff": diff_str(src_name, omop_name),
            "_1": "",
            "src_domain": src_domain,
            "OMOP_domain_id": omop_domain,
            "domain_diff": diff_str(src_domain, omop_domain),
            "_2": "",
            "src_vocabulary_id": src_vocab,
            "OMOP_vocabulary_id": omop_vocab,
            "vocab_diff": diff_str(src_vocab, omop_vocab),
            "_3": "",
            "src_var_name": src_var_name,
        })

    out_df = pd.DataFrame(rows)
    output_path = Path(__file__).parent / "concept_id_validation.csv"
    out_df.to_csv(output_path, index=False)
    print(f"\nOutput written to {output_path}")

    # Print summary stats
    found = out_df[out_df["OMOP_std"] != "NOT FOUND"]
    not_found = out_df[out_df["OMOP_std"] == "NOT FOUND"]
    non_standard = found[found["OMOP_std"] != "S"]
    name_diffs = found[found["name_diff"] == "DIFF"]
    domain_diffs = found[found["domain_diff"] == "DIFF"]
    vocab_diffs = found[found["vocab_diff"] == "DIFF"]

    print(f"\nSummary:")
    print(f"  Total rows:        {len(out_df)}")
    print(f"  Found in OMOP:     {len(found)}")
    print(f"  NOT FOUND:         {len(not_found)}")
    print(f"  Non-standard:      {len(non_standard)}")
    print(f"  Name differences:  {len(name_diffs)}")
    print(f"  Domain differences:{len(domain_diffs)}")
    print(f"  Vocab differences: {len(vocab_diffs)}")


if __name__ == "__main__":
    main()
