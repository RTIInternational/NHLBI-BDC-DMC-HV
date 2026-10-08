"""One known-issue mechanism and one WARNING ratchet for every HV-Lint rule (#885 part 4).

Every phase fails CI on ERROR. What keeps main green is not a lower severity but a written
exception: an entry in ``hv-lint/known_issues.yaml`` naming the finding, the issue that tracks
it, and its status --

* ``defect``          real; the fix is tracked in the named issue;
* ``dbgap-error``     the mapping is right and the dbGaP label (or dictionary) is wrong;
* ``false-positive``  the rule is wrong here; ``note`` says why.

A matching finding is reported at INFO with the entry's issue and status appended. Three
things keep the list honest, each an ERROR:

* **stale entry** (check ``KI``): an entry for a rule this component ran, in a cohort it
  scanned, that matched nothing -- the defect was fixed, so the entry goes;
* **ambiguous entry** (``KI``): an entry that matched more than one finding -- each entry
  covers exactly one finding, so a new finding can never hide behind an old entry;
* **ratchet** (``RATCHET``): the number of WARNING findings per rule and cohort differs from
  ``hv-lint/warning_baseline.json``. A rise fails; so does a fall, until the baseline is
  lowered with ``HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort all``, so the
  floor only descends.

Entry fields: ``rule`` (the check id), ``file`` (cohort-relative, ``FHS-ingest/afib.yaml``),
``block`` (optional), ``match`` (optional substring of the message, used when one block has
several findings of one rule), ``issue`` (int), ``status``, ``note`` (optional).
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

HVLINT_DIR = Path(__file__).resolve().parent
KNOWN_ISSUES_FILE = HVLINT_DIR / "known_issues.yaml"
BASELINE_FILE = HVLINT_DIR / "warning_baseline.json"
STATUSES = ("defect", "dbgap-error", "false-positive")

_COHORT_PATH_RE = re.compile(r"(?:^|[/\\])([^/\\]+-ingest)[/\\](.+)$")


def cohort_relative(path) -> str | None:
    """``.../priority_variables_transform/FHS-ingest/afib.yaml`` -> ``FHS-ingest/afib.yaml``."""
    m = _COHORT_PATH_RE.search(str(path).replace("\\", "/"))
    return f"{m.group(1)}/{m.group(2)}" if m else None


def cohort_of(rel: str | None) -> str | None:
    if not rel:
        return None
    return rel.split("/", 1)[0][: -len("-ingest")]


@dataclass(frozen=True)
class Entry:
    rule: str
    file: str
    issue: int
    status: str
    block: int | None = None
    match: str | None = None
    note: str = ""

    def matches(self, rule: str, file: str | None, block: int, message: str) -> bool:
        return (rule == self.rule and file == self.file
                and (self.block is None or block == self.block)
                and (self.match is None or self.match in message))

    def describe(self) -> str:
        where = f"{self.file}" + (f" block {self.block}" if self.block is not None else "")
        return f"[{self.rule}] {where}" + (f" '{self.match}'" if self.match else "")


def load_entries(path: Path | str | None = None) -> list[Entry]:
    """Read and validate ``known_issues.yaml``. A malformed entry raises ValueError."""
    p = Path(path) if path else KNOWN_ISSUES_FILE
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    entries: list[Entry] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{p.name} entry {i}: not a mapping")
        missing = [k for k in ("rule", "file", "issue", "status") if item.get(k) in (None, "")]
        if missing:
            raise ValueError(f"{p.name} entry {i}: missing {', '.join(missing)}")
        if item["status"] not in STATUSES:
            raise ValueError(f"{p.name} entry {i}: status '{item['status']}' not in {STATUSES}")
        if not isinstance(item["issue"], int) or item["issue"] <= 0:
            raise ValueError(f"{p.name} entry {i}: issue must be a GitHub issue number")
        entries.append(Entry(
            rule=str(item["rule"]), file=str(item["file"]), issue=item["issue"],
            status=item["status"], block=item.get("block"), match=item.get("match"),
            note=str(item.get("note") or ""),
        ))
    return entries


def load_baseline(path: Path | str | None = None) -> dict[str, dict[str, int]]:
    p = Path(path) if path else BASELINE_FILE
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("warnings", {})


def write_baseline(counts: dict[tuple[str, str], int], checks: set[str], cohorts: set[str],
                   path: Path | str | None = None) -> None:
    """Replace the baseline rows for ``checks`` x ``cohorts`` with ``counts``; keep the rest."""
    p = Path(path) if path else BASELINE_FILE
    data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    warnings = data.get("warnings", {})
    for check in list(warnings):
        if check in checks:
            for cohort in list(warnings[check]):
                if cohort in cohorts:
                    del warnings[check][cohort]
    for (check, cohort), n in counts.items():
        if n:
            warnings.setdefault(check, {})[cohort] = n
    warnings = {c: dict(sorted(v.items())) for c, v in sorted(warnings.items()) if v}
    out = {
        "about": "WARNING findings per HV-Lint rule and cohort. CI fails when a count differs. "
                 "Regenerate: HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort all",
        "warnings": warnings,
    }
    p.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


def finalize(
    findings: list,
    *,
    checks: Iterable[str],
    scanned_files: Iterable,
    make_finding: Callable[[str, int, str, str, str], object],
    entries: list[Entry] | None = None,
    baseline: dict[str, dict[str, int]] | None = None,
    update_baseline: bool | None = None,
) -> list:
    """Apply known issues to ``findings`` in place and return the KI / RATCHET findings to add.

    ``checks`` are the rule ids this component ran and ``scanned_files`` the YAML files it read:
    together they scope the stale-entry and ratchet checks, so a single-cohort run never
    reports another cohort's entries as stale. ``make_finding(file, block, check, severity,
    message)`` builds the caller's own Finding type.
    """
    checks = {str(c) for c in checks}
    entries = load_entries() if entries is None else entries
    if update_baseline is None:
        update_baseline = os.environ.get("HVLINT_UPDATE_BASELINE") == "1"
    scanned = {r for r in (cohort_relative(f) for f in scanned_files) if r}
    cohorts = {cohort_of(r) for r in scanned}
    extra: list = []

    hits: dict[Entry, list] = {e: [] for e in entries}
    by_key: dict[tuple[str, str], list[Entry]] = {}
    for e in entries:
        by_key.setdefault((e.rule, e.file), []).append(e)
    for f in findings:
        rel = cohort_relative(f.file)
        for e in by_key.get((str(f.check), rel or ""), ()):
            if e.matches(str(f.check), rel, f.block, f.message):
                hits[e].append(f)
    for e, matched in hits.items():
        for f in matched:
            f.severity = "INFO"
            f.message = (f"{f.message} [known issue #{e.issue}, {e.status}"
                         + (f": {e.note}" if e.note else "") + "]")
        in_scope = e.rule in checks and cohort_of(e.file) in cohorts
        if in_scope and not matched:
            extra.append(make_finding(
                "hv-lint/known_issues.yaml", -1, "KI", "ERROR",
                f"stale known-issue entry {e.describe()} (#{e.issue}): it matches no finding "
                f"any more -- the issue is fixed or the block moved; delete or update the entry"))
        elif len(matched) > 1:
            extra.append(make_finding(
                "hv-lint/known_issues.yaml", -1, "KI", "ERROR",
                f"known-issue entry {e.describe()} (#{e.issue}) matches {len(matched)} findings; "
                f"an entry must name exactly one (add block or match)"))

    counts: Counter = Counter()
    for f in findings:
        if f.severity != "WARNING" or str(f.check) not in checks:
            continue
        cohort = cohort_of(cohort_relative(f.file))
        if cohort in cohorts:
            counts[(str(f.check), cohort)] += 1

    if update_baseline:
        write_baseline(dict(counts), checks, cohorts)
    else:
        base = load_baseline() if baseline is None else baseline
        keys = set(counts) | {(c, h) for c, row in base.items() if c in checks
                              for h in row if h in cohorts}
        for check, cohort in sorted(keys):
            now, was = counts.get((check, cohort), 0), base.get(check, {}).get(cohort, 0)
            if now > was:
                extra.append(make_finding(
                    "hv-lint/warning_baseline.json", -1, "RATCHET", "ERROR",
                    f"rule {check} WARNING findings in {cohort} rose from {was} to {now}: fix the "
                    f"new ones, or raise the baseline in the same PR with the reason"))
            elif now < was:
                extra.append(make_finding(
                    "hv-lint/warning_baseline.json", -1, "RATCHET", "ERROR",
                    f"rule {check} WARNING findings in {cohort} fell from {was} to {now}: lower "
                    f"the baseline (HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort "
                    f"all) so it cannot rise back unnoticed"))

    dump = os.environ.get("HVLINT_DUMP_FINDINGS")
    if dump:
        with open(dump, "a", encoding="utf-8") as fh:
            for f in list(findings) + extra:
                fh.write(json.dumps({"file": cohort_relative(f.file) or str(f.file),
                                     "block": f.block, "check": str(f.check),
                                     "severity": f.severity, "message": f.message}) + "\n")
    return extra
