#!/usr/bin/env python3
"""HV-Lint Phase 2 Manager: Run all BDC-HM model conformance checks.

Orchestrates the Phase 2 sub-components in sequence:
  1. Model conformance  (validate_model_conformance.py) -- checks 2.1-2.6
  2. PHV deduplication   (check_phv_dedup.py) -- check 2.8

Each sub-component runs independently and reports its own findings.
The manager collects exit codes and reports a consolidated summary.

Usage:
    python hv-lint/phase-2/run_phase2.py                            # all cohorts
    python hv-lint/phase-2/run_phase2.py --cohort FHS               # single cohort
    python hv-lint/phase-2/run_phase2.py --skip dedup               # skip PHV dedup
    python hv-lint/phase-2/run_phase2.py --bdchm-ref v1.2.0        # pin schema version
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMPONENTS = {
    "conformance": {
        "script": SCRIPT_DIR / "validate_model_conformance.py",
        "label": "Model Conformance (2.1-2.6)",
        "cohort_flag": "--cohort",
        "extra_args": [],
        "pass_bdchm": True,
    },
    "dedup": {
        "script": SCRIPT_DIR / "check_phv_dedup.py",
        "label": "PHV Deduplication (2.8)",
        "cohort_flag": "--cohort",
        "extra_args": [],
        "pass_bdchm": False,
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 2 Manager: run all BDC-HM model conformance checks"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC) or 'all' (default: all)"
    )
    p.add_argument(
        "--skip", nargs="*", default=[],
        choices=list(COMPONENTS.keys()),
        help="Skip one or more components (e.g., --skip dedup)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Passed to sub-components (default: error)"
    )
    p.add_argument(
        "--bdchm-ref", default="main",
        help="Git ref for BDCHM schema (default: main)"
    )
    p.add_argument(
        "--bdchm-schema", default=None,
        help="Local path to bdchm.yaml (overrides --bdchm-ref)"
    )
    p.add_argument(
        "--hv-root",
        help="Path to an HV repo clone (overrides auto-detection)"
    )
    return p.parse_args()


def run_component(name: str, cohort: str, fail_on: str,
                  bdchm_ref: str, bdchm_schema: str | None) -> int:
    """Run a single Phase 2 component and return its exit code."""
    comp = COMPONENTS[name]
    script = comp["script"]
    if not script.exists():
        print(f"  WARNING: {script.name} not found -- skipping")
        return 0

    cmd = [sys.executable, str(script)]

    if comp["cohort_flag"] and cohort.lower() != "all":
        cmd.extend([comp["cohort_flag"], cohort])

    cmd.extend(["--fail-on", fail_on])

    # Pass BDCHM schema args only to components that need them
    if comp.get("pass_bdchm"):
        if bdchm_schema:
            cmd.extend(["--bdchm-schema", bdchm_schema])
        else:
            cmd.extend(["--bdchm-ref", bdchm_ref])

    cmd.extend(comp["extra_args"])

    print(f"\n{'='*70}")
    print(f"Phase 2 -- {comp['label']}")
    print(f"{'='*70}\n")

    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    args = parse_args()

    # Propagate --hv-root to child processes via environment variable
    if args.hv_root:
        os.environ["HV_ROOT"] = str(Path(args.hv_root).resolve())

    results: dict[str, int] = {}

    for name in COMPONENTS:
        if name in args.skip:
            print(f"\nSkipping: {COMPONENTS[name]['label']}")
            continue
        rc = run_component(name, args.cohort, args.fail_on,
                           args.bdchm_ref, args.bdchm_schema)
        results[name] = rc

    # Summary
    print(f"\n{'='*70}")
    print("Phase 2 Manager: Summary")
    print(f"{'='*70}")
    for name, rc in results.items():
        status = "PASSED" if rc == 0 else "FAILED"
        print(f"  {COMPONENTS[name]['label']:.<50} {status}")

    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        print(f"\n{len(failed)} component(s) failed.")
        return 1
    else:
        print("\nAll Phase 2 components passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
