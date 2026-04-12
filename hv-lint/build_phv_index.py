#!/usr/bin/env python3
"""Build compact PHV-to-PHT indexes from cached dbGaP variable lists.

Reads the full HTML variable index files (variables.xml) from a dbGaP
cache directory and produces compressed JSON files mapping base PHV
accessions to base PHT accessions. These compact indexes are used by
Phase 3 (validate_dbgap_crossref.py).

Usage:
    python hv-lint/build_phv_index.py
    python hv-lint/build_phv_index.py --source-cache hv-lint/dbgap-cache
    python hv-lint/build_phv_index.py --output-dir hv-lint/dbgap-cache

Normally invoked via ``update_data.py`` which handles source fetching
and index building together. Run standalone only when rebuilding
indexes from already-fetched source XML.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from html.parser import HTMLParser
from pathlib import Path


class VariableTableParser(HTMLParser):
    """Parse the dbGaP variable list HTML table.

    Each row has 5 columns:
      [0] Variable accession  (e.g., phv00098579.v7.p3)
      [1] Variable name       (e.g., SUBJECT_ID)
      [2] Variable description
      [3] Dataset accession   (e.g., pht001440.v7.p3)
      [4] Dataset name        (e.g., ARIC_Subject)
    """

    def __init__(self):
        super().__init__()
        self.in_td = False
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.in_td = True
            self.current_text = ""
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
            self.current_row.append(self.current_text.strip())
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_td:
            self.current_text += data


def parse_variable_html(path: Path) -> dict[str, str]:
    """Parse HTML variable list and return {base_phv: base_pht} mapping."""
    parser = VariableTableParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()

    mapping: dict[str, str] = {}
    for row in parser.rows:
        if len(row) < 4:
            continue
        phv_base = row[0].split(".")[0]  # strip .vN.pN version
        pht_base = row[3].split(".")[0]
        if phv_base.startswith("phv") and pht_base.startswith("pht"):
            mapping[phv_base] = pht_base

    return mapping


def main() -> int:
    # Auto-detect repo root -- works from control center (hv-lint/)
    # or HV repo (hv-lint/). The dbGaP cache is in the control center.
    hvlint_dir = Path(__file__).resolve().parent
    for candidate in [hvlint_dir.parent.parent, hvlint_dir.parent]:
        if (candidate / "data" / "dbgap-cache").is_dir():
            repo_root = candidate
            break
    else:
        repo_root = hvlint_dir.parent  # fallback; --source-cache required

    p = argparse.ArgumentParser(description="Build compact PHV-to-PHT indexes")
    p.add_argument(
        "--source-cache",
        default=None,
        help="Path to dbGaP HTML cache (default: data/dbgap-cache in repo root)"
    )
    p.add_argument(
        "--output-dir",
        default=str(hvlint_dir / "dbgap-cache"),
        help="Output directory for compressed JSON (default: hv-lint/dbgap-cache/)"
    )
    args = p.parse_args()

    # Auto-detect source cache
    if args.source_cache:
        source = Path(args.source_cache)
    else:
        source = repo_root / "data" / "dbgap-cache"
        if not source.is_dir():
            print(f"ERROR: Cannot find dbGaP cache at {source}. Use --source-cache.",
                  file=sys.stderr)
            return 1

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print(f"Source cache: {source}")
    print(f"Output dir:   {output}")
    print()

    total_phvs = 0
    for cohort_dir in sorted(source.iterdir()):
        if not cohort_dir.is_dir():
            continue
        vf = cohort_dir / "variables.xml"
        if not vf.exists():
            continue

        mapping = parse_variable_html(vf)
        phts = len(set(mapping.values()))
        total_phvs += len(mapping)

        # Write compressed JSON
        json_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
        gz_path = output / f"{cohort_dir.name.lower()}.json.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(json_bytes)

        gz_size = gz_path.stat().st_size
        print(
            f"  {cohort_dir.name:12s}: {len(mapping):>7,} PHVs, "
            f"{phts:>4} PHTs -> {gz_size:>8,} bytes ({gz_path.name})"
        )

    print(f"\nTotal: {total_phvs:,} PHVs indexed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
