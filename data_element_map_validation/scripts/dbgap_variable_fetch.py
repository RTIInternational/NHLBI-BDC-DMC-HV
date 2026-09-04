#!/usr/bin/env python3
"""Fetch the official dbGaP variable list for a study and write {STUDY}_dbgap_study_variable.csv.

Ground-truth source verification: dbGaP is the authoritative source for a study's variable
names and descriptions. The curie CSVs (`bdc_study_input/{STUDY}_curie.csv`) are curated by
hand and can drift from dbGaP (typos, truncated descriptions, wrong phv). This script pulls
the real thing directly from dbGaP so generate_curie_mapreview.py can verify against it before
querying OBA/LOINC.

Endpoint (server-rendered, no auth, confirmed working):
  GET https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/GetListOfAllObjects.cgi
      ?study_id=<phs_accession>&object_type=variable

The dbGaP study accession per study is read from the `dbgap_study_accession` column of
bdc_study_input/BDC_registered_study_for_semantic_review.csv. A study with no accession set
there is skipped with a clear message (this is expected until confirmed per-study).

Usage:
  python dbgap_variable_fetch.py --study HCHS
  python dbgap_variable_fetch.py --study SPIROMICS
"""

import csv
import html
import re
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent  # data_element_map_validation/
_REGISTRY_CSV = BASE_DIR / "bdc_study_input" / "BDC_registered_study_for_semantic_review.csv"

DBGAP_LIST_URL = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/GetListOfAllObjects.cgi"
DBGAP_STUDY_URL = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi"

_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_VERSIONED_RE = re.compile(r"^phs\d+\.v\d+\.p\d+$")
_ACCESSION_IN_URL_RE = re.compile(r"study_id=(phs\d+\.v\d+\.p\d+)")


def resolve_latest_version(accession: str) -> str:
    """Return the current version of a dbGaP accession, e.g. 'phs000810' -> 'phs000810.v2.p2'.

    dbGaP redirects a bare (unversioned) study_id to its latest version's study page.
    If *accession* is already fully versioned (phsXXXXXX.vN.pN), it's returned as-is —
    callers that want a specific pinned version should pass the full accession.
    """
    if _VERSIONED_RE.match(accession):
        return accession
    bare = accession.split(".")[0]
    resp = requests.get(
        DBGAP_STUDY_URL, params={"study_id": bare}, timeout=30,
        headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True,
    )
    resp.raise_for_status()
    m = _ACCESSION_IN_URL_RE.search(resp.url)
    if not m:
        raise RuntimeError(f"Could not resolve latest version for '{accession}' (landed on {resp.url})")
    return m.group(1)


def _file_key(short_name: str) -> str:
    return short_name.replace("/", "_").replace(" ", "_")


def _load_accession(study: str) -> str:
    with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["cohort_study_short_name"].strip() == study:
                return row.get("dbgap_study_accession", "").strip()
    return ""


def _load_curie_cohort(study: str) -> str:
    """Return the exact Cohort column value used in {STUDY}_curie.csv (e.g. 'HCHS-SOL'
    for study='HCHS'), so the dbGaP file's Cohort column matches it exactly rather
    than falling back to the registry short name. Falls back to *study* if the
    curie CSV doesn't exist yet or has no rows."""
    curie_path = BASE_DIR / "bdc_study_input" / f"{_file_key(study)}_curie.csv"
    if curie_path.exists():
        with open(curie_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                cohort = row.get("Cohort", "").strip()
                if cohort:
                    return cohort
    return study


def fetch_dbgap_variables(cohort: str, phs: str, accession: str) -> list[dict]:
    """Return a list of dicts using the SAME column names as {STUDY}_curie.csv
    (Cohort, PHT, PHV, Variable Name, Variable Description) so the two files line
    up directly for a human reading or joining them, plus the extra dbGaP-only
    detail (bare/versioned accessions, dataset name) that has no curie.csv equivalent.

    curie.csv's PHT/PHV are bare, unversioned accessions (e.g. "PHT004715") —
    dbGaP's own table gives versioned ones (e.g. "pht004715.v2.p2"), so both the
    bare and full forms are kept: PHT/PHV for joining, PHT_full/PHV_full for
    provenance. *cohort* is the curie.csv's own Cohort value (e.g. "HCHS-SOL"),
    not the registry short name, so the two files agree exactly on that column.
    """
    resp = requests.get(
        DBGAP_LIST_URL,
        params={"study_id": accession, "object_type": "variable"},
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    text = resp.text

    rows: list[dict] = []
    for tr_match in re.finditer(r"<tr>(.*?)</tr>", text, re.DOTALL):
        cells = _CELL_RE.findall(tr_match.group(1))
        if len(cells) != 5:
            continue
        clean = [html.unescape(_TAG_RE.sub("", c)).strip() for c in cells]
        phv_full, name, desc, pht_full, dsname = clean
        if not phv_full.startswith("phv"):
            continue
        rows.append({
            "Cohort": cohort,
            "phs": phs,
            "dbgap_study_accession": accession,
            "PHT": pht_full.split(".")[0].upper(),
            "PHV": phv_full.split(".")[0],
            "Variable Name": name,
            "Variable Description": desc.strip('"'),
            "PHT_full": pht_full,
            "PHV_full": phv_full,
            "Dataset Name": dsname,
        })
    return rows


def main(study: str) -> None:
    registered_accession = _load_accession(study)
    if not registered_accession:
        print(
            f"No dbgap_study_accession set for '{study}' in "
            f"{_REGISTRY_CSV.name} — skipping dbGaP fetch. "
            "Add the accession (bare, e.g. phs000810, or fully versioned to pin it) "
            "to enable source verification.",
            file=sys.stderr,
        )
        sys.exit(1)

    accession = resolve_latest_version(registered_accession)
    if accession != registered_accession:
        print(f"Resolved '{registered_accession}' -> latest version '{accession}'", file=sys.stderr)
    phs = accession.split(".")[0]
    cohort = _load_curie_cohort(study)

    print(f"Fetching dbGaP variable list for {study} ({accession}) ...", file=sys.stderr)
    rows = fetch_dbgap_variables(cohort, phs, accession)
    if not rows:
        print(f"No variables returned for {accession} — check the accession is correct.", file=sys.stderr)
        sys.exit(1)

    out_path = BASE_DIR / "bdc_study_input" / f"{_file_key(study)}_dbgap_study_variable.csv"
    fieldnames = ["Cohort", "phs", "PHT", "PHV", "Variable Name", "Variable Description",
                  "dbgap_study_accession", "PHT_full", "PHV_full", "Dataset Name"]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} variables to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    import argparse

    _registered = []
    if _REGISTRY_CSV.exists():
        with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
            _registered = [r["cohort_study_short_name"].strip() for r in csv.DictReader(f)]

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--study", required=True, choices=_registered, metavar="STUDY",
                         help=f"Study to fetch. Known: {_registered}.")
    args = parser.parse_args()
    main(args.study)
