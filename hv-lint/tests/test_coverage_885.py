"""Coverage gaps from #885 part 6: a check that did not run must not read as a pass.

Run: python -m pytest hv-lint/tests/test_coverage_885.py
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "phase-1"))
sys.path.insert(0, str(HVLINT))

import run_yamllint  # noqa: E402


def test_missing_yamllint_fails_instead_of_printing_a_clean_summary(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "yamllint" else real(name, *a))
    monkeypatch.setattr(sys, "argv", ["run_yamllint.py", "--summary"])
    with pytest.raises(SystemExit) as exc:
        run_yamllint.main()
    assert exc.value.code == 2


def test_phase2_schema_ref_is_pinned_to_one_commit():
    """Review round 1 B 2: an enforced, ratcheted Phase 2 must not follow BDC-HM main live."""
    import re
    src = (HVLINT / "phase-2" / "validate_model_conformance.py").read_text(encoding="utf-8")
    pin = re.search(r'^BDCHM_REF = "([0-9a-f]{40})"$', src, re.M)
    assert pin, "BDCHM_REF must be a full commit SHA"
    assert 'default=BDCHM_REF' in src
    manager = (HVLINT / "phase-2" / "run_phase2.py").read_text(encoding="utf-8")
    assert '"--bdchm-ref", default=None' in manager
    workflow = (HVLINT.parent / ".github" / "workflows" / "hv_lint.yml").read_text(encoding="utf-8")
    assert "bdchm_ref=main" not in workflow and "bdchm_ref || 'main'" not in workflow
    assert '${BDCHM_REF:+--bdchm-ref "$BDCHM_REF"}' in workflow


# -- the workflow's Detect step ------------------------------------------------------------------

_FAKE_GIT = r'''
git() {  # git diff --name-only BASE HEAD -- <pathspec>...: the changed files under each pathspec
  local seen=0 p f
  for p in "$@"; do  # a diff naming $FAIL_PATHSPEC fails, as git does on an unknown base
    if [ -n "$FAIL_PATHSPEC" ] && [ "$p" = "$FAIL_PATHSPEC" ]; then return 128; fi
  done
  for p in "$@"; do
    if [ "$seen" = 1 ]; then
      for f in $CHANGED_FILES; do case "$f" in "$p"*) echo "$f";; esac; done
    fi
    if [ "$p" = "--" ]; then seen=1; fi
  done
  return 0
}
'''


def _detect(tmp_path, changed: list[str], fail_pathspec: str = "") -> str:
    """Run the workflow's own Detect step under `bash -e`, as Actions does, on a fake diff."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not on PATH")
    wf = yaml.safe_load((HVLINT.parent / ".github" / "workflows" / "hv_lint.yml").read_text(
        encoding="utf-8"))
    step = next(s for j in wf["jobs"].values() for s in j["steps"] if s.get("id") == "detect")
    script = tmp_path / "detect.sh"
    script.write_text(_FAKE_GIT + step["run"].replace(
        "${{ github.event.pull_request.base.sha }}", "base"), encoding="utf-8", newline="\n")
    out = tmp_path / "github_output"
    out.write_text("", encoding="utf-8")
    env = dict(os.environ, GITHUB_OUTPUT=str(out), CHANGED_FILES=" ".join(changed),
               FAIL_PATHSPEC=fail_pathspec,
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    res = subprocess.run([bash, "-e", str(script)], cwd=HVLINT.parent, env=env,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return out.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("tooling", ["hv-lint/phase-3/validate_semantic.py",
                                     "hv-lint/known_issues.yaml",
                                     "hv-lint/warning_baseline.json",
                                     ".github/workflows/hv_lint.yml"])
def test_detect_lints_all_when_hv_lint_itself_changed(tmp_path, tooling):
    """Review round 2 B F1: a rule change shipped beside one cohort's specs was linted for that
    cohort only, so its new ERRORs and the other cohorts' stale entries were never evaluated."""
    spec = "priority_variables_transform/MESA-ingest/hdl.yaml"
    assert _detect(tmp_path, [spec]) == "cohort=MESA"
    assert _detect(tmp_path, [spec, tooling]) == "cohort=all"


def test_detect_lints_all_when_the_tooling_diff_fails(tmp_path):
    """Review round 3 B D2: a failed hv-lint/ diff must widen to `all`, not read as "no tooling
    change" and narrow the run to the one cohort whose specs changed."""
    spec = "priority_variables_transform/MESA-ingest/hdl.yaml"
    assert _detect(tmp_path, [spec]) == "cohort=MESA"
    assert _detect(tmp_path, [spec], fail_pathspec="hv-lint/") == "cohort=all"


def test_detect_keeps_the_manifest_widening(tmp_path):
    spec = "priority_variables_transform/ARIC-ingest/hdl.yaml"
    manifests = "hv_dataqc/cache_fetcher/manifests/"
    assert _detect(tmp_path, [spec, manifests + "_manifest-mesa.yaml"]) == "cohort=all"
    assert _detect(tmp_path, [spec, manifests + "_manifest-aric.yaml"]) == "cohort=ARIC"
    assert _detect(tmp_path, [spec, ".github/workflows/other.yml"]) == "cohort=ARIC"
