"""The independent gate review (2026-10-08): each test fails if its guard is removed.

B6: HIGH findings are ratcheted, and an undeclared CURIE prefix is an ERROR. B7: a non-string
value_mappings key is an ERROR (1.15). S2/N4: the frozen linkml-map keys fail Phase 2 in CI. N2:
2.0 is ratcheted. N3: yamllint truthy is an error. The component main() paths for B3 and B4 are
in test_known_issues_e2e.py.

Run: python -m pytest hv-lint/tests/test_gate_review_885.py
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-2"):
    sys.path.insert(0, str(HVLINT / sub))
import _known_issues as K  # noqa: E402
import validate_model_conformance as vmc  # noqa: E402


@dataclass
class F:
    file: str
    block: int
    check: str
    severity: str
    message: str


@pytest.fixture
def tree(tmp_path, monkeypatch):
    d = tmp_path / "priority_variables_transform" / "CHS-ingest"
    d.mkdir(parents=True)
    spec = d / "diabetes.yaml"
    spec.write_text(yaml.safe_dump([{"class_derivations": {"Condition": {
        "populated_from": "pht001452", "slot_derivations": {
            "condition_concept": {"value": "MONDO:005015"}}}}}]), encoding="utf-8")
    ki, bl = tmp_path / "ki.yaml", tmp_path / "bl.json"
    ki.write_text("", encoding="utf-8")
    monkeypatch.setenv("HVLINT_KNOWN_ISSUES", str(ki))
    monkeypatch.setenv("HVLINT_WARNING_BASELINE", str(bl))
    for v in ("HVLINT_PRUNE", "HVLINT_UPDATE_BASELINE", "HVLINT_RUN_ALL",
              "HVLINT_PRUNE_REMOVED"):
        monkeypatch.delenv(v, raising=False)
    return spec


# -- B6: HIGH is ratcheted -----------------------------------------------------------------------

def test_a_new_high_finding_fails_and_an_accepted_one_passes(tree, monkeypatch):
    """`MONDO:005015` (6 digits) is a HIGH 2.6 finding. It used to print and then PASS."""
    high = F(str(tree), 0, "2.6", "HIGH", "Invalid MONDO identifier '005015' (expected exactly "
                                          "7 digits): 'MONDO:005015' on Condition.condition_concept")
    extra = K.finalize([high], checks={"2.6"}, scanned_files=[tree], make_finding=F)
    assert [x.severity for x in extra] == ["ERROR"]
    assert extra[0].message.startswith("new HIGH [2.6] in CHS")
    monkeypatch.setenv(K.RUN_ALL_ENV, "1")
    assert K.finalize([high], checks={"2.6"}, scanned_files=[tree], make_finding=F,
                      mode="update") == []
    assert K.finalize([high], checks={"2.6"}, scanned_files=[tree], make_finding=F) == []


# -- B6: an undeclared CURIE prefix --------------------------------------------------------------

PREFIXES = frozenset({"MONDO", "OMOP", "HP"}) | vmc.HV_EXTRA_PREFIXES


def _concept_block(value: str) -> dict:
    return {"Condition": {"populated_from": "pht001452", "slot_derivations": {
        "condition_concept": {"value": value},
        "condition_status": {"expr": f"case(({{phv00100001}} == 1, '{value}'))"}}}}


def test_an_undeclared_prefix_is_an_error_in_value_and_expr():
    ctx = vmc.ValidationContext(prefixes=PREFIXES)
    found = [f for f in vmc.validate_class_derivations(_concept_block("MOND:0005015"), 0,
                                                       "CHS-ingest/x.yaml", ctx)
             if f.check == "2.6"]
    assert len(found) == 2 and {f.severity for f in found} == {"ERROR"}
    assert all("Unknown CURIE prefix 'MOND'" in f.message for f in found)


@pytest.mark.parametrize("value", ["MONDO:0005015", "ATC:C02", "RxCUI:5470", "NCBITaxon:9606"])
def test_a_declared_or_hv_prefix_passes(value):
    ctx = vmc.ValidationContext(prefixes=PREFIXES)
    assert [f for f in vmc.validate_class_derivations(_concept_block(value), 0,
                                                      "CHS-ingest/x.yaml", ctx)
            if f.check == "2.6"] == []


# -- B7: a value_mappings key that is not a string -----------------------------------------------

sys.path.insert(0, str(HVLINT / "tests"))
import _e2e as E  # noqa: E402

P1 = "phase-1/validate_yaml_structure.py"


def _status(keys_text: str) -> str:
    return ("- class_derivations:\n"
            "    Condition:\n"
            "      populated_from: pht001452\n"
            "      slot_derivations:\n"
            "        condition_status:\n"
            "          populated_from: phv00100001\n"
            "          value_mappings:\n" + keys_text)


@pytest.mark.parametrize("keys_text,kind", [
    ("            0: ABSENT\n            1: PRESENT\n", "int"),
    ("            Yes: PRESENT\n            No: ABSENT\n", "bool"),
    ("            ~: ABSENT\n            '1': PRESENT\n", "NoneType"),
])
def test_a_non_string_value_mappings_key_fails_phase1_through_main(tmp_path, keys_text, kind):
    t = E.Tree(tmp_path, "CHS")
    (t.dir / "diabetes.yaml").write_text(_status("            '0': ABSENT\n"
                                                 "            '1': PRESENT\n"), encoding="utf-8")
    ok = t.run(P1, "--cohort", "CHS")
    assert ok.returncode == 0, ok.stdout[-1500:]
    (t.dir / "diabetes.yaml").write_text(_status(keys_text), encoding="utf-8")
    res = t.run(P1, "--cohort", "CHS")
    assert res.returncode == 1 and "[1.15]" in res.stdout and f"parses as {kind}" in res.stdout


# -- S2 / N4: the frozen linkml-map keys are an ERROR in CI --------------------------------------

def test_frozen_key_fallback_fails_in_ci_and_names_the_real_exception(tmp_path):
    """A linkml_map that cannot be imported: under GITHUB_ACTIONS Phase 2 exits 1 before any
    check, and the message is the real exception, not a guess about Python 3.14."""
    import os
    import subprocess
    stub = tmp_path / "stub" / "linkml_map"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("raise ImportError('stub: linkml-map not installed')\n",
                                      encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("HVLINT_")}
    env.update(GITHUB_ACTIONS="true", PYTHONPATH=str(stub.parent), PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(HVLINT / "phase-2/validate_model_conformance.py"),
                          "--cohort", "CHS"], env=env, capture_output=True, text=True,
                         encoding="utf-8")
    assert res.returncode == 1, res.stdout[-1000:] + res.stderr[-1000:]
    assert "linkml_map import failed: ImportError: stub: linkml-map not installed" in res.stderr
    assert "DID NOT RUN" in res.stderr and "3.14" not in res.stderr


# -- N2: Phase 2's "Empty file" is ratcheted; N3: yamllint truthy is fatal -----------------------

def test_phase2_empty_file_is_a_new_finding_through_main(tmp_path):
    """2.0 was outside Phase 2's checks= set, so its WARNING was never ratcheted."""
    pytest.importorskip("linkml_runtime")
    pytest.importorskip("linkml_map")
    t = E.Tree(tmp_path, "CHS")
    (t.dir / "diabetes.yaml").write_text(_status("            '0': ABSENT\n"
                                                 "            '1': PRESENT\n"), encoding="utf-8")
    (t.dir / "hdl.yaml").write_text("# every block commented out\n", encoding="utf-8")
    res = t.run("phase-2/validate_model_conformance.py", "--cohort", "CHS")
    if "Failed to load BDCHM schema" in res.stderr:
        pytest.skip("the pinned BDC-HM schema could not be fetched")
    assert res.returncode == 1, res.stdout[-1500:]
    assert re.search(r"new WARNING \[2\.0\] in CHS: CHS-ingest/hdl\.yaml \| \S+ \| Empty file",
                     res.stdout)
    assert "lost or unlinked record" in res.stdout


def test_yamllint_truthy_is_an_error():
    """yamllint exits 0 on a warning and run_yamllint.py never ratchets one."""
    cfg = yaml.safe_load((HVLINT / ".yamllint").read_text(encoding="utf-8"))
    assert cfg["rules"]["truthy"]["level"] == "error"
