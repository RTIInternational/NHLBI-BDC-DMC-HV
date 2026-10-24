"""Regression tests for the visit-label extractor used by checks 1.8 and 5.1.

Both checks compare the visit labels attached to one PHT across files, and both get those labels
from the one shared parser, ``hv-lint/_visit_ids.py`` (an ``ast`` enumerator that replaced the two
regex copies phase 1 and phase 5 each kept). The defect below was in those regex copies; the
tests pin that the shared parser does not repeat it.

**The defect.** The extractor looked for a case() branch whose result is a bare quoted string::

    ({phv} == 'P1', 'COPDGene P1')        <- matches

It had no pattern for a branch whose result is the whole identifier::

    ({phv} == 'P1', uuid5(<ns>, str({phv}) + ':COPDGene P1'))        <- matched nothing

With no match it fell through to its last resort -- "take every quoted string in the expression" --
which returns the DISCRIMINATOR CODES alongside the labels. A PHT then appears to carry twice the
labels it has, and 1.8/5.1 report a cross-file inconsistency that does not exist.

**This is not a generated-output problem.** COPDGene's shipped specs use the nested form in 48
``associated_visit`` blocks, so the fallback mis-parsed production's own files: ``bdy_hgt.yaml``
returned its four real labels plus ``P1``/``P2``/``P3``/``P3B``. That expression is pinned as a
frozen fixture; the shipped tree is checked only by invariants, so a curator's correct change to a
spec cannot fail this file.

Both nestings are in production and neither is going away -- FHS (448 blocks) and SPIROMICS (19)
write the label-in-case form, COPDGene (48) writes the nested one -- so the extractor has to read
both. The tests below pin each shape, including the two the fix could plausibly have broken.

Run: python -m pytest hv-lint/tests/test_visit_label_extraction.py
"""

import sys
from pathlib import Path

_HV_LINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HV_LINT))
sys.path.insert(0, str(_HV_LINT / "phase-1"))
sys.path.insert(0, str(_HV_LINT / "phase-5"))

import _visit_ids  # noqa: E402
import check_cross_file_pht_consistency as c18  # noqa: E402
import validate_visit_structure as vvs  # noqa: E402

_NS = "https://w3id.org/bdchm/Visit"

#: COPDGene's shape, and what the AI pipeline emits: the whole uuid5 inside each branch.
NESTED = (
    "case(({phv001} == 'VISIT_1', uuid5(\"%s\", str({phv002}) + ':SPIROMICS Visit 1')), "
    "({phv001} == 'VISIT_2', uuid5(\"%s\", str({phv002}) + ':SPIROMICS Visit 2')), (True, None))"
) % (_NS, _NS)

#: FHS's and SPIROMICS's shape: one uuid5 around a case() that returns the label.
LABEL_IN_CASE = (
    "uuid5(\"%s\", str({phv002}) + \":\" + case(({phv001} == 'VISIT_1', 'SPIROMICS Visit 1'), "
    "({phv001} == 'VISIT_2', 'SPIROMICS Visit 2'), (True, None)))"
) % _NS

_BOTH_LABELS = {"SPIROMICS Visit 1", "SPIROMICS Visit 2"}


# -- the defect itself --------------------------------------------------------


def test_check_1_8_reads_the_nested_form_without_returning_the_codes():
    """The bug: `VISIT_1` / `VISIT_2` are discriminator codes, never visit labels."""
    assert c18._extract_labels_from_expr(NESTED) == _BOTH_LABELS


def test_check_5_1_reads_the_nested_form_without_returning_the_codes():
    """Phase 5 carries its own copy of the extractor, so it needs its own test."""
    labels, is_dynamic = vvs.extract_visit_labels_from_expr(NESTED)
    assert labels == _BOTH_LABELS
    assert is_dynamic is True          # uuid5 present -- unchanged by the fix


def test_both_nestings_yield_the_same_labels():
    """The point of the check is cross-FILE comparison, and the two forms coexist in production.

    If one file writes a visit the nested way and another writes it the label-in-case way, they
    must compare equal -- otherwise the check reports an inconsistency created by spec style.
    """
    assert c18._extract_labels_from_expr(NESTED) == c18._extract_labels_from_expr(LABEL_IN_CASE)


def test_a_label_equal_to_its_code_is_not_swallowed():
    """The failure mode a naive fix would introduce.

    Filtering out anything that appears as a comparison operand would fix the symptom and delete
    the real label whenever a cohort names its visits after the codes -- which is the direction
    new cohorts are heading.
    """
    expr = (
        "case(({phv001} == 'V1', uuid5(\"%s\", str({phv002}) + ':V1')), "
        "({phv001} == 'V2', uuid5(\"%s\", str({phv002}) + ':V2')), (True, None))"
    ) % (_NS, _NS)
    assert c18._extract_labels_from_expr(expr) == {"V1", "V2"}


# -- shapes the fix must not disturb -----------------------------------------


def test_the_label_in_case_form_is_unchanged():
    assert c18._extract_labels_from_expr(LABEL_IN_CASE) == _BOTH_LABELS


def test_a_single_label_uuid5_is_unchanged():
    """LTRC's shape: one visit, no case() at all."""
    expr = 'uuid5("%s", str({phv00159568}) + ":LTRC Baseline")' % _NS
    assert c18._extract_labels_from_expr(expr) == {"LTRC Baseline"}


def test_a_case_with_a_real_trailing_suffix_is_unchanged():
    """FHS's shape: the case() supplies a prefix and a literal suffix follows it.

    This is what the suffix handling exists for, and the fix tightens the guard that decides
    whether a trailing string IS a suffix -- so it is the case most at risk.
    """
    expr = "case(({phv001} == 'A', 'FHS Offspring'), ({phv001} == 'B', 'FHS Gen3')) + ' Exam 1'"
    assert c18._extract_labels_from_expr(expr) == {"FHS Offspring Exam 1", "FHS Gen3 Exam 1"}


def test_the_nested_form_does_not_append_its_own_label_as_a_suffix():
    """The second half of the fix, pinned separately.

    A suffix keeps its leading colon (`':SPIROMICS Visit 1'`) where the captured label does not,
    so the original `s not in case_results` guard missed and produced
    `'SPIROMICS Visit 1:SPIROMICS Visit 1'`.
    """
    for label in c18._extract_labels_from_expr(NESTED):
        assert ":" not in label


# -- COPDGene's nested form, from a frozen copy -----------------------------------
#
# The reproduction case is a real expression, but it is pinned here as a FIXTURE: a test that read
# COPDGene-ingest/bdy_hgt.yaml and demanded exactly these four labels would fail a curator who
# correctly adds a fifth visit arm. The string is verbatim from that file's associated_visit as of
# this test's writing (whitespace folded); the shipped tree is checked by INVARIANT, below.

COPDGENE_BDY_HGT_VISIT = (
    "case(({phv00568798} == 'P1', uuid5('https://w3id.org/bdchm/Visit', str({phv00159568}) + "
    "':COPDGene P1')), ({phv00568798} == 'P2', uuid5('https://w3id.org/bdchm/Visit', "
    "str({phv00159568}) + ':COPDGene P2')), ({phv00568798} == 'P3', "
    "uuid5('https://w3id.org/bdchm/Visit', str({phv00159568}) + ':COPDGene P3')), "
    "({phv00568798} == 'P3B', uuid5('https://w3id.org/bdchm/Visit', str({phv00159568}) + "
    "':COPDGene P3B')))"
)


def test_copdgene_nested_form_parses_to_its_four_real_labels():
    """The reproduction case: mis-parsed before the fix as the four labels plus P1/P2/P3/P3B."""
    want = {"COPDGene P1", "COPDGene P2", "COPDGene P3", "COPDGene P3B"}
    assert c18._extract_labels_from_expr(COPDGENE_BDY_HGT_VISIT) == want
    assert vvs.extract_visit_labels_from_expr(COPDGENE_BDY_HGT_VISIT)[0] == want


def _shipped_ingest(cohort: str) -> Path:
    import pytest

    ingest = _HV_LINT.parent / "priority_variables_transform" / f"{cohort}-ingest"
    if not (ingest / "visit.yaml").exists():
        pytest.skip(f"{ingest / 'visit.yaml'} not present in this checkout")
    return ingest


def test_every_label_a_copdgene_spec_emits_is_defined_in_its_visit_yaml():
    """Against the shipped tree, as an invariant rather than a count: a label an associated_visit
    emits that no Visit block defines is either a mis-parse (the discriminator codes this file's
    defect produced) or a broken link -- and neither depends on how many visits COPDGene has.
    """
    ingest = _shipped_ingest("COPDGene")
    hv_root = ingest.parent.parent
    registry = vvs.build_visit_registry(ingest / "visit.yaml", hv_root)
    assert registry is not None and registry.all_labels, "COPDGene visit.yaml defines no labels"
    undefined: dict[str, set[str]] = {}
    for spec in sorted(ingest.glob("*.yaml")):
        if spec.name == "visit.yaml":
            continue
        refs, _ = vvs.scan_transform_file(spec, hv_root)
        for ref in refs:
            extra = ref.visit_labels - registry.all_labels
            if extra:
                undefined.setdefault(spec.name, set()).update(extra)
    assert not undefined, f"labels no COPDGene Visit block defines: {undefined}"


# -- FHS's conditional visit ids ---------------------------------------------
#
# FHS's visit.yaml writes exams 4-10 as a label-in-case uuid5 nested inside a conditional
# branch, because not every FHS cohort attended those exams. The trailing literal of the uuid5
# seed is then a SUFFIX (' EXAM 4'), not a label. The two strings below are verbatim from
# FHS-ingest/visit.yaml (exam 4's id and name), as the YAML loader returns them.

FHS_EXAM4_ID = (
    "case(({phv00177928} in [0, 1, 3, 7, 72], uuid5(\"https://w3id.org/bdchm/Visit\", "
    "str({phv00177926}) + \":\" + case(({phv00177928} == 0, 'FHS ORIGINAL'), "
    "({phv00177928} == 1, 'FHS OFFSPRING'), ({phv00177928} == 3, 'FHS GENERATION 3'), "
    "({phv00177928} == 7, 'FHS OMNI 1'), ({phv00177928} == 72, 'FHS OMNI 2'), "
    "(True, 'FHS UNKNOWN VISIT')) + ' EXAM 4')), (True, None))"
)
FHS_EXAM4_NAME = (
    "case(({phv00177928} in [0, 1, 3, 7, 72], case(({phv00177928} == 0, 'FHS ORIGINAL'), "
    "({phv00177928} == 1, 'FHS OFFSPRING'), ({phv00177928} == 3, 'FHS GENERATION 3'), "
    "({phv00177928} == 7, 'FHS OMNI 1'), ({phv00177928} == 72, 'FHS OMNI 2'), "
    "(True, 'FHS UNKNOWN VISIT')) + ' EXAM 4'), (True, None))"
)
# The inner case()'s `(True, 'FHS UNKNOWN VISIT')` arm is a fallback (a True arm beside other
# non-None arms). 1.8 and 5.1 do not compare fallback labels -- a catch-all is not an exam the
# table holds -- and 5.2 checks a fallback against the observed codes instead, so the label set
# here holds the five cohort labels and not 'FHS UNKNOWN VISIT EXAM 4'.
_FHS_EXAM4_LABELS = {
    "FHS ORIGINAL EXAM 4", "FHS OFFSPRING EXAM 4", "FHS GENERATION 3 EXAM 4",
    "FHS OMNI 1 EXAM 4", "FHS OMNI 2 EXAM 4",
}
_FHS_EXAM4_FALLBACK = "FHS UNKNOWN VISIT EXAM 4"


def test_check_5_1_reads_fhs_conditional_id_as_suffixed_labels():
    """The regression: the suffix was captured as a label, leaving bare 'FHS OFFSPRING'."""
    labels, is_dynamic = vvs.extract_visit_labels_from_expr(FHS_EXAM4_ID)
    assert labels == _FHS_EXAM4_LABELS
    assert is_dynamic is True
    # The fallback is still enumerated, suffixed like the other arms, and marked as a fallback.
    values = _visit_ids.enumerate_ids(FHS_EXAM4_ID)
    assert _visit_ids.labels(values, include_fallback=True) == (
        _FHS_EXAM4_LABELS | {_FHS_EXAM4_FALLBACK})


def test_check_1_8_reads_fhs_conditional_id_as_suffixed_labels():
    assert c18._extract_labels_from_expr(FHS_EXAM4_ID) == _FHS_EXAM4_LABELS


def test_fhs_conditional_id_with_a_space_before_the_inner_case_paren():
    """`case (` is still a case() call -- CASE_USAGE_RE accepts `\\bcase\\s*\\(` -- so the seed's
    trailing ' EXAM 4' is still a suffix, in both parser copies."""
    inner = FHS_EXAM4_ID.index("case(", 1)
    spaced = FHS_EXAM4_ID[:inner] + "case (" + FHS_EXAM4_ID[inner + len("case("):]
    assert vvs.extract_visit_labels_from_expr(spaced)[0] == _FHS_EXAM4_LABELS
    assert c18._extract_labels_from_expr(spaced) == _FHS_EXAM4_LABELS
    assert _FHS_EXAM4_FALLBACK in _visit_ids.labels(
        _visit_ids.enumerate_ids(spaced), include_fallback=True)


def test_fhs_conditional_id_and_name_yield_the_same_labels():
    """A visit block's id and name describe one visit, so they must parse to the same labels."""
    id_labels, _ = vvs.extract_visit_labels_from_expr(FHS_EXAM4_ID)
    name_labels, _ = vvs.extract_visit_labels_from_expr(FHS_EXAM4_NAME)
    assert id_labels == name_labels


def test_fhs_associated_visit_label_in_case_form_is_unchanged():
    """FHS entity files' multi-cohort shape: full labels inside the case, no suffix. The
    `(True, 'FHS UNKNOWN VISIT')` arm is a fallback, so neither 1.8 nor 5.1 compares it."""
    expr = (
        "uuid5(\"https://w3id.org/bdchm/Visit\", str({phv00177926}) + \":\" + "
        "case(({phv00177928} == '2', 'FHS NEW OFFSPRING SPOUSE EXAM 2'), "
        "({phv00177928} == '3', 'FHS GENERATION 3 EXAM 2'), "
        "({phv00177928} == '72', 'FHS OMNI 2 EXAM 2'), (True, 'FHS UNKNOWN VISIT')))"
    )
    labels, _ = vvs.extract_visit_labels_from_expr(expr)
    assert labels == {
        "FHS NEW OFFSPRING SPOUSE EXAM 2", "FHS GENERATION 3 EXAM 2", "FHS OMNI 2 EXAM 2",
    }
    assert c18._extract_labels_from_expr(expr) == labels
    assert _visit_ids.labels(_visit_ids.enumerate_ids(expr), include_fallback=True) == (
        labels | {"FHS UNKNOWN VISIT"})


def test_every_fhs_visit_block_id_parses_to_its_name_labels():
    """Against the shipped file: every Visit block in FHS-ingest/visit.yaml, id vs name.

    An invariant, not a census: it holds for any number of blocks, so adding or removing an FHS
    exam cannot fail it. Skips if the ingest tree is absent, so the suite still runs without it.
    """
    import pytest
    import yaml

    spec = _HV_LINT.parent / "priority_variables_transform" / "FHS-ingest" / "visit.yaml"
    if not spec.exists():
        pytest.skip(f"{spec} not present in this checkout")

    blocks = []
    for doc in yaml.safe_load_all(spec.read_text(encoding="utf-8")):
        blocks.extend(doc if isinstance(doc, list) else [doc] if doc else [])
    checked = 0
    for block in blocks:
        cds = block.get("class_derivations") or {}
        for cd in cds if isinstance(cds, list) else [cds]:
            for cls, body in cd.items():
                slots = (body or {}).get("slot_derivations", {}) or {}
                id_expr = (slots.get("id") or {}).get("expr")
                name_expr = (slots.get("name") or {}).get("expr")
                if cls != "Visit" or not id_expr or not name_expr:
                    continue
                id_labels, _ = vvs.extract_visit_labels_from_expr(str(id_expr))
                name_labels, _ = vvs.extract_visit_labels_from_expr(str(name_expr))
                assert id_labels == name_labels, (id_expr, name_expr)
                assert c18._extract_labels_from_expr(str(id_expr)) == id_labels
                checked += 1
    if not checked:
        pytest.skip("FHS visit.yaml has no Visit block with both id and name exprs")
