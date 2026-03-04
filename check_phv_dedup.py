"""Check for PHVs mapped as measured values in multiple harmonized variables."""

import sys
from collections import defaultdict
from pathlib import Path

import yaml


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
            for obj_deriv in (slots.get("value_quantity") or {}).get("object_derivations") or []:
                qty_slots = ((obj_deriv or {}).get("class_derivations") or {}).get("Quantity", {}).get("slot_derivations") or {}
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

    for file_path in yaml_files:
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
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
    print(f"Found {len(phv_hits)} value-PHVs across {len(yaml_files)} files")

    if duplicates:
        print(f"\nPOTENTIAL DUPLICATES ({len(duplicates)}):")
        for phv, hits in duplicates.items():
            concepts = {c for c, _, _ in hits}
            print(f"\n  {phv} mapped to {len(concepts)} concepts:")
            for concept, file, block_index in hits:
                print(f"    {concept} in {file} (block {block_index})")
    else:
        print("\nNo duplicates found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
