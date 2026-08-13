"""Check for PHVs mapped as measured values in multiple harmonized variables."""

import sys
from collections import defaultdict
from pathlib import Path

import yaml


def iter_nested_class_derivs(slot_def):
    """Yield (class_name, class_spec) for a slot's nested class derivations,
    handling list-based class_derivations in both `- name: X` and dict-keyed
    `- X: {...}` form, plus legacy object_derivations.

    Deliberately local: this module is outside hv-lint/ and importing from a
    hyphenated script tree would invert the dependency. The canonical copy is
    hv-lint/_derivations.py -- keep the two in sync."""
    slot_def = slot_def or {}
    for cd in slot_def.get("class_derivations") or []:
        if not isinstance(cd, dict):
            continue
        if "name" in cd:
            yield cd.get("name"), cd
        elif len(cd) == 1:
            # dict-keyed form: `- ClassName: {...}`
            cls_name, spec = next(iter(cd.items()))
            # a null body (`- X:`) parses as {X: None}; callers expect a dict
            yield cls_name, spec if isinstance(spec, dict) else {}
    for od in slot_def.get("object_derivations") or []:
        for name, spec in ((od or {}).get("class_derivations") or {}).items():
            yield name, spec


# Known duplicates tracked in #455. Remove entries as they are fixed.
KNOWN_ISSUES = {
    "phv00001581",  # FHS tot_chol_bld.yaml — missing observation_type in block 60
    "phv00079854",  # WHI bp_diastolic / bp_systolic
    "phv00079855",  # WHI bp_diastolic / bp_systolic
    "phv00079856",  # WHI bp_diastolic / bp_systolic
    "phv00079857",  # WHI bp_diastolic / bp_systolic
    "phv00100046",  # CHS albumin_bld / mch
    "phv00112688",  # CARDIA hemo / mchc
    "phv00210286",  # ARIC bp_diastolic / bp_systolic
    "phv00210289",  # ARIC bp_diastolic / bp_systolic
    # ARIC lympho_ct / whtbld_ct. Surfaced (not caused) by correcting the
    # lympho_ct typo OBA:VT0000217 -> OBA:VT0000717 in 2026-08. Both specs pull
    # value_decimal from the SAME pht006422/phv00294954 column, so one of them
    # reads the wrong source variable -- the dedup check could not see it while
    # both carried the WBC concept code. Needs an ARIC spec owner to say which
    # column holds lymphocytes; do not "fix" by reverting the concept code.
    # See transform_assessment/history/SPEC_CODE_CORRECTIONS_20260803.md §4.
    "phv00294954",
}


def extract_value_phvs(block, block_index):
    """Yield (phv, concept, block_index) for value-bearing populated_from fields."""
    try:
        class_derivs = block["class_derivations"]
    except (KeyError, TypeError):
        return

    for class_name, class_def in class_derivs.items():
        if not isinstance(class_def, dict):
            continue
        slots = class_def.get("slot_derivations") or {}

        if class_name == "Condition":
            concept = (slots.get("condition_concept") or {}).get("value")
            status = slots.get("condition_status") or {}
            if "populated_from" in status and "value_mappings" not in status:
                phv = status["populated_from"]
                if phv and str(phv).startswith("phv"):
                    yield phv, concept, block_index

        elif class_name == "MeasurementObservation":
            concept = (slots.get("observation_type") or {}).get("value")
            for qty_name, qty in iter_nested_class_derivs(slots.get("value_quantity")):
                if qty_name != "Quantity":
                    continue
                qty_slots = qty.get("slot_derivations") or {}
                for val_slot in ("value_decimal", "value_integer", "value_string"):
                    slot_def = qty_slots.get(val_slot) or {}
                    if "populated_from" in slot_def and "value_mappings" not in slot_def and "expr" not in slot_def:
                        phv = slot_def["populated_from"]
                        if phv and str(phv).startswith("phv"):
                            yield phv, concept, block_index


def main() -> int:
    base_dir = Path("priority_variables_transform")
    yaml_files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.startswith("_")
        and not f.name.endswith(".swp")
    )

    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 1

    # phv -> [(concept, file, block_index), ...]
    phv_hits = defaultdict(list)
    parse_errors = []

    for file_path in yaml_files:
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as exc:
            parse_errors.append((file_path.as_posix(), str(exc)))
            continue
        if data is None:
            continue

        blocks = data if isinstance(data, list) else [data]
        for i, block in enumerate(blocks):
            for phv, concept, block_index in extract_value_phvs(block, i):
                phv_hits[phv].append((concept, file_path.as_posix(), block_index))

    # Flag PHVs mapped to multiple distinct concepts
    duplicates = {
        phv: hits for phv, hits in sorted(phv_hits.items())
        if len({c for c, _, _ in hits}) > 1
    }

    print("PHV Deduplication Report")
    print("========================")
    print(f"Found {len(phv_hits)} unique value-PHVs across {len(yaml_files)} files")

    if parse_errors:
        print(f"\nPARSE ERRORS ({len(parse_errors)}):")
        for path, err in parse_errors:
            print(f"  {path}: {err}")

    known = {phv: hits for phv, hits in duplicates.items() if phv in KNOWN_ISSUES}
    new = {phv: hits for phv, hits in duplicates.items() if phv not in KNOWN_ISSUES}

    if known:
        print(f"\nKNOWN ISSUES ({len(known)} PHVs, see #373):")
        for phv, hits in known.items():
            concepts = {c for c, _, _ in hits}
            print(f"\n  {phv} mapped to {len(concepts)} concepts:")
            for concept, file, block_index in hits:
                print(f"    {concept} in {file} (block {block_index})")

    if new:
        print(f"\nNEW DUPLICATES ({len(new)}):")
        for phv, hits in new.items():
            concepts = {c for c, _, _ in hits}
            print(f"\n  {phv} mapped to {len(concepts)} concepts:")
            for concept, file, block_index in hits:
                print(f"    {concept} in {file} (block {block_index})")
        return 1

    if parse_errors:
        return 1

    if not duplicates:
        print("\nNo duplicates found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
