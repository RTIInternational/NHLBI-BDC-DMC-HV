"""Validate all trans-spec YAML files against the linkml-map transformer model."""

import sys
import warnings
from pathlib import Path

import yaml
from linkml_map.validator import validate_spec

# Known issues to be fixed by curation team. These files are excluded from
# validation failures so CI stays green while issues are tracked separately.
# Remove entries as they are fixed.
KNOWN_ISSUES = {
    "priority_variables_transform/FHS-ingest/_manifest-fhs.yaml": "version tracking manifest, not a transformation spec",
}


def validate_block(block: dict, block_index: int) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        errors = list(validate_spec(block))
    # Gate on the deprecated slot-level `object_derivations` construct (#636):
    # migrate any new occurrence to list-based `class_derivations`. This keeps
    # the gate from going blind to reintroductions of the deprecated form.
    if any("object_derivations" in str(w.message) for w in caught):
        errors.append(
            "uses deprecated 'object_derivations'; migrate to list-based "
            "'class_derivations' (see #636)"
        )
    return [f"  block {block_index}: {e}" for e in errors]


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

    total_files = 0
    total_blocks = 0
    failed_files = []
    skipped_files = []

    for file_path in yaml_files:
        total_files += 1
        rel_path = file_path.as_posix()

        if rel_path in KNOWN_ISSUES:
            skipped_files.append((file_path, KNOWN_ISSUES[rel_path]))
            continue

        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            failed_files.append((file_path, [f"  failed to read/parse YAML: {e}"]))
            continue

        if data is None:
            failed_files.append((file_path, ["  empty file"]))
            continue

        blocks = data if isinstance(data, list) else [data]
        file_errors = []

        for i, block in enumerate(blocks):
            total_blocks += 1
            file_errors.extend(validate_block(block, i))

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
