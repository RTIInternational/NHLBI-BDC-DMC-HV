#!/usr/bin/env python3
"""Generate a release report aggregating all applied CURIE changes across studies.

Reads every change-log JSON file in valueset_mapping_review_output/change_log/
and produces a single markdown report suitable for attaching to a release.

Usage:
    python generate_release_report.py
    python generate_release_report.py --study COPDGene HCHS
    python generate_release_report.py --output my_report.md
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

_HERE      = Path(__file__).parent.parent   # scripts/ → data_element_map_validation/
_LOG_DIR   = _HERE / "valueset_mapping_review_output" / "change_log"
_PENDING_DIR = _HERE / "valueset_mapping_review_output" / "pending_change"
_OUT_DIR   = _HERE / "valueset_mapping_review_output"


# ---------------------------------------------------------------------------
# Parsing helpers — handle both old and new JSON formats
# ---------------------------------------------------------------------------

def _parse_new_format(data: dict, source_file: str) -> list[dict]:
    """Parse {submitted_date, study, curator, changes: {...}} format."""
    submitted = data.get("submitted_date", "")
    study     = data.get("study", "")
    curator   = data.get("curator", "")
    records   = []
    for change in data.get("changes", {}).values():
        if not change.get("applied"):
            continue
        records.append({
            "study":          change.get("study", study),
            "yaml_files":     change.get("yaml_files", []),
            "slot":           change.get("slot", ""),
            "original_curie": change.get("original_curie", ""),
            "new_curie":      change.get("change_request", ""),
            "applied_date":   change.get("applied_date", submitted),
            "applied_by":     change.get("applied_by", curator),
            "notes":          change.get("notes", ""),
            "apply_results":  change.get("apply_results", []),
            "source":         source_file,
        })
    return records


def _parse_legacy_format(data: dict, source_file: str) -> list[dict]:
    """Parse flat {key: {change_request, slot, yaml_files, applied}} format."""
    records = []
    for val in data.values():
        if not isinstance(val, dict) or not val.get("applied"):
            continue
        # Derive study from source filename prefix
        study = Path(source_file).name.split("_change_request")[0].split("_change_requests")[0]
        records.append({
            "study":          val.get("study", study),
            "yaml_files":     val.get("yaml_files", []),
            "slot":           val.get("slot", ""),
            "original_curie": val.get("original_curie", ""),
            "new_curie":      val.get("change_request", ""),
            "applied_date":   val.get("applied_date", ""),
            "applied_by":     val.get("applied_by", ""),
            "notes":          val.get("notes", ""),
            "apply_results":  val.get("apply_results", []),
            "source":         source_file,
        })
    return records


def _load_log_file(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  Warning: could not read {path.name}: {e}")
        return []

    if "changes" in data:
        return _parse_new_format(data, path.name)
    else:
        return _parse_legacy_format(data, path.name)


def _load_pending_file(path: Path) -> list[dict]:
    """Also include applied changes from pending files not yet in a change log."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _parse_legacy_format(data, path.name)


# ---------------------------------------------------------------------------
# Collect all applied changes
# ---------------------------------------------------------------------------

def collect_changes(study_filter: list[str] | None = None) -> dict[str, list[dict]]:
    """Return {study: [change_records]} sorted by applied_date."""
    all_records: list[dict] = []

    # From change log files
    if _LOG_DIR.exists():
        for log_file in sorted(_LOG_DIR.glob("*_change_request*.json")):
            records = _load_log_file(log_file)
            all_records.extend(records)

    # From pending files (catch any applied changes not yet submitted as a log)
    if _PENDING_DIR.exists():
        seen_keys = {(r["study"], tuple(r["yaml_files"]), r["slot"], r["new_curie"])
                     for r in all_records}
        for pf in sorted(_PENDING_DIR.glob("*_pending_changes.json")):
            for rec in _load_pending_file(pf):
                key = (rec["study"], tuple(rec["yaml_files"]), rec["slot"], rec["new_curie"])
                if key not in seen_keys:
                    all_records.append(rec)
                    seen_keys.add(key)

    # Filter by study if requested
    if study_filter:
        all_records = [r for r in all_records if r["study"] in study_filter]

    # Group by study
    by_study: dict[str, list[dict]] = {}
    for rec in all_records:
        by_study.setdefault(rec["study"], []).append(rec)

    # Sort each study's records by applied_date
    for study in by_study:
        by_study[study].sort(key=lambda r: r.get("applied_date", ""))

    return by_study


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _yaml_list(yaml_files: list[str]) -> str:
    return ", ".join(f"`{Path(f).name}`" for f in yaml_files) if yaml_files else "—"


def write_report(by_study: dict[str, list[dict]], output_path: Path) -> None:
    today       = date.today().strftime("%Y-%m-%d")
    total       = sum(len(v) for v in by_study.values())
    lines: list[str] = []

    lines += [
        f"# BDC Semantic Review — Release Report",
        f"",
        f"**Generated:** {today}  ",
        f"**Studies included:** {', '.join(sorted(by_study))}  ",
        f"**Total applied changes:** {total}",
        f"",
        "---",
        "",
    ]

    if not by_study:
        lines.append("_No applied changes found._")
    else:
        # Summary table across all studies
        lines += [
            "## Summary of All Applied Changes",
            "",
            "| Study | YAML File | Slot | Original CURIE | New CURIE | Date Applied | Curator |",
            "| :---- | :---- | :---- | :---- | :---- | :---- | :---- |",
        ]
        for study in sorted(by_study):
            for rec in by_study[study]:
                orig = f"`{rec['original_curie']}`" if rec["original_curie"] else "—"
                new  = f"`{rec['new_curie']}`"      if rec["new_curie"]      else "—"
                lines.append(
                    f"| {study} | {_yaml_list(rec['yaml_files'])} | `{rec['slot']}` "
                    f"| {orig} | {new} | {rec['applied_date'] or '—'} | {rec['applied_by'] or '—'} |"
                )

        lines += ["", "---", ""]

        # Per-study detail sections
        lines.append("## Detail by Study")
        lines.append("")
        for study in sorted(by_study):
            records = by_study[study]
            lines += [
                f"### {study} ({len(records)} change{'s' if len(records) != 1 else ''})",
                "",
            ]
            for rec in records:
                orig = rec["original_curie"] or "—"
                new  = rec["new_curie"]      or "—"
                lines += [
                    f"**{_yaml_list(rec['yaml_files'])}** — `{rec['slot']}`  ",
                    f"- Old CURIE: `{orig}`",
                    f"- New CURIE: `{new}`",
                    f"- Applied: {rec['applied_date'] or '—'} by {rec['applied_by'] or '—'}",
                ]
                if rec["notes"]:
                    notes_single = rec["notes"].replace("\n", " ").strip()
                    lines.append(f"- Notes: {notes_single}")
                if rec["apply_results"]:
                    for result in rec["apply_results"]:
                        lines.append(f"  - {result}")
                lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Release report written to:\n  {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a release report of applied CURIE changes.")
    parser.add_argument(
        "--study", nargs="+", metavar="STUDY",
        help="Filter to specific study short names (e.g. COPDGene HCHS). Default: all studies."
    )
    parser.add_argument(
        "--output", metavar="PATH",
        help="Output file path. Default: valueset_mapping_review_output/release_report_v{YYYYMMDD}.md"
    )
    args = parser.parse_args()

    date_tag    = date.today().strftime("%Y%m%d")
    output_path = Path(args.output) if args.output else (_OUT_DIR / f"release_report_v{date_tag}.md")

    print("Collecting applied changes ...")
    by_study = collect_changes(study_filter=args.study)
    total = sum(len(v) for v in by_study.values())
    print(f"  Found {total} applied change(s) across {len(by_study)} study/studies.")

    write_report(by_study, output_path)


if __name__ == "__main__":
    main()
