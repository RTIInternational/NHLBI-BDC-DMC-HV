#!/usr/bin/env python3
"""HV-Lint Phase 5 Manager: Run visit structure validation.

Orchestrates the Phase 5 sub-components:
  1. Visit structure validation (validate_visit_structure.py) -- checks 5.1-5.10

Usage:
    python hv-lint/phase-5/run_phase5.py
    python hv-lint/phase-5/run_phase5.py --cohort FHS
    python hv-lint/phase-5/run_phase5.py --cohort WHI --visit-cache data/visit-cache
    python hv-lint/phase-5/run_phase5.py --visit-cache data/visit-cache --cache-dir hv-lint/dbgap-cache
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMPONENTS = {
    "visit-structure": {
        "script": SCRIPT_DIR / "validate_visit_structure.py",
        "label": "Visit Structure Validation (5.1-5.8)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 5 Manager: run visit structure validation"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC) or 'all' (default: all)",
    )
    p.add_argument(
        "--skip", nargs="*", default=[],
        choices=list(COMPONENTS.keys()),
        help="Skip one or more components",
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)",
    )
    p.add_argument(
        "--visit-cache", default=None,
        help="Directory with per-cohort visit cache JSON files (checks 5.3, 5.5)",
    )
    p.add_argument(
        "--cache-dir", default=None,
        help="Directory with per-cohort .json.gz PHV indexes (check 5.4)",
    )
    p.add_argument(
        "--hv-root",
        help="Path to an HV repo clone (overrides auto-detection)",
    )
    return p.parse_args()


def run_component(
    name: str,
    cohort: str,
    fail_on: str,
    visit_cache: str | None,
    cache_dir: str | None,
) -> int:
    """Run a single Phase 5 component and return its exit code."""
    comp = COMPONENTS[name]
    script = comp["script"]
    if not script.exists():
        print(f"  WARNING: {script.name} not found -- skipping")
        return 0

    cmd = [sys.executable, str(script)]

    if comp["cohort_flag"] and cohort.lower() != "all":
        cmd.extend([comp["cohort_flag"], cohort])

    cmd.extend(["--fail-on", fail_on])

    if visit_cache:
        cmd.extend(["--visit-cache", visit_cache])
    if cache_dir:
        cmd.extend(["--cache-dir", cache_dir])

    cmd.extend(comp["extra_args"])

    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    args = parse_args()
    skip_set = set(args.skip)

    # Propagate --hv-root to child processes via environment variable
    if args.hv_root:
        os.environ["HV_ROOT"] = str(Path(args.hv_root).resolve())

    # Default cache-dir: hv-lint/dbgap-cache relative to this script
    if args.cache_dir is None:
        args.cache_dir = str(SCRIPT_DIR.parent / "dbgap-cache")

    print("=" * 70)
    print("HV-Lint Phase 5: Visit Structure Validation")
    print(f"Cohort: {args.cohort}")
    if args.hv_root:
        print(f"HV root: {os.environ['HV_ROOT']}")
    if args.visit_cache:
        print(f"Visit cache: {args.visit_cache}")
    if args.cache_dir:
        print(f"Cache dir: {args.cache_dir}")
    print("=" * 70)

    results: dict[str, int] = {}

    for name, comp in COMPONENTS.items():
        if name in skip_set:
            print(f"\n--- {comp['label']} [SKIPPED] ---\n")
            continue
        print(f"\n--- {comp['label']} ---\n")
        rc = run_component(
            name, args.cohort, args.fail_on,
            args.visit_cache, args.cache_dir,
        )
        results[name] = rc

    # Consolidated summary
    print(f"\n{'=' * 70}")
    print("Phase 5 Summary")
    print(f"{'=' * 70}")
    for name, rc in results.items():
        label = COMPONENTS[name]["label"]
        status = "PASSED" if rc == 0 else "FAILED"
        print(f"  {label:<50s} {status}")

    any_failed = any(rc != 0 for rc in results.values())
    if any_failed:
        print("\nPhase 5 FAILED -- one or more components reported errors")
        return 1
    else:
        print("\nPhase 5 PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
