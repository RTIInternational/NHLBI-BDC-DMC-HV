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

def test_318_gated_follow_up_mapped_absent_is_an_error_through_main(tmp_path):
    """DIABF38 '0' ("special diet not for diabetes") -> ABSENT is an unlisted 3.18 ERROR: a gate
    match is as strong as count + wording, so a baseline update cannot absorb it."""
    t = E.Tree(tmp_path, "CHS")
    t.write("diabetes.yaml", [E.fixture_block("chs_diabetes_diabf38.yaml")])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    assert "new WARNING" not in res.stdout
    lines = t.suggested(res)
    assert len(lines) == 1 and '"3.18"' in lines[0]
    assert "gate question DIETF38 (phv00104227)" in lines[0]


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
    assert "drops observed value '0'" not in res.stdout

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


def test_negative_answer_reads_an_unlabelled_n_or_0_only_when_the_variable_has_no_labels():
    assert css.negative_answer("N", None) and css.negative_answer("0", {})
    assert not css.negative_answer("Y", None) and not css.negative_answer("U", None)
    assert css.negative_answer("1", {"1": "No"}) and not css.negative_answer("N", {"N": "Yes"})
    # A labelled variable's unlabelled code means nothing yet (CARDIA A12CB* '0', #873 Q19).
    assert not css.negative_answer("0", {"1": "Yes", "2": "No"})
    assert not css.negative_answer("N", {"Y": "Yes"})


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


# -- Review round 4 deferred items ---------------------------------------------------------------

def _visit_case(pht: str, seed: str, case: str) -> dict:
    b = E.visit_block(pht, seed, "X")
    b["class_derivations"]["Visit"]["slot_derivations"]["id"] = {
        "expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":" + {case})'}
    return b


def test_51_same_table_error_keeps_its_entry_when_blocks_with_different_label_sets_swap(tmp_path):
    """Review 4 A D1 / B D2: the ERROR moved to the other block, whose identity lists two labels."""
    t = E.Tree(tmp_path, "FHS")
    a = _visit_case("pht000012", "phv00001559",
                    "case(({phv00001560} == '1', 'FHS ORIGINAL EXAM 10'), "
                    "({phv00001560} == '2', 'FHS ORIGINAL EXAM 11'))")
    b = E.visit_block("pht000012", "phv00001559", "FHS ORIGINAL EXAM 10")
    t.write("visit.yaml", [a, b])
    first = E.phase5(t)
    assert first.returncode == 1 and "[5.1]" in first.stdout, first.stdout[-1500:]
    lines = t.list_as_known(first, 885)
    # The anchor is the smallest identity (the one-label block); the ERROR is on the other.
    assert len(lines) == 1
    assert 'block: "Visit@pht000012:FHS ORIGINAL EXAM 10,FHS ORIGINAL EXAM 11"' in lines[0]
    assert E.phase5(t).returncode == 0
    t.write("visit.yaml", [b, a])
    res = E.phase5(t)
    assert res.returncode == 0, res.stdout[-2000:]


def test_a_spec_that_is_not_utf8_is_a_finding_not_a_crash_through_main(tmp_path):
    """Review 4 A D3: invalid UTF-8 crashed Phase 5 with a traceback from yaml_parse_error."""
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [E.visit_block("pht000012", "phv00001559", "FHS ORIGINAL EXAM 10")])
    bad = t.write("afib.yaml", [E.fixture_block("fhs_afib_b0.yaml")])
    bad.write_bytes(bad.read_bytes() + b"\xff\xfe\n")
    res = E.phase5(t)
    assert res.returncode == 1 and "Traceback" not in res.stderr, res.stderr[-1500:]
    assert "[5.0] Could not parse afib.yaml" in res.stdout, res.stdout[-1500:]
    for script in ("validate_dbgap_crossref.py", "validate_semantic.py",
                   "check_status_semantic.py", "check_value_semantic.py"):
        r = E.phase3(t, script)
        assert "Traceback" not in r.stderr, (script, r.stderr[-1500:])
    r = E.phase3(t, "validate_dbgap_crossref.py")
    assert r.returncode == 1 and "Cannot parse YAML" in r.stdout
    for script in ("check_cross_file_pht_consistency.py", "check_cross_file_duplicates.py",
                   "check_cross_block_consistency.py", "validate_yaml_structure.py"):
        r = t.run(f"phase-1/{script}", "--cohort", "FHS")
        assert "Traceback" not in r.stderr, (script, r.stderr[-1500:])
    r = t.run("phase-1/validate_yaml_structure.py", "--cohort", "FHS")
    assert r.returncode == 1 and "Failed to parse YAML" in r.stdout
    r = t.run("phase-2/check_phv_dedup.py", "--cohort", "FHS")
    assert r.returncode != 0 and "Traceback" not in r.stderr, r.stderr[-1500:]


def test_prune_and_update_together_are_refused_before_anything_is_written(tmp_path):
    """Review 4 A D2: with both set, update wrote the baseline and the summary said "nothing
    written". run_all refuses before any phase; a component refuses in the known-issue step."""
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [E.visit_block("pht000012", "phv00001559", "FHS ORIGINAL EXAM 10")])
    t.baseline.write_text('{"warnings": {}}', encoding="utf-8")
    before = (t.ki.read_bytes(), t.baseline.read_bytes())
    env_both = {"HVLINT_PRUNE": "1", "HVLINT_UPDATE_BASELINE": "1"}
    import os
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith("HVLINT_")}
    env.update(env_both, HV_ROOT=str(t.root), HVLINT_KNOWN_ISSUES=str(t.ki),
               HVLINT_WARNING_BASELINE=str(t.baseline), PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(HVLINT / "run_all.py"), "--cohort", "FHS",
                          "--no-report", "--cache-dir", str(E.CACHE)], cwd=t.root, env=env,
                         capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 2 and "both HVLINT_PRUNE=1 and HVLINT_UPDATE_BASELINE=1" in res.stderr
    assert "Phase 1" not in res.stdout
    env["HVLINT_RUN_ALL"] = "1"
    comp = subprocess.run([sys.executable, str(HVLINT / "phase-5/validate_visit_structure.py"),
                           "--cohort", "FHS", "--cache-dir", str(E.CACHE)], cwd=t.root, env=env,
                          capture_output=True, text=True, encoding="utf-8")
    assert comp.returncode == 1 and "refusing to run with both" in comp.stdout, comp.stdout[-1500:]
    assert (t.ki.read_bytes(), t.baseline.read_bytes()) == before


# -- Review round 5: guards no test reached, each through the real main() -----------------------

def _cache_without(t: E.Tree, sub: str, *names: str) -> Path:
    """A copy of the committed cache with ``names`` removed. The tree gets the cohort manifests,
    which name the release a cache outside hv-lint/ is keyed by."""
    import shutil
    manifests = t.root / "hv_dataqc" / "cache_fetcher" / "manifests"
    if not manifests.is_dir():
        shutil.copytree(HVLINT.parent / "hv_dataqc" / "cache_fetcher" / "manifests", manifests)
    cache = t.tmp / sub
    shutil.copytree(E.CACHE, cache)
    for n in names:
        (cache / n).unlink()
    return cache


def test_114_refuses_to_run_without_the_aric_detail_index_through_main(tmp_path):
    """Review 5 A S2: with the refusal removed, 1.14 judged ARIC against no metadata and passed."""
    t = E.Tree(tmp_path, "ARIC")
    t.write("afib.yaml", [_relabel(E.fixture_block("aric_afib_atrfib31.yaml"),
                                   "ARIC EXAM 3", "ARIC EXAM 2")])
    full = t.run(P1, "--cohort", "ARIC", "--cache-dir", str(_cache_without(t, "a")))
    assert full.returncode == 1 and "[1.14]" in full.stdout, full.stdout[-1500:]
    cache = _cache_without(t, "b", "phs000280.v8_detail.json.gz")
    res = t.run(P1, "--cohort", "ARIC", "--cache-dir", str(cache))
    assert res.returncode == 1 and "1.14 DID NOT RUN" in res.stderr, res.stderr[-800:]
    assert "[1.14]" not in res.stdout


def test_114_refuses_to_run_without_the_mesa_tables_index_through_main(tmp_path):
    """The MESA arm reads table names; without them it would judge nothing and pass."""
    t = E.Tree(tmp_path, "MESA")
    t.write("hdl.yaml", [_labelled_mesa("MESA CLASSIC EXAM 1")])
    cache = _cache_without(t, "c", "phs000209.v13_tables.json.gz")
    res = t.run(P1, "--cohort", "MESA", "--cache-dir", str(cache))
    assert res.returncode == 1 and "1.14 DID NOT RUN" in res.stderr, res.stderr[-800:]
    # The remedy it names is runnable: the cache holds no data_dict files to default to.
    assert "--tables --cohort phs000209.v13 --source-dir" in res.stderr


def _spirometry_obs(b: dict) -> list:
    sd = b["class_derivations"]["MeasurementObservationSet"]["slot_derivations"]
    return sd["observations"]["class_derivations"]


def _obs_type(o: dict) -> str:
    return o["MeasurementObservation"]["slot_derivations"]["observation_type"]["value"]


def test_319_reports_an_empty_quantity_two_levels_down_through_main(tmp_path):
    """Review 5 A S2: the recursion into a nested class that is not wholly empty. The
    predicted-FVC observation also reads a filled variable (method_type), so only its Quantity
    -- Set > observation > Quantity -- reads nothing but pfvca4 (n = 0)."""
    t = E.Tree(tmp_path, "MESA")
    b = copy.deepcopy(E.fixture_block("mesa_spirometry_b0.yaml"))
    obs = _spirometry_obs(b)
    obs[:] = [o for o in obs if _obs_type(o) != "OMOP:3022891"]
    fvc = next(o for o in obs if _obs_type(o) == "OMOP:3002094")
    fvc["MeasurementObservation"]["slot_derivations"]["method_type"] = {
        "populated_from": "phv00083474"}
    t.write("spirometry.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = [x for x in t.suggested(res) if '"3.19"' in x]
    assert len(lines) == 1, lines
    assert ("nested MeasurementObservationSet.observations>MeasurementObservation"
            ".value_quantity>Quantity" in lines[0] and "pfvca4" in lines[0])


def test_319_a_value_class_with_no_value_slot_fails_through_main(tmp_path):
    """Review 5 A S1 / B S1: ARIC insulin_blood b3's value_quantity is commented out (#410), so
    every row of pht006444 emits an insulin observation with no value. It reads no value phv,
    so the empty-source arm cannot see it."""
    t = E.Tree(tmp_path, "ARIC")
    b = E.fixture_block("aric_insulin_blood_b3.yaml")
    t.write("insulin_blood.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = t.suggested(res)
    assert len(lines) == 1 and '"3.19"' in lines[0], lines
    assert 'block: "MeasurementObservation@pht006444:-"' in lines[0]
    assert "MeasurementObservation has no value" in lines[0]
    # Restored, the block passes.
    fixed = copy.deepcopy(b)
    fixed["class_derivations"]["MeasurementObservation"]["slot_derivations"]["value_quantity"] = {
        "class_derivations": [{"Quantity": {"populated_from": "pht006444", "slot_derivations": {
            "value_decimal": {"populated_from": "phv00296699"},
            "unit": {"value": "pmol/L"}}}}]}
    t.write("insulin_blood.yaml", [fixed])
    assert "[3.19]" not in E.phase3(t, "validate_semantic.py").stdout


def test_319_a_nested_observation_with_no_value_slot_fails_through_main(tmp_path):
    """A Set's observation with no value slot is reported on its own; the Set has values."""
    t = E.Tree(tmp_path, "MESA")
    b = copy.deepcopy(E.fixture_block("mesa_spirometry_b0.yaml"))
    obs = _spirometry_obs(b)
    obs[:] = [o for o in obs if _obs_type(o) not in ("OMOP:3002094", "OMOP:3022891")]
    del obs[0]["MeasurementObservation"]["slot_derivations"]["value_quantity"]
    t.write("spirometry.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = [x for x in t.suggested(res) if '"3.19"' in x]
    assert len(lines) == 1, lines
    assert ("nested MeasurementObservationSet.observations>MeasurementObservation has no value"
            in lines[0])


def test_319_no_value_arm_skips_classes_that_are_their_own_datum():
    """Person, Visit, ResearchStudy and Condition carry no value_* slot by design."""
    for cls in ("Person", "Visit", "ResearchStudy", "Condition"):
        block = {"class_derivations": {cls: {"populated_from": PHT, "slot_derivations": {
            "associated_participant": {"expr": "str({phv00000009})"}}}}}
        assert _empty_source(block, {"phv00000009": 10}) == [], cls
    # A literal is a value: a Quantity with value_decimal: 5 is not reported.
    assert _empty_source(_no_phv_block(None), {}) == []


def test_319_reports_an_empty_top_level_class_beside_a_filled_one():
    """Review 5 B N2: a block with two top-level classes, one reading only an empty variable."""
    block = {"class_derivations": {
        "Condition": {"populated_from": PHT, "slot_derivations": {
            "condition_status": {"populated_from": "phv00000001",
                                 "value_mappings": {"1": "PRESENT"}}}},
        "MeasurementObservation": {"populated_from": PHT, "slot_derivations": {
            "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": {
                "value_decimal": {"populated_from": "phv00000002"}}}}]}}},
    }}
    msgs = _empty_source(block, {"phv00000001": 0, "phv00000002": 40})
    assert len(msgs) == 1 and "of class Condition" in msgs[0], msgs
    assert _empty_source(block, {"phv00000001": 3, "phv00000002": 40}) == []


def _whi_mi_block(status_phv: str, vm: dict) -> dict:
    return {"class_derivations": {"Condition": {"populated_from": "pht003406", "slot_derivations": {
        "associated_participant": {
            "expr": 'uuid5("https://w3id.org/bdchm/Participant", str({phv00193046}) + ":WHI")'},
        "condition_concept": {"value": "MONDO:0005068"},
        "condition_status": {"populated_from": status_phv, "value_mappings": vm},
        "relationship_to_participant": {"value": "ONESELF"},
    }}}}


def test_318_gate_answered_yes_fewer_than_five_times_is_not_evidence_through_main(tmp_path):
    """Review 5 A S2, FOLLOWUP_MIN_COUNT in _detect_gate: WHI MICABGENZ ("For MI-CABG, enzyme
    levels at least 5X uln", n = 4) under MIPROCCABG (yes = 4) is in the gate band; 4 "yes"
    answers are noise, so its '0' -> ABSENT is not reported."""
    t = E.Tree(tmp_path, "WHI")
    t.write("my_inf.yaml", [_whi_mi_block("phv00193082", {"0": "ABSENT", "1": "PRESENT"})])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "[3.18]" not in res.stdout


def test_318_a_for_far_from_the_start_is_not_a_branch_item_through_main(tmp_path):
    """Review 5 A S2, the GATE_ITEM_RE anchor: JHS ANGINAMEDSAFU ("Did you take any medication
    for chest pain or angina in the past two weeks?") is asked of everyone; its count happens
    to sit in the band of ASPIRINMEDSAFU's "yes". Its "No" -> ABSENT is not a 3.18 finding."""
    t = E.Tree(tmp_path, "JHS")
    t.write("angina.yaml", [{"class_derivations": {"Condition": {
        "populated_from": "pht008725", "slot_derivations": {
            "associated_participant": {
                "expr": 'uuid5("https://w3id.org/bdchm/Participant", str({phv00400849}) + ":JHS")'},
            "condition_concept": {"value": "HP:0001681"},
            "condition_status": {"populated_from": "phv00400897",
                                 "value_mappings": {"1": "PRESENT", "2": "ABSENT"}},
            "relationship_to_participant": {"value": "ONESELF"},
        }}}}])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "[3.18]" not in res.stdout


def test_318_a_same_condition_sibling_outranks_a_gate_through_main(tmp_path):
    """Review 5 A S2, the precedence of signal (a) over (c): CHS DIABO38 ("FOR DIABETES", off a
    diet) matches both DIABET37 (same condition, counts) and the gate OFFDIT38. The finding keeps
    the sibling's evidence, and with it the fingerprint it had before gates were recognised."""
    t = E.Tree(tmp_path, "CHS")
    b = copy.deepcopy(E.fixture_block("chs_diabetes_diabf38.yaml"))
    _status(b)["populated_from"] = "phv00104260"
    t.write("diabetes.yaml", [b])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    assert "DIABO38" in res.stdout and "vs DIABET37 (phv00104107) yes=" in res.stdout
    assert "gate question" not in res.stdout


# -- Review round 5 B S4: findings that named whichever block was scanned first ----------------

def _two_label_block(pht: str, seed: str, value_phv: str, labels: tuple[str, str]) -> dict:
    case = (f"case(({{{seed}}} == 1, '{labels[0]}'), ({{{seed}}} == 2, '{labels[1]}'))")
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": pht, "slot_derivations": {
            "associated_participant": {
                "expr": f'uuid5("https://w3id.org/bdchm/Participant", str({{{seed}}}) + ":X")'},
            "associated_visit": {
                "expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":" + {case})'},
            "observation_type": {"value": "OMOP:3004249"},
            "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": {
                "value_decimal": {"populated_from": value_phv}, "unit": {"value": "1"}}}}]},
        }}}}


def test_18_overlap_names_the_smallest_identity_not_the_first_file_through_main(tmp_path):
    """b.yaml's block has the smaller identity, so the WARNING names it whatever sorts first;
    a new file sorting before it with the same labels does not re-key the row. d.yaml sorts
    after b.yaml with a larger identity, so naming the last block scanned also fails."""
    t = E.Tree(tmp_path, "COPDGene")
    p12, p23 = ("COPDGene P1", "COPDGene P2"), ("COPDGene P2", "COPDGene P3")
    t.write("a.yaml", [_two_label_block("pht002239", "phv00568800", "phv00568909", p12)])
    t.write("b.yaml", [_two_label_block("pht002239", "phv00568800", "phv00568901", p12)])
    t.write("c.yaml", [_two_label_block("pht002239", "phv00568800", "phv00568902", p23)])
    t.write("d.yaml", [_two_label_block("pht002239", "phv00568800", "phv00568908", p12)])
    first = t.run(P1, "--cohort", "COPDGene", mode="update")
    assert "in b.yaml block" in first.stdout, first.stdout[-1500:]
    t.write("0.yaml", [_two_label_block("pht002239", "phv00568800", "phv00568905", p12)])
    res = t.run(P1, "--cohort", "COPDGene")
    assert res.returncode == 0, res.stdout[-1500:]


def _drug_block(phv: str, concept: str, extra: str | None = None) -> dict:
    slots = {"drug_concept": {"expr": f"case(({{{phv}}} == 1, '{concept}'))"}}
    if extra:
        slots["exposure_status"] = {"populated_from": extra,
                                    "value_mappings": {"1": "PRESENT"}}
    return {"class_derivations": {"DrugExposure": {"populated_from": "pht000012",
                                                   "slot_derivations": slots}}}


def test_17_drug_duplicate_keeps_its_row_when_the_blocks_swap_through_main(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    a = _drug_block("phv00001339", "RXNORM:1", extra="phv00001340")
    b = _drug_block("phv00001339", "RXNORM:2")
    t.write("meds.yaml", [a, b])
    script = "phase-1/validate_yaml_structure.py"
    first = t.run(script, "--cohort", "FHS", mode="update")
    assert "[1.7]" in first.stdout, first.stdout[-1500:]
    t.write("meds.yaml", [b, a])
    res = t.run(script, "--cohort", "FHS")
    assert res.returncode == 0, res.stdout[-1500:]


def _status_block(phv: str, concept: str, extra: str | None = None) -> dict:
    slots = {"condition_concept": {"value": concept},
             "condition_status": {"populated_from": phv}}
    if extra:
        slots["condition_provenance"] = {"populated_from": extra}
    return {"class_derivations": {"Condition": {"populated_from": "pht000012",
                                                "slot_derivations": slots}}}


def test_28_phv_in_two_concepts_keeps_its_entry_when_the_blocks_swap_through_main(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    a = _status_block("phv00001339", "MONDO:0004981", extra="phv00001340")
    b = _status_block("phv00001339", "MONDO:0005068")
    t.write("x.yaml", [a, b])
    script = "phase-2/check_phv_dedup.py"
    first = t.run(script, "--cohort", "FHS")
    assert first.returncode == 1 and "[2.8]" in first.stdout, first.stdout[-1500:]
    lines = t.list_as_known(first, 885)
    assert len(lines) == 1 and 'block: "Condition@pht000012:phv00001339"' in lines[0], lines
    assert t.run(script, "--cohort", "FHS").returncode == 0
    t.write("x.yaml", [b, a])
    res = t.run(script, "--cohort", "FHS")
    assert res.returncode == 0, res.stdout[-1500:]


def test_a_join_added_to_a_listed_block_keeps_its_entry_through_main(tmp_path):
    """A join's keys say how rows are linked, not what the block reads: adding one (the WHI #500
    fix adds `joins: pht000998` to 96 blocks) must not re-key the block's entries. Its keys are
    not source variables for 3.19 either, so the empty block is still reported."""
    t = E.Tree(tmp_path, "CARDIA")
    b = E.fixture_block("cardia_hist_cor_bypg_b0.yaml")
    t.write("hist_cor_bypg.yaml", [b])
    first = E.phase3(t, "validate_semantic.py")
    lines = t.list_as_known(first, 884)
    assert len(lines) == 1 and '"3.19"' in lines[0], lines
    assert E.phase3(t, "validate_semantic.py").returncode == 0
    joined = copy.deepcopy(b)
    joined["class_derivations"]["Procedure"]["joins"] = {
        "pht001870": {"source_key": "phv00121257", "lookup_key": "phv00121382"}}
    t.write("hist_cor_bypg.yaml", [joined])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "[3.19]" in res.stdout and "known issue #884" in res.stdout
