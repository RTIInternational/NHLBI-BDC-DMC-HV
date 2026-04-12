#!/usr/bin/env python3
"""Check Issue #387 quoting rules against HV repo transformation YAML files.

Scans raw file text (not YAML-parsed) for legacy triple-quote patterns
and reports violations by rule. Designed to complement yamllint which
cannot detect these semantic quoting conventions.

Rules (from Issue #387):
  Rule 1: value_mappings values -- strip '''...''' wrapper, leave bare
  Rule 2: value: static values -- strip '''...''' wrapper, leave bare
  Rule 3: expr: with '''VALUE''' (not properly outer-quoted) -- replace with "VALUE"
  Rule 4: expr: with ''X'' inside proper 'expr: ...' quoting -- LEAVE ALONE
  Rule 5: Commented-out lines -- LEAVE AS-IS

Key distinction between Rule 3 and Rule 4:
  Rule 3: expr: '''VALUE'''   -- starts with ''', the ''' IS the wrapper
  Rule 4: expr: '...''X''...' -- outer ' wraps the full expr, '' inside = YAML escapes

Usage:
    python hv-lint/phase-1/check_quoting_rules.py                   # all cohorts
    python hv-lint/phase-1/check_quoting_rules.py --cohort FHS      # single cohort
    python hv-lint/phase-1/check_quoting_rules.py --summary         # counts only
"""

import argparse
import re
import sys
from pathlib import Path

# Path resolution -- works in both control center and HV repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

COHORTS = [
    "ARIC", "CARDIA", "CHS", "COPDGene",
    "FHS", "HCHS", "JHS", "MESA", "SPIROMICS", "WHI",
]

# --- Pattern definitions ---

# Detect expr lines and how they're quoted
# Rule 3 pattern: expr: '''...  (opens with triple-quote -- no proper outer wrapping)
EXPR_TRIPLE_OPEN_RE = re.compile(r"""^\s+expr:\s+'''""")
# Rule 4 pattern: expr: '...   (proper outer single-quote wrapping)
EXPR_PROPER_OPEN_RE = re.compile(r"""^\s+expr:\s+'(?!'')""")
# Bare/double-quoted expr: expr: case(...) or expr: "..."
EXPR_BARE_RE = re.compile(r"""^\s+expr:\s+[^'"]""")
EXPR_DOUBLE_RE = re.compile(r"""^\s+expr:\s+\"""")

# value_mappings context:  'key': '''VALUE'''
VALUE_MAPPINGS_RE = re.compile(r"""^\s+'[^']*':\s+'''([^']*)'''""")
# static value context:  value: '''VALUE'''
STATIC_VALUE_RE = re.compile(r"""^\s+value:\s+'''([^']*)'''""")

# General triple-quote detection (for lines not matching specific contexts)
TRIPLE_QUOTE_RE = re.compile(r"'''")

# Any new YAML key (to detect end of multi-line exprs)
NEW_KEY_RE = re.compile(r"""^\s+\w[\w_]*:""")


class Finding:
    """A single quoting rule violation."""

    def __init__(self, file: str, line_num: int, rule: int, severity: str,
                 line_text: str, message: str):
        self.file = file
        self.line_num = line_num
        self.rule = rule
        self.severity = severity
        self.line_text = line_text
        self.message = message

    def __str__(self):
        return (f"  {self.severity:8s} Rule {self.rule}  "
                f"{self.file}:{self.line_num}: {self.message}")


def check_file(filepath: Path) -> list[Finding]:
    """Scan a single file for quoting rule violations.

    The critical logic is distinguishing Rule 3 (real violation) from
    Rule 4 (legitimate YAML escapes):
      - Rule 3: expr: '''VALUE'''  -- the ''' is the wrapper itself
      - Rule 4: expr: '...''X''...' -- outer ' wraps the expr, '' = YAML escapes
    """
    findings = []
    rel_path = str(filepath)

    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        findings.append(Finding(rel_path, 0, 0, "ERROR", "", f"Cannot read file: {e}"))
        return findings

    # Track multi-line expression context
    in_rule3_expr = False  # Inside a triple-quote-opened expr (violation)
    in_rule4_expr = False  # Inside a properly-quoted expr (legitimate)

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            continue

        # Skip comment lines (Rule 5)
        if stripped.startswith("#"):
            continue

        # --- Detect expr: line openings ---
        if EXPR_TRIPLE_OPEN_RE.match(line):
            # Rule 3: expr: '''...  (triple-quote opener -- violation)
            in_rule3_expr = True
            in_rule4_expr = False

            findings.append(Finding(
                rel_path, i, 3, "ERROR", stripped,
                "Rule 3: expr uses '''...''' quoting -- replace with \"...\" "
                "and wrap full expr in outer single quotes",
            ))
            continue

        if EXPR_PROPER_OPEN_RE.match(line) or EXPR_DOUBLE_RE.match(line):
            # Rule 4 or double-quoted: properly wrapped -- no violation
            in_rule4_expr = True
            in_rule3_expr = False
            continue

        if EXPR_BARE_RE.match(line):
            # Bare expr (no quotes): check for triple-quotes inside
            in_rule3_expr = False
            in_rule4_expr = False
            if TRIPLE_QUOTE_RE.search(line):
                findings.append(Finding(
                    rel_path, i, 3, "ERROR", stripped,
                    "Rule 3: bare expr contains '''...''' -- needs quoting fix",
                ))
            continue

        # --- Detect new key (ends multi-line expr context) ---
        if NEW_KEY_RE.match(line) and not line.strip().startswith("-"):
            # Check if this new key has triple-quote violations
            in_rule3_expr = False
            in_rule4_expr = False

            # Rule 1: value_mappings
            m = VALUE_MAPPINGS_RE.match(line)
            if m:
                findings.append(Finding(
                    rel_path, i, 1, "ERROR", stripped,
                    f"Rule 1: value_mapping has '''...''' -- should be bare: {m.group(1)}",
                ))
                continue

            # Rule 2: static value
            m = STATIC_VALUE_RE.match(line)
            if m:
                findings.append(Finding(
                    rel_path, i, 2, "ERROR", stripped,
                    f"Rule 2: value: has '''...''' -- should be bare: {m.group(1)}",
                ))
                continue

            # Other keys with triple-quotes
            if TRIPLE_QUOTE_RE.search(line):
                findings.append(Finding(
                    rel_path, i, 0, "WARNING", stripped,
                    "Triple-quote in unexpected context -- review manually",
                ))
            continue

        # --- Continuation lines ---
        if in_rule4_expr:
            # Inside a properly-quoted expr -- all '' patterns are Rule 4 (legitimate)
            # The ''' at end of line is just '' (escaped quote) + ' (closing string)
            continue

        if in_rule3_expr:
            # Inside a triple-quote-opened expr -- these are part of the violation
            # (already flagged on the opening line)
            continue

        # --- Catch-all for non-expr lines ---
        # Check for list items that start new blocks
        if stripped.startswith("- "):
            in_rule3_expr = False
            in_rule4_expr = False

        # Check value_mappings and static values
        m = VALUE_MAPPINGS_RE.match(line)
        if m:
            findings.append(Finding(
                rel_path, i, 1, "ERROR", stripped,
                f"Rule 1: value_mapping has '''...''' -- should be bare: {m.group(1)}",
            ))
            continue

        m = STATIC_VALUE_RE.match(line)
        if m:
            findings.append(Finding(
                rel_path, i, 2, "ERROR", stripped,
                f"Rule 2: value: has '''...''' -- should be bare: {m.group(1)}",
            ))
            continue

        if TRIPLE_QUOTE_RE.search(line):
            findings.append(Finding(
                rel_path, i, 0, "WARNING", stripped,
                "Triple-quote in unexpected context -- review manually",
            ))

    return findings


def get_ingest_dir(cohort: str) -> Path:
    return TRANSFORM_DIR / f"{cohort}-ingest"


def collect_yaml_files(targets: list[Path]) -> list[Path]:
    yaml_files = []
    for t in targets:
        if t.is_dir():
            yaml_files.extend(sorted(t.glob("*.yaml")))
        elif t.suffix in (".yaml", ".yml"):
            yaml_files.append(t)
    return yaml_files


def print_findings(findings: list[Finding]):
    """Print findings grouped by file."""
    if not findings:
        print("No quoting rule violations found.")
        return

    current_file = None
    for f in findings:
        if f.file != current_file:
            current_file = f.file
            print(f"\n{f.file}")
        print(f"  {f.line_num}:{f.severity:>8s}  [Rule {f.rule}] {f.message}")


def print_summary(findings: list[Finding], total_files: int):
    """Print aggregated summary."""
    files_with_issues = set(f.file for f in findings)
    rule_counts: dict[int, int] = {}
    severity_counts: dict[str, int] = {}

    for f in findings:
        rule_counts[f.rule] = rule_counts.get(f.rule, 0) + 1
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    print(f"\n{'='*60}")
    print(f"Issue #387 Quoting Rules Check")
    print(f"{'='*60}")
    print(f"Files scanned:     {total_files}")
    print(f"Files clean:       {total_files - len(files_with_issues)}")
    print(f"Files with issues: {len(files_with_issues)}")
    print(f"Total findings:    {len(findings)}")

    if severity_counts:
        print(f"\nBy severity:")
        for sev in ["ERROR", "WARNING"]:
            if sev in severity_counts:
                print(f"  {sev:10s} {severity_counts[sev]:>6d}")

    if rule_counts:
        rule_names = {
            0: "Unclassified (manual review)",
            1: "value_mappings: strip '''...''' wrapper",
            2: "value: strip '''...''' wrapper",
            3: "expr: replace '''...''' with \"...\"",
        }
        print(f"\nBy rule:")
        for rule in sorted(rule_counts):
            desc = rule_names.get(rule, f"Rule {rule}")
            print(f"  Rule {rule}: {rule_counts[rule]:>4d}  ({desc})")

    if files_with_issues:
        print(f"\nAffected files:")
        for fp in sorted(files_with_issues):
            count = sum(1 for f in findings if f.file == fp)
            print(f"  {count:>4d}  {fp}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Check Issue #387 quoting rules against HV repo YAML files."
    )
    parser.add_argument(
        "--cohort",
        choices=COHORTS + ["all"],
        default="all",
        help="Cohort to check (default: all)",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Print summary counts instead of individual findings",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Check a specific file (overrides --cohort)",
    )
    args = parser.parse_args()

    if not TRANSFORM_DIR.is_dir():
        print(f"ERROR: HV repo transform directory not found: {TRANSFORM_DIR}", file=sys.stderr)
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

    yaml_files = collect_yaml_files(targets)
    if not yaml_files:
        print("No YAML files found.")
        sys.exit(0)

    # Run checks
    all_findings = []
    for yf in yaml_files:
        all_findings.extend(check_file(yf))

    # Output
    if args.summary:
        print_summary(all_findings, len(yaml_files))
    else:
        print_findings(all_findings)
        print()
        print_summary(all_findings, len(yaml_files))

    # Exit code: non-zero if any errors found
    has_errors = any(f.severity == "ERROR" for f in all_findings)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
