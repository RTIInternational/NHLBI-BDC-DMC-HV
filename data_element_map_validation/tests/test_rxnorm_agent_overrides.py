"""DRUG_CURIE_OVERRIDES coverage for rxnorm_agent.py.

RxNorm has no single generic Ingredient concept for a whole drug class
(e.g. "insulin" -- only specific formulations like insulin glargine exist),
so a bare class-level free-text query can never resolve correctly via a
live/local RxNorm lookup alone. Confirmed via two independent real cases
this session (CARDIA tak_insulin.yaml fix #33, CHS tak_insulin.yaml fix #38)
that both landed on ATC:A10A -- added as a standing override.

The override must still match real generic phrasing regardless of word
count ("TAKE INSULIN", "CURRENTLY TAKING INSULIN OR ORAL DRUGS? Q 14" are
both real dbGaP text), while NOT swallowing a query that names a specific
insulin type (e.g. "insulin glargine"), which RxNorm can resolve to its own
concept on its own. An earlier implementation attempt required an exact
whole-string match to solve the specific-mention problem, which broke the
real multi-word generic cases above -- the tests below guard against that
regression specifically.
"""
import rxnorm_agent as agent


class TestInsulinOverride:
    def test_bare_insulin_resolves_to_atc_class(self):
        assert agent.get_drug_curie_override("insulin") == "ATC:A10A"

    def test_case_insensitive(self):
        assert agent.get_drug_curie_override("INSULIN") == "ATC:A10A"

    def test_plural_form_matches_real_chs_dbgap_text(self):
        """CHS's actual dbGaP variable description for several fix #38 PHVs
        is literally 'Insulins' -- must match on its own, not just 'insulin'."""
        assert agent.get_drug_curie_override("Insulins") == "ATC:A10A"

    def test_does_not_match_unrelated_word_containing_substring(self):
        """Whole-word boundary must hold -- 'insulinoma' contains 'insulin'
        as a substring but is not the same word."""
        assert agent.get_drug_curie_override("insulinoma") is None

    def test_real_chs_multiword_generic_text_still_matches(self):
        """Regression guard: a stricter 'exact match only' design was tried
        and rejected because it broke this exact real dbGaP text (CHS
        INSUL12, fix #38) -- multi-word but still a generic yes/no question,
        must still hit the override."""
        assert agent.get_drug_curie_override("TAKE INSULIN") == "ATC:A10A"

    def test_real_cardia_multiword_generic_text_still_matches(self):
        """Same regression guard, CARDIA's actual dbGaP text (fix #33)."""
        assert agent.get_drug_curie_override(
            "CURRENTLY TAKING INSULIN OR ORAL DRUGS? Q 14"
        ) == "ATC:A10A"

    def test_specific_formulation_mention_does_not_match(self):
        """'insulin glargine' is a real, specific RxNorm Ingredient concept
        (confirmed present in rxnorm2omop_standard.csv) -- must fall through
        to the RxNorm lookup instead of being swallowed into the generic
        ATC class."""
        assert agent.get_drug_curie_override("insulin glargine") is None

    def test_other_specific_insulin_types_do_not_match(self):
        for text in ["NPH insulin", "insulin isophane", "insulin lispro", "insulin detemir"]:
            assert agent.get_drug_curie_override(text) is None, text


class TestExistingOverridesUnaffected:
    """Regression guard: adding the insulin entries must not disturb the
    existing overrides or their whole-word matching behavior."""

    def test_metoprolol_unchanged(self):
        assert agent.get_drug_curie_override("metoprolol") == "RxCUI:6918"

    def test_gemfibrozil_unchanged(self):
        assert agent.get_drug_curie_override("gemfibrozil") == "ATC:C10AB"

    def test_niacin_500mg_tablets_unchanged(self):
        assert agent.get_drug_curie_override("niacin 500mg tablets") == "RxCUI:198024"

    def test_plain_niacin_still_not_overridden(self):
        assert agent.get_drug_curie_override("niacin") is None

    def test_unrelated_drug_name_returns_none(self):
        assert agent.get_drug_curie_override("lisinopril") is None


class TestOtherMultiWordNonInsulinCases:
    """The bounded-word search mechanism (pattern.search(), not a full-string
    match) is generic -- it isn't special-cased for insulin. These confirm
    the other existing override keys are found the same way when embedded
    in arbitrary surrounding text, exactly like the insulin cases above.

    Where real dbGaP text exists for these drugs, it's used directly rather
    than invented phrasing (checked against *_dbgap_study_variable.csv
    fleet-wide: FHS has real gemfibrozil variables; no study has a real
    metoprolol-naming variable anywhere in this fleet, so that one stays
    illustrative/synthetic -- noted explicitly rather than left ambiguous)."""

    def test_gemfibrozil_real_fhs_dbgap_text(self):
        """Real FHS dbGaP text (multiple PHVs share this wording, e.g.
        phv00004974/phv00006485/phv00006880/phv00007317), not invented."""
        assert agent.get_drug_curie_override(
            "MEDICATION USE: ANTI CHOLESTEROL DRUGS (FIBRATES -- E.G. GEMFIBROZIL)"
        ) == "ATC:C10AB"

    def test_gemfibrozil_real_fhs_dbgap_text_variant_phrasing(self):
        """A second real FHS variant (phv00006145) -- different surrounding
        wording, same drug name, confirms the search isn't tied to one
        specific phrasing."""
        assert agent.get_drug_curie_override(
            "MEDICATION USE - ANTI CHOLESTEROL DRUGS, (FILBRATES- E.G. GEMFIBROZIL)"
        ) == "ATC:C10AB"

    def test_metoprolol_embedded_in_longer_phrase_illustrative_only(self):
        """No study in this fleet has a real dbGaP variable naming
        metoprolol specifically (checked all 10 *_dbgap_study_variable.csv
        files) -- this phrasing is invented, kept only to confirm the
        mechanism generalizes beyond gemfibrozil's real text above."""
        assert agent.get_drug_curie_override("patient reports metoprolol use") == "RxCUI:6918"

    def test_niacin_500mg_tablets_embedded_in_longer_phrase_illustrative_only(self):
        """The key itself is already multi-word -- confirm the whole phrase
        is still found (as one unit) inside even more surrounding text, not
        just when it's the entire query. Surrounding text here is invented
        (this override matches a specific resolved free-text value from
        CARDIA tak_statin.yaml, not a raw dbGaP variable description)."""
        assert agent.get_drug_curie_override(
            "free text value: niacin 500mg tablets, prescribed daily"
        ) == "RxCUI:198024"

    def test_multiword_phrase_with_no_override_drug_returns_none(self):
        assert agent.get_drug_curie_override("currently taking lisinopril daily") is None

    def test_partial_word_boundary_still_enforced_in_longer_phrase(self):
        """'metoprololx' (not a real drug) must not match 'metoprolol' even
        embedded in a longer phrase -- the word-boundary rule, not just the
        substring, must hold regardless of surrounding text."""
        assert agent.get_drug_curie_override("taking metoprololx daily") is None
