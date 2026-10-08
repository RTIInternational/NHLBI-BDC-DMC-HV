"""#885 refinements after review round 4, each through the real component main().

- 3.18 / 3.9: a follow-up whose gate question names no condition (CHS DIABF38 under DIETF38
  "follow a special diet?", ARIC IFIA06A under IFIA05 "hospitalized in the past four weeks?").
- 3.19: a block, or a nested class, whose every source variable has no value (var_report n = 0).
- The known-issue identity of a block that reads no phv (ResearchStudy).
- 1.14: a single-label block whose own dbGaP metadata names a different exam.

Run: python -m pytest hv-lint/tests/test_refinements_885.py
"""

import copy
import sys
from pathlib import Path

import yaml

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
sys.path.insert(0, str(HVLINT / "phase-3"))
sys.path.insert(0, str(HVLINT / "phase-1"))
import _e2e as E  # noqa: E402
import check_status_semantic as css  # noqa: E402
import validate_semantic as vs  # noqa: E402


def _status(block: dict) -> dict:
    return block["class_derivations"]["Condition"]["slot_derivations"]["condition_status"]


# -- 3.18 / 3.9: gate questions ----------------------------------------------------------------

def test_318_gated_follow_up_mapped_absent_is_reported_through_main(tmp_path):
    """DIABF38 '0' ("special diet not for diabetes") -> ABSENT is a new 3.18 WARNING."""
    t = E.Tree(tmp_path, "CHS")
    t.write("diabetes.yaml", [E.fixture_block("chs_diabetes_diabf38.yaml")])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    assert "new WARNING [3.18]" in res.stdout
    assert "gate question DIETF38 (phv00104227)" in res.stdout


def test_318_unlabelled_n_of_a_gated_follow_up_is_an_error_through_main(tmp_path):
    """IFIA06A has no code labels; its 'N' is still the "No" of a follow-up (gate IFIA05)."""
    t = E.Tree(tmp_path, "ARIC")
    t.write("hist_my_inf.yaml", [E.fixture_block("aric_hist_my_inf_ifia06a.yaml")])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = t.suggested(res)
    assert len(lines) == 1 and '"3.18"' in lines[0] and "gate question IFIA05" in lines[0]


def test_39_dropping_the_no_of_a_gated_follow_up_passes_through_main(tmp_path):
    """The #888 fix (drop the follow-up's "No") must not trade 3.18 for a 3.9 ERROR."""
    t = E.Tree(tmp_path, "CHS")
    b = copy.deepcopy(E.fixture_block("chs_diabetes_diabf38.yaml"))
    _status(b)["value_mappings"] = {"1": "PRESENT"}
    t.write("diabetes.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "[3.9]" not in res.stdout.split("drops observed value '0'")[0] or \
        "drops observed value '0'" not in res.stdout

    t2 = E.Tree(tmp_path / "aric", "ARIC")
    a = copy.deepcopy(E.fixture_block("aric_hist_my_inf_ifia06a.yaml"))
    _status(a)["value_mappings"] = {"Y": "HISTORICAL"}
    t2.write("hist_my_inf.yaml", [a])
    res = E.phase3(t2, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "drops observed value 'N'" not in res.stdout


def test_39_dropping_no_on_a_question_asked_of_everyone_still_fails_through_main(tmp_path):
    """Control: DIETF38 itself is asked of everyone; dropping its '0' is data loss."""
    t = E.Tree(tmp_path, "CHS")
    b = copy.deepcopy(E.fixture_block("chs_diabetes_diabf38.yaml"))
    _status(b)["populated_from"] = "phv00104227"
    _status(b)["value_mappings"] = {"1": "PRESENT"}
    t.write("diabetes.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1 and "drops observed value '0'" in res.stdout


PHT = "pht000001"


def _gate_index(item_desc: str, between_n: int = 800, gate_desc: str = "FOLLOW A SPECIAL DIET"):
    recs = {
        "phv00000001": css._cvs.PhvDetail("FAR", PHT, "", None, "EVER HAD A COLD",
                                          {"0": "NO", "1": "YES"}),
        "phv00000002": css._cvs.PhvDetail("GATE", PHT, "", None, gate_desc,
                                          {"0": "NO", "1": "YES"}),
        "phv00000003": css._cvs.PhvDetail("MID", PHT, "", None, "TO LOSE WEIGHT",
                                          {"0": "NO", "1": "YES"}),
        "phv00000004": css._cvs.PhvDetail("ITEM", PHT, "", None, item_desc,
                                          {"0": "NO", "1": "YES"}),
    }
    stats = {
        "phv00000001": css.PhvStats(4600, {"0": 3600, "1": 1000}),
        "phv00000002": css.PhvStats(4600, {"0": 3680, "1": 920}),
        "phv00000003": css.PhvStats(between_n, {"0": 500, "1": between_n - 500}),
        "phv00000004": css.PhvStats(790, {"0": 545, "1": 245}),
    }
    return css.DetailIndex.from_records(recs), stats


def test_gate_needs_a_branch_item_the_nearest_gate_and_no_condition_in_the_gate():
    idx, st = _gate_index("FOR DIABETES")
    fu = css.detect_followup("phv00000004", idx, st)
    assert fu is not None and fu.gate and fu.sibling_name == "GATE"
    # Not worded as an item of the branch: its "No" is a real answer about the condition.
    idx, st = _gate_index("EVER HAD DIABETES")
    assert css.detect_followup("phv00000004", idx, st) is None
    # An item between them asked of more people ends the branch: GATE is not this item's gate.
    idx, st = _gate_index("FOR DIABETES", between_n=1100)
    assert css.detect_followup("phv00000004", idx, st) is None
    # A gate that names another condition screens for that one.
    idx, st = _gate_index("FOR DIABETES", gate_desc="EVER TOLD ANGINA")
    assert css.detect_followup("phv00000004", idx, st) is None


def test_gate_ratio_band():
    idx, st = _gate_index("FOR DIABETES")
    st["phv00000004"] = css.PhvStats(735, {"0": 500, "1": 235})     # 735 / 920 = 0.799
    assert css.detect_followup("phv00000004", idx, st) is None
    st["phv00000004"] = css.PhvStats(737, {"0": 500, "1": 237})     # 0.801
    assert css.detect_followup("phv00000004", idx, st) is not None
    # A gate with no "yes" answer is not a yes/no question.
    idx.records["phv00000002"].codes = {"0": "NO", "1": "SOMETIMES"}
    assert css.detect_followup("phv00000004", idx, st) is None
    idx.records["phv00000002"].codes = {"0": "NO", "1": "YES"}
    # A gate answered "yes" by more than half its respondents does not split the table.
    st["phv00000002"] = css.PhvStats(1700, {"0": 780, "1": 920})
    assert css.detect_followup("phv00000004", idx, st) is None


def test_negative_answer_reads_an_unlabelled_n_or_0():
    assert css.negative_answer("N", None) and css.negative_answer("0", "")
    assert not css.negative_answer("Y", None) and not css.negative_answer("U", None)
    assert css.negative_answer("1", "No") and not css.negative_answer("N", "Yes")


# -- 3.19: every source variable empty ---------------------------------------------------------

def test_319_block_reading_only_an_empty_variable_fails_through_main(tmp_path):
    """CARDIA hist_cor_bypg b0 reads Y01BAPAS, n = 0 at phs000285.v3; repointed, it passes."""
    t = E.Tree(tmp_path, "CARDIA")
    b = E.fixture_block("cardia_hist_cor_bypg_b0.yaml")
    t.write("hist_cor_bypg.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = t.suggested(res)
    assert len(lines) == 1 and '"3.19"' in lines[0] and "phv00121381 (Y01BAPAS)" in lines[0]
    # Y01STENT (phv00121382, same table) has data: the block is no longer empty.
    fixed = yaml.safe_load(yaml.safe_dump(b).replace("phv00121381", "phv00121382"))
    t.write("hist_cor_bypg.yaml", [fixed])
    assert "[3.19]" not in E.phase3(t, "validate_semantic.py").stdout


def test_319_reports_each_empty_nested_observation_through_main(tmp_path):
    """MESA spirometry b0: pfvca4 / pfev1a4 are n = 0; the Set's other observations have data."""
    t = E.Tree(tmp_path, "MESA")
    b = E.fixture_block("mesa_spirometry_b0.yaml")
    t.write("spirometry.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = [x for x in t.suggested(res) if '"3.19"' in x]
    assert len(lines) == 2
    assert any("OMOP:3002094" in x and "pfvca4" in x for x in lines)
    assert any("OMOP:3022891" in x and "pfev1a4" in x for x in lines)
    assert not any("of this block" in x for x in lines)
    obs = b["class_derivations"]["MeasurementObservationSet"]["slot_derivations"]["observations"]
    obs["class_derivations"] = [
        o for o in obs["class_derivations"]
        if o["MeasurementObservation"]["slot_derivations"]["observation_type"]["value"]
        not in ("OMOP:3002094", "OMOP:3022891")]
    t.write("spirometry.yaml", [b])
    assert "[3.19]" not in E.phase3(t, "validate_semantic.py").stdout


def test_319_needs_n_for_uncoded_variables(tmp_path):
    """A coded-only value-count index cannot tell empty from unreported: the run fails."""
    import gzip
    import json
    import shutil
    t = E.Tree(tmp_path, "CARDIA")
    t.write("hist_cor_bypg.yaml", [E.fixture_block("cardia_hist_cor_bypg_b0.yaml")])
    manifests = HVLINT.parent / "hv_dataqc" / "cache_fetcher" / "manifests"
    shutil.copytree(manifests, t.root / "hv_dataqc" / "cache_fetcher" / "manifests")
    cache = t.root / "hv-lint" / "cache"
    shutil.copytree(E.CACHE, cache)
    stats = cache / "phs000285.v3_stats.json.gz"
    with gzip.open(stats, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    with gzip.open(stats, "wt", encoding="utf-8") as fh:
        json.dump({k: v for k, v in raw.items() if "c" in v}, fh)
    res = t.run("phase-3/validate_semantic.py", "--cohort", "CARDIA", "--cache-dir", str(cache),
                "--fail-on", "error")
    assert res.returncode == 1 and "3.19 cannot run" in res.stderr, res.stderr[-800:]


def _empty_source(block, nonnull):
    detail = vs.DetailIndex()
    return [f.message for f in vs.check_empty_source(block, 0, "X-ingest/x.yaml", nonnull,
                                                      detail, "phs000001.v1")]


def test_319_ignores_who_and_when_slots_and_unknown_variables():
    block = {"class_derivations": {"Condition": {"populated_from": PHT, "slot_derivations": {
        "associated_participant": {"expr": "str({phv00000009})"},
        "age_at_condition_start": {"expr": "{phv00000008} * 365"},
        "condition_status": {"populated_from": "phv00000001", "value_mappings": {"1": "PRESENT"}},
    }}}}
    nonnull = {"phv00000001": 0, "phv00000008": 500, "phv00000009": 500}
    assert len(_empty_source(block, nonnull)) == 1
    del nonnull["phv00000001"]          # no var_report: n unknown, not 0
    assert _empty_source(block, nonnull) == []
    nonnull["phv00000001"] = 3
    assert _empty_source(block, nonnull) == []


# -- Known-issue identity of a block that reads no phv -----------------------------------------

def _no_phv_block(name: str | None) -> dict:
    slots = {
        "observation_type": {"value": "OMOP:3004249"},
        "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": {
            "value_decimal": {"value": 5}}}}]},
    }
    if name:
        slots["name"] = {"value": name}
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": "pht004715", "slot_derivations": slots}}}


def test_a_block_with_no_phv_keeps_its_entry_when_a_slot_is_added_through_main(tmp_path):
    """Keyed on class, table and name, not a body digest: adding a slot is not a new finding."""
    t = E.Tree(tmp_path, "HCHS")
    b = _no_phv_block("Study A")
    t.write("x.yaml", [b])
    first = E.phase3(t, "validate_semantic.py")
    assert first.returncode == 1 and "[3.16]" in first.stdout, first.stdout[-1500:]
    lines = t.list_as_known(first, 884)
    assert len(lines) == 1 and "MeasurementObservation@pht004715:name~Study A" in lines[0]
    assert E.phase3(t, "validate_semantic.py").returncode == 0
    b["class_derivations"]["MeasurementObservation"]["slot_derivations"]["unit_note"] = {
        "value": "added"}
    t.write("x.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]


def test_blocks_with_no_phv_and_no_name_are_numbered():
    import _known_issues as K
    assert K.file_identities([_no_phv_block(None), _no_phv_block(None)]) == [
        "MeasurementObservation@pht004715:-", "MeasurementObservation@pht004715:-#2"]
    assert K.block_identity(_no_phv_block("  Study\n B ")) == (
        "MeasurementObservation@pht004715:name~Study B")


# -- 1.14: a single-label block's visit vs its own dbGaP metadata -----------------------------

P1 = "phase-1/check_cross_file_pht_consistency.py"


def _relabel(block: dict, old: str, new: str) -> dict:
    b = copy.deepcopy(block)
    visit = next(iter(b["class_derivations"].values()))["slot_derivations"]["associated_visit"]
    assert f":{old}" in visit["expr"]
    visit["expr"] = visit["expr"].replace(f":{old}", f":{new}")
    return b


def test_114_aric_single_block_table_relabelled_fails_through_main(tmp_path):
    """Review round 3 A M4: ATRFIB31 pht004039 ("Visit 3") relabelled EXAM 3 -> EXAM 2 passed
    every phase; 1.8's majority arm needs two other blocks of the table."""
    t = E.Tree(tmp_path, "ARIC")
    b = E.fixture_block("aric_afib_atrfib31.yaml")
    t.write("afib.yaml", [b])
    assert t.run(P1, "--cohort", "ARIC").returncode == 0
    t.write("afib.yaml", [_relabel(b, "ARIC EXAM 3", "ARIC EXAM 2")])
    res = t.run(P1, "--cohort", "ARIC")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = t.list_as_known(res, 872)
    assert len(lines) == 1 and '"1.14"' in lines[0] and "'ARIC EXAM 2'" in lines[0]
    assert t.run(P1, "--cohort", "ARIC").returncode == 0
    # Fixed: the listed entry is stale and fails until it is pruned.
    t.write("afib.yaml", [b])
    stale = t.run(P1, "--cohort", "ARIC")
    assert stale.returncode == 1 and "stale known-issue entry [1.14]" in stale.stdout


def test_114_mesa_table_named_for_another_exam_fails_through_main(tmp_path):
    """MESA pht001116 is MESA_Exam1Main: a block labelled EXAM 3 is wrong, EXAM 1 is right."""
    t = E.Tree(tmp_path, "MESA")
    t.write("hdl.yaml", [_labelled_mesa("MESA CLASSIC EXAM 1")])
    assert t.run(P1, "--cohort", "MESA").returncode == 0
    t.write("hdl.yaml", [_labelled_mesa("MESA CLASSIC EXAM 3")])
    res = t.run(P1, "--cohort", "MESA")
    assert res.returncode == 1 and "[1.14]" in res.stdout and "MESA_Exam1Main" in res.stdout, \
        res.stdout[-1500:]


def _labelled_mesa(label: str) -> dict:
    seed = "phv00084441"
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": "pht001116", "slot_derivations": {
            "associated_participant": {
                "expr": f'uuid5("https://w3id.org/bdchm/Participant", str({{{seed}}}) + ":MESA")'},
            "associated_visit": {
                "expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":{label}")'},
            "observation_type": {"value": "OMOP:4041720"},
            "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": {
                "value_decimal": {"populated_from": "phv00084970"}, "unit": {"value": "mg/dL"}}}}]},
        }}}}


def _ref(file: str, label: str, phvs=(), pht="pht000001"):
    import check_cross_file_pht_consistency as C
    return C.PhtVisitRef(pht, frozenset([label]), file, 0, "Condition", frozenset(phvs))


def test_114_judges_only_a_numbered_label_against_its_own_bracketed_visit():
    import check_cross_file_pht_consistency as C
    rec = css._cvs.PhvDetail
    details = {
        "phv00000001": rec("A", "pht000001", "", None, "Q1 [Form X. Visit 4]", None),
        "phv00000002": rec("B", "pht000001", "", None, "Since visit 1, any? [Form X, Visit 2]",
                           None),
        "phv00000003": rec("C", "pht000001", "", None, "Prevalent at visit 1 [Derived, visit 4]",
                           None),
    }
    f = "priority_variables_transform/ARIC-ingest/x.yaml"
    run = lambda *refs: [x.message for x in C.check_visit_vs_dbgap(list(refs), {}, details)]  # noqa: E731
    assert len(run(_ref(f, "ARIC EXAM 3", ["phv00000001"]))) == 1
    assert run(_ref(f, "ARIC EXAM 4", ["phv00000001"])) == []
    # A number outside the bracketed source is not the variable's visit.
    assert run(_ref(f, "ARIC EXAM 2", ["phv00000002"])) == []
    assert len(run(_ref(f, "ARIC EXAM 1", ["phv00000002"]))) == 1
    assert run(_ref(f, "ARIC EXAM 4", ["phv00000003"])) == []
    # Two value variables from two visits: either label is one of them.
    assert run(_ref(f, "ARIC EXAM 2", ["phv00000001", "phv00000002"])) == []
    assert run(_ref(f, "ARIC EXAM 4", ["phv00000001", "phv00000002"])) == []
    # A label with no exam number, or a block with several labels, is not judged.
    assert run(_ref(f, "ARIC CHEM 2", ["phv00000001"])) == []
    two = C.PhtVisitRef("pht000001", frozenset(["ARIC EXAM 3", "ARIC EXAM 5"]), f, 0,
                        "Condition", frozenset(["phv00000001"]))
    assert run(two) == []
    # MESA reads the table name; a label with no exam number is not judged.
    m = "priority_variables_transform/MESA-ingest/x.yaml"
    names = {"pht000001": {"name": "MESA_AncilMesaLungExam3CT"}}
    msgs = [x.message for x in C.check_visit_vs_dbgap(
        [_ref(m, "MESA LUNG CT EXAM 2"), _ref(m, "MESA LUNG CT EXAM 3"), _ref(m, "MESA LUNG CT")],
        names, {})]
    assert len(msgs) == 1 and "'MESA LUNG CT EXAM 2'" in msgs[0]
