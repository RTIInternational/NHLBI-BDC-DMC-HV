#!/usr/bin/env python3
"""HV-Lint Phase 1: Cross-file PHT visit label consistency (Rule 1.8).

For each populated_from PHT used across all YAML files in a cohort,
collects every associated_visit label paired with that PHT.  If a PHT
appears with more than one DISTINCT visit label, the minority usage is
flagged as ERROR -- this is always a copy-paste bug.

Handles both static associated_visit values (value: "...") and
expr-based visit references (including uuid5 patterns).  For expr-based
visits, visit labels are extracted using regex parsing of case() results
and uuid5 seed strings.

Checks:
    1.8  Cross-file PHT visit label consistency -- a given PHT should
         map to the same visit label everywhere in the cohort.

Usage:
    python hv-lint/phase-1/check_cross_file_pht_consistency.py
    python hv-lint/phase-1/check_cross_file_pht_consistency.py --cohort MESA
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

PHT_RE = re.compile(r"pht\d{6}")

# -- Regex patterns for visit label extraction from expressions -----------
# Replicates Phase 5's extract_visit_labels_from_expr() locally, since
# phases are independent modules.

# Matches the result string in a case tuple: , "RESULT") or , 'RESULT')
CASE_RESULT_DQ_RE = re.compile(r',\s*"([^"]+)"\s*\)')
CASE_RESULT_SQ_RE = re.compile(r",\s*'([^']+)'\s*\)")

# Matches string concatenated after closing paren: ) + "SUFFIX" or ) + 'SUFFIX'
SUFFIX_AFTER_PAREN_DQ_RE = re.compile(r'\)\s*\+\s*"([^"]*)"')
SUFFIX_AFTER_PAREN_SQ_RE = re.compile(r"\)\s*\+\s*'([^']*)'")

# Matches any quoted string (double or single)
QUOTED_DQ_RE = re.compile(r'"([^"]+)"')
QUOTED_SQ_RE = re.compile(r"'([^']+)'")

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}


def _extract_labels_from_expr(expr: str) -> set[str]:
    """Extract human-readable visit labels from a uuid5 or case expression.

    Handles:
      - Simple case(): case((..., "LABEL1"), (..., "LABEL2"))
      - Case + suffix: case((..., "PREFIX1"), ...) + " SUFFIX"
      - UUID5 wrapping: uuid5("URL", ... + case(...) + " SUFFIX")
      - FHS Pattern A: str({phv}) + ":LABEL"
      - Single-label uuid5: uuid5("URL", str({phv}) + ":LABEL")
    """
    expr_str = str(expr)

    # Extract case() result strings (both quote flavours)
    case_results = (
        CASE_RESULT_DQ_RE.findall(expr_str)
        + CASE_RESULT_SQ_RE.findall(expr_str)
    )

    if case_results:
        # Look for suffix concatenated after case(): ) + "SUFFIX"
        suffixes = (
            SUFFIX_AFTER_PAREN_DQ_RE.findall(expr_str)
            + SUFFIX_AFTER_PAREN_SQ_RE.findall(expr_str)
        )
        visit_suffix = ""
        for s in suffixes:
            stripped = s.strip()
            if (stripped
                    and not stripped.startswith("http")
                    and stripped != ":"
                    and s not in case_results
                    and any(c.isalpha() for c in stripped)):
                visit_suffix = s
                break
        return {
            (cr + visit_suffix).lstrip(":")
            for cr in case_results
        }

    # No case() -- extract quoted strings as candidate labels
    all_quoted = (
        QUOTED_DQ_RE.findall(expr_str)
        + QUOTED_SQ_RE.findall(expr_str)
    )
    labels = {
        s.lstrip(":")
        for s in all_quoted
        if not s.startswith("http")
        and len(s) > 1
        and any(c.isalpha() for c in s)
        and s.lstrip(":") != ""
    }
    labels.discard("")
    return labels


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


@dataclass
class PhtVisitRef:
    """A single (PHT, visit_label) reference from a data block."""
    pht: str
    visit_label: str
    file: str
    block_index: int
    bdchm_class: str


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


def _extract_visit_refs(
    block: dict, block_idx: int, rel_path: str,
) -> list[PhtVisitRef]:
    """Extract (PHT, visit_label) pairs from a block.

    Handles BOTH static ``value:`` and ``expr:`` (including uuid5)
    visit references.  Skips visit.yaml blocks (Visit class) since
    they define visits rather than reference them.

    For expr-based visits, extracts visit labels using regex parsing
    of case() results and uuid5 seed strings.  Each extracted label
    generates a separate PhtVisitRef.
    """
    refs: list[PhtVisitRef] = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return refs

    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue

        # Skip visit.yaml Visit blocks -- they define, not reference
        if cls_name == "Visit":
            continue

        pht = cls_def.get("populated_from")
        if not isinstance(pht, str) or not PHT_RE.fullmatch(pht):
            continue

        slot_derivs = cls_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            continue

        visit_def = slot_derivs.get("associated_visit")
        if not isinstance(visit_def, dict):
            continue

        # Try static value first
        visit_value = visit_def.get("value")
        if isinstance(visit_value, str) and visit_value.strip():
            if not visit_def.get("expr"):
                refs.append(PhtVisitRef(
                    pht=pht,
                    visit_label=visit_value.strip(),
                    file=rel_path,
                    block_index=block_idx,
                    bdchm_class=cls_name,
                ))
                continue

        # Try expr-based visit (uuid5, case, etc.)
        visit_expr = visit_def.get("expr")
        if isinstance(visit_expr, str) and visit_expr.strip():
            labels = _extract_labels_from_expr(visit_expr)
            for label in labels:
                if label.strip():
                    refs.append(PhtVisitRef(
                        pht=pht,
                        visit_label=label.strip(),
                        file=rel_path,
                        block_index=block_idx,
                        bdchm_class=cls_name,
                    ))

    return refs


def check_cross_file_pht_consistency(
    all_refs: list[PhtVisitRef],
) -> list[Finding]:
    """Check 1.8: Cross-file PHT visit label consistency.

    Groups references by PHT.  For each PHT with >1 distinct visit
    label, identifies the majority label and flags minority occurrences
    as ERROR.  If there's no clear majority (equal split), all
    occurrences are flagged so the user can investigate.
    """
    findings: list[Finding] = []

    # Group by PHT
    pht_refs: dict[str, list[PhtVisitRef]] = defaultdict(list)
    for ref in all_refs:
        pht_refs[ref.pht].append(ref)

    for pht, refs in sorted(pht_refs.items()):
        # Count distinct labels
        label_counts: dict[str, int] = defaultdict(int)
        label_refs: dict[str, list[PhtVisitRef]] = defaultdict(list)
        for ref in refs:
            label_counts[ref.visit_label] += 1
            label_refs[ref.visit_label].append(ref)

        if len(label_counts) <= 1:
            continue  # Consistent -- nothing to flag

        # Find majority label
        sorted_labels = sorted(label_counts.items(), key=lambda x: -x[1])
        majority_label, majority_count = sorted_labels[0]
        second_count = sorted_labels[1][1]

        if majority_count == second_count:
            # No clear majority -- flag ALL occurrences
            all_labels = ", ".join(
                f"'{lb}' ({ct}x)" for lb, ct in sorted_labels
            )
            for ref in refs:
                findings.append(Finding(
                    file=ref.file,
                    block=ref.block_index,
                    check="1.8",
                    severity="ERROR",
                    message=(
                        f"{pht} has inconsistent visit labels across files: "
                        f"{all_labels} -- no clear majority, manual review needed"
                    ),
                ))
        else:
            # Clear majority -- flag minority occurrences only
            for label, label_count in sorted_labels[1:]:
                majority_files = sorted(set(
                    r.file.rsplit("/", 1)[-1] for r in label_refs[majority_label]
                ))
                majority_examples = ", ".join(majority_files[:3])
                if len(majority_files) > 3:
                    majority_examples += f" (+{len(majority_files) - 3} more)"

                for ref in label_refs[label]:
                    findings.append(Finding(
                        file=ref.file,
                        block=ref.block_index,
                        check="1.8",
                        severity="ERROR",
                        message=(
                            f"{pht} uses visit label '{ref.visit_label}' here "
                            f"but '{majority_label}' in {majority_count} other "
                            f"block(s) ({majority_examples}) -- likely copy-paste error"
                        ),
                    ))

    return findings


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Check 1.8: Cross-file PHT visit label consistency"
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

    all_refs: list[PhtVisitRef] = []
    files_checked = 0

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

        for idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            all_refs.extend(
                _extract_visit_refs(block, idx, rel_path)
            )

    findings = check_cross_file_pht_consistency(all_refs)

    # -- Report --------------------------------------------------------
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    # Count distinct PHTs checked
    unique_phts = len(set(r.pht for r in all_refs))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    findings_by_file: dict[str, list[Finding]] = {}
    for f in findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"{'='*70}")
    print("HV-Lint Check 1.8: Cross-File PHT Visit Label Consistency")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"PHT references: {len(all_refs)} (across {unique_phts} unique PHTs)")

    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print(
            "Findings:       None -- all PHTs have consistent visit "
            "labels across files"
        )

    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            print(f"\n{short}:")
            for f in sorted(
                findings_by_file[fpath], key=lambda x: (x.block, x.check)
            ):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    blocking = [
        f for f in findings
        if SEVERITY_RANK.get(f.severity, 0) >= fail_rank
    ]
    if blocking:
        print(f"\nFAILED: {len(blocking)} findings at or above '{args.fail_on}'")
        return 1
    if findings:
        print(
            f"\nPASSED (with {len(findings)} advisory findings "
            f"below fail threshold)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
