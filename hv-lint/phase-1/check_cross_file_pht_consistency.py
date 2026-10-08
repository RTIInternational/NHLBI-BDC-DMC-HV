#!/usr/bin/env python3
"""HV-Lint Phase 1: Cross-file PHT visit label consistency (Rule 1.8).

Every data block names the visit(s) its rows belong to. Blocks that read the same dbGaP table
should agree on them. The unit of comparison is a block's label SET: a block whose
``associated_visit`` is a ``case()`` over a cohort or phase code legitimately emits several labels,
and two blocks of one multi-exam table legitimately emit different ones, so counting labels across
blocks (and calling the rarer one a copy-paste error) reports differences that are design.

Labels come from the shared enumerator (``_visit_ids``): comparison operands are never labels,
and a ``(True, ...)`` fallback arm (``FHS UNKNOWN VISIT``) is dropped.

Checks:
    1.8  Cross-file PHT visit label consistency
         - ERROR: a block with exactly one label disagrees with the exam its FHS table encodes
           in its dbGaP short name (``ex<cohort>_<exam>s``, ``..._ex<NN>_<cohort>[b]_...``).
           This is the check that found #782's 11 real wrong labels.
         - ERROR: on any table, a block with exactly one label disagrees with a label carried by
           at least MAJORITY_MIN_BLOCKS of the table's other single-label blocks, making up at
           least MAJORITY_MIN_SHARE of them (a copy-paste label on a single-exam table).
         - WARNING: two blocks of one table carry label sets that overlap while neither contains
           the other.

Usage:
    python hv-lint/phase-1/check_cross_file_pht_consistency.py
    python hv-lint/phase-1/check_cross_file_pht_consistency.py --cohort MESA
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
import _known_issues  # noqa: E402
import _cohorts  # noqa: E402
import _visit_ids  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

PHT_RE = re.compile(r"pht\d{6}")

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# FHS cohort codes as they appear in table short names and IDTYPE values.
FHS_COHORT_CODE = {
    "0": "ORIGINAL", "1": "OFFSPRING", "2": "NEW OFFSPRING SPOUSE", "3": "GENERATION 3",
    "7": "OMNI 1", "72": "OMNI 2",
}
_FHS_EXAM_SHORT_RE = re.compile(r"^ex(\d+)_(\d+)s$")
_FHS_EXAM_LONG_RE = re.compile(r"(?:^|_)ex(\d+)_(\d+)(b?)(?:_|$)")


_EXAM_RANGE_RE = re.compile(r"Exams?\s+(\d+)\s*-\s*(?:Exam\s+)?(\d+)", re.IGNORECASE)


def expected_fhs_labels(short_name: str, description: str = "") -> set[str] | None:
    """The visit labels an FHS table's dbGaP short name allows, or None when it encodes none.

    ``ex0_7s`` names Original Exam 7 but holds Exams 1-7, which its description says ("Original
    Cohort Exams 1 - 7"), so a description range widens the set. ``l_cortisol_ex06_1b_0495s``
    is Offspring Exam 6; its ``b`` marks a table shared with Omni 1, whose exam number is five
    lower (the Offspring / Omni 1 exam alignment). ``..._ex01_3b_...`` is Gen 3 Exam 1 shared
    with New Offspring Spouse and Omni 2. Derived ``vr_`` tables carry one column per exam, so
    their name encodes no single exam.
    """
    if short_name.startswith("vr_"):
        return None
    m = _FHS_EXAM_SHORT_RE.match(short_name)
    if m:
        cohort = FHS_COHORT_CODE.get(m.group(1))
        if not cohort:
            return None
        exam = int(m.group(2))
        r = _EXAM_RANGE_RE.search(description or "")
        exams = range(int(r.group(1)), int(r.group(2)) + 1) if r else [exam]
        return {f"FHS {cohort} EXAM {n}" for n in exams}
    m = _FHS_EXAM_LONG_RE.search(short_name)
    if not m:
        return None
    exam, code, shared = int(m.group(1)), m.group(2), m.group(3)
    if code == "1" and shared:
        return {f"FHS OFFSPRING EXAM {exam}", f"FHS OMNI 1 EXAM {exam - 5}"}
    if code == "3" and shared:
        return {f"FHS GENERATION 3 EXAM {exam}", f"FHS NEW OFFSPRING SPOUSE EXAM {exam}",
                f"FHS OMNI 2 EXAM {exam}"}
    cohort = FHS_COHORT_CODE.get(code)
    return {f"FHS {cohort} EXAM {exam}"} if cohort else None


def _extract_labels_from_expr(expr: str) -> set[str]:
    """The visit labels an ``associated_visit`` expression can emit, fallback arms excluded.

    Delegates to the shared enumerator, so 1.8 and Phase 5 read one parse of each expression.
    An expression the enumerator cannot model yields no labels.
    """
    try:
        return _visit_ids.labels(_visit_ids.enumerate_ids(str(expr)))
    except _visit_ids.Unparsed:
        return set()


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
    """One data block's visit labels for the PHT it reads."""
    pht: str
    labels: frozenset[str]
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
        files = [f for f in files if any(part.lower() == pattern for part in f.parts)]
    return files


def _extract_visit_refs(
    block: dict, block_idx: int, rel_path: str,
) -> list[PhtVisitRef]:
    """One ref per top-level data class that reads a PHT and names a visit.

    Visit blocks (visit.yaml) define visits rather than reference them and are skipped.
    """
    refs: list[PhtVisitRef] = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return refs
    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict) or cls_name == "Visit":
            continue
        pht = cls_def.get("populated_from")
        if not isinstance(pht, str) or not PHT_RE.fullmatch(pht):
            continue
        slot_derivs = cls_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            continue
        visit = slot_derivs.get("associated_visit")
        labels = frozenset(_visit_ids.labels(_visit_ids.slot_ids(visit)))
        if labels:
            refs.append(PhtVisitRef(pht, labels, rel_path, block_idx, cls_name))
    return refs


def _fmt(labels) -> str:
    return "{" + ", ".join(f"'{x}'" for x in sorted(labels)) + "}"


# A single-label block disagreeing with a strong majority of its table's single-label blocks is
# an ERROR. Warrant (all cohorts, 2026-10-08): of 5,573 single-label blocks on 566 tables, the
# largest share of "other" blocks agreeing on a different label that any block faces is 28%
# (ARIC pht012853, a wide multi-exam table), so 5 and 80% leave a wide margin, give 0 findings,
# and arm the rule on 163 tables (4,409 blocks; 10 and 90% arm 103). Lower them only with a new
# census of that maximum share.
MAJORITY_MIN_BLOCKS = 5
MAJORITY_MIN_SHARE = 0.8


def _majority_label(pht: str, candidates: list[PhtVisitRef],
                    refs: list[PhtVisitRef]) -> list[Finding]:
    """1.8 outside the FHS name rule: the #782 copy-paste label on a single-exam table."""
    singles = [r for r in refs if len(r.labels) == 1]
    counts = Counter(next(iter(r.labels)) for r in singles)
    out: list[Finding] = []
    for ref in candidates:
        if len(ref.labels) != 1:
            continue
        (label,) = ref.labels
        others = counts.copy()
        others[label] -= 1
        total = sum(others.values())
        if not total:
            continue
        top, n = max(others.items(), key=lambda kv: (kv[1], kv[0]))
        if top != label and n >= MAJORITY_MIN_BLOCKS and n / total >= MAJORITY_MIN_SHARE:
            out.append(Finding(
                ref.file, ref.block_index, "1.8", "ERROR",
                f"{pht}: this {ref.bdchm_class} block labels its rows '{label}', but {n} of the "
                f"{total} other single-label blocks of this table label theirs '{top}' -- likely "
                f"a copy-paste visit label",
            ))
    return out


def check_cross_file_pht_consistency(
    all_refs: list[PhtVisitRef],
    table_names: dict[str, dict[str, str]] | None = None,
) -> list[Finding]:
    """Check 1.8 over every data block of one run.

    ``table_names`` maps a PHT to its dbGaP short name (FHS's ``_tables`` index); without it the
    ERROR sub-check has nothing to compare against and only the overlap WARNING runs.
    """
    findings: list[Finding] = []
    table_names = table_names or {}

    by_pht: dict[str, list[PhtVisitRef]] = defaultdict(list)
    for ref in all_refs:
        by_pht[ref.pht].append(ref)

    for pht, refs in sorted(by_pht.items()):
        table = table_names.get(pht) or {}
        short = table.get("name", "")
        expected = expected_fhs_labels(short, table.get("description", "")) if short else None
        flagged: set[int] = set()
        if expected:
            for ref in refs:
                if len(ref.labels) == 1 and not ref.labels <= expected:
                    flagged.add(id(ref))
                    findings.append(Finding(
                        ref.file, ref.block_index, "1.8", "ERROR",
                        f"{pht} ({short}) is {_fmt(expected)} by its dbGaP table name, but this "
                        f"{ref.bdchm_class} block labels its rows {_fmt(ref.labels)} -- wrong visit "
                        f"label",
                    ))

        findings.extend(_majority_label(pht, [r for r in refs if id(r) not in flagged], refs))

        sets = sorted({ref.labels for ref in refs}, key=lambda x: (len(x), sorted(x)))
        first_block: dict[frozenset[str], PhtVisitRef] = {}
        for ref in refs:
            first_block.setdefault(ref.labels, ref)
        for i, a_set in enumerate(sets):
            for b_set in sets[i + 1:]:
                if a_set & b_set and not (a_set <= b_set or b_set <= a_set):
                    other = first_block[a_set]
                    for ref in refs:
                        if ref.labels == b_set:
                            findings.append(Finding(
                                ref.file, ref.block_index, "1.8", "WARNING",
                                f"{pht}: this block's visit labels {_fmt(b_set)} overlap "
                                f"{_fmt(a_set)} in {other.file.rsplit('/', 1)[-1]} block "
                                f"{other.block_index}, and neither contains the other -- check "
                                f"which visits the table holds",
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

    cache_dir = Path(__file__).resolve().parent.parent / "dbgap-cache"
    table_names: dict[str, dict[str, str]] = {}
    for _name, key in _cohorts.cohorts_to_load(args.cohort, cache_dir, base_dir):
        table_names.update(_cohorts.load_table_names(cache_dir, key))
    findings = check_cross_file_pht_consistency(all_refs, table_names)

    # -- Report --------------------------------------------------------
    # Known issues, stale entries and the WARNING ratchet (hv-lint/_known_issues.py).
    findings.extend(_known_issues.finalize(
        findings, checks={"1.8"}, scanned_files=yaml_files, make_finding=Finding))

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
