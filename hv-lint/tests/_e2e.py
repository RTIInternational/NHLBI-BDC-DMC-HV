"""Drive a real HV-Lint component's main() on a temporary spec tree.

Each tree has its own ``known_issues.yaml`` and ``warning_baseline.json`` (through
``HVLINT_KNOWN_ISSUES`` / ``HVLINT_WARNING_BASELINE``) and reads the committed dbGaP cache, so a
test exercises the component's own ``checks=`` set and its call into ``_known_issues.finalize`` --
the path a unit test of the rule function never reaches.
"""

from __future__ import annotations

import json
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
            run_all: bool | None = None,
            extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("HVLINT_")}
        env.update(HV_ROOT=str(self.root), HVLINT_KNOWN_ISSUES=str(self.ki),
                   HVLINT_WARNING_BASELINE=str(self.baseline), PYTHONIOENCODING="utf-8")
        env.update(extra_env or {})
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


def seed_baseline(tree: Tree, runner) -> subprocess.CompletedProcess:
    """Record every WARNING one run reports as the tree's baseline, written directly.

    The baseline update refuses new rows of a lost-or-unlinked rule (``NO_BASELINE_RULES``), so
    a test that needs such a WARNING already accepted -- the state main is in for its existing
    rows -- seeds it here. ``runner(extra_env=...)`` runs the component or run_all."""
    sys.path.insert(0, str(HVLINT))
    import _known_issues as K  # noqa: PLC0415

    dump = tree.tmp / "seed_dump.jsonl"
    dump.unlink(missing_ok=True)
    res = runner(extra_env={"HVLINT_DUMP_FINDINGS": str(dump)})
    rows: dict = {}
    if dump.is_file():
        for line in dump.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            if d["severity"] in K.RATCHETED and d["key"]:
                rows.setdefault(d["check"], {}).setdefault(
                    str(K.cohort_of(d["file"])), []).append(d["key"])
    K.write_baseline(rows, tree.baseline)
    return res


def phase5(tree: Tree, **kw) -> subprocess.CompletedProcess:
    return tree.run("phase-5/validate_visit_structure.py", "--cohort", tree.cohort,
                    "--cache-dir", str(CACHE), "--fail-on", "error", **kw)


def phase3(tree: Tree, script: str, **kw) -> subprocess.CompletedProcess:
    return tree.run(f"phase-3/{script}", "--cohort", tree.cohort, "--cache-dir", str(CACHE),
                    "--fail-on", "error", **kw)


_DRIVER = """import sys
from pathlib import Path
sys.path.insert(0, {hvlint!r})
import run_all
for name, rc in {stubs!r}.items():
    stub = Path({tmp!r}) / f"stub_{{name}}.py"
    stub.write_text(f"print('stub {{name}}: exit {{rc}}')\\nraise SystemExit({{rc}})\\n",
                    encoding="utf-8")
    run_all.PHASES[name]["script"] = stub
sys.exit(run_all.main())
"""


def run_all_stubbed(tree: Tree, stubs: dict[str, int], *args: str,
                    mode: str | None = None,
                    extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """``run_all.py --cohort <cohort>`` with every phase run, the ``stubs`` phases replaced by a
    script that exits with the given code.

    Phases 1 and 2 need yamllint and a network fetch of the BDC-HM schema, which the unit-test
    job does not have. A stub keeps run_all's own logic -- no phase skipped, the per-phase
    exit codes, the staged prune -- on the path under test; ``--skip`` would not (a prune
    refuses a run with a skipped phase)."""
    driver = tree.tmp / "run_all_driver.py"
    driver.write_text(_DRIVER.format(hvlint=str(HVLINT), stubs=stubs, tmp=str(tree.tmp)),
                      encoding="utf-8")
    return tree.run(str(driver), "--cohort", tree.cohort, "--no-report", "--cache-dir",
                    str(CACHE), *args, mode=mode, run_all=False, extra_env=extra_env)
