#!/usr/bin/env python3
"""
Scan all registered studies and write pipeline_status.json.

Called automatically at the end of generate_curie_mapreview.py and
generate_semantic_review.py — run directly to refresh without running a pipeline step.

Version fields (preserved across rebuilds, never overwritten automatically):
  input_version  int   incremented manually each time a new curie CSV is received
  release        str|null  e.g. "001.000" when snapshot is handed off to production
"""

import csv
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
_REVIEW_OUT = BASE_DIR / "valueset_mapping_review_output"
_REGISTRY_CSV = BASE_DIR / "bdc_study_input" / "BDC_registered_study_for_semantic_review.csv"
STATUS_FILE = _REVIEW_OUT / "pipeline_status.json"


def _file_key(short_name: str) -> str:
    return short_name.replace("/", "_").replace(" ", "_")


def _stat(path: Path) -> dict | None:
    if path.exists():
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return {"file": path.name, "completed": mtime.strftime("%Y-%m-%dT%H:%M:%S")}
    return None


def _count_md_table_rows(lines: list[str]) -> int:
    """Count data rows in a markdown table (excluding header and separator lines)."""
    data_rows = 0
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        inner = stripped.strip("|")
        if all(c in "-: |" for c in inner):
            continue
        data_rows += 1
    return max(0, data_rows - 1)


def _semantic_review_stat(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime)

    findings_lines: list[str] = []
    questions_lines: list[str] = []
    current: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ") and "Confirmed Findings" in line:
            current = "findings"
        elif line.startswith("## ") and ("Questions" in line or "Anne Review" in line):
            current = "questions"
        elif line.startswith("## "):
            current = None
        elif current == "findings":
            findings_lines.append(line)
        elif current == "questions":
            questions_lines.append(line)

    return {
        "file":      path.name,
        "completed": mtime.strftime("%Y-%m-%dT%H:%M:%S"),
        "findings":  _count_md_table_rows(findings_lines),
        "questions": _count_md_table_rows(questions_lines),
    }


def _mapreview_stat(path: Path) -> dict | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    with open(path, newline="", encoding="utf-8") as f:
        rows = max(sum(1 for _ in f) - 1, 0)
    return {
        "file": path.name,
        "completed": mtime.strftime("%Y-%m-%dT%H:%M:%S"),
        "rows": rows,
    }


def _latest_match(pattern: str) -> Path | None:
    matches = sorted(_REVIEW_OUT.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _load_existing() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_status() -> dict:
    existing = _load_existing()
    existing_studies = existing.get("studies", {})
    studies: dict[str, dict] = {}

    if not _REGISTRY_CSV.exists():
        return {"studies": studies, "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}

    with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            short = row["cohort_study_short_name"].strip()
            fk = _file_key(short)

            mapreview_csv = BASE_DIR / "bdc_study_input" / f"{fk}_curie_mapreview.csv"
            sem_review_md = _latest_match(f"{fk}_semantic_review_v*.md")
            summary_md    = _latest_match(f"{fk}_semantic_validator_summary_v*.md")

            prev = existing_studies.get(short, {})

            studies[short] = {
                "input_version": prev.get("input_version", 1),
                "release":       prev.get("release", None),
                "mapreview":       _mapreview_stat(mapreview_csv),
                "semantic_review": _semantic_review_stat(sem_review_md),
                "summary":         _stat(summary_md) if summary_md else None,
            }

    return {
        "studies": studies,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def write_status() -> Path:
    status = build_status()
    STATUS_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"Pipeline status written: {STATUS_FILE}")
    return STATUS_FILE


if __name__ == "__main__":
    write_status()
