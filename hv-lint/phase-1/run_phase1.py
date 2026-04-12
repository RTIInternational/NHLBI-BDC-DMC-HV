#!/usr/bin/env python3
"""HV-Lint Phase 1 Manager: Run all YAML structural & formatting checks.

Orchestrates the three Phase 1 sub-components in sequence:
  1. yamllint           (run_yamllint.py)
  2. Quoting rules      (check_quoting_rules.py)
  3. Structural checks  (validate_yaml_structure.py)

Each sub-component runs independently and reports its own findings.
The manager collects exit codes and reports a consolidated summary.

Usage:
    python hv-lint/phase-1/run_phase1.py                    # all cohorts
    python hv-lint/phase-1/run_phase1.py --cohort FHS       # single cohort
    python hv-lint/phase-1/run_phase1.py --skip yamllint    # skip a step
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMPONENTS = {
    "yamllint": {
        "script": SCRIPT_DIR / "run_yamllint.py",
        "label": "yamllint",
        "cohort_flag": "--cohort",
        "extra_args": ["--summary"],
    },
    "quoting": {
        "script": SCRIPT_DIR / "check_quoting_rules.py",
        "label": "Quoting Rules (Issue #387)",
        "cohort_flag": "--cohort",
        "extra_args": ["--summary"],
    },
    "structure": {
        "script": SCRIPT_DIR / "validate_yaml_structure.py",
        "label": "Structural Checks (1.1-1.5)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
    "cross-block": {
        "script": SCRIPT_DIR / "check_cross_block_consistency.py",
        "label": "Cross-Block Slot Consistency (1.6)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
    "cross-file-pht": {
        "script": SCRIPT_DIR / "check_cross_file_pht_consistency.py",
        "label": "Cross-File PHT Visit Label Consistency (1.8)",
        "cohort_flag": "--cohort",
        "extra_args": [],
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 1 Manager: run all YAML structural checks"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC) or 'all' (default: all)"
    )
    p.add_argument(
        "--skip", nargs="*", default=[],
        choices=list(COMPONENTS.keys()),
        help="Skip one or more components (e.g., --skip yamllint)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Passed to validate_yaml_structure.py (default: error)"
    )
    p.add_argument(
        "--hv-root",
        help="Path to an HV repo clone (overrides auto-detection)"
    )
    return p.parse_args()


def run_component(name: str, cohort: str, fail_on: str) -> int:
    """Run a single Phase 1 component and return its exit code."""
    comp = COMPONENTS[name]
    script = comp["script"]
    if not script.exists():
        print(f"  WARNING: {script.name} not found -- skipping")
        return 0

    cmd = [sys.executable, str(script)]

    if comp["cohort_flag"] and cohort.lower() != "all":
        cmd.extend([comp["cohort_flag"], cohort])

    cmd.extend(comp["extra_args"])

    if name == "structure":
        cmd.extend(["--fail-on", fail_on])

    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    args = parse_args()
    skip_set = set(args.skip)

    # Propagate --hv-root to child processes via environment variable
    if args.hv_root:
        os.environ["HV_ROOT"] = str(Path(args.hv_root).resolve())

    print("=" * 70)
    print("HV-Lint Phase 1: YAML Structural & Formatting")
    print(f"Cohort: {args.cohort}")
    if args.hv_root:
        print(f"HV root: {os.environ['HV_ROOT']}")
    print("=" * 70)

    results: dict[str, int] = {}

    for name, comp in COMPONENTS.items():
        if name in skip_set:
            print(f"\n--- {comp['label']} [SKIPPED] ---\n")
            continue
        print(f"\n--- {comp['label']} ---\n")
        rc = run_component(name, args.cohort, args.fail_on)
        results[name] = rc

    # Consolidated summary
    print(f"\n{'=' * 70}")
    print("Phase 1 Summary")
    print(f"{'=' * 70}")
    for name, rc in results.items():
        label = COMPONENTS[name]["label"]
        status = "PASSED" if rc == 0 else "FAILED"
        print(f"  {label:<40s} {status}")

    any_failed = any(rc != 0 for rc in results.values())
    if any_failed:
        print(f"\nPhase 1 FAILED -- one or more components reported errors")
        return 1
    else:
        print(f"\nPhase 1 PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
