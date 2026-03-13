#!/usr/bin/env python3
"""HV-Lint Phase 2: dbGaP cross-reference validation for HV YAML files.

Validates that PHV and PHT accessions referenced in transformation YAML
files actually exist in the dbGaP variable index and have correct
table membership.

Requires a pre-built compressed index in hv-lint/dbgap-cache/ (generated
by build_phv_index.py).

Usage:
    python hv-lint/validate_phv_cross_reference.py
    python hv-lint/validate_phv_cross_reference.py --cohort ARIC
    python hv-lint/validate_phv_cross_reference.py --cache-dir /path/to/indexes

Checks implemented:
    2.1  PHV existence — referenced PHVs must exist in dbGaP index
    2.2  PHT existence — referenced PHTs must exist in dbGaP index
    2.3  PHV-to-PHT membership — PHVs must belong to the declared table
    2.5  Cross-table reference — PHV from a different table without joins
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps directory-derived cohort name → dbGaP cache key
COHORT_TO_CACHE_KEY: dict[str, str] = {
    "ARIC": "aric",
    "CARDIA": "cardia",
    "CHS": "chs",
    "COPDGene": "copdgene",
    "FHS": "fhs",
    "HCHS": "hchs_sol",
    "JHS": "jhs",
    "MESA": "mesa",
    "SPIROMICS": "spiromics",
    "WHI": "whi",
}

# Files to skip entirely
KNOWN_ISSUES: dict[str, str] = {
    "priority_variables_transform/FHS-ingest/il18.yaml":
        "empty file (entirely commented out)",
    "priority_variables_transform/FHS-ingest/pr_qrs_qt.yaml":
        "MeasurementObservationSet nesting not in linkml-map schema",
    "priority_variables_transform/FHS-ingest/_manifest-fhs.yaml":
        "version tracking manifest, not a transformation spec",
}

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# Slots that routinely reference a different table (e.g.,
# associated_participant always comes from the subject table,
# age_at_* slots reference the visit/age table).
EXPECTED_CROSS_TABLE_SLOTS = {
    "associated_participant", "associated_visit",
}
# Slot name prefixes where cross-table references are normal
EXPECTED_CROSS_TABLE_PREFIXES = (
    "age_at_", "age_of_",
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int
    check: str       # e.g., "2.1"
    severity: str    # CRITICAL, ERROR, WARNING, INFO
    message: str

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error",
            "WARNING": "warning", "HIGH": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        return f"::{level} file={self.file}::HV-Lint [{self.check}] {self.message} (block {self.block})"

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        return f"  {sev}  block {self.block:>3}  [{self.check}] {self.message}"


@dataclass
class DbGaPIndex:
    """Pre-built dbGaP index for a single cohort."""
    phv_to_pht: dict[str, str] = field(default_factory=dict)  # phv -> pht
    valid_phts: set[str] = field(default_factory=set)

# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def load_dbgap_index(cache_dir: Path, cache_key: str) -> DbGaPIndex:
    """Load compressed phv->pht index for a cohort."""
    gz_path = cache_dir / f"{cache_key}.json.gz"
    json_path = cache_dir / f"{cache_key}.json"

    if gz_path.exists():
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            mapping = json.load(f)
    elif json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        raise FileNotFoundError(
            f"No dbGaP index for '{cache_key}': "
            f"expected {gz_path} or {json_path}"
        )

    idx = DbGaPIndex()
    idx.phv_to_pht = mapping
    idx.valid_phts = set(mapping.values())
    return idx

# ---------------------------------------------------------------------------
# File discovery (shared with Phase 1)
# ---------------------------------------------------------------------------

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


def detect_cohort(file_path: Path) -> str:
    for part in file_path.parts:
        if part.endswith("-ingest"):
            return part.replace("-ingest", "")
    return "UNKNOWN"

# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------

PHV_RE = re.compile(r"phv\d{8}")
PHT_RE = re.compile(r"pht\d{6}")


def extract_slot_refs(
    slot_derivs: dict, class_name: str
) -> tuple[list[tuple[str, str]], set[str]]:
    """Extract PHV references and join PHTs from slot_derivations.

    Returns:
        phv_refs: list of (phv, "slot_name on ClassName")
        join_phts: set of PHTs declared via joins
    """
    phv_refs: list[tuple[str, str]] = []
    join_phts: set[str] = set()

    if not isinstance(slot_derivs, dict):
        return phv_refs, join_phts

    for slot_name, slot_def in slot_derivs.items():
        if not isinstance(slot_def, dict):
            continue

        # Direct populated_from
        pf = slot_def.get("populated_from")
        if isinstance(pf, str) and PHV_RE.fullmatch(pf):
            phv_refs.append((pf, f"{slot_name} on {class_name}"))

        # PHVs in expr (within {phv...} or plain references)
        expr = slot_def.get("expr")
        if isinstance(expr, str):
            for m in PHV_RE.finditer(expr):
                phv_refs.append((m.group(), f"expr in {slot_name} on {class_name}"))

        # PHVs in value_mappings keys
        vm = slot_def.get("value_mappings")
        if isinstance(vm, dict):
            for k in vm:
                if isinstance(k, str):
                    for m in PHV_RE.finditer(k):
                        phv_refs.append((m.group(), f"value_mappings key in {slot_name} on {class_name}"))

        # PHVs in expression_to_value_mappings keys
        evm = slot_def.get("expression_to_value_mappings")
        if isinstance(evm, dict):
            for k in evm:
                if isinstance(k, str):
                    for m in PHV_RE.finditer(k):
                        phv_refs.append((m.group(), f"expression_to_value_mappings in {slot_name} on {class_name}"))

        # Recurse into object_derivations
        for od in (slot_def.get("object_derivations") or []):
            if isinstance(od, dict) and "class_derivations" in od:
                for nested_cls, nested_def in od["class_derivations"].items():
                    if isinstance(nested_def, dict):
                        nested_slots = nested_def.get("slot_derivations", {})
                        nested_phvs, nested_joins = extract_slot_refs(nested_slots, nested_cls)
                        phv_refs.extend(nested_phvs)
                        join_phts.update(nested_joins)

                        # Nested class populated_from PHT
                        npht = nested_def.get("populated_from")
                        if isinstance(npht, str) and PHT_RE.fullmatch(npht):
                            join_phts.add(npht)

    return phv_refs, join_phts


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_block(
    block: dict, block_idx: int, rel_path: str,
    dbgap: DbGaPIndex
) -> list[Finding]:
    """Run all Phase 2 checks on a single block."""
    findings: list[Finding] = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return findings

    for class_name, class_def in class_derivs.items():
        if not isinstance(class_def, dict):
            continue

        class_pht = class_def.get("populated_from", "")
        has_joins = isinstance(class_def.get("joins"), list)
        slot_derivs = class_def.get("slot_derivations") or {}

        # Collect join PHTs for cross-table detection
        join_phts: set[str] = set()
        if has_joins:
            for j in class_def["joins"]:
                if isinstance(j, dict):
                    jpht = j.get("populated_from", "")
                    if PHT_RE.fullmatch(jpht):
                        join_phts.add(jpht)

        # -- Check 2.2: PHT existence --
        if isinstance(class_pht, str) and PHT_RE.fullmatch(class_pht):
            if class_pht not in dbgap.valid_phts:
                findings.append(Finding(
                    rel_path, block_idx, "2.2", "ERROR",
                    f"PHT '{class_pht}' on {class_name} not found in "
                    f"dbGaP variable index"
                ))

        # Extract PHV references from slot derivations
        phv_refs, nested_join_phts = extract_slot_refs(slot_derivs, class_name)
        join_phts.update(nested_join_phts)

        # Track which non-class PHTs are reachable via joins
        all_reachable_phts = {class_pht} | join_phts

        for phv, context in phv_refs:
            # -- Check 2.1: PHV existence --
            if phv not in dbgap.phv_to_pht:
                findings.append(Finding(
                    rel_path, block_idx, "2.1", "ERROR",
                    f"PHV '{phv}' ({context}) not found in dbGaP index"
                ))
                continue

            actual_pht = dbgap.phv_to_pht[phv]

            # -- Check 2.3 / 2.5: PHV-to-PHT membership --
            if not (isinstance(class_pht, str) and PHT_RE.fullmatch(class_pht)):
                continue
            if actual_pht != class_pht:
                # Determine the slot name from context string
                slot_in_context = context.split(" on ")[0] if " on " in context else ""
                # For "expr in slot_name" patterns, extract the actual slot
                bare_slot = slot_in_context.replace("expr in ", "").replace(
                    "value_mappings key in ", ""
                ).replace("expression_to_value_mappings in ", "")

                if actual_pht in all_reachable_phts:
                    # Cross-table but covered by a join
                    findings.append(Finding(
                        rel_path, block_idx, "2.3", "INFO",
                        f"PHV '{phv}' ({context}) belongs to {actual_pht}, "
                        f"not class PHT {class_pht} (covered by joins)"
                    ))
                elif (bare_slot in EXPECTED_CROSS_TABLE_SLOTS
                      or any(bare_slot.startswith(pfx) for pfx in EXPECTED_CROSS_TABLE_PREFIXES)):
                    # Expected cross-table pattern
                    findings.append(Finding(
                        rel_path, block_idx, "2.3", "INFO",
                        f"PHV '{phv}' ({context}) belongs to {actual_pht}, "
                        f"not class PHT {class_pht} (expected cross-table)"
                    ))
                else:
                    # Unexpected cross-table reference
                    findings.append(Finding(
                        rel_path, block_idx, "2.5", "WARNING",
                        f"PHV '{phv}' ({context}) belongs to {actual_pht}, "
                        f"not class PHT {class_pht} - possible cross-table "
                        f"reference without joins"
                    ))

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 2: dbGaP cross-reference validation"
    )
    p.add_argument(
        "--cache-dir",
        default=str(Path(__file__).parent / "dbgap-cache"),
        help="Directory containing per-cohort .json.gz indexes "
             "(default: hv-lint/dbgap-cache/)"
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
        help="Write a Markdown summary table to this file (for GITHUB_STEP_SUMMARY)"
    )
    p.add_argument(
        "--summary-limit", type=int, default=50,
        help="Max findings to include in the Markdown summary (default: 50)"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    cache_dir = Path(args.cache_dir)

    if not cache_dir.is_dir():
        print(f"ERROR: Cache directory not found: {cache_dir}", file=sys.stderr)
        print("Run build_phv_index.py first to generate the indexes.", file=sys.stderr)
        return 1

    # Load indexes for all available cohorts
    indexes: dict[str, DbGaPIndex] = {}
    for cohort_name, cache_key in COHORT_TO_CACHE_KEY.items():
        try:
            indexes[cohort_name] = load_dbgap_index(cache_dir, cache_key)
            count = len(indexes[cohort_name].phv_to_pht)
            phts = len(indexes[cohort_name].valid_phts)
            print(f"  Loaded {cohort_name}: {count:,} PHVs across {phts} PHTs")
        except FileNotFoundError:
            pass  # cohort not available — will skip files for it

    if not indexes:
        print("ERROR: No dbGaP indexes found. Run build_phv_index.py.", file=sys.stderr)
        return 1

    # Discover YAML files
    base_dir = Path("priority_variables_transform")
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 1
    print(f"Found {len(yaml_files)} YAML files to validate")

    # Run checks
    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0
    skipped_no_index: list[str] = []

    for file_path in yaml_files:
        rel_path = file_path.as_posix()

        if rel_path in KNOWN_ISSUES:
            continue

        cohort = detect_cohort(file_path)
        if cohort not in indexes:
            skipped_no_index.append(rel_path)
            continue

        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue  # Phase 1 catches parse errors

        if data is None:
            continue

        blocks = data if isinstance(data, list) else [data]
        files_checked += 1
        dbgap = indexes[cohort]

        for idx, block in enumerate(blocks):
            blocks_checked += 1
            if not isinstance(block, dict):
                continue
            all_findings.extend(check_block(block, idx, rel_path, dbgap))

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"\n{'='*70}")
    print("HV-Lint Phase 2 Results")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")
    if skipped_no_index:
        print(f"Files skipped (no index): {len(skipped_no_index)}")

    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print("Findings:       None - all checks passed!")

    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath], key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    # Write Markdown summary
    if args.summary_file:
        _write_summary(args.summary_file, "Phase 2", files_checked, blocks_checked,
                       counts, all_findings, args.summary_limit)

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


def _write_summary(path: str, phase: str, files: int, blocks: int,
                   counts: dict[str, int], findings: list[Finding],
                   limit: int) -> None:
    """Write a Markdown summary table for GITHUB_STEP_SUMMARY."""
    lines: list[str] = []
    lines.append(f"## HV-Lint {phase} Results\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Files checked | {files} |")
    lines.append(f"| Blocks checked | {blocks} |")
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            lines.append(f"| {sev} | {counts[sev]} |")
    lines.append("")
    if findings:
        sorted_findings = sorted(findings, key=lambda f: SEVERITY_RANK.get(f.severity, 0), reverse=True)
        shown = sorted_findings[:limit]
        lines.append(f"### Findings (showing {len(shown)} of {len(findings)})\n")
        lines.append("| Severity | File | Block | Check | Message |")
        lines.append("|----------|------|-------|-------|---------|")
        for f in shown:
            short = f.file.replace("priority_variables_transform/", "")
            lines.append(f"| {f.severity} | {short} | {f.block} | {f.check} | {f.message} |")
        if len(findings) > limit:
            lines.append(f"\n> **{len(findings) - limit} additional findings omitted.** "
                         f"Re-run with a higher `summary_limit` or check the raw log.")
    else:
        lines.append("All checks passed!\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
