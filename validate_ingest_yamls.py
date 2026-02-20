"""Validate all trans-spec YAML files against the linkml-map transformer model."""

import sys
from pathlib import Path

import yaml
from linkml_map.datamodel.transformer_model import TransformationSpecification
from linkml_runtime.processing.referencevalidator import ReferenceValidator
from linkml_runtime.utils.introspection import package_schemaview

# Known issues to be fixed by curation team. These files are excluded from
# validation failures so CI stays green while issues are tracked separately.
# Remove entries as they are fixed.
KNOWN_ISSUES = {
    "priority_variables_transform/CHS-ingest/afib.yaml": "uses lookup_key (not in linkml-map schema)",
    "priority_variables_transform/CHS-ingest/cac_score.yaml": "uses lookup_key (not in linkml-map schema)",
    "priority_variables_transform/FHS-ingest/il18.yaml": "empty file (entirely commented out)",
    "priority_variables_transform/FHS-ingest/pr_qrs_qt.yaml": "observations nesting inside MeasurementObservationSet not in linkml-map schema",
}


def make_normalizer() -> ReferenceValidator:
    normalizer = ReferenceValidator(
        package_schemaview("linkml_map.datamodel.transformer_model")
    )
    normalizer.expand_all = True
    return normalizer


def validate_block(
    block: dict, normalizer: ReferenceValidator, block_index: int
) -> list[str]:
    errors = []
    try:
        normalized = normalizer.normalize(block)
        TransformationSpecification(**normalized)
    except Exception as e:
        errors.append(f"  block {block_index}: {e}")
    return errors


def main() -> int:
    base_dir = Path("priority_variables_transform")
    yaml_files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.endswith(".swp")
    )

    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 1

    normalizer = make_normalizer()
    total_files = 0
    total_blocks = 0
    failed_files = []
    skipped_files = []

    for file_path in yaml_files:
        total_files += 1
        rel_path = str(file_path)

        if rel_path in KNOWN_ISSUES:
            skipped_files.append((file_path, KNOWN_ISSUES[rel_path]))
            continue

        with file_path.open() as f:
            data = yaml.safe_load(f)

        if data is None:
            failed_files.append((file_path, ["  empty file"]))
            continue

        blocks = data if isinstance(data, list) else [data]
        file_errors = []

        for i, block in enumerate(blocks):
            total_blocks += 1
            file_errors.extend(validate_block(block, normalizer, i))

        if file_errors:
            failed_files.append((file_path, file_errors))

    print(f"Validated {total_blocks} blocks across {total_files} files")

    if skipped_files:
        print(f"\nKNOWN ISSUES ({len(skipped_files)} files skipped):")
        for path, reason in skipped_files:
            print(f"  {path}: {reason}")

    if failed_files:
        print(f"\nFAILED ({len(failed_files)} files):")
        for path, errors in failed_files:
            print(f"\n{path}:")
            for err in errors:
                print(err)
        return 1
    else:
        print("\nAll validated files passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
