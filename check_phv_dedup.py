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
#
# Re-triaged in #735 once this check could see MeasurementObservationSet.
# Seven entries were dropped as genuinely resolved; the two below are still
# live and were only invisible because they sit inside a Set.
KNOWN_ISSUES = {
    # ARIC blood_pressure.yaml emits the same random-zero "zero reading"
    # (SBPA17 / SBPA20) twice, typed as both OMOP:4152194 (systolic) and
    # OMOP:4154790 (diastolic), distinguished only by method_type. Whether
    # a calibration offset should carry a BP concept at all is open in #735.
    "phv00210286",
    "phv00210289",
}


def _measurement_value_phvs(slots, block_index):
    """Yield (phv, concept, block_index) for one MeasurementObservation's slots.

    Shared by top-level MeasurementObservation derivations and those nested
    inside a MeasurementObservationSet.
    """
    concept = (slots.get("observation_type") or {}).get("value")
    for qty_name, qty in iter_nested_class_derivs(slots.get("value_quantity")):
        if qty_name != "Quantity":
            continue
        qty_slots = qty.get("slot_derivations") or {}
        # value_concept carries the measured value for coded quantities; slots
        # that also declare value_mappings or expr are skipped below, so only
        # raw populated_from concepts are counted.
        for val_slot in ("value_decimal", "value_integer", "value_string", "value_concept"):
            slot_def = qty_slots.get(val_slot) or {}
            if "populated_from" in slot_def and "value_mappings" not in slot_def and "expr" not in slot_def:
                phv = slot_def["populated_from"]
                if phv and str(phv).startswith("phv"):
                    yield phv, concept, block_index


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
            yield from _measurement_value_phvs(slots, block_index)

        elif class_name == "MeasurementObservationSet":
            # Measurements bundled in a Set hang off `observations` rather than
            # sitting at the top level, but they are value-bearing in exactly
            # the same way -- skipping them left blood_pressure and spirometry
            # specs unchecked.
            for obs_name, obs in iter_nested_class_derivs(slots.get("observations")):
                if obs_name != "MeasurementObservation":
                    continue
                yield from _measurement_value_phvs(
                    obs.get("slot_derivations") or {}, block_index
                )


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
