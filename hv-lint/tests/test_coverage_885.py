"""Coverage gaps from #885 part 6: a check that did not run must not read as a pass.

Run: python -m pytest hv-lint/tests/test_coverage_885.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

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
