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

import yaml

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
sys.path.insert(0, str(HVLINT))
import _e2e as E  # noqa: E402
import _known_issues as K  # noqa: E402

FHS_VISIT = E.visit_block("pht000012", "phv00001559", "FHS ORIGINAL EXAM 10")


def _fhs_tree(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [FHS_VISIT])
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b0.yaml")])
    return t


def _clean_block():
    """afib b0 seeded from shareid and reading its own table: no 5.11 / 3.5 finding."""
    b = copy.deepcopy(E.fixture_block("fhs_afib_b0.yaml"))
    slots = b["class_derivations"]["Condition"]["slot_derivations"]
    for s in ("associated_participant", "associated_visit"):
        slots[s]["expr"] = slots[s]["expr"].replace("phv00001558", "phv00001559")
    slots["condition_status"]["populated_from"] = "phv00001560"
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

    t.write("afib.yaml", [_clean_block(), E.fixture_block("fhs_afib_b0.yaml")])
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
    args = ("run_all.py", "--cohort", "FHS", "--skip", "phase1", "phase2", "phase3",
            "--no-report", "--cache-dir", str(E.CACHE))
    assert t.run(*args).returncode == 1
    pruned = t.run(*args, mode="prune", run_all=False)
    assert pruned.returncode == 0, pruned.stdout[-1500:]
    assert K.load_entries(t.ki) == [] and t.run(*args).returncode == 0


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
    assert E.phase5(t, mode="update").returncode == 0
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


def test_51_a_changed_age_multiplier_changes_the_fingerprint(tmp_path):
    """Review round 2 A D1: 5.1's message names the age expressions; with them unquoted the
    multiplier was masked, so `* 365` -> `* 12` kept the baselined fingerprint and passed."""
    t = E.Tree(tmp_path, "CHS")
    b1, b2 = E.fixture_block("chs_visit_b1.yaml"), E.fixture_block("chs_visit_b2.yaml")
    t.write("visit.yaml", [b1, b2])
    assert E.phase5(t, mode="update").returncode == 0          # record the 5.1 WARNING
    assert "5.1" in t.baseline.read_text(encoding="utf-8")
    assert E.phase5(t).returncode == 0
    t.write("visit.yaml", [b1, _set_age(b2, "12")])
    res = E.phase5(t)
    assert res.returncode == 1 and "new WARNING [5.1]" in res.stdout, res.stdout[-2000:]
    assert "* 12" in res.stdout


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
    assert t.run(script, "--cohort", "COPDGene", mode="update").returncode == 0
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
    shutil.copy(HVLINT / "known_issues.yaml", t.ki)
    return t


def _run_all(t, *skip: str):
    return ("run_all.py", "--cohort", t.cohort, "--skip", *skip, "--no-report",
            "--cache-dir", str(E.CACHE))


def _start_clean(t, args):
    assert t.run(*args, mode="update", run_all=False).returncode == 0
    clean = t.run(*args)
    assert clean.returncode == 0, clean.stdout[-2000:]
    return t.ki.read_text(encoding="utf-8"), t.baseline.read_text(encoding="utf-8")


def test_prune_refuses_when_a_partial_fix_leaves_a_new_warning(tmp_path):
    """One more idtype arm on FHS cig_smok b36 narrows its 5.2 finding ('2', '3', '72' -> '2',
    '72'). The old entry matches nothing, but the defect is still there under a new message:
    pruning it first would delete the entry and leave the run red on a line nobody re-adds."""
    t = _real_subset(tmp_path, "FHS", ["visit.yaml", "cig_smok.yaml"])
    args = _run_all(t, "phase2", "phase3")
    ki, bl = _start_clean(t, args)
    blocks = yaml.safe_load((t.dir / "cig_smok.yaml").read_text(encoding="utf-8"))
    v = blocks[36]["class_derivations"]["MeasurementObservation"]["slot_derivations"][
        "associated_visit"]
    v["expr"] = v["expr"].replace(
        "(True, 'FHS UNKNOWN VISIT')",
        "({phv00525297} == '3', 'FHS OFFSPRING EXAM 5'), (True, 'FHS UNKNOWN VISIT')")
    t.write("cig_smok.yaml", blocks)
    res = t.run(*args, mode="prune", run_all=False)
    assert res.returncode == 1 and "refusing to prune" in res.stdout, res.stdout[-3000:]
    assert "new WARNING [5.2]" in res.stdout
    assert t.ki.read_text(encoding="utf-8") == ki
    assert t.baseline.read_text(encoding="utf-8") == bl


def test_prune_refuses_when_a_cohort_did_not_run(tmp_path):
    """MESA's visit.yaml deleted: 5.0 fails the run, and 5.8's cohort-level row (MESA's detail
    index has no coll_interval) must survive the prune, not be read as fixed."""
    t = _real_subset(tmp_path, "MESA", ["visit.yaml", "hdl.yaml"])
    args = _run_all(t, "phase1", "phase2", "phase3")
    ki, bl = _start_clean(t, args)
    assert "MESA-ingest/ | cohort" in bl
    (t.dir / "visit.yaml").unlink()
    res = t.run(*args, mode="prune", run_all=False)
    assert res.returncode == 1 and "refusing to prune" in res.stdout, res.stdout[-3000:]
    assert t.ki.read_text(encoding="utf-8") == ki
    assert t.baseline.read_text(encoding="utf-8") == bl
