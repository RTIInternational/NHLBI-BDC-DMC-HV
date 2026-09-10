#!/usr/bin/env python3
"""
reconcile_dictionary.py -- config.py concept maps vs. the BDC-HM data dictionary

Reports where the hand-maintained comparison maps in config.py disagree with the
BDC-HM data dictionary export. Read-only: it changes nothing and recommends
nothing automatically, because whether a code belongs in the TOPMed comparison
is a curation judgement, not something a diff can settle.

Three findings are reported:

  1. Mapped but unknown -- a code config.py compares against a TOPMed variable
     that the dictionary does not list. Either config.py is stale (the pipeline
     no longer emits it, so the comparison silently covers nothing) or the
     dictionary is incomplete. Worth checking one at a time.

  2. Vocabulary mismatch -- config.py and the dictionary use different coding
     systems for the same output column. Seen 2026-09-10: COPDGene emitted
     ATC drug classes while the dictionary declares RxNorm ingredients, so no
     drug code could ever match.

  3. Known but unmapped -- a dictionary code with no entry in config.py. Mostly
     expected (TOPMed DCC never harmonized spirometry or COPD diagnosis), so
     this is an inventory to skim, not a defect list.

Usage:
    python compare/reconcile_dictionary.py [--data-dictionary CSV] [--verbose]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    BDC_CONDITION_MAP,
    BDC_MEASUREMENT_MAP,
    BDC_PROCEDURE_MAP,
    OMOP_SMOKING_MAP,
    SMOKING_OBSERVATION_TYPE,
    find_data_dictionary,
    load_data_dictionary,
)

# config map -> the dictionary output_table/output_column it should agree with
MAP_CONTEXT = [
    ("BDC_MEASUREMENT_MAP", BDC_MEASUREMENT_MAP, "MeasurementObservation", "observation_type"),
    ("BDC_CONDITION_MAP", BDC_CONDITION_MAP, "Condition", "condition_concept"),
    ("BDC_PROCEDURE_MAP", BDC_PROCEDURE_MAP, "Procedure", "procedure_concept"),
]


def codes_in_map(mapping: dict) -> dict[str, str]:
    """Every code a map can match (primary + aliases) -> its display label."""
    out: dict[str, str] = {}
    for code, spec in mapping.items():
        label = spec.get("bdc_label", code) if isinstance(spec, dict) else str(spec)
        out[code] = label
        if isinstance(spec, dict):
            for alias in spec.get("aliases", []):
                out[alias] = f"{label} (alias)"
    return out


def prefix_of(code: str) -> str:
    return code.split(":", 1)[0] if ":" in code else "(none)"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile config.py concept maps against the BDC-HM data dictionary."
    )
    ap.add_argument("--data-dictionary", default=None, metavar="CSV",
                    help="Dictionary CSV (default: newest BDC-HM-*DataDictionary*.csv found).")
    ap.add_argument("--verbose", action="store_true",
                    help="List every known-but-unmapped code, not just a per-column count.")
    args = ap.parse_args()

    path = find_data_dictionary(args.data_dictionary)
    if path is None:
        print("ERROR: no BDC-HM data dictionary found. Pass --data-dictionary.",
              file=sys.stderr)
        return 1
    dictionary = load_data_dictionary(args.data_dictionary, verbose=False)
    if not dictionary:
        print(f"ERROR: {path} produced no usable rows.", file=sys.stderr)
        return 1

    qualified = {k: v for k, v in dictionary.items() if isinstance(k, tuple)}
    bare = {k: v for k, v in dictionary.items() if isinstance(k, str)}

    print("=" * 78)
    print("  config.py concept maps  vs.  BDC-HM data dictionary")
    print("=" * 78)
    print(f"  dictionary : {path.name}  ({len(bare):,} distinct codes)")
    print()

    # ---- 1. mapped but not in the dictionary -------------------------------
    print("-" * 78)
    print("  [1] MAPPED BUT NOT IN THE DICTIONARY")
    print("      config.py compares these; the dictionary does not list them.")
    print("-" * 78)
    total_unknown = 0
    for name, mapping, table, column in MAP_CONTEXT:
        codes = codes_in_map(mapping)
        unknown = {c: lbl for c, lbl in codes.items() if c not in bare}
        print(f"\n  {name}  ({len(codes) - len(unknown)}/{len(codes)} recognised)")
        if not unknown:
            print("    all recognised")
            continue
        total_unknown += len(unknown)
        # Primary vs alias changes what the finding means. A missing PRIMARY
        # code means the comparison for that variable can never fire. A missing
        # alias is usually benign -- aliases are synonym fallbacks, and the
        # dictionary only declares the canonical code.
        primaries = {c: l for c, l in unknown.items() if not l.endswith("(alias)")}
        aliases = {c: l for c, l in unknown.items() if l.endswith("(alias)")}
        if primaries:
            print("    PRIMARY codes (this comparison can never match):")
            for code, label in sorted(primaries.items()):
                print(f"      {code:22} {label}")
        if aliases:
            print(f"    alias codes ({len(aliases)}, usually benign -- synonym fallbacks):")
            for code, label in sorted(aliases.items()):
                print(f"      {code:22} {label[:-8].strip()}")
    smoking_known = SMOKING_OBSERVATION_TYPE in bare
    print(f"\n  SMOKING_OBSERVATION_TYPE {SMOKING_OBSERVATION_TYPE}: "
          f"{'recognised' if smoking_known else 'NOT IN DICTIONARY'}")
    unknown_values = [c for c in OMOP_SMOKING_MAP if c.startswith("OMOP:") and c not in bare]
    if unknown_values:
        print(f"  smoking value codes not in dictionary: {', '.join(sorted(unknown_values))}")

    # ---- 2. vocabulary mismatch --------------------------------------------
    print()
    print("-" * 78)
    print("  [2] VOCABULARY MISMATCH")
    print("      Different coding systems for the same output column cannot match.")
    print("-" * 78)
    found_mismatch = False
    for name, mapping, table, column in MAP_CONTEXT:
        cfg_prefixes = {prefix_of(c) for c in codes_in_map(mapping)}
        dict_prefixes = {prefix_of(code) for (t, col, code) in qualified
                         if t == table and col == column}
        if not dict_prefixes:
            continue
        only_cfg = cfg_prefixes - dict_prefixes
        if only_cfg:
            found_mismatch = True
            print(f"\n  {table}.{column}")
            print(f"    config.py uses     : {', '.join(sorted(cfg_prefixes))}")
            print(f"    dictionary declares: {', '.join(sorted(dict_prefixes))}")
            print(f"    in config.py only  : {', '.join(sorted(only_cfg))}")

    # DrugExposure has no config map, but the pipeline emits drug codes.
    drug_prefixes = {prefix_of(code) for (t, col, code) in qualified
                     if t == "DrugExposure" and col == "drug_concept"}
    if drug_prefixes:
        print(f"\n  DrugExposure.drug_concept")
        print(f"    dictionary declares: {', '.join(sorted(drug_prefixes))}")
        print("    config.py has no drug concept map; drug codes seen in an extract "
              "that use a different\n    vocabulary (e.g. ATC classes vs RxNorm "
              "ingredients) will never resolve to a label.")
        found_mismatch = True
    if not found_mismatch:
        print("\n  none")

    # ---- 3. in the dictionary, not mapped ----------------------------------
    print()
    print("-" * 78)
    print("  [3] IN THE DICTIONARY, NOT IN config.py")
    print("      Expected for concepts TOPMed DCC never harmonized. Skim, don't fix.")
    print("-" * 78)
    all_mapped = set()
    for _, mapping, _, _ in MAP_CONTEXT:
        all_mapped |= set(codes_in_map(mapping))
    all_mapped.add(SMOKING_OBSERVATION_TYPE)

    by_column: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for (table, column, code), label in qualified.items():
        if code not in all_mapped:
            by_column[(table, column)].append((code, label))
    for (table, column), items in sorted(by_column.items()):
        print(f"\n  {table}.{column}  ({len(items)})")
        if args.verbose:
            for code, label in sorted(items):
                print(f"    {code:22} {label}")
        else:
            preview = ", ".join(c for c, _ in sorted(items)[:6])
            more = f", +{len(items) - 6} more" if len(items) > 6 else ""
            print(f"    {preview}{more}")

    print()
    print("=" * 78)
    print(f"  {total_unknown} mapped code(s) unknown to the dictionary "
          f"(see PRIMARY vs alias above); "
          f"{sum(len(v) for v in by_column.values())} dictionary code(s) unmapped.")
    print("  Nothing was changed. Decide each case by hand.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
