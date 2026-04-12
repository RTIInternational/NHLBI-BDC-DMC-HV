#!/usr/bin/env python3
"""HV-Lint Phase 1: Cross-block slot consistency check (Rule 1.6).

Detects slots present in one class_derivation block but missing from
another block of the same BDCHM class within the same YAML file.
Catches the common copy-paste error where a new block omits a slot
that the original block had.

Checks:
    1.6  Cross-block slot consistency -- slots in the union but absent
         from a block are flagged as WARNING.

Usage:
    python hv-lint/phase-1/check_cross_block_consistency.py
    python hv-lint/phase-1/check_cross_block_consistency.py --cohort HCHS
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

# Slots that legitimately vary between blocks and should not be flagged.
EXCLUDED_SLOTS = {
    "id",
    "associated_participant",
    "associated_visit",
}

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}


@dataclass
class Finding:
    file: str
    block: int
    check: str
    severity: str
    message: str

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        return f"  {sev}  block {self.block:>3}  [{self.check}] {self.message}"

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error", "HIGH": "warning",
            "WARNING": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        file_esc = (self.file.replace("%", "%25").replace("\r", "%0D")
                    .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))
        msg_esc = self.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return f"::{level} file={file_esc}::HV-Lint [{self.check}] {msg_esc} (block {self.block})"


def find_yaml_files(base_dir: Path, cohort: str) -> list[Path]:
    files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.endswith(".swp")
    )
    if cohort.lower() != "all":
        pattern = f"{cohort}-ingest".lower()
        files = [f for f in files if pattern in str(f).lower()]
    return files


def _extract_class_slots(block: dict) -> dict[str, dict[str, set[str]]]:
    """Extract class name -> {block_pht -> set of slot names} from one block.

    Returns a dict keyed by BDCHM class name, with values being a dict
    mapping populated_from PHT to the set of slot names defined.
    """
    result: dict[str, dict[str, set[str]]] = {}
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return result

    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        pht = cls_def.get("populated_from", "")
        if not isinstance(pht, str):
            pht = str(pht)
        slot_derivs = cls_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            continue
        slots = set(slot_derivs.keys()) - EXCLUDED_SLOTS
        result[cls_name] = {pht: slots}

    return result


def check_cross_block_consistency(
    blocks: list[dict], rel_path: str
) -> list[Finding]:
    """Check 1.6: Cross-block slot consistency within a single file.

    Groups blocks by BDCHM class name. For each class with 2+ blocks,
    computes the union of all slot names and flags blocks missing slots
    from the union. Only compares blocks sharing the same populated_from
    PHT (different source tables may genuinely lack certain variables).
    """
    findings: list[Finding] = []

    # Collect: class_name -> [(block_idx, pht, slots)]
    class_blocks: dict[str, list[tuple[int, str, set[str]]]] = {}

    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        for cls_name, pht_slots in _extract_class_slots(block).items():
            for pht, slots in pht_slots.items():
                class_blocks.setdefault(cls_name, []).append((idx, pht, slots))

    for cls_name, block_list in class_blocks.items():
        if len(block_list) < 2:
            continue

        # Compute union of all slots across all blocks of this class
        all_slots = set()
        for _, _, slots in block_list:
            all_slots.update(slots)

        for block_idx, pht, slots in block_list:
            missing = all_slots - slots
            if not missing:
                continue
            pht_label = pht if pht else "unknown"
            for slot in sorted(missing):
                # Find which block(s) have this slot for context
                providers = [
                    str(bi) for bi, _, s in block_list if slot in s
                ]
                provider_str = ", ".join(providers[:3])
                findings.append(Finding(
                    file=rel_path,
                    block=block_idx,
                    check="1.6",
                    severity="WARNING",
                    message=(
                        f"{cls_name} block {block_idx} ({pht_label}) "
                        f"missing slot '{slot}' -- present in block(s) "
                        f"{provider_str}"
                    ),
                ))

    return findings


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Check 1.6: Cross-block slot consistency"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate or 'all' (default: all)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    base_dir = TRANSFORM_DIR
    hv_root = base_dir.parent
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 0

    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0

    for file_path in yaml_files:
        rel_path = file_path.relative_to(hv_root).as_posix()

        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue

        if data is None:
            continue

        blocks = data if isinstance(data, list) else [data]
        files_checked += 1
        blocks_checked += len(blocks)

        all_findings.extend(
            check_cross_block_consistency(blocks, rel_path)
        )

    # Report
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"{'='*70}")
    print("HV-Lint Check 1.6: Cross-Block Slot Consistency")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")

    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print("Findings:       None -- all blocks have consistent slots")

    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath], key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    blocking = [
        f for f in all_findings
        if SEVERITY_RANK.get(f.severity, 0) >= fail_rank
    ]
    if blocking:
        print(f"\nFAILED: {len(blocking)} findings at or above '{args.fail_on}'")
        return 1
    if all_findings:
        print(f"\nPASSED (with {len(all_findings)} advisory warnings below fail threshold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
