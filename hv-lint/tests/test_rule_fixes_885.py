"""Rule fixes from #885 part 2, each pinned on a known case from the 2026-10 review.

Blocks are copied verbatim from HV main 731984f5 into tests/fixtures/known_cases/, so a later
data fix does not change what these tests prove. dbGaP metadata comes from the committed cache.

Run: python -m pytest hv-lint/tests/test_rule_fixes_885.py
"""

import sys
from pathlib import Path

import pytest
import yaml

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-1", "phase-2", "phase-3", "phase-5"):
    sys.path.insert(0, str(HVLINT / sub) if sub else str(HVLINT))

import _expr  # noqa: E402
import _visit_ids  # noqa: E402
import check_cross_file_pht_consistency as c18  # noqa: E402
import check_status_semantic as css  # noqa: E402
import validate_dbgap_crossref as xref  # noqa: E402
import validate_semantic as vs  # noqa: E402
import validate_visit_structure as vvs  # noqa: E402
import validate_yaml_structure as vys  # noqa: E402

FIX = HVLINT / "tests" / "fixtures" / "known_cases"
CACHE = HVLINT / "dbgap-cache"
RELEASE = {"FHS": "phs000007.v35", "JHS": "phs000286.v7", "CHS": "phs000287.v7",
           "WHI": "phs000200.v12", "ARIC": "phs000280.v8", "MESA": "phs000209.v13"}


def case(name: str) -> dict:
    return yaml.safe_load((FIX / f"{name}.yaml").read_text(encoding="utf-8"))


_cache: dict = {}


def detail(cohort):
    if cohort not in _cache:
        _cache[cohort] = vs.load_detail_index(CACHE, RELEASE[cohort])
    return _cache[cohort]


def stats(cohort):
    key = ("stats", cohort)
    if key not in _cache:
        _cache[key] = css.load_stats_index(CACHE, RELEASE[cohort])
    return _cache[key]


def checks(findings, check=None):
    return [(f.check, f.severity) for f in findings if check is None or f.check == check]


# -- shared enumerator ---------------------------------------------------------------------------

def test_enumerator_composes_a_nested_case_inside_the_seed():
    """FHS visit.yaml blocks 3-9: a case() inside the seed, followed by ' EXAM n'."""
    expr = ("case(({phv00177928} in [0, 1, 7], uuid5(\"https://w3id.org/bdchm/Visit\", "
            "str({phv00177926}) + \":\" + case(({phv00177928} == 0, 'FHS ORIGINAL'), "
            "({phv00177928} == 1, 'FHS OFFSPRING'), (True, 'FHS UNKNOWN VISIT')) + ' EXAM 7')), "
            "(True, None))")
    vals = _visit_ids.enumerate_ids(expr)
    assert _visit_ids.labels(vals) == {"FHS ORIGINAL EXAM 7", "FHS OFFSPRING EXAM 7"}
    assert {s.phv for v in vals for s in v.seeds} == {"phv00177926"}
    assert [v.label for v in vals if v.fallback] == ["FHS UNKNOWN VISIT EXAM 7"]


def test_comparison_operands_are_never_labels():
    hbp = case("cardia_hypert_trt_hbp")
    labels = set()
    for site in vs.walk_slot_derivations(hbp):
        if site.slot_name == "associated_visit":
            labels |= _visit_ids.labels(_visit_ids.slot_ids(site.slot_def))
    assert labels and "HBP" not in labels


def test_every_id_expression_on_the_tree_parses():
    tree = HVLINT.parent / "priority_variables_transform"
    if not tree.is_dir():
        pytest.skip("no spec tree")
    bad = []
    for f in tree.glob("*-ingest/*.yaml"):
        for b in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            for site in vs.walk_slot_derivations(b):
                if site.slot_name in ("id", "associated_visit", "associated_participant") \
                        and "expr" in site.slot_def:
                    try:
                        _visit_ids.enumerate_ids(site.slot_def["expr"])
                    except _visit_ids.Unparsed as exc:
                        bad.append((f.name, str(exc)))
    assert bad == []


# -- 1.8 -----------------------------------------------------------------------------------------

def _refs(*named):
    out = []
    for i, (name, path) in enumerate(named):
        out += c18._extract_visit_refs(case(name), i, path)
    return out


def test_18_copdgene_phase_case_blocks_agree():
    refs = _refs(("copdgene_bdy_hgt_b0", "COPDGene-ingest/bdy_hgt.yaml"),
                 ("copdgene_bdy_hgt_b0", "COPDGene-ingest/other.yaml"))
    assert refs[0].labels == {"COPDGene P1", "COPDGene P2", "COPDGene P3", "COPDGene P3B"}
    assert c18.check_cross_file_pht_consistency(refs) == []


def test_18_mesa_potassium_exam_3_or_4_is_a_superset_not_a_conflict():
    pot = case("mesa_potassium_b0")
    exam4 = yaml.safe_load(yaml.safe_dump(pot))
    exam4["class_derivations"]["MeasurementObservation"]["slot_derivations"]["associated_visit"] = {
        "expr": 'uuid5("https://w3id.org/bdchm/Visit", str({phv00191190}) + ":MESA CLASSIC EXAM 4")'}
    refs = c18._extract_visit_refs(pot, 0, "MESA-ingest/potassium.yaml") + \
        c18._extract_visit_refs(exam4, 1, "MESA-ingest/other.yaml")
    assert c18.check_cross_file_pht_consistency(refs) == []


def test_18_fhs_single_label_against_its_table_exam():
    good = c18._extract_visit_refs(case("fhs_afib_b24"), 24, "FHS-ingest/afib.yaml")
    tables = {"pht000012": {"name": "ex0_10s", "description": ""}}
    assert c18.check_cross_file_pht_consistency(good, tables) == []
    wrong = {"pht000012": {"name": "ex0_9s", "description": ""}}
    assert checks(c18.check_cross_file_pht_consistency(good, wrong)) == [("1.8", "ERROR")]


def test_18_fhs_table_name_expectations():
    assert c18.expected_fhs_labels("ex0_7s", "Clinic Exam, Original Cohort Exams 1 - 7") == {
        f"FHS ORIGINAL EXAM {n}" for n in range(1, 8)}
    assert c18.expected_fhs_labels("l_cortisol_ex06_1b_0495s") == {
        "FHS OFFSPRING EXAM 6", "FHS OMNI 1 EXAM 1"}
    assert c18.expected_fhs_labels("vr_wkthru_ex32_0_0997s") is None


def test_18_partial_overlap_is_a_warning():
    a = c18.PhtVisitRef("pht1", frozenset({"P1", "P2"}), "x/a.yaml", 0, "Condition")
    b = c18.PhtVisitRef("pht1", frozenset({"P2", "P3"}), "x/b.yaml", 0, "Condition")
    assert checks(c18.check_cross_file_pht_consistency([a, b])) == [("1.8", "WARNING")]


# -- 1.2 -----------------------------------------------------------------------------------------

def test_12_blood_pressure_replicates_do_not_collide():
    blocks = [case("aric_blood_pressure_b0"), case("aric_blood_pressure_b1")]
    assert vys.check_duplicates(blocks, "ARIC-ingest/blood_pressure.yaml") == []


def test_12_drug_blocks_reading_different_variables_do_not_collide():
    blocks = [case("aric_hypert_trt_b10"), case("aric_hypert_trt_b11")]
    assert vys.check_duplicates(blocks, "ARIC-ingest/hypert_trt.yaml") == []


def test_12_same_records_twice_is_an_error():
    b = case("fhs_afib_b24")
    f = vys.check_duplicates([b, b], "FHS-ingest/afib.yaml")
    assert checks(f) == [("1.2", "ERROR")] and "byte-identical" in f[0].message


# -- 3.9 / 3.15 ----------------------------------------------------------------------------------

def test_39_label_keyed_jhs_block_is_not_data_loss():
    f = vs.check_value_mappings_completeness(
        case("jhs_afib_label_keyed"), 0, "JHS-ingest/afib.yaml", detail("JHS"), stats("JHS"))
    assert [x for x in f if x.severity in ("ERROR", "WARNING")] == []


def test_39_follow_up_no_is_not_asked_for():
    """CHS MIHOSP59: '0' = had an MI, not hospitalized. 3.9 must not ask for '0': ABSENT."""
    f = vs.check_value_mappings_completeness(
        case("chs_hist_mi_mihosp59"), 0, "CHS-ingest/hist_mi.yaml", detail("CHS"), stats("CHS"),
        css.DetailIndex.from_records(detail("CHS").records))
    assert [x for x in f if "'0'" in x.message] == []


def test_315_case_variant_key_never_matches():
    f = vs.check_phantom_codes(case("jhs_fam_stroke_b4"), 4, "JHS-ingest/fam_stroke.yaml",
                               detail("JHS"), stats("JHS"))
    errs = [x for x in f if x.severity == "ERROR"]
    assert len(errs) == 1 and "Don't know" in errs[0].message and "Don't Know" in errs[0].message


def test_39_walks_nested_value_concept():
    sites = [s.path for s, _pf, _vm in vs._vm_slots(case("whi_fam_income_b0"))]
    assert any(p.endswith("Quantity.value_concept") for p in sites)


# -- 3.4 / 3.5 -----------------------------------------------------------------------------------

def _xref(name, cohort):
    idx = xref.load_dbgap_index(CACHE, RELEASE[cohort])
    return xref.check_block(case(name), 0, f"{cohort}-ingest/{name}.yaml", idx)


def test_35_bare_reference_to_another_table_is_an_error():
    for name in ("fhs_afib_b0", "fhs_stroke_b21"):
        assert ("3.5", "ERROR") in checks(_xref(name, "FHS")), name


def test_35_dotted_reference_is_resolved_by_a_join():
    assert [x for x in _xref("fhs_albumin_bld_b0", "FHS") if x.check in ("3.4", "3.5")] == []


def test_35_correct_block_is_quiet():
    assert [x for x in _xref("fhs_afib_b24", "FHS") if x.check in ("3.4", "3.5")] == []


# -- Phase 2 -------------------------------------------------------------------------------------

def test_27_membership_tuple_is_not_a_case_result():
    expr = "case(({phv00000001} in ('1', '2'), 'PRESENT'), (True, 'ABSENT'))"
    assert _expr.case_result_literals(expr) == ["PRESENT", "ABSENT"]


def test_210_age_gated_on_own_status_is_guarded():
    assert _expr.guarded_by("None if str({phv00113376}) != '2' else float({phv00113379}) * 365",
                            "phv00113376")
    assert not _expr.guarded_by("float({phv00113379}) * 365", "phv00113376")


def test_24_case_without_default():
    assert _expr.outer_case_lacks_default("case(({phv00000001} == 1, 'OMOP:1'))")
    assert not _expr.outer_case_lacks_default("case(({phv00000001} == 1, 'X'), (True, 'Y'))")


# -- Phase 5 -------------------------------------------------------------------------------------

def _vb(i, pht, labels, age=None):
    return vvs.VisitBlock(i, None, set(labels), pht, True, None, age, None, set(), set(), True)


def _reg(*blocks):
    return vvs.VisitRegistry("X", "X-ingest/visit.yaml", list(blocks), set(),
                             set().union(*(b.visit_labels for b in blocks)), True)


def test_51_multi_table_visit_is_a_warning_same_table_an_error():
    multi = vvs.check_5_1_uniqueness(_reg(_vb(0, "pht1", {"E1"}, "a"), _vb(1, "pht2", {"E1"}, "b")))
    assert checks(multi) == [("5.1", "WARNING")]
    same = vvs.check_5_1_uniqueness(_reg(_vb(0, "pht1", {"E1"}), _vb(1, "pht1", {"E1"})))
    assert checks(same) == [("5.1", "ERROR")]


def test_52_fhs_visit_registry_reads_composed_labels():
    labels, dyn = vvs.extract_visit_labels_from_expr(
        "uuid5(\"https://w3id.org/bdchm/Visit\", str({phv00177926}) + \":\" + "
        "case(({phv00177928} == 1, 'FHS OFFSPRING'), (True, 'FHS UNKNOWN VISIT')) + ' EXAM 2')")
    assert dyn and labels == {"FHS OFFSPRING EXAM 2"}
