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
                "semantic_review": _stat(sem_review_md) if sem_review_md else None,
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
