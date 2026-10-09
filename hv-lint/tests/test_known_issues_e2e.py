"""Each enforced component's real main(), through its own checks= set and the known-issue step.

A known case is listed, passes, fails when its entry is removed, survives a block inserted above
it, goes stale when fixed, and is pruned by one command (#885 part 4).

Run: python -m pytest hv-lint/tests/test_known_issues_e2e.py
"""

import copy
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
sys.path.insert(0, str(HVLINT))
sys.path.insert(0, str(HVLINT / "phase-5"))
import _e2e as E  # noqa: E402
import _known_issues as K  # noqa: E402
import validate_visit_structure as V  # noqa: E402

FHS_VISIT = E.visit_block("pht000012", "phv00001559", "FHS ORIGINAL EXAM 10")


def _fhs_tree(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [FHS_VISIT])
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b0.yaml")])
    return t


def _clean_block():
    """afib b0 seeded from shareid: no 5.11 finding. It still reads phv00001339 (another
    table's variable, a 3.5 the phase-5 tests do not run): a fix keeps the variable it fixes,
    and a block that stops reading it reads as REMOVED (block_removed_why)."""
    b = copy.deepcopy(E.fixture_block("fhs_afib_b0.yaml"))
    slots = b["class_derivations"]["Condition"]["slot_derivations"]
    for s in ("associated_participant", "associated_visit"):
        slots[s]["expr"] = slots[s]["expr"].replace("phv00001558", "phv00001559")
    return b


def _other_block():
    """A clean block of the same table reading its own variable: a different identity."""
    b = _clean_block()
    b["class_derivations"]["Condition"]["slot_derivations"]["condition_status"][
        "populated_from"] = "phv00001560"
    return b


def test_phase5_known_issue_lifecycle(tmp_path):
    t = _fhs_tree(tmp_path)
    first = E.phase5(t)
    assert first.returncode == 1 and "[5.11]" in first.stdout
    lines = t.list_as_known(first, 882)
    assert len(lines) == 1 and '"5.11"' in lines[0]
    assert E.phase5(t, mode="update").returncode == 0          # record the WARNING baseline

    listed = E.phase5(t)
    assert listed.returncode == 0, listed.stdout
    assert "known issue #882, defect" in listed.stdout

    t.ki.write_text("", encoding="utf-8")                        # entry removed -> that ERROR
    assert E.phase5(t).returncode == 1
    t.ki.write_text(lines[0] + "\n", encoding="utf-8")

    t.write("afib.yaml", [_other_block(), E.fixture_block("fhs_afib_b0.yaml")])
    shifted = E.phase5(t)                                       # block 0 -> 1: still listed
    assert shifted.returncode == 0, shifted.stdout

    t.write("afib.yaml", [_clean_block()])                      # the defect is fixed
    fixed = E.phase5(t)
    assert fixed.returncode == 1 and "stale known-issue entry" in fixed.stdout
    assert K.PRUNE_CMD in fixed.stdout

    assert E.phase5(t, mode="prune").returncode == 0
    assert K.load_entries(t.ki) == []
    assert E.phase5(t).returncode == 0


def test_phase5_prune_refuses_outside_run_all(tmp_path):
    t = _fhs_tree(tmp_path)
    t.list_as_known(E.phase5(t), 882)
    t.write("afib.yaml", [_clean_block()])
    before = t.ki.read_text(encoding="utf-8")
    res = E.phase5(t, mode="prune", run_all=False)
    assert res.returncode == 1 and "refusing to prune" in res.stdout
    assert t.ki.read_text(encoding="utf-8") == before


def test_phase5_missing_visit_yaml_fails(tmp_path):
    t = E.Tree(tmp_path, "MESA")
    t.write("potassium.yaml", [E.fixture_block("mesa_potassium_b0.yaml")])
    res = E.phase5(t)
    assert res.returncode == 1
    assert re.search(r"ERROR .*\[5\.0\] No visit.yaml found for cohort MESA", res.stdout)


def test_run_all_is_the_one_prune_command(tmp_path):
    """The command the stale-entry message prints works end to end (run_all sets the flag)."""
    t = _fhs_tree(tmp_path)
    t.list_as_known(E.phase5(t), 882)
    assert E.phase5(t, mode="update").returncode == 0
    t.write("afib.yaml", [_clean_block()])
    run = _runner(t, {"phase1": 0, "phase2": 0, "phase3": 0})   # the fixture has a 3.5
    assert run().returncode == 1
    pruned = run("prune")
    assert pruned.returncode == 0 and "Prune applied: 1 known-issue entry" in pruned.stdout, \
        pruned.stdout[-1500:]
    assert K.load_entries(t.ki) == [] and run().returncode == 0


def _fixed_afib_tree(tmp_path):
    """FHS afib b0's 5.11 ERRORs listed, then fixed: a prune would remove the entries."""
    t = _fhs_tree(tmp_path)
    t.list_as_known(E.phase5(t), 882)
    assert E.phase5(t, mode="update").returncode == 0
    t.write("afib.yaml", [_clean_block()])
    return t


def _files(t):
    return t.ki.read_text(encoding="utf-8"), t.baseline.read_text(encoding="utf-8")


def test_prune_refuses_when_a_phase_fails_outside_the_known_issue_step(tmp_path):
    """Review round 3 B D1: the "phase(s) failed" refusal alone. Phase 1 fails as yamllint or a
    crash would (no finding, nothing staged); Phase 5 passes and stages a clean prune. Only
    run_all's own check of the phase exit codes stands between that stage and a write."""
    t = _fixed_afib_tree(tmp_path)
    before = _files(t)
    res = E.run_all_stubbed(t, {"phase1": 1, "phase2": 0, "phase3": 0}, mode="prune")
    assert res.returncode == 1, res.stdout[-1500:]
    assert "Prune REFUSED, nothing written: 1 phase(s) failed (phase1)" in res.stdout
    assert "refusing to prune" not in res.stdout              # no component refused
    assert _files(t) == before


def test_prune_refuses_a_staged_refusal_when_every_phase_passes(tmp_path):
    """Review round 3 B D1: apply_staged_prune's refusal alone. At --fail-on critical an
    unlisted ERROR does not fail Phase 5, so every phase passes; the component's staged refusal
    is what keeps the fixed entries from being removed while another ERROR is unlisted."""
    t = _fixed_afib_tree(tmp_path)
    t.write("afib2.yaml", [E.fixture_block("fhs_afib_b0.yaml")])     # a new, unlisted 5.11
    before = _files(t)
    res = E.run_all_stubbed(t, {"phase1": 0, "phase2": 0, "phase3": 0}, "--fail-on",
                            "critical", mode="prune")
    assert "All phases passed." in res.stdout, res.stdout[-1500:]
    assert res.returncode == 1 and "Prune REFUSED, nothing written" in res.stdout
    assert "refusing to prune" in res.stdout
    assert _files(t) == before


def test_prune_refuses_a_run_with_a_skipped_phase(tmp_path):
    """Review round 3 A M3: a skipped phase proved nothing fixed, so a prune from that run
    refuses, even when the phases that did run are clean."""
    t = _fhs_tree(tmp_path)
    t.list_as_known(E.phase5(t), 882)
    assert E.phase5(t, mode="update").returncode == 0
    t.write("afib.yaml", [_clean_block()])
    before = t.ki.read_text(encoding="utf-8"), t.baseline.read_text(encoding="utf-8")
    args = _run_all(t, "phase1", "phase2", "phase3")
    res = t.run(*args, mode="prune", run_all=False)
    assert res.returncode == 1, res.stdout[-1500:]
    assert "Prune REFUSED" in res.stdout and "skipped (phase1, phase2, phase3)" in res.stdout
    assert "phase(s) failed" not in res.stdout                  # the skip alone refused it
    assert (t.ki.read_text(encoding="utf-8"), t.baseline.read_text(encoding="utf-8")) == before


def test_phase5_new_warning_fails_even_when_another_is_fixed(tmp_path):
    """Fix one 5.2 WARNING and add another: the WARNING count is unchanged, CI still fails."""
    t = _fhs_tree(tmp_path)
    a, b = _clean_block(), _clean_block()
    for blk, label in ((a, "FHS OFFSPRING EXAM 6-7"), (b, "FHS ORIGINAL EXAM 10")):
        v = blk["class_derivations"]["Condition"]["slot_derivations"]["associated_visit"]
        v["expr"] = v["expr"].replace("FHS ORIGINAL EXAM 10", label)
    b["class_derivations"]["Condition"]["slot_derivations"]["condition_status"][
        "populated_from"] = "phv00001561"
    t.write("afib.yaml", [a, b])
    assert E.seed_baseline(t, lambda **kw: E.phase5(t, **kw)).returncode == 1   # new [5.2]
    assert "[5.2]" in E.phase5(t).stdout and E.phase5(t).returncode == 0
    for blk, old, new in ((a, "EXAM 6-7", "EXAM 10"), (b, "ORIGINAL EXAM 10", "ORIGNAL EXAM 10")):
        v = blk["class_derivations"]["Condition"]["slot_derivations"]["associated_visit"]
        v["expr"] = v["expr"].replace(old, new)
    t.write("afib.yaml", [a, b])
    res = E.phase5(t)
    assert res.returncode == 1
    assert "new WARNING [5.2]" in res.stdout and "is fixed" in res.stdout


def _phase3_cycle(tmp_path, cohort, fixture, script, rule, fixed_block):
    t = E.Tree(tmp_path, cohort)
    t.write("x.yaml", [E.fixture_block(fixture)])
    first = E.phase3(t, script)
    assert first.returncode == 1 and f"[{rule}]" in first.stdout, first.stdout
    t.list_as_known(first, 885)
    assert E.phase3(t, script, mode="update").returncode == 0
    assert E.phase3(t, script).returncode == 0
    t.write("x.yaml", [fixed_block])
    stale = E.phase3(t, script)
    assert stale.returncode == 1 and "stale known-issue entry" in stale.stdout, stale.stdout
    assert E.phase3(t, script, mode="prune").returncode == 0
    assert K.load_entries(t.ki) == []


def test_crossref_35_is_enforced_through_main(tmp_path):
    b = E.fixture_block("mesa_potassium_b0.yaml")
    fixed = copy.deepcopy(b)
    del fixed["class_derivations"]["MeasurementObservation"]["slot_derivations"][
        "age_at_observation"]
    _phase3_cycle(tmp_path, "MESA", "mesa_potassium_b0.yaml", "validate_dbgap_crossref.py",
                  "3.5", fixed)


def test_semantic_315_is_enforced_through_main(tmp_path):
    b = E.fixture_block("jhs_fam_stroke_b4.yaml")
    fixed = copy.deepcopy(b)
    vm = fixed["class_derivations"]["Condition"]["slot_derivations"]["condition_status"][
        "value_mappings"]
    vm["Don't Know"] = vm.pop("Don't know")
    _phase3_cycle(tmp_path, "JHS", "jhs_fam_stroke_b4.yaml", "validate_semantic.py", "3.15",
                  fixed)


def test_status_semantic_317_is_enforced_through_main(tmp_path):
    b = E.fixture_block("aric_carotid_plaque_b3.yaml")
    fixed = copy.deepcopy(b)
    fixed["class_derivations"]["Condition"]["slot_derivations"]["condition_status"][
        "value_mappings"] = {"0": "PRESENT", "1": "ABSENT"}
    _phase3_cycle(tmp_path, "ARIC", "aric_carotid_plaque_b3.yaml", "check_status_semantic.py",
                  "3.17", fixed)


def _cache_without(tree, suffix: str, name: str = "cache") -> Path:
    """A copy of the committed cache minus every ``*<suffix>`` file, with the release manifests
    beside it so the cohort still resolves to its declared release."""
    manifests = HVLINT.parent / "hv_dataqc" / "cache_fetcher" / "manifests"
    shutil.copytree(manifests, tree.root / "hv_dataqc" / "cache_fetcher" / "manifests",
                    dirs_exist_ok=True)
    cache = tree.root / "hv-lint" / name
    cache.mkdir(parents=True)
    for f in E.CACHE.iterdir():
        if f.is_file() and not f.name.endswith(suffix):
            (cache / f.name).write_bytes(f.read_bytes())
    return cache


def test_missing_stats_index_fails_both_status_components(tmp_path):
    """A block that passes with the full cache fails when only the value-count index is gone."""
    t = E.Tree(tmp_path, "ARIC")
    clean = E.fixture_block("aric_carotid_plaque_b3.yaml")
    clean["class_derivations"]["Condition"]["slot_derivations"]["condition_status"][
        "value_mappings"] = {"0": "PRESENT", "1": "ABSENT"}
    t.write("x.yaml", [clean])
    cache = _cache_without(t, "_stats.json.gz")
    for script in ("check_status_semantic.py", "validate_semantic.py"):
        assert E.phase3(t, script, mode="update").returncode == 0, script
        assert E.phase3(t, script).returncode == 0, script
        res = t.run(f"phase-3/{script}", "--cohort", "ARIC", "--cache-dir", str(cache),
                    "--fail-on", "error")
        assert res.returncode != 0, (script, res.stdout[-800:])
        assert "_stats.json.gz" in res.stdout + res.stderr, script


def test_missing_detail_index_fails_the_status_component(tmp_path):
    """Review round 1 B 9e: the cohort's files were skipped with no finding."""
    t = E.Tree(tmp_path, "ARIC")
    t.write("x.yaml", [E.fixture_block("aric_carotid_plaque_b3.yaml")])
    cache = _cache_without(t, "_detail.json.gz")
    res = t.run("phase-3/check_status_semantic.py", "--cohort", "ARIC", "--cache-dir", str(cache),
                "--fail-on", "error")
    assert res.returncode == 1 and "_detail.json.gz for ARIC" in res.stderr


def test_file_run_scopes_entries_and_refuses_an_update(tmp_path):
    """A --file run checks one file: other files' entries are not stale, and no rewrite runs."""
    t = E.Tree(tmp_path, "FHS")
    dup = E.fixture_block("fhs_afib_b0.yaml")
    t.write("a.yaml", [dup, dup])                                # 1.2: same block twice
    t.write("b.yaml", [_clean_block()])
    script = "phase-1/validate_yaml_structure.py"
    first = t.run(script, "--cohort", "FHS")
    assert first.returncode == 1 and "[1.2]" in first.stdout
    t.list_as_known(first, 872)
    assert t.run(script, "--cohort", "FHS").returncode == 0
    b_only = t.run(script, "--file", str(t.dir / "b.yaml"))
    assert b_only.returncode == 0, b_only.stdout
    refused = t.run(script, "--file", str(t.dir / "b.yaml"), mode="update")
    assert refused.returncode == 1 and "refusing to update on a --file run" in refused.stdout
    assert not t.baseline.exists() or json.loads(t.baseline.read_text())["warnings"] == {}


def test_12_swapping_a_same_file_duplicate_pair_keeps_its_entry(tmp_path):
    """Review round 3 A M2: 1.2 reported the pair on whichever block came second, so swapping
    two blocks that differ (CHS diabetes b5/b6: provenance, and b6 also reads phv00101793)
    re-keyed the finding and left its entry stale."""
    t = E.Tree(tmp_path, "CHS")
    b5, b6 = E.fixture_block("chs_diabetes_b5.yaml"), E.fixture_block("chs_diabetes_b6.yaml")
    t.write("diabetes.yaml", [b5, b6])
    script = "phase-1/validate_yaml_structure.py"
    first = t.run(script, "--cohort", "CHS")
    assert first.returncode == 1 and "[1.2]" in first.stdout, first.stdout[-2000:]
    assert len(t.list_as_known(first, 872)) == 1
    assert t.run(script, "--cohort", "CHS").returncode == 0
    t.write("diabetes.yaml", [b6, b5])
    swapped = t.run(script, "--cohort", "CHS")
    assert swapped.returncode == 0, swapped.stdout[-2000:]


def _labelled(phv: str, label: str) -> dict:
    seed = "phv00084441"
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": "pht001116", "slot_derivations": {
            "associated_participant": {
                "expr": f'uuid5("https://w3id.org/bdchm/Participant", str({{{seed}}}) + ":MESA")'},
            "associated_visit": {
                "expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":{label}")'},
            "observation_type": {"value": "OMOP:4041720"},
            "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": {
                "value_decimal": {"populated_from": phv}, "unit": {"value": "mg/dL"}}}}]},
        }}}}


def test_18_copy_paste_label_fails_phase1_through_main(tmp_path):
    """Review round 1 F1: one block relabelled on a single-exam MESA table must fail CI."""
    t = E.Tree(tmp_path, "MESA")
    good = [_labelled(f"phv0008497{i}", "MESA CLASSIC EXAM 1") for i in range(6)]
    t.write("hdl.yaml", good)
    script = "phase-1/check_cross_file_pht_consistency.py"
    assert t.run(script, "--cohort", "MESA").returncode == 0
    t.write("hdl.yaml", good[:5] + [_labelled("phv00084975", "MESA CLASSIC EXAM 2")])
    res = t.run(script, "--cohort", "MESA")
    assert res.returncode == 1 and "likely a copy-paste visit label" in res.stdout


def test_18_copy_paste_label_on_a_four_block_table_fails_phase1_through_main(tmp_path):
    """Review round 2 A M1: MESA pht001205 has 4 single-label blocks, all 'MESA AORTIC CT EXAM 4'.
    cac_volume b42 relabelled 'MESA CLASSIC EXAM 4' (a mintable label, so 5.2 is silent) faces
    3 agreeing blocks; main's 1.8 flagged it and so must this one."""
    t = E.Tree(tmp_path, "MESA")
    vol = [E.fixture_block(f"mesa_cac_volume_b{i}.yaml") for i in (42, 43)]
    t.write("cac_score.yaml", [E.fixture_block(f"mesa_cac_score_b{i}.yaml") for i in (55, 56)])
    t.write("cac_volume.yaml", vol)
    script = "phase-1/check_cross_file_pht_consistency.py"
    assert t.run(script, "--cohort", "MESA").returncode == 0
    visit = vol[0]["class_derivations"]["MeasurementObservation"]["slot_derivations"][
        "associated_visit"]
    visit["expr"] = visit["expr"].replace("MESA AORTIC CT EXAM 4", "MESA CLASSIC EXAM 4")
    t.write("cac_volume.yaml", vol)
    res = t.run(script, "--cohort", "MESA")
    assert res.returncode == 1 and "[1.8]" in res.stdout and "pht001205" in res.stdout, \
        res.stdout[-2000:]
    assert "'MESA AORTIC CT EXAM 4'" in res.stdout and "likely a copy-paste" in res.stdout


def test_512_unparsed_id_expression_fails_ci_through_main(tmp_path):
    """An id expression the parser cannot read is a ratcheted WARNING, not a silent skip."""
    t = _fhs_tree(tmp_path)
    b = _clean_block()
    b["class_derivations"]["Condition"]["slot_derivations"]["associated_visit"]["expr"] = (
        "':A' if {phv00001559} == 1 else ':B'")
    t.write("afib.yaml", [b])
    res = E.phase5(t)
    assert res.returncode == 1 and "new WARNING [5.12]" in res.stdout, res.stdout[-2000:]


def test_reached_fallback_fails_ci_through_main(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [E.visit_block("pht012916", "phv00525296", "FHS OFFSPRING EXAM 5")])
    t.write("cig_smok.yaml", [E.fixture_block("fhs_cig_smok_b36.yaml")])
    res = E.phase5(t)
    assert res.returncode == 1 and "fallback label 'FHS UNKNOWN VISIT' has no Visit block" in \
        res.stdout


def _set_age(block: dict, mult: str) -> dict:
    b = copy.deepcopy(block)
    slots = b["class_derivations"]["Visit"]["slot_derivations"]
    for s in ("age_at_visit_start", "age_at_visit_end"):
        slots[s]["expr"] = slots[s]["expr"].replace("* 365", f"* {mult}")
    return b


def _cardia_y20(pht: str, seed: str, age: str | None) -> dict:
    b = E.visit_block(pht, seed, "CARDIA YEAR 20", cohort="CARDIA")
    if age:
        expr = f"None if str({{{age}}}) == 'M' else float({{{age}}}) * 365"
        b["class_derivations"]["Visit"]["slot_derivations"].update(
            age_at_visit_start={"expr": expr}, age_at_visit_end={"expr": expr})
    return b


@pytest.mark.parametrize("cohort", ["CHS", "CARDIA"])
def test_51_a_changed_age_multiplier_changes_the_fingerprint(tmp_path, cohort):
    """Review round 2 A D1: 5.1's message names the age expressions; with them unquoted the
    multiplier was masked, so `* 365` -> `* 12` kept the baselined fingerprint and passed.
    CARDIA (review round 3 B F1): YEAR 20's expression holds a quoted 'M', which closed a
    single-quoted run early and masked the multiplier after it."""
    t = E.Tree(tmp_path, cohort)
    if cohort == "CHS":
        b1, b2 = E.fixture_block("chs_visit_b1.yaml"), E.fixture_block("chs_visit_b2.yaml")
    else:
        b1 = _cardia_y20("pht003298", "phv00190551", None)
        b2 = _cardia_y20("pht001999", "phv00129484", "phv00129493")
    t.write("visit.yaml", [b1, b2])
    assert E.phase5(t, mode="update").returncode == 0          # record the 5.1 WARNING
    assert "5.1" in t.baseline.read_text(encoding="utf-8")
    assert E.phase5(t).returncode == 0
    t.write("visit.yaml", [b1, _set_age(b2, "12")])
    res = E.phase5(t)
    assert res.returncode == 1 and "new WARNING [5.1]" in res.stdout, res.stdout[-2000:]
    assert "* 12" in res.stdout


@pytest.mark.parametrize("cohort", ["CHS", "CARDIA"])
def test_51_reordering_visit_blocks_keeps_the_baseline(tmp_path, cohort):
    """Review round 3 A M1: 5.1 listed the tables in file order and put the WARNING on every
    table after the first in the file, so reversing visit.yaml re-keyed its baselined rows."""
    t = E.Tree(tmp_path, cohort)
    if cohort == "CHS":
        blocks = [E.fixture_block("chs_visit_b1.yaml"), E.fixture_block("chs_visit_b2.yaml")]
    else:
        blocks = [_cardia_y20("pht003298", "phv00190551", None),
                  _cardia_y20("pht001999", "phv00129484", "phv00129493"),
                  _cardia_y20("pht001851", "phv00120733", None)]
    t.write("visit.yaml", blocks)
    assert E.phase5(t, mode="update").returncode == 0
    assert "5.1" in t.baseline.read_text(encoding="utf-8")
    t.write("visit.yaml", blocks[::-1])
    res = E.phase5(t)
    assert res.returncode == 0, res.stdout[-2000:]


def test_51_no_age_expression_in_a_message_has_a_masked_multiplier():
    """Every quoting repr_age can produce keeps the expression's numbers in the fingerprint."""
    for expr in ("{phv00098799} * 365",
                 "None if str({phv00129493}) == 'M' else float({phv00129493}) * 365",
                 'case(({phv00297378} == "Y", {phv00297379} * 365))',
                 "case(({a} == \"Y\", 1), ({b} == 'N', {c} * 365))"):
        key = K.message_key(f"Visit id 'X 1' emitted by 2 tables; age expressions: "
                            f"{V.repr_age(expr)}; no age")
        assert "* 365" in key, (expr, key)


def _phase_block(labels: list[str]) -> dict:
    b = copy.deepcopy(E.fixture_block("copdgene_asthma_b0.yaml"))
    slots = b["class_derivations"]["Condition"]["slot_derivations"]
    arms = ", ".join(f"({{phv00568798}} == '{i}', uuid5('https://w3id.org/bdchm/Visit', "
                     f"str({{phv00159568}}) + ':{lab}'))" for i, lab in enumerate(labels))
    slots["associated_visit"]["expr"] = f"case({arms}, (True, None))"
    return b


def test_18_overlap_label_change_changes_the_fingerprint(tmp_path):
    """Review round 2 A D2: the apostrophe in "block's" paired with the first label's opening
    quote, so the labels after it were read as unquoted and their exam numbers masked."""
    t = E.Tree(tmp_path, "COPDGene")
    a = _phase_block(["FHS OMNI 1 EXAM 1", "FHS OMNI 1 EXAM 2"])
    t.write("a.yaml", [a])
    t.write("b.yaml", [_phase_block(["FHS OMNI 1 EXAM 2", "FHS OMNI 1 EXAM 3"])])
    script = "phase-1/check_cross_file_pht_consistency.py"
    E.seed_baseline(t, lambda **kw: t.run(script, "--cohort", "COPDGene", **kw))
    assert t.run(script, "--cohort", "COPDGene").returncode == 0
    t.write("b.yaml", [_phase_block(["FHS OMNI 1 EXAM 2", "FHS OMNI 1 EXAM 4"])])
    res = t.run(script, "--cohort", "COPDGene")
    assert res.returncode == 1 and "new WARNING [1.8]" in res.stdout, res.stdout[-2000:]


def test_quoted_text_keeps_its_numbers_beside_an_apostrophe():
    key = K.message_key("pht1: this block's labels {'FHS OMNI 1 EXAM 4'} in 3 files")
    assert "'FHS OMNI 1 EXAM 4'" in key and "in # files" in key
    assert K.message_key("label 'Don't know 2' seen 5 times") == "label 'Don't know 2' seen # times"


# -- a prune writes only after a clean run (review round 2 A D3) --------------------------------

def _real_subset(tmp_path, cohort: str, names: list[str]):
    """Real spec files of one cohort, the committed known issues, and a baseline recorded on
    exactly this subset, so the run starts clean."""
    t = E.Tree(tmp_path, cohort)
    for name in names:
        shutil.copy(HVLINT.parent / "priority_variables_transform" / f"{cohort}-ingest" / name,
                    t.dir / name)
    # Entries for this cohort's other files would be stale here (a file not in the tree is a
    # deleted one), so only the copied files' entries are kept.
    keep = {f"file: {cohort}-ingest/{name}," for name in names}
    lines = (HVLINT / "known_issues.yaml").read_text(encoding="utf-8").splitlines()
    t.ki.write_text("".join(x + "\n" for x in lines
                            if f"file: {cohort}-ingest/" not in x or any(k in x for k in keep)),
                    encoding="utf-8")
    return t


def _run_all(t, *skip: str):
    return ("run_all.py", "--cohort", t.cohort, "--skip", *skip, "--no-report",
            "--cache-dir", str(E.CACHE))


def _runner(t, stubs: dict[str, int] | None = None):
    """run_all.py over every phase, Phases 1 and 2 stubbed (E.run_all_stubbed)."""
    stubs = {"phase1": 0, "phase2": 0} if stubs is None else stubs
    return lambda mode=None, extra_env=None: E.run_all_stubbed(t, stubs, mode=mode,
                                                               extra_env=extra_env)


def _start_clean(t, run):
    E.seed_baseline(t, lambda **kw: run(**kw))
    clean = run()
    assert clean.returncode == 0, clean.stdout[-2000:]
    return t.ki.read_text(encoding="utf-8"), t.baseline.read_text(encoding="utf-8")


def test_prune_refuses_when_a_partial_fix_leaves_a_new_warning(tmp_path):
    """One more idtype arm on FHS cig_smok b36 narrows its 5.2 finding ('2', '3', '72' -> '2',
    '72'). The old entry matches nothing, but the defect is still there under a new message:
    pruning it first would delete the entry and leave the run red on a line nobody re-adds.
    b36 is the frozen fixture block, not the live one: the live block gates every arm to a
    cohort that has the exam (#888), so it raises no 5.2 to narrow."""
    t = _real_subset(tmp_path, "FHS", ["visit.yaml", "cig_smok.yaml"])
    blocks = yaml.safe_load((t.dir / "cig_smok.yaml").read_text(encoding="utf-8"))
    blocks[36] = E.fixture_block("fhs_cig_smok_b36.yaml")
    t.write("cig_smok.yaml", blocks)
    run = _runner(t)
    ki, bl = _start_clean(t, run)
    assert ("phv00525302 | MeasurementObservation.associated_visit fallback label 'FHS UNKNOWN "
            "VISIT' has no Visit block, and observed codes reach it: phv00525297 '2' (# rows), "
            "'3' (# rows), '72' (# rows)") in bl, bl[-2000:]
    blocks = yaml.safe_load((t.dir / "cig_smok.yaml").read_text(encoding="utf-8"))
    v = blocks[36]["class_derivations"]["MeasurementObservation"]["slot_derivations"][
        "associated_visit"]
    v["expr"] = v["expr"].replace(
        "(True, 'FHS UNKNOWN VISIT')",
        "({phv00525297} == '3', 'FHS OFFSPRING EXAM 5'), (True, 'FHS UNKNOWN VISIT')")
    t.write("cig_smok.yaml", blocks)
    res = run("prune")
    assert res.returncode == 1 and "refusing to prune" in res.stdout, res.stdout[-3000:]
    assert "new WARNING [5.2]" in res.stdout
    assert t.ki.read_text(encoding="utf-8") == ki
    assert t.baseline.read_text(encoding="utf-8") == bl


def test_prune_refuses_when_a_cohort_did_not_run(tmp_path):
    """MESA's visit.yaml deleted: 5.0 fails the run, and 5.8's cohort-level row (MESA's detail
    index has no coll_interval) must survive the prune, not be read as fixed."""
    t = _real_subset(tmp_path, "MESA", ["visit.yaml", "hdl.yaml"])
    run = _runner(t)
    ki, bl = _start_clean(t, run)
    assert "MESA-ingest/ | cohort" in bl
    (t.dir / "visit.yaml").unlink()
    res = run("prune")
    assert res.returncode == 1 and "refusing to prune" in res.stdout, res.stdout[-3000:]
    assert t.ki.read_text(encoding="utf-8") == ki
    assert t.baseline.read_text(encoding="utf-8") == bl


def _break(t, name: str) -> None:
    with open(t.dir / name, "a", encoding="utf-8") as fh:
        fh.write("x: [unclosed\n")


@pytest.mark.parametrize("fail_on", ["error", "critical"])
def test_phase5_reports_an_unparseable_spec_as_unrun(tmp_path, fail_on):
    """Review round 3 A M3: Phase 5 read an unparseable spec as empty and reported nothing, so
    its 5.2 findings vanished and a Phase 5-only prune removed their entries."""
    t = _real_subset(tmp_path, "FHS", ["visit.yaml", "cig_smok.yaml"])
    _break(t, "cig_smok.yaml")
    res = t.run("phase-5/validate_visit_structure.py", "--cohort", "FHS", "--cache-dir",
                str(E.CACHE), "--fail-on", fail_on)
    assert res.returncode == 1, res.stdout[-2000:]
    assert re.search(r"ERROR .*\[5\.0\] Could not parse cig_smok\.yaml", res.stdout), \
        res.stdout[-2000:]


@pytest.mark.parametrize("how", ["skip", "every-phase"])
def test_prune_refuses_an_unparseable_spec(tmp_path, how):
    """Review round 3 A M3, as reported (`skip`): FHS cig_smok.yaml unparseable, then
    `HVLINT_PRUNE=1 run_all.py --cohort FHS --skip phase1 phase2 phase3` pruned its 7 entries.
    `every-phase` runs Phase 5 for real with Phases 1-3 stubbed as passing, so Phase 5's own
    5.0 is what refuses it."""
    t = _real_subset(tmp_path, "FHS", ["visit.yaml", "cig_smok.yaml"])
    if how == "skip":
        args = _run_all(t, "phase1", "phase2", "phase3")
        run = lambda mode=None, extra_env=None: t.run(*args, mode=mode, run_all=False,  # noqa: E731
                                                      extra_env=extra_env)
    else:
        run = _runner(t, {"phase1": 0, "phase2": 0, "phase3": 0})
    ki, bl = _start_clean(t, run)
    assert "cig_smok.yaml" in ki
    _break(t, "cig_smok.yaml")
    res = run("prune")
    assert res.returncode == 1 and "Prune REFUSED" in res.stdout, res.stdout[-3000:]
    assert "[5.0] Could not parse cig_smok.yaml" in res.stdout
    assert t.ki.read_text(encoding="utf-8") == ki
    assert t.baseline.read_text(encoding="utf-8") == bl


def test_unevaluable_fallback_reach_fails_ci_through_main(tmp_path):
    """Review round 2 B F4: a fallback label with no Visit block whose reach cannot be evaluated
    (here a `>` test the evaluator does not read) is a 5.2 WARNING, never a silent skip."""
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [E.visit_block("pht012916", "phv00525296", "FHS OFFSPRING EXAM 5")])
    b = E.fixture_block("fhs_cig_smok_b36.yaml")
    v = b["class_derivations"]["MeasurementObservation"]["slot_derivations"]["associated_visit"]
    v["expr"] = v["expr"].replace("{phv00525297} == '7'", "{phv00525297} > '6'")
    t.write("cig_smok.yaml", [b])
    res = E.phase5(t)
    assert res.returncode == 1 and "new WARNING [5.2]" in res.stdout, res.stdout[-2000:]
    assert "whether observed codes reach it cannot be evaluated" in res.stdout


# -- a deleted spec is lost data, not a fix (gate review B3) ------------------------------------

def test_deleting_a_spec_with_an_entry_does_not_go_green_through_plain_prune(tmp_path):
    """Delete a spec file that carries a known issue. The entry is reported as REMOVED, and the
    command the old message printed (a plain prune) refuses instead of turning the deletion
    green. Only the acknowledged prune removes it, and its summary names the entry."""
    t = _fhs_tree(tmp_path)
    t.list_as_known(E.phase5(t), 882)
    assert E.phase5(t, mode="update").returncode == 0
    run = _runner(t, {"phase1": 0, "phase2": 0, "phase3": 0})
    assert run().returncode == 0
    (t.dir / "afib.yaml").unlink()
    before = _files(t)

    red = run()
    assert red.returncode == 1
    assert "file removed: FHS-ingest/afib.yaml" in red.stdout and "not a fix" in red.stdout
    assert "the issue is fixed here" not in red.stdout

    plain = run("prune")
    assert plain.returncode == 1, plain.stdout[-2000:]
    assert "Prune REFUSED, nothing written" in plain.stdout and "REMOVED" in plain.stdout
    assert _files(t) == before
    assert run().returncode == 1                                # still red

    acked = E.run_all_stubbed(t, {"phase1": 0, "phase2": 0, "phase3": 0}, mode="prune",
                              extra_env={K.PRUNE_REMOVED_ENV: "1"})
    assert acked.returncode == 0, acked.stdout[-2000:]
    assert "REMOVED, not fixed (HVLINT_PRUNE_REMOVED=1): 1 entry/row(s)" in acked.stdout
    assert "FHS-ingest/afib.yaml" in acked.stdout.split("REMOVED, not fixed")[1]
    logged = yaml.safe_load(t.ki.with_name("removed.yaml").read_text(encoding="utf-8"))
    assert [(x["rule"], x["file"], x["issue"]) for x in logged] == [
        ("5.11", "FHS-ingest/afib.yaml", 882)]
    assert "appended to hv-lint/removed.yaml" in acked.stdout
    assert K.load_entries(t.ki) == [] and run().returncode == 0


# -- the baseline update never accepts a lost or unlinked record (gate review B4) ---------------

def test_update_refuses_a_new_unlinked_visit_label_through_main(tmp_path):
    """A label visit.yaml does not define links every record of the block to nothing (5.2).
    HVLINT_UPDATE_BASELINE used to accept it as one baseline row; now it refuses, writes no row,
    and prints the known_issues.yaml line that accepts it with an issue number instead."""
    t = E.Tree(tmp_path, "MESA")
    t.write("visit.yaml", [E.visit_block("pht001116", "phv00084441", "MESA CLASSIC EXAM 1",
                                         cohort="MESA")])
    t.write("hdl.yaml", [_labelled("phv00084970", "MESA CLASSIC EXAM 1")])
    assert E.phase5(t, mode="update").returncode == 0
    clean = E.phase5(t)
    assert clean.returncode == 0, clean.stdout[-2000:]
    before = t.baseline.read_text(encoding="utf-8")

    t.write("hdl.yaml", [_labelled("phv00084970", "MESA CLASSIC EXAM 55")])
    red = E.phase5(t)
    assert red.returncode == 1 and "new WARNING [5.2]" in red.stdout, red.stdout[-2000:]
    assert K.UPDATE_CMD not in red.stdout.split("new WARNING [5.2]")[1].splitlines()[0]

    upd = E.phase5(t, mode="update")
    assert upd.returncode == 1, upd.stdout[-2000:]
    assert "refusing to add a baseline row for new WARNING [5.2]" in upd.stdout
    assert t.baseline.read_text(encoding="utf-8") == before
    assert E.phase5(t).returncode == 1                          # still red

    lines = t.suggested(red)                   # printed at line start, ready to copy
    assert len(lines) == 1 and lines[0].startswith('- {rule: "5.2"')
    assert t.list_as_known(red, 999) and "issue: 999" in t.ki.read_text(encoding="utf-8")
    listed = E.phase5(t)
    assert listed.returncode == 0 and "known issue #999, defect" in listed.stdout, \
        listed.stdout[-2000:]
