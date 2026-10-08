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
