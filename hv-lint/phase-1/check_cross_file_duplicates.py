#!/usr/bin/env python3
"""HV-Lint Phase 1: identical blocks in different files of one cohort (Rule 1.12).

Rule 1.2 finds duplicate blocks inside one file. The same block can also
sit in two files -- a medication question mapped in both med_use.yaml and
tak_diuret.yaml, a heart-failure flag in both chf.yaml and hist_hrtfail.yaml
-- and then every participant gets the record twice. This check compares
blocks across all files of a cohort.

Two blocks are identical when they agree on all of:

    class, populated_from table, source (the status / value slot's
    populated_from or expr), concept (drug_concept / condition_concept /
    procedure_concept / observation_type), associated_visit, and the
    status / value slot's value_mappings.

Provenance, age and other context slots are not compared: two blocks that
differ only there still emit the same fact twice. Classes without a status
or value slot (Visit, Person, Demography, ...) are compared on their whole
body, so only true copies match.

Checks:
    1.12  Cross-file identical blocks

Usage:
    python hv-lint/phase-1/check_cross_file_duplicates.py
    python hv-lint/phase-1/check_cross_file_duplicates.py --cohort FHS
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
import _known_issues  # noqa: E402
from _derivations import iter_nested_class_derivs  # noqa: E402

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}
PHV_RE = re.compile(r"phv\d{8}")

# class -> (concept slot, status/value slot). The value of a measurement
# sits in a nested Quantity and is handled separately.
CLASS_SLOTS: dict[str, tuple[str, str]] = {
    "Condition": ("condition_concept", "condition_status"),
    "DrugExposure": ("drug_concept", "exposure_status"),
    "Procedure": ("procedure_concept", "procedure_status"),
}
OBSERVATION_CLASSES = {"MeasurementObservation", "Observation", "SdohObservation"}



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


@dataclass(frozen=True)
class BlockRef:
    file: str      # cohort-relative, e.g. "FHS-ingest/med_use.yaml"
    block: int


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _d(val) -> dict:
    return val if isinstance(val, dict) else {}


def _src(slot: dict) -> str:
    """The slot's source: populated_from, else expr, else value."""
    for key in ("populated_from", "expr", "value"):
        v = slot.get(key)
        if v is not None and v != "":
            return str(v)
    return ""


def _vm_sig(slot: dict) -> str:
    vm = slot.get("value_mappings")
    if not isinstance(vm, dict):
        return ""
    return json.dumps({str(k): v for k, v in vm.items()}, sort_keys=True, default=str)


def _observation_value(slots: dict) -> dict:
    for qty_name, qty in iter_nested_class_derivs(slots.get("value_quantity")):
        if qty_name != "Quantity":
            continue
        qslots = _d(_d(qty).get("slot_derivations"))
        for name in ("value_decimal", "value_integer", "value_concept", "value_string"):
            if name in qslots:
                return _d(qslots[name])
    return _d(slots.get("value_enum"))


def block_identities(block: dict) -> list[tuple[str, tuple]]:
    """Return ``[(class_name, identity)]`` for each class in a block.

    The identity for a class with a status / value slot is
    ``(class, table, source, concept, visit, value_mappings)``. A class
    without one is identified by its whole body. A block whose source is
    empty is skipped: there is nothing to say it reads the same data.
    """
    out: list[tuple[str, tuple]] = []
    class_derivs = block.get("class_derivations") if isinstance(block, dict) else None
    if not isinstance(class_derivs, dict):
        return out
    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        slots = _d(cls_def.get("slot_derivations"))
        table = str(cls_def.get("populated_from") or "")
        visit = _src(_d(slots.get("associated_visit")))
        if cls_name in CLASS_SLOTS:
            concept_slot, status_slot = CLASS_SLOTS[cls_name]
            status = _d(slots.get(status_slot))
            source = _src(status)
            concept = _src(_d(slots.get(concept_slot)))
            vm = _vm_sig(status)
        elif cls_name in OBSERVATION_CLASSES:
            value = _observation_value(slots)
            source = _src(value)
            concept = _src(_d(slots.get("observation_type")))
            vm = _vm_sig(value)
        else:
            body = json.dumps(cls_def, sort_keys=True, default=str)
            out.append((cls_name, (cls_name, "body", body)))
            continue
        if not source:
            continue
        out.append((cls_name, (cls_name, table, source, concept, visit, vm)))
    return out


def _context_diff(a: dict, b: dict) -> list[str]:
    """Slot names whose derivation differs between two blocks (same class)."""
    def slots(block):
        cds = _d(_d(block).get("class_derivations"))
        return {name: _d(cd.get("slot_derivations")) if isinstance(cd, dict) else {}
                for name, cd in cds.items()}
    sa, sb = slots(a), slots(b)
    diff: set[str] = set()
    for cls in set(sa) | set(sb):
        x, y = sa.get(cls, {}), sb.get(cls, {})
        for slot in set(x) | set(y):
            # `range: string` is a no-op annotation, not a difference.
            xs = {k: v for k, v in _d(x.get(slot)).items() if k != "range"}
            ys = {k: v for k, v in _d(y.get(slot)).items() if k != "range"}
            if xs != ys:
                diff.add(slot)
    return sorted(diff)


def find_cross_file_duplicates(
    cohort_blocks: dict[str, list[tuple[BlockRef, dict]]],
) -> list[Finding]:
    """Group identical blocks per cohort; flag groups that span two or more files.

    ``cohort_blocks`` maps cohort -> [(ref, block)], where ref.file is the
    cohort-relative path. One finding is emitted per extra file in a group,
    on that file, naming the first file as the other copy.
    """
    findings: list[Finding] = []
    for cohort in sorted(cohort_blocks):
        groups: dict[tuple, list[BlockRef]] = defaultdict(list)
        by_ref: dict[BlockRef, dict] = {}
        for ref, block in cohort_blocks[cohort]:
            by_ref[ref] = block
            for _cls, ident in block_identities(block):
                groups[ident].append(ref)
        for ident, refs in groups.items():
            files = sorted({r.file for r in refs})
            if len(files) < 2:
                continue
            first = min(refs, key=lambda r: (r.file, r.block))
            cls_name = ident[0]
            if ident[1] == "body":
                desc = f"{cls_name} (whole block identical)"
                source = ""
            else:
                _, table, source, concept, _visit, _vm = ident
                desc = f"{cls_name} table={table} source={source[:60]} concept={concept[:60]}"
            for other in files:
                if other == first.file:
                    continue
                ref = min((r for r in refs if r.file == other), key=lambda r: r.block)
                differs = _context_diff(by_ref[first], by_ref[ref])
                how = (f"differs only in {', '.join(differs)}" if differs
                       else "identical apart from `range:` annotations")
                findings.append(Finding(
                    file=f"priority_variables_transform/{other}",
                    block=ref.block,
                    check="1.12",
                    severity="ERROR",
                    message=(
                        f"Identical to {first.file} block {first.block}: {desc} -- "
                        f"same table, source, concept, visit and status mapping "
                        f"({how}), so each record is emitted twice"
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# File discovery / main
# ---------------------------------------------------------------------------


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Check 1.12: identical blocks across files of one cohort"
    )
    p.add_argument("--cohort", default="all",
                   help="Cohort to validate or 'all' (default: all)")
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    base_dir = find_transform_dir()
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 0

    cohort_blocks: dict[str, list[tuple[BlockRef, dict]]] = defaultdict(list)
    files_checked = 0
    blocks_checked = 0
    for file_path in yaml_files:
        rel = file_path.relative_to(base_dir).as_posix()
        cohort = rel.split("/", 1)[0]
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if data is None:
            continue
        blocks = data if isinstance(data, list) else [data]
        files_checked += 1
        for idx, block in enumerate(blocks):
            if isinstance(block, dict):
                blocks_checked += 1
                cohort_blocks[cohort].append((BlockRef(rel, idx), block))

    findings = find_cross_file_duplicates(cohort_blocks)

    # Known issues, stale entries and the WARNING ratchet (hv-lint/_known_issues.py).
    findings.extend(_known_issues.finalize(
        findings, checks={"1.12"}, scanned_files=yaml_files, make_finding=Finding))

    fail_rank = SEVERITY_RANK[args.fail_on.upper()]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    print(f"{'='*70}")
    print("HV-Lint Check 1.12: Cross-File Identical Blocks")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")
    parts = [f"{counts[s]} {s}" for s in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO")
             if counts.get(s, 0) > 0]
    print(f"Findings:       {', '.join(parts)}" if parts
          else "Findings:       None -- no block is repeated in another file")

    if by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(by_file):
            print(f"\n{fpath.replace('priority_variables_transform/', '')}:")
            for f in sorted(by_file[fpath], key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    blocking = [f for f in findings if SEVERITY_RANK.get(f.severity, 0) >= fail_rank]
    if blocking:
        print(f"\nFAILED: {len(blocking)} findings at or above '{args.fail_on}'")
        return 1
    if findings:
        print(f"\nPASSED (with {len(findings)} advisory findings below fail threshold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
