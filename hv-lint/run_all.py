#!/usr/bin/env python3
"""Run all HV-Lint phases against a cohort (or all cohorts).

Output is written to both the terminal and a timestamped Markdown report
in ``hv-lint/reports/`` (git-ignored).

Usage:
    python hv-lint/run_all.py --cohort WHI
    python hv-lint/run_all.py --cohort all
    python hv-lint/run_all.py --cohort ARIC --skip phase2
    python hv-lint/run_all.py --cohort FHS --fail-on warning
    python hv-lint/run_all.py --cohort WHI --no-report
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"

sys.path.insert(0, str(SCRIPT_DIR))
import _cohorts  # noqa: E402

PHASES = {
    "phase1": {
        "script": SCRIPT_DIR / "phase-1" / "run_phase1.py",
        "label": "Phase 1 -- YAML Structure & Formatting",
        "needs_cache": False,
    },
    "phase2": {
        "script": SCRIPT_DIR / "phase-2" / "run_phase2.py",
        "label": "Phase 2 -- BDC-HM Model Conformance",
        "needs_cache": False,
    },
    "phase3": {
        "script": SCRIPT_DIR / "phase-3" / "run_phase3.py",
        "label": "Phase 3 -- dbGaP Cross-Reference",
        "needs_cache": True,
    },
    "phase5": {
        "script": SCRIPT_DIR / "phase-5" / "run_phase5.py",
        "label": "Phase 5 -- Visit Structure Validation",
        "needs_cache": True,
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run all HV-Lint phases in sequence"
    )
    p.add_argument(
        "--expect-study", default=None,
        help="Fail unless the dbGaP cache was built from this study (phs000287 or "
             "phs000287.v7). Phase 3 only -- it is the phase that cross-references PHVs.",
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., WHI) or 'all' (default: all)"
    )
    p.add_argument(
        "--skip", nargs="*", default=[],
        choices=list(PHASES.keys()),
        help="Skip one or more phases (e.g., --skip phase2)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity for non-zero exit (default: error)"
    )
    p.add_argument(
        "--cache-dir", default=None,
        help="Index directory (default: hv-lint/dbgap-cache)"
    )
    p.add_argument(
        "--hv-root",
        help="Path to HV repo clone (overrides auto-detection)"
    )
    p.add_argument(
        "--bdchm-ref", default=None,
        help="Git ref for BDCHM schema in Phase 2 (default: main)"
    )
    p.add_argument(
        "--bdchm-schema", default=None,
        help="Local BDCHM schema file for Phase 2 (overrides --bdchm-ref)"
    )
    p.add_argument(
        "--no-report", action="store_true",
        help="Skip writing the Markdown report file"
    )
    p.add_argument(
        "--report-dir", default=None,
        help="Directory for report files (default: hv-lint/reports/)"
    )
    return p.parse_args()


def run_phase(phase_name: str, args: argparse.Namespace, cache_dir: str) -> tuple[int, str]:
    """Run a single phase and return (exit_code, captured_output)."""
    phase = PHASES[phase_name]
    script = phase["script"]
    if not script.exists():
        # See the managers: a phase whose script is absent did not run, and returning 0 made
        # that indistinguishable from a phase that passed.
        msg = f"  ERROR: {script} not found -- this phase DID NOT RUN\n"
        print(msg, end="", file=sys.stderr)
        return 1, msg

    cmd = [sys.executable, str(script)]
    cmd.extend(["--cohort", args.cohort])
    cmd.extend(["--fail-on", args.fail_on])

    if phase["needs_cache"]:
        cmd.extend(["--cache-dir", cache_dir])
        # Only Phase 3 accepts the study pin today; forwarding it blindly to a phase that does
        # not would turn a version check into an argparse failure -- which is exactly the class
        # of defect this branch removes.
        if args.expect_study and phase_name == "phase3":
            cmd.extend(["--expect-study", args.expect_study])

    if args.hv_root:
        cmd.extend(["--hv-root", args.hv_root])

    # Phase 2 extras
    if phase_name == "phase2":
        if args.bdchm_schema:
            cmd.extend(["--bdchm-schema", args.bdchm_schema])
        elif args.bdchm_ref:
            cmd.extend(["--bdchm-ref", args.bdchm_ref])

    header = f"\n{'#'*70}\n  {phase['label']}\n{'#'*70}\n\n"
    print(header, end="")

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr

    # Print buffered output after phase completes
    print(output, end="")

    return result.returncode, header + output


def main() -> int:
    args = parse_args()
    timestamp = datetime.now()

    # Default cache-dir
    cache_dir = args.cache_dir or str(SCRIPT_DIR / "dbgap-cache")

    # Propagate --hv-root
    if args.hv_root:
        os.environ["HV_ROOT"] = str(Path(args.hv_root).resolve())

    # Canonicalise the cohort to the casing its ingest directory actually uses, BEFORE any phase
    # runs. This replaced `args.cohort.upper()`, whose comment claimed "Phase 1 scripts use
    # uppercase choices" -- one of those choices was `COPDGene`, so upper-casing produced
    # `COPDGENE`, argparse rejected it, and COPDGene's yamllint / quoting-rules checks have never
    # run through this entry point. Upper-casing is independently wrong now that the choices are
    # gone: `get_ingest_dir` joins the token onto a path, and `COPDGENE-ingest` resolves on a
    # case-insensitive filesystem but not on the ubuntu-latest runner CI uses.
    if args.cohort.lower() != "all":
        args.cohort = _cohorts.canonical_cohort(args.cohort)

    # Report directory
    report_dir = Path(args.report_dir) if args.report_dir else REPORTS_DIR

    banner = (
        f"{'='*70}\n"
        f"HV-Lint: Running all phases for {args.cohort}\n"
        f"Cache: {cache_dir}\n"
    )
    if args.skip:
        banner += f"Skipping: {', '.join(args.skip)}\n"
    banner += f"{'='*70}\n"
    print(banner, end="")

    report_lines = [banner]
    results: dict[str, int] = {}

    for name in PHASES:
        if name in args.skip:
            skip_msg = f"\nSkipping: {PHASES[name]['label']}\n"
            print(skip_msg, end="")
            report_lines.append(skip_msg)
            continue
        rc, output = run_phase(name, args, cache_dir)
        results[name] = rc
        report_lines.append(output)

    # Summary
    summary = io.StringIO()
    summary.write(f"\n{'='*70}\n")
    summary.write("HV-Lint: Final Summary\n")
    summary.write(f"{'='*70}\n")
    for name, rc in results.items():
        status = "PASSED" if rc == 0 else "FAILED"
        summary.write(f"  {PHASES[name]['label']:.<55} {status}\n")

    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        summary.write(f"\n{len(failed)} phase(s) failed.\n")
    else:
        summary.write("\nAll phases passed.\n")

    summary_text = summary.getvalue()
    print(summary_text, end="")
    report_lines.append(summary_text)

    # Write report file
    if not args.no_report:
        report_dir.mkdir(parents=True, exist_ok=True)
        cohort_label = args.cohort.upper()
        ts = timestamp.strftime("%Y-%m-%dT%H%M")
        phases_run = "-".join(
            f"P{n[-1]}" for n in PHASES if n not in (args.skip or [])
        )
        report_name = f"hv-lint-{cohort_label}-{phases_run}-{ts}.md"
        report_path = report_dir / report_name

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# HV-Lint Report: {cohort_label}\n\n")
            f.write(f"**Date:** {timestamp.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"**Cohort:** {cohort_label}\n")
            f.write(f"**Phases:** {phases_run}\n")
            f.write(f"**Fail-on:** {args.fail_on}\n\n")
            f.write("```\n")
            f.write("".join(report_lines))
            f.write("```\n")

        print(f"\nReport written to: {report_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
