#!/usr/bin/env python3
"""HV-Lint Phase 3 Manager: Run all dbGaP cross-reference checks.

Orchestrates the Phase 3 sub-components in sequence:
  1. dbGaP cross-reference  (validate_dbgap_crossref.py) — checks 3.1–3.5

Each sub-component runs independently and reports its own findings.
The manager collects exit codes and reports a consolidated summary.

Usage:
    python hv-lint/phase-3/run_phase3.py --cohort ARIC
    python hv-lint/phase-3/run_phase3.py --cache-dir hv-lint/dbgap-cache --cohort ARIC
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMPONENTS = {
    "crossref": {
        "script": SCRIPT_DIR / "validate_dbgap_crossref.py",
        "label": "dbGaP Cross-Reference (3.1–3.5)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
    "semantic": {
        "script": SCRIPT_DIR / "validate_semantic.py",
        "label": "Semantic Validation (3.9, 3.10, 3.12–3.16)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
    "value-semantic": {
        "script": SCRIPT_DIR / "check_value_semantic.py",
        "label": "Value Semantic Alignment (3.11)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 3 Manager: run all dbGaP cross-reference checks"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC) or 'all' (default: all)"
    )
    p.add_argument(
        "--skip", nargs="*", default=[],
        choices=list(COMPONENTS.keys()),
        help="Skip one or more components"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Passed to sub-components (default: error)"
    )
    p.add_argument(
        "--cache-dir",
        default=None,
        help="Directory containing per-cohort .json.gz indexes (default: hv-lint/dbgap-cache relative to HV root)"
    )
    p.add_argument(
        "--hv-root",
        help="Path to an HV repo clone (overrides auto-detection)"
    )
    return p.parse_args()


def run_component(name: str, cohort: str, fail_on: str,
                  cache_dir: str) -> int:
    """Run a single Phase 3 component and return its exit code."""
    comp = COMPONENTS[name]
    script = comp["script"]
    if not script.exists():
        print(f"  WARNING: {script.name} not found — skipping")
        return 0

    cmd = [sys.executable, str(script)]

    cmd.extend(["--cache-dir", cache_dir])

    if comp["cohort_flag"] and cohort.lower() != "all":
        cmd.extend([comp["cohort_flag"], cohort])

    cmd.extend(["--fail-on", fail_on])
    cmd.extend(comp["extra_args"])

    print(f"\n{'='*70}")
    print(f"Phase 3 — {comp['label']}")
    print(f"{'='*70}\n")

    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    args = parse_args()

    # Propagate --hv-root to child processes via environment variable
    if args.hv_root:
        os.environ["HV_ROOT"] = str(Path(args.hv_root).resolve())

    # Default cache-dir: hv-lint/dbgap-cache relative to this script
    if args.cache_dir is None:
        args.cache_dir = str(SCRIPT_DIR.parent / "dbgap-cache")

    results: dict[str, int] = {}

    for name in COMPONENTS:
        if name in args.skip:
            print(f"\nSkipping: {COMPONENTS[name]['label']}")
            continue
        rc = run_component(name, args.cohort, args.fail_on, args.cache_dir)
        results[name] = rc

    # Summary
    print(f"\n{'='*70}")
    print("Phase 3 Manager: Summary")
    print(f"{'='*70}")
    for name, rc in results.items():
        status = "PASSED" if rc == 0 else "FAILED"
        print(f"  {COMPONENTS[name]['label']:.<50} {status}")

    failed = [n for n, rc in results.items() if rc != 0]
    if failed:
        print(f"\n{len(failed)} component(s) failed.")
        return 1
    else:
        print("\nAll Phase 3 components passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
