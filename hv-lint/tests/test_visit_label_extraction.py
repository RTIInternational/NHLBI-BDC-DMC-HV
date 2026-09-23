"""Regression tests for the visit-label extractor used by checks 1.8 and 5.1.

Both checks compare the visit labels attached to one PHT across files, and both get those labels
from a regex extractor -- phase 1 keeps its own copy, replicated from phase 5's, because the phases
are independent modules.

**The defect.** The extractor looked for a case() branch whose result is a bare quoted string::

    ({phv} == 'P1', 'COPDGene P1')        <- matches

It had no pattern for a branch whose result is the whole identifier::

    ({phv} == 'P1', uuid5(<ns>, str({phv}) + ':COPDGene P1'))        <- matched nothing

With no match it fell through to its last resort -- "take every quoted string in the expression" --
which returns the DISCRIMINATOR CODES alongside the labels. A PHT then appears to carry twice the
labels it has, and 1.8/5.1 report a cross-file inconsistency that does not exist.

**This is not a generated-output problem.** COPDGene's shipped specs use the nested form in 48
``associated_visit`` blocks, so the fallback mis-parsed production's own files: ``bdy_hgt.yaml``
returned its four real labels plus ``P1``/``P2``/``P3``/``P3B``.

Both nestings are in production and neither is going away -- FHS (448 blocks) and SPIROMICS (19)
write the label-in-case form, COPDGene (48) writes the nested one -- so the extractor has to read
both. The tests below pin each shape, including the two the fix could plausibly have broken.

Run: python -m pytest hv-lint/tests/test_visit_label_extraction.py
"""

import sys
from pathlib import Path

_HV_LINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HV_LINT / "phase-1"))
sys.path.insert(0, str(_HV_LINT / "phase-5"))

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


# -- against production's own files ------------------------------------------


def test_copdgene_shipped_spec_parses_to_its_four_real_labels():
    """The reproduction case: a real file in this repo, mis-parsed before the fix.

    Skips rather than fails if the ingest tree is not present, so the suite still runs in a
    checkout without it.
    """
    import re

    import pytest

    spec = _HV_LINT.parent / "priority_variables_transform" / "copdgene-ingest" / "bdy_hgt.yaml"
    if not spec.exists():
        pytest.skip(f"{spec} not present in this checkout")

    text = spec.read_text(encoding="utf-8")
    match = re.search(r"associated_visit:\s*\n\s*expr:\s*(.+?)(?=\n\s{0,10}\w+:)", text, re.S)
    assert match, "no associated_visit expr found -- the spec's shape changed"

    labels = c18._extract_labels_from_expr(" ".join(match.group(1).split()))
    assert labels == {"COPDGene P1", "COPDGene P2", "COPDGene P3", "COPDGene P3B"}
