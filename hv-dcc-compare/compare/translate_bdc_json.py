"""translate_bdc_json.py — Post-process a BDC summary JSON to rename raw concept-
code keys to canonical TOPMed variable names.

The BDC extract script (extract_harmonized_summaries.py) outputs most variables under
their canonical TOPMed names (e.g. 'bp_systolic_1') but falls through to raw
observation_type codes (e.g. 'OMOP:607590') for any code not present in the
BDC_MEASUREMENT_MAP at the time of extraction.  This script applies the
current map retroactively so that match_quality_table.py can compare them.

Usage:
    python translate_bdc_json.py <bdc_json_in> [<bdc_json_out>]

If <bdc_json_out> is omitted, writes to <bdc_json_in>.translated.json in the
same directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add the hv-dcc-compare root to path so config.py is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BDC_MEASUREMENT_MAP, BDC_CONDITION_MAP, BDC_PROCEDURE_MAP


def build_code_to_canonical() -> dict[str, str]:
    """Build reverse lookup: raw concept code -> canonical topmed_var name."""
    lookup: dict[str, str] = {}
    for primary_code, spec in BDC_MEASUREMENT_MAP.items():
        topmed_var = spec["topmed_var"]
        # Register primary
        lookup[primary_code] = topmed_var
        # Register aliases
        for alias in spec.get("aliases", []):
            lookup[alias] = topmed_var
    for primary_code, spec in BDC_CONDITION_MAP.items():
        lookup[primary_code] = spec["topmed_var"]
    for primary_code, spec in BDC_PROCEDURE_MAP.items():
        lookup[primary_code] = spec["topmed_var"]
    return lookup


def translate(in_path: str, out_path: str | None = None) -> str:
    in_p = Path(in_path)
    if out_path is None:
        out_p = in_p.parent / (in_p.stem + ".translated.json")
    else:
        out_p = Path(out_path)

    with open(in_p, encoding="utf-8") as f:
        data = json.load(f)

    lookup = build_code_to_canonical()

    old_vars: dict = data.get("variables", {})
    new_vars: dict = {}
    renamed = 0
    merged = 0
    kept_raw = 0

    for key, val in old_vars.items():
        canonical = lookup.get(key)
        if canonical and canonical != key:
            if canonical in new_vars:
                # Already have this canonical key — merge by taking max n_valid
                existing = new_vars[canonical]
                if val.get("n_valid", 0) > existing.get("n_valid", 0):
                    new_vars[canonical] = val
                merged += 1
                print(f"  MERGE: {key} -> {canonical} (kept higher n_valid)")
            else:
                new_vars[canonical] = val
                renamed += 1
                print(f"  RENAME: {key} -> {canonical}")
        else:
            # Already canonical or unmapped — keep as-is
            new_vars[key] = val
            if canonical is None:
                kept_raw += 1

    data["variables"] = new_vars
    data.setdefault("metadata", {})["translated_by"] = "translate_bdc_json.py"
    data["metadata"]["source_file"] = str(in_p.name)

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\nSummary: {renamed} renamed, {merged} merged, {kept_raw} kept as raw code")
    print(f"Written to: {out_p}")
    return str(out_p)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <bdc_json_in> [<bdc_json_out>]")
        sys.exit(1)
    in_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) > 2 else None
    translate(in_arg, out_arg)
