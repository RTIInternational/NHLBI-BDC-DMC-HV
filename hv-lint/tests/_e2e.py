"""Drive a real HV-Lint component's main() on a temporary spec tree.

Each tree has its own ``known_issues.yaml`` and ``warning_baseline.json`` (through
``HVLINT_KNOWN_ISSUES`` / ``HVLINT_WARNING_BASELINE``) and reads the committed dbGaP cache, so a
test exercises the component's own ``checks=`` set and its call into ``_known_issues.finalize`` --
the path a unit test of the rule function never reaches.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

HVLINT = Path(__file__).resolve().parent.parent
CACHE = HVLINT / "dbgap-cache"
FIX = HVLINT / "tests" / "fixtures" / "known_cases"

ENTRY_LINE_RE = re.compile(r"^\s+(- \{rule: .*\})\s*$", re.M)


def fixture_block(name: str) -> dict:
    return yaml.safe_load((FIX / name).read_text(encoding="utf-8"))


def visit_block(pht: str, seed: str, label: str, cohort: str = "FHS") -> dict:
    return {"class_derivations": {"Visit": {"populated_from": pht, "slot_derivations": {
        "id": {"expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":{label}")'},
        "associated_participant": {
            "expr": f'uuid5("https://w3id.org/bdchm/Participant", str({{{seed}}}) + ":{cohort}")'},
        "visit_category": {"value": "Study visit", "range": "string"},
    }}}}


class Tree:
    def __init__(self, tmp_path: Path, cohort: str):
        self.tmp = tmp_path
        self.root = tmp_path / "hv"
        self.cohort = cohort
        self.dir = self.root / "priority_variables_transform" / f"{cohort}-ingest"
        self.dir.mkdir(parents=True)
        self.ki = tmp_path / "known_issues.yaml"
        self.baseline = tmp_path / "warning_baseline.json"
        self.ki.write_text("", encoding="utf-8")

    def write(self, name: str, blocks: list) -> Path:
        p = self.dir / name
        p.write_text(yaml.safe_dump(blocks, sort_keys=False), encoding="utf-8")
        return p

    def run(self, script: str, *args: str, mode: str | None = None,
            run_all: bool | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("HVLINT_")}
        env.update(HV_ROOT=str(self.root), HVLINT_KNOWN_ISSUES=str(self.ki),
                   HVLINT_WARNING_BASELINE=str(self.baseline), PYTHONIOENCODING="utf-8")
        if mode == "prune":
            env["HVLINT_PRUNE"] = "1"
        elif mode == "update":
            env["HVLINT_UPDATE_BASELINE"] = "1"
        if run_all if run_all is not None else mode is not None:
            env["HVLINT_RUN_ALL"] = "1"
        cmd = [sys.executable, str(HVLINT / script), *args]
        return subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True,
                              encoding="utf-8")

    def suggested(self, res: subprocess.CompletedProcess) -> list[str]:
        """The entry lines a run printed for its unlisted ERRORs."""
        return ENTRY_LINE_RE.findall(res.stdout)

    def list_as_known(self, res, issue: int, status: str = "defect") -> list[str]:
        lines = [x.replace("issue: <issue>", f"issue: {issue}")
                  .replace("status: <status>", f"status: {status}") for x in self.suggested(res)]
        self.ki.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return lines


def phase5(tree: Tree, **kw) -> subprocess.CompletedProcess:
    return tree.run("phase-5/validate_visit_structure.py", "--cohort", tree.cohort,
                    "--cache-dir", str(CACHE), "--fail-on", "error", **kw)


def phase3(tree: Tree, script: str, **kw) -> subprocess.CompletedProcess:
    return tree.run(f"phase-3/{script}", "--cohort", tree.cohort, "--cache-dir", str(CACHE),
                    "--fail-on", "error", **kw)
