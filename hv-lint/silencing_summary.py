"""List what a PR adds to HV-Lint's three silencing files, for the CI job summary.

A finding stops failing CI when a PR adds a ``known_issues.yaml`` entry, a
``warning_baseline.json`` row, or (with an acknowledged prune) a ``removed.yaml`` line. Each is a
reviewed decision, but in a large diff it is easy to miss. This prints, as Markdown, every one the
PR adds relative to the merge base with the base branch -- what ``git diff origin/<base>...HEAD``
shows -- so the reviewer reads "this PR silences N findings" at a glance.

    python hv-lint/silencing_summary.py --base origin/main >> "$GITHUB_STEP_SUMMARY"
    python hv-lint/silencing_summary.py --base-dir <dir holding the base versions>

An entry whose issue, status or note changed counts as added: it is a new decision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

HVLINT_DIR = Path(__file__).resolve().parent
FILES = ("known_issues.yaml", "warning_baseline.json", "removed.yaml")
LIMIT = 200


def _yaml_items(text: str | None) -> list[str]:
    """Each list item of a known_issues.yaml / removed.yaml text, as a canonical JSON string."""
    data = yaml.safe_load(text or "") or []
    return [json.dumps(x, sort_keys=True, default=str) for x in data if isinstance(x, dict)]


def _rows(text: str | None) -> set[tuple[str, str, str]]:
    warnings = (json.loads(text).get("warnings", {}) if text and text.strip() else {})
    return {(r, c, t) for r, by_c in warnings.items() for c, ts in by_c.items() for t in ts}


def added(base: dict[str, str | None], head: dict[str, str | None]) -> dict[str, list]:
    """What ``head`` adds over ``base``, per file name (texts keyed by FILES; None = absent)."""
    out: dict[str, list] = {}
    for name in ("known_issues.yaml", "removed.yaml"):
        old = set(_yaml_items(base.get(name)))
        out[name] = [json.loads(x) for x in _yaml_items(head.get(name)) if x not in old]
    old_rows = _rows(base.get("warning_baseline.json"))
    out["warning_baseline.json"] = sorted(_rows(head.get("warning_baseline.json")) - old_rows)
    return out


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render(adds: dict[str, list]) -> str:
    ki, rows, rem = (adds["known_issues.yaml"], adds["warning_baseline.json"],
                     adds["removed.yaml"])
    n = len(ki) + len(rows) + len(rem)
    lines = [f"## HV-Lint silencing: this PR silences {n} finding(s)", ""]
    if not n:
        lines.append("No known-issue entry, baseline row or removed.yaml line added.")
        return "\n".join(lines) + "\n"
    lines.append(f"- {len(ki)} known-issue entr{'y' if len(ki) == 1 else 'ies'} added or changed "
                 f"(`hv-lint/known_issues.yaml`)")
    lines.append(f"- {len(rows)} WARNING/HIGH baseline row(s) added "
                 f"(`hv-lint/warning_baseline.json`)")
    lines.append(f"- {len(rem)} removal(s) acknowledged: file or block REMOVED, not fixed "
                 f"(`hv-lint/removed.yaml`)")
    if ki:
        lines += ["", "### known_issues.yaml", "", "| rule | file | block | message | issue | "
                  "status |", "|---|---|---|---|---|---|"]
        lines += [f"| {_cell(e.get('rule'))} | {_cell(e.get('file'))} | {_cell(e.get('block'))} "
                  f"| {_cell(e.get('message'))} | {_cell(e.get('issue'))} | "
                  f"{_cell(e.get('status'))} |" for e in ki[:LIMIT]]
    if rows:
        lines += ["", "### warning_baseline.json", "", "| rule | cohort | file \\| block \\| "
                  "message |", "|---|---|---|"]
        lines += [f"| {_cell(r)} | {_cell(c)} | {_cell(t)} |" for r, c, t in rows[:LIMIT]]
    if rem:
        lines += ["", "### removed.yaml", "", "| rule | file | block | issue | why |",
                  "|---|---|---|---|---|"]
        lines += [f"| {_cell(e.get('rule'))} | {_cell(e.get('file'))} | {_cell(e.get('block'))} "
                  f"| {_cell(e.get('issue'))} | {_cell(e.get('why'))} |" for e in rem[:LIMIT]]
    if max(len(ki), len(rows), len(rem)) > LIMIT:
        lines += ["", f"(each table shows the first {LIMIT}; see the PR diff for the rest)"]
    return "\n".join(lines) + "\n"


def _git_show(rev: str, path: str) -> str | None:
    res = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    return res.stdout.decode("utf-8") if res.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--base", help="base branch ref; compared at its merge base with HEAD")
    src.add_argument("--base-dir", type=Path, help="a directory holding the base versions")
    p.add_argument("--head-dir", type=Path, default=HVLINT_DIR,
                   help="the directory holding the head versions (default: hv-lint/)")
    args = p.parse_args(argv)

    head = {n: (args.head_dir / n).read_text(encoding="utf-8")
            if (args.head_dir / n).is_file() else None for n in FILES}
    if args.base_dir is not None:
        base = {n: (args.base_dir / n).read_text(encoding="utf-8")
                if (args.base_dir / n).is_file() else None for n in FILES}
    else:
        mb = subprocess.run(["git", "merge-base", args.base, "HEAD"], capture_output=True,
                            text=True)
        if mb.returncode != 0:
            print(f"silencing_summary: no merge base with {args.base}: {mb.stderr.strip()}",
                  file=sys.stderr)
            return 1
        base = {n: _git_show(mb.stdout.strip(), f"hv-lint/{n}") for n in FILES}
    sys.stdout.write(render(added(base, head)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
