"""The 2.8 and 3.11 gates must be able to fail.

Each fixture is a case that used to pass a step labelled "enforced": a PHV mapped as both
systolic and diastolic, an unparseable YAML, and a code whose label contradicts its OMOP target.

Run: python -m pytest hv-lint/tests/test_gates_fail.py
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

HVLINT = Path(__file__).resolve().parent.parent
REPO = HVLINT.parent
sys.path.insert(0, str(HVLINT))
sys.path.insert(0, str(HVLINT / "phase-3"))
import check_value_semantic as cvs  # noqa: E402


def _bp_block(phv: str, concept: str) -> dict:
    quantity = {"Quantity": {"slot_derivations": {"value_decimal": {"populated_from": phv},
                                                  "unit": {"value": "mm[Hg]"}}}}
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": "pht000001",
        "slot_derivations": {
            "observation_type": {"value": concept},
            "value_quantity": {"class_derivations": [quantity]},
        }}}}


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    base = tmp_path / "priority_variables_transform" / "ARIC-ingest"
    base.mkdir(parents=True)
    for name, text in files.items():
        (base / name).write_text(text, encoding="utf-8")
    return tmp_path


def _run_28(script: Path, root: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HV_ROOT=str(root))
    return subprocess.run([sys.executable, str(script), "--fail-on", "error"],
                          cwd=cwd, env=env, capture_output=True, text=True)


def test_28_one_phv_two_concepts_fails(tmp_path):
    root = _tree(tmp_path, {
        "bp.yaml": yaml.safe_dump([_bp_block("phv00000001", "OMOP:4152194"),
                                   _bp_block("phv00000001", "OMOP:4154790")]),
    })
    res = _run_28(HVLINT / "phase-2" / "check_phv_dedup.py", root, REPO)
    assert res.returncode == 1, res.stdout
    assert "ERROR" in res.stdout and "phv00000001" in res.stdout


def test_28_parse_error_fails(tmp_path):
    root = _tree(tmp_path, {
        "ok.yaml": yaml.safe_dump([_bp_block("phv00000001", "OMOP:4152194")]),
        "broken.yaml": "- class_derivations:\n    Condition: [unclosed\n",
    })
    res = _run_28(HVLINT / "phase-2" / "check_phv_dedup.py", root, REPO)
    assert res.returncode == 1, res.stdout
    assert "parse error" in res.stdout


def test_root_copy_fails_on_both(tmp_path):
    root = _tree(tmp_path, {
        "bp.yaml": yaml.safe_dump([_bp_block("phv00000001", "OMOP:4152194"),
                                   _bp_block("phv00000001", "OMOP:4154790")]),
    })
    res = subprocess.run([sys.executable, str(REPO / "check_phv_dedup.py")],
                         cwd=root, capture_output=True, text=True)
    assert res.returncode == 1 and "NEW DUPLICATES" in res.stdout


def test_root_known_issues_is_empty_so_no_entry_can_go_stale():
    sys.path.insert(0, str(REPO))
    import check_phv_dedup as root_dedup
    assert root_dedup.KNOWN_ISSUES == {}


def _detail(codes: dict[str, str]) -> cvs.DetailIndex:
    idx = cvs.DetailIndex()
    idx.records["phv00000002"] = cvs.PhvDetail("SEX", "pht000001", "encoded", None, "Sex", codes)
    return idx


def _demo_block(mappings: dict[str, str], nested: bool = False) -> dict:
    slot = {"populated_from": "phv00000002", "value_mappings": mappings}
    if nested:
        inner = {"Quantity": {"slot_derivations": {"value_concept": slot}}}
        slots = {"value_quantity": {"class_derivations": [inner]}}
        return {"class_derivations": {"MeasurementObservation": {"populated_from": "pht000001",
                                                                 "slot_derivations": slots}}}
    return {"class_derivations": {"Demography": {"populated_from": "pht000001",
                                                 "slot_derivations": {"sex": slot}}}}


def test_311_contradiction_is_an_error():
    f = cvs.check_value_semantic_alignment(
        _demo_block({"1": "OMOP:8532"}), 0, "x.yaml", _detail({"1": "Male", "2": "Female"}),
        dict(cvs.EMBEDDED_CONCEPT_NAMES))
    assert [(x.check, x.severity) for x in f] == [("3.11", "ERROR")]
    assert cvs.SEVERITY_RANK[f[0].severity] >= cvs.SEVERITY_RANK["ERROR"]


def test_311_walks_nested_slots():
    f = cvs.check_value_semantic_alignment(
        _demo_block({"1": "OMOP:8532"}, nested=True), 0, "x.yaml",
        _detail({"1": "Male"}), dict(cvs.EMBEDDED_CONCEPT_NAMES))
    assert len(f) == 1 and "Quantity.value_concept" in f[0].message


def test_311_correct_mapping_is_quiet():
    f = cvs.check_value_semantic_alignment(
        _demo_block({"1": "OMOP:8507", "2": "OMOP:8532"}), 0, "x.yaml",
        _detail({"1": "Male", "2": "Female"}), dict(cvs.EMBEDDED_CONCEPT_NAMES))
    assert f == []


def test_311_table_entries_match_bdchm():
    names = cvs.EMBEDDED_CONCEPT_NAMES
    assert names[8657] == "American Indian or Alaska Native" and 8567 not in names
    assert names[4282779] == "Cigarette smoking tobacco"
