"""Tests for HV-Lint rule 1.12 (identical blocks in different files of one cohort).

Run: python -m pytest hv-lint/tests/test_cross_file_duplicates.py
"""

import copy
import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
sys.path.insert(0, str(HVLINT / "phase-1"))
import check_cross_file_duplicates as xfd  # noqa: E402

VISIT = 'uuid5("https://w3id.org/bdchm/Visit", str({phv00002000}) + ":FHS ORIGINAL EXAM 14")'


def drug(phv="phv00002223", concept="ATC:C03", visit=VISIT, mappings=None, provenance=None):
    slots = {
        "associated_visit": {"expr": visit},
        "drug_concept": {"value": concept},
        "exposure_status": {"populated_from": phv,
                            "value_mappings": mappings or {"0": "ABSENT", "1": "PRESENT"}},
    }
    if provenance:
        slots["exposure_provenance"] = {"value": provenance}
    return {"class_derivations": {"DrugExposure": {"populated_from": "pht000016",
                                                    "slot_derivations": slots}}}


def run(blocks_by_file, known=None):
    refs = []
    for path, blocks in blocks_by_file.items():
        for i, b in enumerate(blocks):
            refs.append((xfd.BlockRef(path, i), b))
    return xfd.find_cross_file_duplicates({"FHS-ingest": refs}, known=known or {})


def test_identical_drug_blocks_in_two_files_are_flagged():
    f = run({"FHS-ingest/hypert_trt.yaml": [drug()], "FHS-ingest/tak_diuret.yaml": [drug()]})
    assert [(x.check, x.severity, x.file) for x in f] == [
        ("1.12", "ERROR", "priority_variables_transform/FHS-ingest/tak_diuret.yaml")]
    assert "hypert_trt.yaml block 0" in f[0].message


def test_same_file_duplicates_are_left_to_rule_1_2():
    assert run({"FHS-ingest/med_use.yaml": [drug(), drug()]}) == []


def test_different_visit_concept_or_mapping_is_not_a_duplicate():
    for other in (drug(visit=VISIT.replace("14", "15")), drug(concept="ATC:C03A"),
                  drug(mappings={"1": "PRESENT"}), drug(phv="phv00002224")):
        assert run({"FHS-ingest/a.yaml": [drug()], "FHS-ingest/b.yaml": [other]}) == []


def test_blocks_differing_only_in_provenance_are_flagged_and_say_so():
    f = run({"FHS-ingest/a.yaml": [drug(provenance="STUDY_RECORD")],
             "FHS-ingest/b.yaml": [drug(provenance="PATIENT_SELF_REPORT")]})
    assert len(f) == 1 and "differs only in exposure_provenance" in f[0].message


def test_range_annotation_is_not_a_difference():
    b = drug()
    b["class_derivations"]["DrugExposure"]["slot_derivations"]["drug_concept"]["range"] = "string"
    f = run({"FHS-ingest/a.yaml": [drug()], "FHS-ingest/b.yaml": [b]})
    assert len(f) == 1 and "identical apart from" in f[0].message


def test_condition_blocks_use_condition_slots():
    cond = {"class_derivations": {"Condition": {"populated_from": "pht001121", "slot_derivations": {
        "associated_visit": {"expr": VISIT},
        "condition_concept": {"value": "MONDO:0005252"},
        "condition_status": {"populated_from": "phv00087140",
                             "value_mappings": {"0": "ABSENT", "1": "PRESENT"}},
    }}}}
    f = run({"MESA-ingest/chf.yaml": [cond], "MESA-ingest/hist_hrtfail.yaml": [copy.deepcopy(cond)]})
    assert len(f) == 1 and "Condition table=pht001121" in f[0].message


def test_class_without_status_matches_only_on_whole_body():
    visit = {"class_derivations": {"Visit": {"populated_from": "pht000016",
                                             "slot_derivations": {"id": {"expr": VISIT}}}}}
    other = copy.deepcopy(visit)
    other["class_derivations"]["Visit"]["slot_derivations"]["age_at_visit_start"] = {"expr": "1"}
    assert len(run({"FHS-ingest/a.yaml": [visit], "FHS-ingest/b.yaml": [copy.deepcopy(visit)]})) == 1
    assert run({"FHS-ingest/a.yaml": [visit], "FHS-ingest/b.yaml": [other]}) == []


def test_known_issue_is_reported_at_info():
    key = "FHS-ingest/hypert_trt.yaml|FHS-ingest/tak_diuret.yaml|phv00002223"
    f = run({"FHS-ingest/hypert_trt.yaml": [drug()], "FHS-ingest/tak_diuret.yaml": [drug()]},
            known={key: "tracked in #785"})
    assert f[0].severity == "INFO" and "tracked in #785" in f[0].message


def test_known_issues_keys_are_well_formed():
    for key in xfd.KNOWN_ISSUES:
        a, b, phv = key.split("|")
        assert a < b and a.split("/")[0] == b.split("/")[0]
        assert xfd.PHV_RE.fullmatch(phv)
