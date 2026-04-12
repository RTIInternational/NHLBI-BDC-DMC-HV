#!/usr/bin/env python3
"""HV-Lint Phase 3: value_mappings label ↔ OMOP concept semantic check (Rule 3.11).

Detects value_mappings entries where the dbGaP source label semantically
contradicts the target OMOP concept. Catches copy-paste swaps of target
concept IDs between value_mappings entries.

Requires:
  - Extended PHV detail index (build_phv_detail_index.py)
  - Optionally: OMOP CONCEPT.csv extract in data/terminology-cache/omop/
    (if absent, uses an embedded lookup of ~100 common HV concepts)

Check:
    3.11  value_mappings label ↔ OMOP concept semantic alignment

Usage:
    python hv-lint/phase-3/check_value_semantic.py --cache-dir hv-lint/dbgap-cache
    python hv-lint/phase-3/check_value_semantic.py --cache-dir hv-lint/dbgap-cache --cohort WHI
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COHORT_TO_CACHE_KEY: dict[str, str] = {
    "ARIC": "aric", "CARDIA": "cardia", "CHS": "chs",
    "COPDGene": "copdgene", "FHS": "fhs", "HCHS": "hchs_sol",
    "JHS": "jhs", "MESA": "mesa", "SPIROMICS": "spiromics", "WHI": "whi",
    "LTRC": "ltrc",
}

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}
PHV_RE = re.compile(r"phv\d{8}")
OMOP_RE = re.compile(r"OMOP:(\d+)")

# Contradictory keyword pairs: if source label contains A and target
# concept name contains B (or vice versa), flag as HIGH.
CONTRADICTORY_PAIRS: list[tuple[set[str], set[str]]] = [
    ({"current"}, {"past", "former", "never", "ex-"}),
    ({"past", "former", "ex-"}, {"current", "every day", "some days"}),
    ({"never"}, {"current", "former", "past", "ex-"}),
    ({"yes"}, {"no", "absent", "negative"}),
    ({"no"}, {"yes", "present", "positive"}),
    ({"male"}, {"female"}),
    ({"female"}, {"male"}),
    ({"positive"}, {"negative", "absent"}),
    ({"negative"}, {"positive", "present"}),
    ({"present"}, {"absent", "negative"}),
    ({"absent"}, {"present", "positive"}),
    ({"active"}, {"inactive", "resolved", "remission"}),
    ({"smoker"}, {"non-smoker", "nonsmoker"}),
    ({"non-smoker", "nonsmoker"}, {"smoker", "current"}),
]

# Embedded lookup for the most common OMOP concept IDs used in HV YAMLs.
# This allows Rule 3.11 to run even without the full Athena extract.
EMBEDDED_CONCEPT_NAMES: dict[int, str] = {
    # Smoking status (Athena-verified 2026-03-28)
    45883537: "Never smoked",
    45883458: "Former smoker",
    45884037: "Current some day smoker",
    40766945: "Current smoker",
    45885135: "Unknown if ever smoked",
    40766929: "How many cigarettes do you smoke per day now",
    # Condition status
    4181412: "Present",
    4132135: "Absent",
    45885051: "Unknown",
    45878245: "Self-reported",
    # Sex
    8507: "Male",
    8532: "Female",
    8551: "Unknown",
    # Race
    8527: "White",
    8516: "Black or African American",
    8515: "Asian",
    8557: "Native Hawaiian or Other Pacific Islander",
    8567: "American Indian or Alaska Native",
    8552: "Unknown",
    # Ethnicity (Athena-verified 2026-03-31: 38003563=Hispanic, 38003564=Not Hispanic)
    38003563: "Hispanic or Latino",
    38003564: "Not Hispanic or Latino",
    # Vital status (bdchm VitalStatusEnum)
    4230556: "Alive",
    434489: "Dead",
    # General yes/no (SNOMED qualifier values)
    4188539: "Yes",
    4188540: "No",
    # Drug exposure types
    38000177: "Prescription written",
    38000175: "Prescription dispensed in pharmacy",
    # Condition types
    32817: "EHR",
    32879: "Registry",
    32810: "Claim",
    # Common condition concepts
    201820: "Diabetes mellitus",
    316866: "Hypertensive disorder",
    4185932: "Current smoker",
    # Stroke types
    443454: "Cerebral infarction",
    439847: "Intracranial hemorrhage",
    381591: "Cerebrovascular disease",
    # Heart conditions
    317576: "Atrial fibrillation",
    4329847: "Myocardial infarction",
    321318: "Heart failure",
    # Other common
    4282779: "COPD",
    4195665: "Asthma",
    40481531: "Peripheral arterial disease",
    321052: "Peripheral vascular disease",
    320128: "Angina pectoris",
}


@dataclass
class PhvDetail:
    name: str
    pht: str
    type: str
    unit: str | None
    description: str
    codes: dict[str, str] | None


@dataclass
class DetailIndex:
    records: dict[str, PhvDetail] = field(default_factory=dict)


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


# ---------------------------------------------------------------------------
# OMOP Concept Name Lookup
# ---------------------------------------------------------------------------


def load_omop_concepts(cache_root: Path) -> dict[int, str]:
    """Load OMOP concept_id → concept_name from Athena extract or embedded.

    Tries ``data/terminology-cache/omop/CONCEPT.csv`` first; falls back
    to the embedded lookup table.
    """
    concept_csv = cache_root / "data" / "terminology-cache" / "omop" / "CONCEPT.csv"
    if concept_csv.exists():
        lookup: dict[int, str] = {}
        with concept_csv.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                cid = row.get("concept_id", "")
                cname = row.get("concept_name", "")
                if cid.isdigit():
                    lookup[int(cid)] = cname
        return lookup

    # Fallback: embedded table
    return dict(EMBEDDED_CONCEPT_NAMES)


# ---------------------------------------------------------------------------
# Index Loading
# ---------------------------------------------------------------------------


def load_detail_index(cache_dir: Path, cache_key: str) -> DetailIndex:
    gz_path = cache_dir / f"{cache_key}_detail.json.gz"
    json_path = cache_dir / f"{cache_key}_detail.json"

    if gz_path.exists():
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            raw = json.load(f)
    elif json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raise FileNotFoundError(f"No detail index for '{cache_key}'")

    idx = DetailIndex()
    for phv, rec in raw.items():
        idx.records[phv] = PhvDetail(
            name=rec.get("name", ""),
            pht=rec.get("pht", ""),
            type=rec.get("type", ""),
            unit=rec.get("unit"),
            description=rec.get("description", ""),
            codes=rec.get("codes"),
        )
    return idx


# ---------------------------------------------------------------------------
# File Discovery
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
# Check 3.11: value_mappings Label ↔ OMOP Concept Alignment
# ---------------------------------------------------------------------------


def _extract_keywords(text: str) -> set[str]:
    """Extract lowercase keywords from a label or concept name."""
    return set(re.findall(r"[a-z]+(?:-[a-z]+)*", text.lower()))


def _find_contradictions(
    source_label: str, target_name: str
) -> list[tuple[str, str]]:
    """Find contradictory keyword pairs between source and target.

    Returns list of (source_keyword, target_keyword) contradictions.
    """
    src_kw = _extract_keywords(source_label)
    tgt_kw = _extract_keywords(target_name)
    contradictions: list[tuple[str, str]] = []

    for pair_a, pair_b in CONTRADICTORY_PAIRS:
        src_hit = src_kw & pair_a
        tgt_hit = tgt_kw & pair_b
        if src_hit and tgt_hit:
            contradictions.append(
                (sorted(src_hit)[0], sorted(tgt_hit)[0])
            )

    return contradictions


def check_value_semantic_alignment(
    block: dict, block_idx: int, rel_path: str,
    detail_idx: DetailIndex,
    omop_lookup: dict[int, str],
) -> list[Finding]:
    """Check 3.11: Flag value_mappings where source label contradicts target."""
    findings: list[Finding] = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return findings

    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        slot_derivs = cls_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            continue

        for slot_name, slot_def in slot_derivs.items():
            if not isinstance(slot_def, dict):
                continue

            vm = slot_def.get("value_mappings")
            if not isinstance(vm, dict) or not vm:
                continue

            # Get source PHV to look up code labels
            pf = slot_def.get("populated_from")
            if not isinstance(pf, str) or not PHV_RE.fullmatch(pf):
                continue

            detail = detail_idx.records.get(pf)
            if not detail or not detail.codes:
                continue

            for source_key, target_val in vm.items():
                source_key_str = str(source_key)
                source_label = detail.codes.get(source_key_str, "")
                if not source_label:
                    continue

                # Extract OMOP concept ID from target (e.g., "OMOP:45883458")
                if not isinstance(target_val, str):
                    continue
                omop_match = OMOP_RE.search(target_val)
                if not omop_match:
                    continue

                concept_id = int(omop_match.group(1))
                concept_name = omop_lookup.get(concept_id)
                if not concept_name:
                    continue

                contradictions = _find_contradictions(source_label, concept_name)
                if contradictions:
                    pairs_str = ", ".join(
                        f"'{s}' vs '{t}'" for s, t in contradictions
                    )
                    findings.append(Finding(
                        file=rel_path,
                        block=block_idx,
                        check="3.11",
                        severity="HIGH",
                        message=(
                            f"value_mappings on {cls_name}.{slot_name}: "
                            f"code '{source_key_str}' "
                            f"(\"{source_label}\") → "
                            f"{target_val} (\"{concept_name}\") — "
                            f"contradictory keywords: {pairs_str}"
                        ),
                    ))

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Check 3.11: value_mappings label ↔ OMOP alignment"
    )
    p.add_argument(
        "--cache-dir", required=True,
        help="Directory containing *_detail.json.gz indexes"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort or 'all' (default: all)"
    )
    p.add_argument(
        "--fail-on", default="high",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity for non-zero exit (default: high)"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    cache_dir = Path(args.cache_dir)

    if not cache_dir.is_dir():
        print(f"ERROR: Cache directory not found: {cache_dir}", file=sys.stderr)
        return 1

    # Auto-detect repo root for OMOP cache
    hvlint_dir = Path(__file__).resolve().parent.parent
    for candidate in [hvlint_dir.parent.parent, hvlint_dir.parent]:
        if (candidate / "data" / "terminology-cache").is_dir():
            repo_root = candidate
            break
    else:
        repo_root = hvlint_dir.parent

    omop_lookup = load_omop_concepts(repo_root)
    omop_src = "Athena extract" if len(omop_lookup) > len(EMBEDDED_CONCEPT_NAMES) else "embedded table"
    print(f"  OMOP concept lookup: {len(omop_lookup):,} concepts ({omop_src})")

    # Load detail indexes
    indexes: dict[str, DetailIndex] = {}
    cohort_upper = args.cohort.upper()
    needed = (
        {k: v for k, v in COHORT_TO_CACHE_KEY.items() if k.upper() == cohort_upper}
        if cohort_upper != "ALL"
        else COHORT_TO_CACHE_KEY
    )
    for cohort_name, cache_key in needed.items():
        try:
            indexes[cohort_name] = load_detail_index(cache_dir, cache_key)
            print(f"  Loaded {cohort_name}: {len(indexes[cohort_name].records):,} PHVs")
        except FileNotFoundError:
            pass

    if not indexes:
        print("ERROR: No detail indexes found.", file=sys.stderr)
        return 1

    base_dir = find_transform_dir()
    hv_root = base_dir.parent
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 0

    print(f"Found {len(yaml_files)} YAML files to validate")

    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0

    for file_path in yaml_files:
        rel_path = file_path.relative_to(hv_root).as_posix()
        cohort = detect_cohort(file_path)
        if cohort not in indexes:
            continue

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
            blocks_checked += 1
            if not isinstance(block, dict):
                continue
            all_findings.extend(
                check_value_semantic_alignment(
                    block, idx, rel_path,
                    indexes[cohort], omop_lookup
                )
            )

    # Report
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"\n{'='*70}")
    print("HV-Lint Check 3.11: value_mappings Label <-> OMOP Alignment")
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
        print("Findings:       None — all value_mappings semantically consistent")

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
        print(f"\nPASSED (with {len(all_findings)} advisory findings below fail threshold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
