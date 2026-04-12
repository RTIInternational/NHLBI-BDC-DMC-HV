#!/usr/bin/env python3
"""Run yamllint against HV repo transformation YAML files.

Wrapper script that points yamllint at the correct config (hv-lint/.yamllint)
and targets the appropriate cohort directories in the HV repo.

Usage:
    python hv-lint/phase-1/run_yamllint.py                     # all cohorts
    python hv-lint/phase-1/run_yamllint.py --cohort FHS        # single cohort
    python hv-lint/phase-1/run_yamllint.py --cohort FHS --format parsable
    python hv-lint/phase-1/run_yamllint.py --summary           # counts only
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Path resolution -- works in both control center and HV repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir, YAMLLINT_CONFIG  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

COHORTS = [
    "ARIC", "CARDIA", "CHS", "COPDGene",
    "FHS", "HCHS", "JHS", "MESA", "SPIROMICS", "WHI",
]


def get_ingest_dir(cohort: str) -> Path:
    """Return the *-ingest directory for a cohort."""
    return TRANSFORM_DIR / f"{cohort}-ingest"


def run_yamllint(targets: list[Path], fmt: str = "standard") -> int:
    """Run yamllint and return the exit code.

    Runs one yamllint invocation per target directory to avoid
    exceeding the Windows command-line length limit with 600+ files.
    """
    base_cmd = [
        sys.executable, "-m", "yamllint",
        "-c", str(YAMLLINT_CONFIG),
        "-f", fmt,
    ]
    worst_exit = 0
    for t in targets:
        if t.is_dir():
            yaml_files = sorted(t.glob("*.yaml"))
        elif t.suffix in (".yaml", ".yml"):
            yaml_files = [t]
        else:
            continue

        if not yaml_files:
            continue

        cmd = base_cmd + [str(f) for f in yaml_files]
        result = subprocess.run(cmd, capture_output=False)
        worst_exit = max(worst_exit, result.returncode)

    return worst_exit


def run_yamllint_summary(targets: list[Path]) -> int:
    """Run yamllint in parsable mode and print a severity summary.

    Runs one invocation per target directory to stay within the
    Windows command-line length limit.
    """
    base_cmd = [
        sys.executable, "-m", "yamllint",
        "-c", str(YAMLLINT_CONFIG),
        "-f", "parsable",
    ]

    all_output = ""
    all_files_count = 0
    worst_exit = 0

    for t in targets:
        if t.is_dir():
            yaml_files = sorted(t.glob("*.yaml"))
        elif t.suffix in (".yaml", ".yml"):
            yaml_files = [t]
        else:
            continue

        if not yaml_files:
            continue

        all_files_count += len(yaml_files)
        cmd = base_cmd + [str(f) for f in yaml_files]
        result = subprocess.run(cmd, capture_output=True, text=True)
        all_output += result.stdout + result.stderr
        worst_exit = max(worst_exit, result.returncode)

    # Parse aggregated output
    counts = {"error": 0, "warning": 0}
    rule_counts: dict[str, int] = {}
    files_with_issues: set[str] = set()

    # Regex for parsable output: filepath:line:col: [level] message (rule)
    # Windows paths have drive letters (C:\...) so we can't split on ':'
    parsable_re = re.compile(
        r'^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): \[(?P<level>error|warning)\] .+\((?P<rule>[^)]+)\)$'
    )

    for line in all_output.splitlines():
        m = parsable_re.match(line)
        if not m:
            continue
        level = m.group("level")
        counts[level] = counts.get(level, 0) + 1
        files_with_issues.add(m.group("file"))
        rule = m.group("rule")
        rule_counts[rule] = rule_counts.get(rule, 0) + 1

    total_files = all_files_count
    clean_files = total_files - len(files_with_issues)

    print(f"\n{'='*60}")
    print(f"yamllint Summary")
    print(f"{'='*60}")
    print(f"Files scanned:    {total_files}")
    print(f"Files clean:      {clean_files}")
    print(f"Files with issues: {len(files_with_issues)}")
    print(f"Total errors:     {counts['error']}")
    print(f"Total warnings:   {counts['warning']}")

    if rule_counts:
        print(f"\nFindings by rule:")
        for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
            print(f"  {rule:30s} {count:>6d}")

    print(f"{'='*60}\n")
    return worst_exit


def main():
    parser = argparse.ArgumentParser(
        description="Run yamllint against HV repo transformation YAML files."
    )
    parser.add_argument(
        "--cohort",
        choices=COHORTS + ["all"],
        default="all",
        help="Cohort to lint (default: all)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["standard", "parsable", "colored", "github", "auto"],
        default="standard",
        help="Output format (default: standard)",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Print summary counts instead of individual findings",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Lint a specific file (overrides --cohort)",
    )
    args = parser.parse_args()

    # Validate paths
    if not TRANSFORM_DIR.is_dir():
        print(f"ERROR: HV repo transform directory not found: {TRANSFORM_DIR}", file=sys.stderr)
        sys.exit(2)

    if not YAMLLINT_CONFIG.is_file():
        print(f"ERROR: yamllint config not found at {YAMLLINT_CONFIG}", file=sys.stderr)
        sys.exit(2)

    # Determine targets
    if args.file:
        target_path = Path(args.file).resolve()
        if not target_path.exists():
            print(f"ERROR: File not found: {target_path}", file=sys.stderr)
            sys.exit(2)
        targets = [target_path]
    elif args.cohort == "all":
        targets = [get_ingest_dir(c) for c in COHORTS if get_ingest_dir(c).is_dir()]
    else:
        d = get_ingest_dir(args.cohort)
        if not d.is_dir():
            print(f"ERROR: Directory not found: {d}", file=sys.stderr)
            sys.exit(2)
        targets = [d]

    # Run
    if args.summary:
        exit_code = run_yamllint_summary(targets)
    else:
        exit_code = run_yamllint(targets, fmt=args.format)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
