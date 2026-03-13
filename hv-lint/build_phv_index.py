#!/usr/bin/env python3
"""Build compact PHV-to-PHT indexes from cached dbGaP variable lists.

Reads the full HTML variable index files (variables.xml) from a dbGaP
cache directory and produces compressed JSON files mapping base PHV
accessions to base PHT accessions. These compact indexes are used by
validate_phv_cross_reference.py.

Usage:
    python hv-lint/build_phv_index.py
    python hv-lint/build_phv_index.py --source-cache /path/to/dbgap-cache
    python hv-lint/build_phv_index.py --output-dir /path/to/output

The default source cache is ../BDC-DMC-Harmonization-Virtual-Team/data/dbgap-cache
(the parent workspace). Override with --source-cache.
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
    p = argparse.ArgumentParser(description="Build compact PHV-to-PHT indexes")
    p.add_argument(
        "--source-cache",
        default=None,
        help="Path to dbGaP HTML cache (default: auto-detect)"
    )
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "dbgap-cache"),
        help="Output directory for compressed JSON (default: hv-lint/dbgap-cache/)"
    )
    args = p.parse_args()

    # Auto-detect source cache
    if args.source_cache:
        source = Path(args.source_cache)
    else:
        # Try common locations
        candidates = [
            Path(__file__).resolve().parent.parent.parent
            / "BDC-DMC-Harmonization-Virtual-Team" / "data" / "dbgap-cache",
            Path(__file__).resolve().parent.parent / "data" / "dbgap-cache",
        ]
        source = None
        for c in candidates:
            if c.is_dir():
                source = c
                break
        if source is None:
            print("ERROR: Cannot find dbGaP cache. Use --source-cache.", file=sys.stderr)
            return 1

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print(f"Source cache: {source}")
    print(f"Output dir:   {output}")
    print()

    total_phvs = 0
    for cohort_dir in sorted(source.iterdir()):
        vf = cohort_dir / "variables.xml"
        if not vf.exists():
            continue

        mapping = parse_variable_html(vf)
        phts = len(set(mapping.values()))
        total_phvs += len(mapping)

        # Write compressed JSON
        json_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
        gz_path = output / f"{cohort_dir.name}.json.gz"
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
