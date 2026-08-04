#!/usr/bin/env python3
"""HV-Lint Phase 2: PHV Deduplication Check (2.8).

Flags any PHV accession that is mapped as a measured value in more than one
harmonized variable block within the same cohort.

Adapted from check_phv_dedup.py (HV repo root, currently in validate_ingest_yamls.yml CI).

Usage:
    python hv-lint/phase-2/check_phv_dedup.py
    python hv-lint/phase-2/check_phv_dedup.py --cohort ARIC
    python hv-lint/phase-2/check_phv_dedup.py --fail-on warning
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

# Cohort detection: directory name before "-ingest" -> cohort key
COHORT_DIR_PATTERN = "-ingest"

# Severity ranking for --fail-on filtering
SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int
    check: str       # "2.8"
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


# ---------------------------------------------------------------------------
# PHV extraction
# ---------------------------------------------------------------------------

def _get_cohort_from_path(file_path: Path) -> str:
    """Extract cohort name from file path (e.g., ARIC-ingest/bmi.yaml -> ARIC)."""
    for part in file_path.parts:
        if COHORT_DIR_PATTERN in part:
            return part.split(COHORT_DIR_PATTERN)[0]
    return "UNKNOWN"


def iter_nested_class_derivs(slot_def):
    """Yield (class_name, class_spec) for a slot's nested class derivations,
    handling list-based class_derivations in both `- name: X` and dict-keyed
    `- X: {...}` form, plus legacy object_derivations."""
    slot_def = slot_def or {}
    for cd in slot_def.get("class_derivations") or []:
        if not isinstance(cd, dict):
            continue
        if "name" in cd:
            yield cd.get("name"), cd
        elif len(cd) == 1:
            # dict-keyed form: `- ClassName: {...}`
            cls_name, spec = next(iter(cd.items()))
            yield cls_name, spec
    for od in slot_def.get("object_derivations") or []:
        for name, spec in ((od or {}).get("class_derivations") or {}).items():
            yield name, spec


def extract_value_phvs(block: dict, block_index: int):
    """Yield (phv, concept, block_index) for value-bearing populated_from fields.

    Only extracts PHVs from slots that carry the measured/observed value,
    not from linkage slots like associated_participant or associated_visit.
    """
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


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_yaml_files(base_dir: Path, cohort: str) -> list[Path]:
    """Find all *-ingest/*.yaml files, optionally filtered by cohort."""
    files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.startswith("_")
        and not f.name.endswith(".swp")
    )
    if cohort.lower() != "all":
        pattern = f"{cohort}-ingest".lower()
        files = [f for f in files if any(part.lower() == pattern for part in f.parts)]
    return files


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 2: PHV deduplication check (2.8)"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC, CHS) or 'all' (default: all)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)"
    )
    p.add_argument(
        "--summary-file", default=None,
        help="Write a Markdown summary table to this file"
    )
    p.add_argument(
        "--summary-limit", type=int, default=50,
        help="Max findings to include in the Markdown summary (default: 50)"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    # Discover YAML files
    base_dir = TRANSFORM_DIR
    if not base_dir.exists():
        print(f"HV repo transform directory not found: {base_dir}", file=sys.stderr)
        return 1
    yaml_files = find_yaml_files(base_dir, args.cohort)

    if not yaml_files:
        print("No YAML files found to validate")
        return 1
    print(f"Found {len(yaml_files)} YAML files to check for PHV deduplication")

    # Collect PHV -> (concept, file, block) mappings per cohort
    # phv -> [(concept, file_path, block_index), ...]
    phv_hits: dict[str, dict[str, list[tuple[str | None, str, int]]]] = {}
    parse_errors: list[tuple[str, str]] = []

    for file_path in yaml_files:
        try:
            rel_path = file_path.relative_to(base_dir.parent).as_posix()
        except ValueError:
            rel_path = file_path.as_posix()
        cohort = _get_cohort_from_path(file_path)

        if cohort not in phv_hits:
            phv_hits[cohort] = defaultdict(list)

        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as exc:
            parse_errors.append((rel_path, str(exc)))
            continue

        if data is None:
            continue

        blocks = data if isinstance(data, list) else [data]
        for i, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            for phv, concept, block_index in extract_value_phvs(block, i):
                phv_hits[cohort][phv].append((concept, rel_path, block_index))

    # Identify duplicates: PHVs mapped to multiple distinct concepts
    all_findings: list[Finding] = []
    total_phvs = sum(len(d) for d in phv_hits.values())

    for cohort in sorted(phv_hits):
        for phv in sorted(phv_hits[cohort]):
            hits = phv_hits[cohort][phv]
            concepts = {c for c, _, _ in hits}
            if len(concepts) > 1:
                # Build a human-readable message
                details = []
                for concept, fpath, block_idx in hits:
                    short = fpath.replace("priority_variables_transform/", "")
                    details.append(f"{concept} in {short} block {block_idx}")
                msg = (f"PHV {phv} mapped to {len(concepts)} concepts in {cohort}: "
                       f"{'; '.join(details)}")
                # Report on the first file that uses this PHV
                first_file = hits[0][1]
                first_block = hits[0][2]
                all_findings.append(Finding(
                    first_file, first_block, "2.8", "WARNING", msg
                ))

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    print(f"\n{'='*70}")
    print("HV-Lint Phase 2: PHV Deduplication Results (Check 2.8)")
    print(f"{'='*70}")
    print(f"Files scanned:  {len(yaml_files)}")
    print(f"Unique PHVs:    {total_phvs}")

    if parse_errors:
        print(f"Parse errors:   {len(parse_errors)}")

    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print("Findings:       None -- no PHV duplicates detected!")

    if all_findings:
        print(f"\n{'-'*70}")
        for f in sorted(all_findings, key=lambda x: x.message):
            print(f.terminal_line())
            if in_ci:
                print(f.gh_annotation())

    # Write Markdown summary
    if args.summary_file:
        _write_summary(args.summary_file, len(yaml_files), total_phvs,
                       counts, all_findings, args.summary_limit)

    # Determine exit code
    blocking = [
        f for f in all_findings
        if SEVERITY_RANK.get(f.severity, 0) >= fail_rank
    ]
    if blocking:
        print(f"\n{'='*70}")
        print(f"FAILED: {len(blocking)} findings at or above '{args.fail_on}' severity")
        return 1
    else:
        if all_findings:
            print(f"\n{'='*70}")
            print(f"PASSED (with {len(all_findings)} advisory findings below fail threshold)")
        return 0


def _write_summary(path: str, files: int, phvs: int,
                   counts: dict[str, int], findings: list[Finding],
                   limit: int) -> None:
    """Write a Markdown summary table for GITHUB_STEP_SUMMARY."""
    lines: list[str] = []
    lines.append("## HV-Lint Phase 2: PHV Deduplication Results (Check 2.8)\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Files scanned | {files} |")
    lines.append(f"| Unique PHVs | {phvs} |")
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            lines.append(f"| {sev} | {counts[sev]} |")
    lines.append("")
    if findings:
        sorted_findings = sorted(findings, key=lambda f: f.message)
        shown = sorted_findings[:limit]
        lines.append(f"### Findings (showing {len(shown)} of {len(findings)})\n")
        lines.append("| Severity | PHV | Message |")
        lines.append("|----------|-----|---------|")
        _phv_re = re.compile(r"(phv\d{8})")
        for f in shown:
            msg = (f.message.replace("\r", " ").replace("\n", " ")
                   .replace("|", "\\|"))
            phv_match = _phv_re.search(f.message)
            phv_col = phv_match.group(1) if phv_match else f.check
            lines.append(f"| {f.severity} | {phv_col} | {msg} |")
        if len(findings) > limit:
            lines.append(
                f"\n> **{len(findings) - limit} additional findings omitted.**"
            )
    else:
        lines.append("No PHV duplicates detected!\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
