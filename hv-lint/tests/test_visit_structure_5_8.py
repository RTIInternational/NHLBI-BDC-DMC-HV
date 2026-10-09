"""Regression tests for Phase 5 check 5.8 (Collection Interval Mismatch).

9a2f9637 removed checks 5.5/5.7 (correctly -- both validated against a regex-guessed visit
cache) but swept up ``_COLLECTED_IN_RE`` and ``_PHASE_SUB_ALIASES`` in the same deletion, even
though both belong to check 5.8, an unrelated and still-active check. Nothing in the existing
suite called ``parse_coll_interval_phases``/``expand_ci_phases``/``check_5_8_collection_interval``,
so the resulting ``NameError`` shipped silently: Phase 5 runs as advisory in
``.github/workflows/hv_lint.yml`` (``exit 0``), so a crash there looked identical to a clean run.
Reproduced directly against COPDGene and FHS before the fix; both crashed.

These tests call the 5.8 code path directly so a future edit that touches these two names (or
anything else check 5.8 depends on) fails the suite instead of only failing silently on CI.

Run: python -m pytest hv-lint/tests/test_visit_structure_5_8.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase-5"))
import validate_visit_structure as vvs  # noqa: E402

# -- parse_coll_interval_phases / expand_ci_phases ----------------------------
# The two functions that reference _COLLECTED_IN_RE and _PHASE_SUB_ALIASES directly.
# A NameError here is exactly the crash this file guards against.


def test_parse_coll_interval_phases_reads_a_structured_string():
    assert vvs.parse_coll_interval_phases("Collected in: P1 P2 P3") == {"P1", "P2", "P3"}


def test_parse_coll_interval_phases_returns_none_for_unstructured_text():
    # FHS-style free-text date ranges are not "Collected in: ..." -- skip, don't guess.
    assert vvs.parse_coll_interval_phases("1971-1975") is None
    assert vvs.parse_coll_interval_phases("") is None


def test_expand_ci_phases_adds_the_copdgene_p3b_alias():
    # COPDGene's Phase 3B is a sub-visit dbGaP rolls into "Collected in: P3".
    assert vvs.expand_ci_phases({"P3"}) == {"P3", "P3B"}
    assert vvs.expand_ci_phases({"P1", "P2"}) == {"P1", "P2"}


# -- check_5_8_collection_interval --------------------------------------------
# End-to-end through the function CI actually calls, closest to the real crash.


def _write_transform_file(hv_root: Path, cohort: str, class_name: str, phv: str,
                           case_expr: str) -> Path:
    ingest = hv_root / "priority_variables_transform" / f"{cohort}-ingest"
    ingest.mkdir(parents=True, exist_ok=True)
    f = ingest / "drug.yaml"
    f.write_text(f"""\
- class_derivations:
    {class_name}:
      populated_from: pht000001
      slot_derivations:
        associated_visit:
          expr: '{case_expr}'
        value_string:
          populated_from: {phv}
""", encoding="utf-8")
    return f


def test_flags_a_visit_phase_the_phv_was_not_collected_at(tmp_path):
    phv = "phv00568929"
    case_expr = 'case((eq({phv00000002}, 1), "COPDGene P2"))'
    yaml_file = _write_transform_file(tmp_path, "COPDGene", "DrugExposure", phv, case_expr)
    detail_index = {phv: {"coll_interval": "Collected in: P3", "name": "currmedhighbp"}}

    findings = vvs.check_5_8_collection_interval([yaml_file], tmp_path, detail_index)

    assert len(findings) == 1
    assert findings[0].check == "5.8"
    assert findings[0].severity == "ERROR"  # DrugExposure is not a Condition class
    assert "P2" in findings[0].message
    assert "P3" in findings[0].message


def test_condition_class_mismatch_is_critical_not_error(tmp_path):
    phv = "phv00568929"
    case_expr = 'case((eq({phv00000002}, 1), "COPDGene P2"))'
    yaml_file = _write_transform_file(tmp_path, "COPDGene", "Condition", phv, case_expr)
    detail_index = {phv: {"coll_interval": "Collected in: P3", "name": "currmedhighbp"}}

    findings = vvs.check_5_8_collection_interval([yaml_file], tmp_path, detail_index)

    assert len(findings) == 1
    assert findings[0].severity == "CRITICAL"


def test_no_finding_when_the_phase_is_covered_directly(tmp_path):
    phv = "phv00568929"
    case_expr = 'case((eq({phv00000002}, 1), "COPDGene P3"))'
    yaml_file = _write_transform_file(tmp_path, "COPDGene", "DrugExposure", phv, case_expr)
    detail_index = {phv: {"coll_interval": "Collected in: P3", "name": "currmedhighbp"}}

    assert vvs.check_5_8_collection_interval([yaml_file], tmp_path, detail_index) == []


def test_no_finding_when_the_phase_is_covered_via_the_sub_phase_alias(tmp_path):
    # This is what the P3B alias exists for: dbGaP records COPDGene's P3B sub-visit
    # under the parent phase's "Collected in: P3".
    phv = "phv00568929"
    case_expr = 'case((eq({phv00000002}, 1), "COPDGene P3B"))'
    yaml_file = _write_transform_file(tmp_path, "COPDGene", "DrugExposure", phv, case_expr)
    detail_index = {phv: {"coll_interval": "Collected in: P3", "name": "currmedhighbp"}}

    assert vvs.check_5_8_collection_interval([yaml_file], tmp_path, detail_index) == []
