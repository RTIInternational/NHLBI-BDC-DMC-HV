"""Every HV-Lint test runs against empty known-issue and baseline files, with no HVLINT_* mode set.

A component's main() reads ``hv-lint/known_issues.yaml`` and ``hv-lint/warning_baseline.json``
unless ``HVLINT_KNOWN_ISSUES`` / ``HVLINT_WARNING_BASELINE`` point elsewhere, and writes them under
``HVLINT_PRUNE`` / ``HVLINT_UPDATE_BASELINE``. Without this fixture an in-process test passes or
fails on whatever the committed files hold, and a shell that exported the prune variables would
let pytest rewrite them. Subprocesses inherit the same environment.

A test that means to read the committed files opts in by deleting the two path variables itself
(``test_known_issues.py``'s ``committed`` fixture); one that needs a mode sets it with monkeypatch.
"""

import json
import os

import pytest


@pytest.fixture(autouse=True)
def _hermetic_known_issues(tmp_path_factory):
    # Not monkeypatch: requesting it here would set it up before test_phase_mains.py's
    # HV_ROOT leak guard and undo it after that guard checks, failing every test there.
    saved = {k: v for k, v in os.environ.items() if k.startswith("HVLINT_")}
    for name in saved:
        del os.environ[name]
    d = tmp_path_factory.mktemp("hvlint_state")
    ki, bl = d / "known_issues.yaml", d / "warning_baseline.json"
    ki.write_text("", encoding="utf-8")
    bl.write_text(json.dumps({"warnings": {}}), encoding="utf-8")
    os.environ["HVLINT_KNOWN_ISSUES"] = str(ki)
    os.environ["HVLINT_WARNING_BASELINE"] = str(bl)
    yield
    for name in [k for k in os.environ if k.startswith("HVLINT_")]:
        del os.environ[name]
    os.environ.update(saved)
