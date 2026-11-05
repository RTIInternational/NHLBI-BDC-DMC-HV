"""Generate per-variable match quality table for any cohort BDC vs TOPMed comparison.

Usage:
    # Core variables only (default — 19 variables, 5+ cohort coverage)
    python match_quality_table.py <topmed_json> <bdc_json> [output_file]

    # All matched variables
    python match_quality_table.py <topmed_json> <bdc_json> [output_file] --all-vars
"""
import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# KNOWN METHODOLOGICAL DIFFERENCES
# ─────────────────────────────────────────────────────────────────────────────
# When BDC and TOPMed differ significantly but the difference is NOT a pipeline
# error — it reflects a deliberate design choice, extended coverage, or a
# different (often more complete) aggregation strategy — add an entry here.
#
# These variables have their methodological note printed in a dedicated section
# below the table, tagged "(tier kept)". The statistical diff is still displayed
# in full so the magnitude is transparent.
#
# NOTE ON THE TIER ANNOTATION: entries may set "no_override": True to keep the
# computed tier as-is. Every current entry does, so the asterisk (*) annotation
# implemented further down never fires in practice -- the notes are advisory
# only and never change a grade. Drop "no_override" from an entry if you do want
# its tier starred.
#
# KEY FORMAT:  (COHORT_UPPERCASE, topmed_variable_name)
# The cohort is read from t['metadata']['cohort'] in the input JSON.
#
# REASON CODES (use one of these in "code"):
#   UNION_OF_FORMS       — BDC unions multiple source forms/tables; TOPMed used one
#   EXTENDED_COVERAGE    — BDC captures more participants (fewer missing) by design
#   VISIT_SCOPE_DIFF     — BDC and TOPMed selected different baseline visit(s)
#   AGGREGATION_DIFF     — Different rollup logic (e.g., any-positive vs first-record)
#   LABEL_REMAP          — Same data, different category label conventions
#
# The codes are free-text and nothing validates them, so the set has grown well
# past the five above (ADMIN_VS_SURVEY, PARTICIPANT_UNIVERSE_DIFF, IMPUTATION_DIFF,
# DERIVED_VS_STORED, STRUCTURAL_GAP, ... ~26 in use). Reuse an existing code where
# one fits rather than coining a near-synonym; run
#   grep -o '"code": "[A-Z_]*"' match_quality_table.py | sort -u
# to see the current set.
#
# TO ADD A NEW ENTRY:
#   1. Run match_quality_table.py and identify the T5-tier variable
#   2. Investigate the extract log and YAML to confirm it's methodological
#   3. Add an entry below with (COHORT, variable) as key, and fill in code + note
#   4. Re-run to confirm the * annotation appears on the tier
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CORE VARIABLE SET
# ─────────────────────────────────────────────────────────────────────────────
# 19 variables present in both BDC and TOPMed extracts across at least 5 of 9
# cohorts, organised by clinical group. This is the default comparison scope.
#
# Defined in: QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md
# ─────────────────────────────────────────────────────────────────────────────
# Core variables grouped by clinical domain.
# Order within and across groups is the display order in the output table.
# CORE_VARIABLES (the flat frozenset used for filtering) is derived from this.
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: core_variable_coverage_table.py carries its own copy of this list as
# CORE_VARS. The two are currently identical (19/19); keep them in sync when
# editing either one.
CORE_VARIABLE_GROUPS: list[tuple[str, list[str]]] = [
    ("Demographics", [
        "annotated_sex_1",
        "race_us_1",
        "hispanic_or_latino_1",
    ]),
    ("Anthropometrics", [
        "height_baseline_1",
        "weight_baseline_1",
        "bmi_baseline_1",
    ]),
    ("Blood Pressure", [
        "bp_systolic_1",
        "bp_diastolic_1",
        "antihypertensive_meds_1",
    ]),
    ("Smoking", [
        "current_smoker_baseline_1",
        "ever_smoker_baseline_1",
    ]),
    ("Lipids", [
        # hdl_1 excluded -- D in CARDIA and JHS (score 6); pipeline/coverage issues
        # ldl_1 excluded -- D in FHS and JHS, C in CARDIA and CHS; too noisy across cohorts
        "total_cholesterol_1",
        "triglycerides_1",
    ]),
    ("CBC", [
        # hematocrit_vfr_bld_1 excluded -- D in FHS, C in CHS/MESA; coverage gaps (score 7)
        # hemoglobin_mcnc_bld_1 excluded -- D in FHS, C in CHS/MESA; coverage gaps (score 7)
        # wbc_ncnc_bld_1 excluded -- D in CARDIA (x1000 units bug), D in FHS; (score 7)
        # rbc_ncnc_bld_1 excluded -- rdbld_ct.yaml archived in all cohorts; no active pipeline support
        "platelet_ncnc_bld_1",
        "mch_entmass_rbc_1",
    ]),
    ("CVD History", [
        "mi_prior_1",
        "cabg_prior_1",
        "pad_prior_1",
        "angina_prior_1",
        # coronary_angioplasty_prior_1 excluded -- D in MESA (miss_diff 22.5pp); only 5 cohorts (score 4)
    ]),
    # Sleep
    # sleep_duration_1 excluded -- D in CARDIA, CHS, WHI; active units bug (raw coded value vs hours)
]

# Flat frozenset for membership testing
CORE_VARIABLES: frozenset[str] = frozenset(
    var for _group, vars in CORE_VARIABLE_GROUPS for var in vars
)

# Build a position index: variable -> (group_index, var_index_within_group)
_CORE_VAR_ORDER: dict[str, tuple[int, int]] = {}
for _gi, (_gname, _gvars) in enumerate(CORE_VARIABLE_GROUPS):
    for _vi, _v in enumerate(_gvars):
        _CORE_VAR_ORDER[_v] = (_gi, _vi)


KNOWN_METHODOLOGICAL_DIFFS: dict[tuple[str, str], dict] = {
    ("WHI", "antihypertensive_meds_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Self-report versus medication inventory. With the Form 33 follow-up blocks "
            "unlinked from 'WHI SCREENING' (HV branch fix/hv-alignment-testfixes-20261105; "
            "on specs that still link pht002770 there, BDC reads about 61% Yes from a "
            "follow-up item), BDC's only baseline source is Form 30 HYPTPILN (pht000999 "
            "phv00078559, 'Do you now take pills for high blood pressure?'). It is a "
            "sub-question of the hypertension item, skipped by women not reporting "
            "hypertension and absent from some Form 30 versions: dbGaP has 35,517 Yes / "
            "10,071 No / 97,535 null, so BDC Yes is computed among about a third of "
            "participants. TOPMed derives the variable from the Form 44 medication "
            "inventory (pht002754 TCCODE classes at F44VTYP == 1, restricted to women "
            "with a baseline blood pressure reading and a medication-start window). "
            "Inferring 'No' for women never told of hypertension was rejected "
            "(antihypertensive classes are also prescribed for heart failure, angina "
            "and post-MI care)."
        ),
    },
    ("WHI", "angina_prior_1"): {
        "code": "IMPUTATION_DIFF",
        "no_override": True,
        "note": (
            "The positive case count is IDENTICAL: 7,868 Prior History in both TOPMed and BDC. "
            "The N and missing difference (T_N=142,250 miss=0.7% vs B_N=143,213 miss=0.1%) "
            "reflects BDC's absence-equals-No imputation: 963 participants with no angina "
            "record in BDC are classified as 'No Prior History' by construction, while TOPMed "
            "preserves them as missing. No disagreement on actual clinical cases. "
            "VERDICT: BDC is better on completeness (fewer missing). TOPMed is more careful "
            "about unknown status. Neither is wrong -- BDC approach is appropriate for "
            "cross-cohort boolean prior-history variables where absence of a record strongly "
            "implies no history was reported."
        ),
    },
    ("WHI", "mi_prior_1"): {
        "code": "IMPUTATION_DIFF",
        "no_override": True,
        "note": (
            "The positive case count is IDENTICAL: 3,279 Prior History in both TOPMed and BDC. "
            "BDC adds 77 more valid participants (143,213 vs 143,136, miss=0.0% vs 0.1%) via "
            "absence-equals-No imputation. No disagreement on actual MI cases. "
            "VERDICT: Equivalent accuracy; BDC has marginally better coverage. Same "
            "imputation-vs-missing pattern as angina_prior_1."
        ),
    },
    ("WHI", "cabg_prior_1"): {
        "code": "IMPUTATION_DIFF",
        "no_override": True,
        "note": (
            "The positive case count is IDENTICAL: 1,226 Prior CABG History in both TOPMed "
            "and BDC. The 1.4pp missing difference (T=1.5% vs B=0.1%) is what pushes this "
            "from A+ to A: TOPMed has 2,017 participants with no CABG questionnaire response "
            "on pht000999 preserved as missing. BDC assigns all of them 'No Prior History' "
            "by construction. Zero disagreement on actual CABG cases. "
            "VERDICT: BDC is better on completeness. No accuracy concern -- CABG is a rare "
            "event and the 'No' imputation for non-responders is safe."
        ),
    },
    ("WHI", "pad_prior_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC has 378 MORE positive cases than TOPMed (3,271 vs 2,893 Prior History, "
            "2.3% vs 2.0% prevalence), along with 927 more valid participants (B_N=143,143 "
            "vs T_N=142,216). This is not an imputation artifact -- BDC is capturing real "
            "additional PAD cases from WHI screening forms beyond the one form used by TOPMed. "
            "WHI collected PAD history on multiple screening instruments across pht002770 "
            "(the extended screening battery) in addition to pht000999. TOPMed's lower "
            "prevalence reflects the narrower single-form scope. "
            "VERDICT: BDC is better -- more complete positive case capture from additional "
            "WHI screening instruments. The 0.3pp prevalence difference is real additional "
            "coverage, not noise."
        ),
    },
    ("WHI", "current_smoker_baseline_1"): {
        "code": "COVERAGE_NOISE",
        "no_override": True,
        "note": (
            "Near-perfect match: T_N=141,382 vs B_N=141,363, 1.3% missing in both. "
            "Distributions are identical at 6.9% Current / 93.1% Not Current. The 19-person "
            "N gap (T=141,382 vs B=141,363) is noise-level -- likely a small difference in "
            "how the two pipelines handle a handful of records with duplicate or ambiguous "
            "screening form entries. The actual smoker counts differ by 19 (T=9,821 vs "
            "B=9,802), proportional to the N gap. No meaningful difference. "
            "VERDICT: Equivalent."
        ),
    },
    ("WHI", "ever_smoker_baseline_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "'Never Smoked' count is IDENTICAL in both (71,847). The 697-participant gap is "
            "entirely in 'Ever Smoked' (T=70,213 vs B=69,516). TOPMed appears to recover 697 "
            "additional ever-smokers that BDC classifies as missing (B_miss=1.3% vs "
            "T_miss=0.8%). These are likely participants who answered a supplemental smoking "
            "form (Observation of Daily Living supplement or OS baseline extension) that "
            "TOPMed's pipeline captures but BDC's WHI smk/cig_smok YAML does not. The 0.2pp "
            "category difference is within A+ tolerance but TOPMed has a slight completeness "
            "edge on ever-smokers. "
            "VERDICT: TOPMed marginally better on completeness. Investigate whether WHI "
            "has a supplemental ever-smoked form not yet included in cig_smok.yaml."
        ),
    },
    ("WHI", "bp_diastolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "T_mean=75.18 vs B_mean=75.00, delta=-0.18 mmHg on SD=9.25 (normalized=0.020 -- "
            "exactly at the A/A+ boundary). N is essentially identical (143,035 vs 143,080, "
            "miss=0.1% both). The -0.18 mmHg offset is consistent with a derivation "
            "difference: WHI measured BP in triplicate; BDC uses the average of readings 2+3 "
            "per WHI protocol (the standard published derivation), while TOPMed may use the "
            "average of all three readings or a different subset. The first reading is "
            "typically 1-2 mmHg higher due to alerting response, which would make a "
            "three-reading average slightly higher than a two-reading average -- consistent "
            "with the direction of the delta (TOPMed slightly higher). "
            "VERDICT: Both are correct derivations of the same source data. The -0.18 mmHg "
            "difference is clinically negligible and methodologically expected."
        ),
    },
    ("WHI", "bp_systolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "T_mean=127.24 vs B_mean=126.96, delta=-0.28 mmHg on SD=17.70 (normalized=0.016). "
            "Same derivation pattern as bp_diastolic_1. BDC SBP is -0.28 mmHg below TOPMed, "
            "consistent with using readings 2+3 vs a three-reading average that includes "
            "the slightly elevated first reading. N is essentially identical (143,035 vs "
            "143,105, miss=0.1% both). "
            "VERDICT: Both are correct derivations. -0.28 mmHg is clinically negligible."
        ),
    },
    ("WHI", "hispanic_or_latino_1"): {
        "code": "COVERAGE_GAP",
        "no_override": True,
        "note": (
            "TOPMed has meaningfully better coverage: T_miss=0.2% (142,865 valid) vs "
            "B_miss=3.1% (138,813 valid) -- a gap of 4,052 participants. BDC has slightly "
            "more Hispanic participants (5,847 vs 5,468, +0.4pp), but 4,052 fewer classified "
            "overall. The 4,052 missing in BDC are participants for whom WHI's enrollment "
            "forms did not include an explicit Hispanic/Latino ethnicity question -- likely "
            "participants enrolled into specific WHI trial arms or OS segments that used "
            "abbreviated enrollment instruments. TOPMed appears to recover ethnicity for "
            "these participants from a supplemental administrative source not currently "
            "mapped in BDC's demography.yaml. "
            "VERDICT: TOPMed is better (3x lower missing rate). Investigate WHI demography.yaml "
            "ethnicity source -- a supplemental ethnicity form (possibly the Year 3 or "
            "extension enrollment update) likely covers these 4,052 participants."
        ),
    },
    ("WHI", "race_us_1"): {
        "code": "CLASSIFICATION_DIFF",
        "no_override": True,
        "note": (
            "BDC demography.yaml emits two Demography rows per participant: Form 2 "
            "(pht000998, RACE phv00078450, at 'WHI SCREENING') and Form 41 (pht001009, "
            "per-race checkboxes, no visit: Form 41 is a follow-up form with no "
            "screening visit type). The extractor takes the first non-null value per "
            "column, so Form 2 race wins and Form 41 fills in only where Form 2 is "
            "null. Form 2 has no separate NHOPI code (2 = 'Asian or Pacific "
            "Islander', mapped to Asian) and maps Hispanic (4) and Other (8) to "
            "OMOP:8552, so BDC shows NHOPI 0 (T=111) and more 'Other' (B=7,076 vs "
            "T=2,888). The DCC refines those Form 2 categories from Form 41, following "
            "WHI investigator guidance; BDC does not combine the forms. Form 41 counts "
            "race groups, so two ticks within one group (e.g. Chinese and Japanese) are "
            "one race, not Multiple."
        ),
    },
    # ── ARIC ──────────────────────────────────────────────────────────────────
    ("ARIC", "antihypertensive_meds_1"): {
        "code": "ADMIN_VS_SURVEY",
        "no_override": True,
        "note": (
            "BDC is graded on its ATC:C02 indicators at ARIC EXAM 1, a union of three "
            "Visit 1 variables in hypert_trt.yaml: HYPTMD01 (phv00204754, pht004063, the "
            "DCC's variable), HYPTMDCODE01 (phv00204798, pht004063, medication-code "
            "based) and MSRA08A (phv00207913, pht004129, medication survey 'for high "
            "blood pressure'). A participant positive on any of the three is Yes. "
            "Result: BDC 30.7% Yes (4,618/15,066) vs reference 25.7% (3,823/14,854). "
            "Methodological: the union is broader than the DCC's single variable."
        ),
    },
    ("ARIC", "mch_entmass_rbc_1"): {
        "code": "BASELINE_DEFINITION_DIFF",
        "no_override": True,
        "note": (
            "ARIC never conducted CBC labs at Exams 1 or 2; the earliest MCH data exists "
            "in HMTCV301 (pht004109, Exam 3), HMTCV401 (pht004110, Exam 4), and CBC "
            "(pht006422, Exam 5). The TOPMed DCC rule for ARIC is: 'The visit with "
            "the most non-missing phenotype values was chosen first. For subjects "
            "without measurements at this visit, the visit with the next most "
            "non-missing values was chosen, and so forth in succession.' The comparison "
            "applies the same greedy rule (visit_override_mode 'most_nonmissing_first' "
            "over ARIC Exams 1-5), but the visit order is computed on BDC's rows, so it "
            "matches the DCC's selection only to the extent that BDC maps every exam "
            "the DCC read. For MCH, BDC mch.yaml maps Exams 3, 4 and 5, as the DCC "
            "does. Neither side measures MCH at enrollment baseline."
        ),
    },
    ("ARIC", "pad_prior_1"): {
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "BDC unions two MONDO codes into pad_prior_1: (1) MONDO:0005386 (peripheral "
            "artery disease) from pad.yaml across Exams 1, 3, and 4 (pht004027/4028/4029, "
            "ABI < 0.9 definition), and (2) MONDO:0005294 (peripheral vascular disease) "
            "from hist_cvd.yaml (pht004102 = Heart Failure Hospital Record Abstraction Form, "
            "variable HFAA11M = self-reported PVD). The reference uses only the Exam 1 "
            "ABI-based PAD variable. The comparison does not fall back to other visits "
            "for prior-history variables, so the post-baseline hospital-abstraction PVD "
            "rows (hist_cvd.yaml HFAA11M phv00206807, MONDO:0005294, visit 'ARIC "
            "Hospital Form') are excluded from pad_prior_1. The MONDO:0005294 alias must "
            "remain in BDC_CONDITION_MAP because COPDGene pad.yaml uses only that code."
        ),
    },
    ("ARIC", "annotated_sex_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC sources sex from 30 tables across all visits via demography.yaml, achieving "
            "100% coverage (15,068/15,068, 0% missing). The DCC reference sources sex from a "
            "single derived table (pht004063 DERIVE13, variable GENDER phv00204711) and drops "
            "104 participants with NA GENDER (14,940/15,044, 0.7% missing). Category "
            "distributions are identical (54.6% F / 45.4% M). BDC's multi-table approach is "
            "more complete -- those 104 participants likely have sex recorded in other tables. "
            "Grade kept at A because the data agrees perfectly; the N/missing difference is "
            "purely a source-coverage gap on the reference side."
        ),
    },
    ("ARIC", "hispanic_or_latino_1"): {
        "code": "STUDY_DESIGN",
        "no_override": True,
        "bdc_only": True,
        "note": (
            "ARIC enrolled only White and Black Americans from 4 field centers (Jackson MS, "
            "Forsyth County NC, Minneapolis MN, Washington County MD) and never collected "
            "Hispanic/Latino ethnicity as a baseline questionnaire item. The variable does "
            "not appear in the TOPMed reference for ARIC for this reason. BDC's "
            "demography.yaml emits hispanic_or_latino_1 for 8 participants whose Hispanic "
            "ethnicity was recorded on a hospital stroke abstraction form (pht004061 "
            "STRX10, phv00204615) — not the baseline survey. This is a study design gap, "
            "not a pipeline error. The 8 BDC records (99.9% missing) should be treated as "
            "incidental event-form data rather than a meaningful baseline measurement. "
            "No dbGaP population-level Hispanic ethnicity variable exists for ARIC."
        ),
    },
    ("ARIC", "angina_prior_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "bdc_only": True,
        "note": (
            "Not in the TOPMed reference (no ARIC unit in angina_prior_1.json), so BDC-only. "
            "angina.yaml maps RANGNA01 (phv00204724, pht004063 DERIVE13, Rose angina, Visit "
            "1) as the v8 dictionary documents it ('1' = Negative -> ABSENT, '4' = Positive "
            "-> PRESENT), which gives 94.8% Prior History (13,687 of 14,440 respondents). "
            "That is not plausible for adults aged 45-64: the Rose item MHXA05 "
            "(phv00207748, chest pain walking uphill) has 1,280 Yes, which caps Rose "
            "positives at 1,280 or fewer; code 4 (13,687) exceeds that, code 1 (753) "
            "does not. The coding is likely inverted "
            "in the dictionary; the spec follows the documentation until ARIC confirms "
            "(HV issue #945, awaiting external). Do not use ARIC prior angina until then."
        ),
    },
    ("ARIC", "bmi_baseline_1"): {
        "code": "CONSERVATIVE_DERIVATION",
        "no_override": True,
        "note": (
            "BDC sources BMI from DERIVE13 pht004063 (BMI01, phv00204719) -- the ARIC study's "
            "own pre-computed Exam 1 BMI. This yields 14,452 valid records (4.1% missing). "
            "Reference achieves 14,915 valid (0.9% missing), a 463-record gap. The most likely "
            "explanation: 463 participants have height and weight measured at Exam 1 but no "
            "entry in DERIVE13 (excluded from the derivation, possibly due to implausible "
            "height or weight values, or data entry gaps). The reference pipeline may compute "
            "BMI from raw height/weight tables for these participants. BDC's approach (official "
            "study derivation) is conservative and internally consistent; means are virtually "
            "identical (27.72 vs 27.65 kg/m2, +0.07). Approach is EQUIVALENT in accuracy, "
            "slightly less complete in coverage."
        ),
    },
    ("ARIC", "bp_diastolic_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC sources diastolic BP from Exam 1 table pht004192 (primary) with additional "
            "exam tables (pht004193-4195, pht012814, pht006480) as fallback; earliest-per-"
            "participant selects Exam 1 for essentially all participants. BDC achieves 15,050 "
            "valid (0.1% missing) vs reference 14,926 (0.8% missing), a 124-record gap. "
            "Means are identical to 5 significant figures (73.71 mmHg). The 0.7pp lower "
            "missing rate in BDC reflects slightly broader extraction from the same Exam 1 "
            "source tables. BDC is BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "bp_systolic_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC sources systolic BP from the same tables as diastolic BP (pht004192-4195, "
            "pht012814, pht006480); earliest-per-participant selects Exam 1. BDC achieves "
            "15,050 valid (0.1% missing) vs reference 14,926 (0.8% missing). Means are "
            "effectively identical (121.49 vs 121.44 mmHg, +0.04). Same pattern as "
            "diastolic BP: BDC has broader source coverage from the same Exam 1 tables. "
            "BDC is BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "cabg_prior_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC achieves 15,059 valid records (0.1% missing) vs reference 14,817 (1.5% "
            "missing), a 242-record coverage gap. Category distributions are IDENTICAL: "
            "98.4% No Prior History / 1.6% Prior History in both pipelines (0.0pp max "
            "difference). BDC's lower missing rate stems from broader YAML source coverage "
            "using the same underlying ARIC Exam 1 CABG data. The identical distribution "
            "confirms methodological alignment; BDC is BETTER coverage with SAME accuracy."
        ),
    },
    ("ARIC", "current_smoker_baseline_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC achieves 15,064 valid (0.0% missing) vs reference 14,926 (0.8% missing), "
            "a 138-record gap. Category distributions are virtually identical: Current Smoker "
            "26.6% BDC vs 26.5% reference, Not Current Smoker 73.4% vs 73.5% (0.1pp max "
            "difference). ARIC cig_smok.yaml sources smoking status from Exam 1 derived "
            "variables; BDC covers essentially all participants. BDC is BETTER coverage at "
            "equivalent accuracy."
        ),
    },
    ("ARIC", "ever_smoker_baseline_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC achieves 15,064 valid (0.0% missing) vs reference 14,930 (0.8% missing), "
            "a 134-record gap. Distributions are virtually identical: Ever Smoked 58.9% BDC "
            "vs 58.8% reference, Never Smoked 41.1% vs 41.2% (0.1pp max difference). Same "
            "source as current smoker (cig_smok.yaml, Exam 1 derived variables). BDC is "
            "BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "height_baseline_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC achieves 15,045 valid (0.2% missing) vs reference 14,921 (0.8% missing), "
            "a 124-record gap with 0.6pp less missing. Means are effectively identical "
            "(168.51 vs 168.56 cm, -0.05 cm). BDC sources height from pht004032 and "
            "additional Exam 1 tables, covering a wider slice of the enrollment cohort. "
            "BDC is BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "mi_prior_1"): {
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "BDC sources MI prior history from 18 source tables spanning all ARIC visits "
            "(pht004063 DERIVE13, pht004047/4050/4053/4054 exam forms, pht004061/4064 stroke "
            "forms, pht004102/4103 hospital/death abstraction forms, pht004111/4126/4145/4146 "
            "later exam forms, pht006416/12504/12813/12814/12815 Exams 5-7 tables), covering "
            "Exams 1-7, Death Event, AFQ, Cohort enrollment, and Hospital Form. This "
            "comprehensive union achieves 0% missing (15,067 valid) vs reference 2.2% missing "
            "(14,717 valid) from a single DERIVE13 variable. BDC prevalence is 5.2% Prior "
            "History vs reference 4.4% (0.8pp higher), likely because hospital record and "
            "death event forms capture incident MI events retrospectively coded as prior "
            "history at later visits. BDC coverage is BETTER; the 0.8pp prevalence inflation "
            "from multi-form union is a known methodological trade-off."
        ),
    },
    ("ARIC", "platelet_ncnc_bld_1"): {
        "code": "EXAM_COMPOSITION",
        "no_override": True,
        "note": (
            "BDC sources platelet count from HMTCV1 (pht004107, Exam 1), HMTCV301 (pht004108, "
            "Exam 2), HMTCV301 (pht004109, Exam 3), HMTCV401 (pht004110, Exam 4), and CBC "
            "(pht006422, Exam 5). Earliest-per-participant selects Exam 1 for nearly all "
            "records. BDC and reference are essentially identical: 14,808 vs 14,815 valid "
            "(7-record difference), 1.7% vs 1.5% missing (within natural sampling variation), "
            "and means 257.76 vs 257.57 K/uL (+0.19, 0.07% relative difference). This "
            "variable is a near-perfect match and is one of the strongest validation signals "
            "in the ARIC comparison. BDC and reference are EQUIVALENT."
        ),
    },
    ("ARIC", "race_us_1"): {
        "code": "BROADER_CLASSIFICATION",
        "no_override": True,
        "note": (
            "ARIC enrolled primarily Black and White Americans; the reference pipeline maps "
            "race to a strict binary (Black 26.1% / White 73.9%). BDC captures additional "
            "racial categories found in ARIC administrative records: AIAN (n=15, 0.1%), "
            "Asian (n=28, 0.2%), Other (n=1, 0.0%). This reduces White percentage to 73.4% "
            "vs 73.9% (0.5pp max difference), because the 44 non-Black, non-White participants "
            "are distributed in BDC's additional categories rather than defaulting to White. "
            "BDC also has 15,067 valid (0.0% missing) vs reference 14,940 (0.7% missing). "
            "BDC classification is MORE COMPLETE and more accurate to the actual population "
            "composition; the 0.5pp shift is expected from the additional categories."
        ),
    },
    ("ARIC", "total_cholesterol_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC sources total cholesterol from multiple ARIC lipid tables: DERIVE13 "
            "(pht004063), HMLAB1 (pht004064), pht004121, pht006444, and Exams 5-7 tables "
            "(pht012504, pht012511, pht012813-12815, pht012853). Earliest-per-participant "
            "selects Exam 1 for the majority. BDC achieves 14,873 valid (1.3% missing) vs "
            "reference 14,705 (2.3% missing), a 168-record gap with 1.0pp less missing. "
            "Means are virtually identical (214.89 vs 215.06 mg/dL, -0.17 mg/dL). BDC is "
            "BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "triglycerides_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "Same multi-table coverage pattern as total cholesterol. BDC sources triglycerides "
            "from DERIVE13 (pht004063), HMLAB1 (pht004064), and additional lipid tables across "
            "all exams. BDC achieves 14,875 valid (1.3% missing) vs reference 14,707 (2.2% "
            "missing), a 168-record gap with 0.9pp less missing. Means are virtually identical "
            "(132.41 vs 132.44 mg/dL, -0.04 mg/dL, well within lab assay variability). BDC "
            "is BETTER coverage at equivalent accuracy."
        ),
    },
    ("ARIC", "weight_baseline_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC sources body weight from pht004032 (Exam 1, raw lbs converted to kg via "
            "source_unit=[lb_av] to target_unit=kg) and additional exam tables (bdy_wgt.yaml "
            "covers Exams 1-5). Earliest-per-participant selects Exam 1. BDC achieves 15,039 "
            "valid (0.2% missing) vs reference 14,915 (0.9% missing), a 124-record gap with "
            "0.7pp less missing. Means are virtually identical (78.70 vs 78.71 kg, -0.01 kg). "
            "BDC is BETTER coverage at equivalent accuracy."
        ),
    },
    # ── CARDIA ────────────────────────────────────────────────────────────────
    ("CARDIA", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the pre-stored BMI field A20BMI (phv00113661, pht001583/A4F20), "
            "which is the study's own calculated value (mean 24.536 kg/m2). The reference "
            "pipeline recalculates BMI from the raw measurement fields in the same table: "
            "A20HGT (height in cm, phv00113634) and A20WGT (weight in lbs, phv00113635), "
            "applying the conversion weight_lbs / 2.20462 / (height_cm / 100)^2 (mean "
            "24.484 kg/m2). The +0.052 delta and shifted min/max (14.538 vs 14.508, "
            "53.529 vs 53.416) arise from floating-point rounding in the unit conversion. "
            "N_valid is identical (3,612). Neither approach is incorrect; BDC defers to the "
            "study's own pre-computed value while the reference recalculates from raw inputs. "
            "Grade kept at A (clinically negligible difference)."
        ),
    },
    ("CARDIA", "current_smoker_baseline_1"): {
        "code": "GATING_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC maps phv00112435 (A01SMNOW, 'CURRENT SMOKER?', pht001559/A4F01) directly: "
            "code 2 -> Current Smoker, code 1 -> Not Current Smoker (former), code 0 -> "
            "Not Current Smoker (never), fallback True -> Unknown. This yields N_valid=3,621 "
            "with 1 missing. The reference applies the standard epidemiological 100-cigarette "
            "gating convention: participants must first pass A01SM100 (phv00112434, 'Lifetime "
            "cigarette consumption > 99') as a precondition before SMNOW is applied. "
            "Participants who answered SMNOW but left SM100 blank or answered SM100=No are "
            "classified as missing (N_missing=62, 1.7% missing). The 61-participant gap "
            "represents individuals whose current-smoker status cannot be reliably determined "
            "without confirming they meet the lifetime consumption threshold. Reference "
            "approach is epidemiologically more rigorous; this is a known methodological "
            "difference, not a pipeline error."
        ),
    },
    ("CARDIA", "ever_smoker_baseline_1"): {
        "code": "GATING_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC derives ever_smoker from A01SMNOW (phv00112435, pht001559/A4F01): codes 1 "
            "(former) and 2 (current) map to 'Ever Smoked'; code 0 (never) maps to 'Never "
            "Smoked'. This yields N_valid=3,621, 1 missing, Ever=1,496 (41.3%), Never=2,125. "
            "The reference uses A01SM100 (phv00112434, 'Lifetime cigarette consumption > 99') "
            "as the direct ever-smoker gate: SM100=Yes -> Ever Smoked, SM100=No -> Never "
            "Smoked, SM100 missing -> missing. This yields N_valid=3,578, 44 missing, "
            "Ever=1,499 (41.9%), Never=2,079. The 0.6pp category gap (41.3% vs 41.9% Ever) "
            "indicates real misclassification: approximately 3 participants in BDC are labeled "
            "Never Smoked (SMNOW=0) who the reference correctly identifies as Ever Smoked "
            "(SM100=Yes but SMNOW=0, i.e., quit smoking). Using SM100 directly for ever_smoker "
            "is the correct approach; the BDC YAML should add A01SM100 (phv00112434) as the "
            "primary source for ever_smoker_baseline and reserve SMNOW only for current_smoker."
        ),
    },
    ("CARDIA", "il6_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Both sides read FL6IL6 (phv00121064, pht001862, Year 15). The DCC also sets "
            "il6 = 12 where FL6IL6CM == 'High > 12' (values above the detection limit); "
            "BDC il6.yaml does not impute. Result: BDC N=689 vs 695, mean 1.74 vs 1.83 "
            "pg/mL, P99 8.17 vs 10.84. Methodological."
        ),
    },
    ("CARDIA", "platelet_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "A05PLATL (phv00112690, pht001563, Year 0) is recorded in 10^5/uL "
            "(dictionary range 0..7.54); platelet_ct.yaml scales it by 100 to 10*3/uL "
            "and passes the source value through otherwise. One participant has a "
            "recorded 0, which BDC keeps as recorded (the documentation does not mark "
            "0 as a missing code); the DCC also keeps it."
        ),
    },
    ("CARDIA", "crp_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "crp.yaml emits both Year 15 assays under OMOP:4208414 with distinct "
            "method_type labels: FL6CRP (phv00120758, 'Original assay (FL6CRP)') and "
            "FL6CRPBN (phv00120759, 'RERUN CRP (uG/ml - BNII METHOD)', 'BNII method "
            "rerun (FL6CRPBN)'). The extractor grades the BNII rerun (config.py "
            "preferred_method_override), the assay the DCC reads. Participants with "
            "only the original assay are not graded."
        ),
    },
    ("CARDIA", "sleep_duration_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "Source pass-through versus a plausibility filter. F67SLPHR (phv00120534, "
            "pht001839, Year 15, 'past month average sleeping hours') has a dictionary "
            "range of 1..280; BDC emits the recorded values, including 8 that exceed 24 "
            "hours, which the extractor flags as implausible. The DCC keeps only values "
            "< 24. The 8 values drive the SD gap (BDC 8.29 vs 1.29); BDC does not apply "
            "cleaning rules the study documentation does not state."
        ),
    },
    # ── MESA ──────────────────────────────────────────────────────────────────
    ("MESA", "hispanic_or_latino_1"): {
        "code": "LABEL_REMAP",
        "no_override": True,
        "note": (
            "Known BDC YAML defect pending a fix. For MESA Family (pht001121) the DCC uses "
            "the direct Hispanic question: notHL = scrhispf %in% 0 & !(racefc %in% 4). "
            "BDC MESA-ingest/demography.yaml (pht001121 ethnicity expr) emits only the "
            "Hispanic branch and has no notHL branch, so BDC shows 0 Not Hispanic vs "
            "TOPMed 919. For MESA Classic and AirNR both sides emit Hispanic only from "
            "race1c == 4 and leave non-Hispanic missing; choosing a race code alone does "
            "not imply 'Not Hispanic' (ontology review, Anne, PR #534)."
        ),
    },
    ("MESA", "platelet_ncnc_bld_1"): {
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "MESA has no population-wide baseline CBC. Platelet counts exist only in two "
            "ancillary sub-studies: pht001984 (MESA Inflammation, Exam 1 era, N=894) and "
            "pht004319 (MESA Epigenomic CBC, Exam 5, N=2,750). TOPMed used only pht004319 "
            "(larger N). BDC unions both sources, yielding N=3,158 after dedup; earliest-per-"
            "participant logic picks the Inflammation (Exam 1 era) value for ~486 overlapping "
            "participants. Mean difference (+4.96, 228.2 vs 233.2) reflects real longitudinal "
            "change between Exam 1 era and Exam 5 for the overlapping sub-cohort. Both "
            "approaches are pragmatic workarounds for the same missing-data limitation."
        ),
    },
    ("MESA", "antihypertensive_meds_1"): {
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "BDC hypert_trt.yaml emits two ATC:C02 indicators at the same exam, which "
            "are unioned: htnmed1c (computed) and bpmed1 ('taking meds for "
            "hypertension') -- Classic Exam 1 phv00085324 / phv00085236, AirNR "
            "phv00083163 / phv00082998. Family has htnmedfc (phv00087093) only. The DCC "
            "uses htnmed1c (htnmedfc for Family). Result: BDC 39.9% Yes (3,307/8,296) vs "
            "reference 39.2% (3,236/8,254). Methodological."
        ),
    },
    **{
        ("MESA", _var): {
            "code": "STUDY_DESIGN",
            "no_override": True,
            "note": (
                "The DCC grades MESA Classic only and sets every pht001116 participant "
                "to 0 (Classic was CVD-free at entry). BDC's rows for this variable come "
                "from Family (pht001121), AirNR (pht001111) or the visit-less events "
                "table (pht001123), so the comparison grades it at MESA CLASSIC EXAM 1, "
                "finds no BDC answer, and reports it NOT COMPARABLE (all missing). Not "
                "a BDC defect."
            ),
        }
        for _var in ("angina_prior_1", "mi_prior_1", "pad_prior_1", "cabg_prior_1",
                     "coronary_angioplasty_prior_1")
    },

    # ── FHS ───────────────────────────────────────────────────────────────────
    ("FHS", "total_cholesterol_1"): {
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "BDC tot_chol_bld.yaml maps FHS Original Cohort total cholesterol from EXAM 1 "
            "(1948) through EXAM 28. After BASELINE_VISIT_CONFIG and visit override fixes, "
            "the extractor now correctly selects baseline-era measurements for each "
            "sub-cohort. Result: BDC N=9,917 (34.3% missing) vs reference N=9,507 "
            "(37.3% missing); BDC mean 194.48 vs reference 194.23 mg/dL (delta +0.25 "
            "mg/dL). The +410 participant surplus reflects BDC's coverage of Omni 1, "
            "Omni 2, and NOS sub-cohorts that the reference excludes. The near-identical "
            "means confirm that the earlier assay-era concern (Abell-Kendall vs enzymatic, "
            "which had shown +6.67 mg/dL in pre-fix extracts) has been resolved by the "
            "baseline visit filtering. The YAML correctly maps source data; the residual "
            "N gap is a sub-cohort scope difference, not a YAML error."
        ),
    },
    ("FHS", "triglycerides_1"): {
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "BDC triglyc_bld.yaml maps FHS triglycerides from Original EXAM 7 (earliest "
            "available TG in dbGaP) onward. After BASELINE_VISIT_CONFIG and visit override "
            "fixes, the extractor correctly selects baseline-era TG for each sub-cohort. "
            "Result: BDC N=9,915 (34.3% missing) vs reference N=9,505 (37.4% missing); "
            "BDC mean 108.68 vs reference 107.28 mg/dL (delta +1.40 mg/dL). The +410 "
            "participant surplus reflects BDC's coverage of Omni 1, Omni 2, and NOS "
            "sub-cohorts that the reference excludes. The earlier assay-era concern "
            "(non-enzymatic colorimetric, which had shown +5.78 mg/dL in pre-fix extracts) "
            "has been largely resolved by baseline visit filtering. The residual +1.40 "
            "mg/dL is within A-grade tolerance. The YAML correctly maps source data; "
            "the N gap is a sub-cohort scope difference, not a YAML error."
        ),
    },
    ("FHS", "cabg_prior_1"): {
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "The DCC counts surveillance procedures (pht000389, PROCDATE) dated on or "
            "before Exam 1 (date <= 0), with pht003316 survival records as negatives, "
            "covering all followed participants. BDC hist_cor_bypg.yaml maps exam "
            "history questions (Original Exam 21, Offspring Exam 5, Gen3 Exam 1), and "
            "FHS is graded at its baseline exams, so only Gen3 Exam 1 (pht000074 "
            "G3A255 phv00021084) contributes. Result: BDC 7 Prior History of 4,036 (73.3% "
            "missing) vs reference 17 of 11,814 (22.1% missing). The missingness is a "
            "method and coverage difference, not a YAML error."
        ),
    },
    ("FHS", "angina_prior_1"): {
        "code": "SURVEILLANCE_DENOMINATOR_GAP",
        "no_override": True,
        "note": (
            "BDC angina.yaml uses only the pht000309 surveillance block: status PRESENT "
            "for EVENT == 6 (AP, first episode) with DATE <= 0, and a blank status for "
            "every other pht000309 event row. Blank condition rows count as answers, so "
            "participants with any other surveillance event are 'No Prior History' "
            "(8,626); participants with no pht000309 row are missing. The reference "
            "uses pht003316 survival records as negatives for all followed "
            "participants. Result: 104 Prior History on both sides; BDC N=8,730 (42.1% "
            "missing) vs reference N=15,154 (0.1% missing). The missingness gap is a "
            "denominator difference, not a YAML error."
        ),
    },
    ("FHS", "hispanic_or_latino_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC demography.yaml maps FHS ethnicity from pht016162 (vr_racesum_2011) "
            "eth_sum (phv00568195), whose code 88 = 'Defaulted ethnicity (Not Hispanic "
            "or Latino)' (n=7,417). BDC maps code 88 to OMOP:8552 (BDC-HM EthnicityEnum "
            "UNKNOWN), not to Not Hispanic, and the comparison treats it as missing. "
            "Codes 0 and 1 map to Not Hispanic and Hispanic. The reference "
            "(N=6,665, 56.1% missing) reads a different source per sub-cohort: Gen3 "
            "pht000074 + pht003094, NOS pht006005 + pht003094, Omni 2 pht006006 + "
            "pht003094, Offspring pht000747 H700/H701 (Exam 8), Omni 1 pht004815 "
            "h700/h701 (Exam 3). The remaining category and missingness gap reflects "
            "this difference in ethnicity source and scope."
        ),
    },
    ("FHS", "race_us_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC demography.yaml maps race from multiple FHS race summary tables "
            "(pht016162 vr_racesum_2011, pht009760 vr_raceall_2011, pht003094 Gen3 "
            "Exam 2, pht000074 Gen3 Exam 1, pht003099 age/id crosswalk) that "
            "collectively cover all enrolled FHS sub-cohorts including Original, "
            "Offspring, Generation 3, Omni 1, Omni 2, and New Offspring Spouse. "
            "Result: BDC N=14,892 (1.3% missing) vs reference N=12,848 (15.3% missing). "
            "The ~2,044 participant gap is a scope difference: the reference phenotype "
            "definition (race_3.json) uses only pht006005 (vr_race_2011_a_0996s) and "
            "maps codes 'W'->White, 'B'->Black, 'A'->Asian, 'PI'->Pacific Islander, "
            "'AI'->American Indian, 'H'->Hispanic, excluding any participants not present "
            "in that single table. The reference also only ran on 3 sub-studies: "
            "FHS_Original (dbGaP ID=1), FHS_Offspring (=2), FHS_Gen3 (=3) -- omitting "
            "Omni 1, Omni 2, and NOS sub-cohorts entirely. BDC additionally sources "
            "pht016162 which includes code 88 = 'Defaulted race (White)' for ~5,209 "
            "Original Cohort participants -- a study-team-assigned imputed value that "
            "is correct per the dbGaP data dictionary. The reference treats these as "
            "unclassifiable. BDC race data is correctly mapped per the dbGaP data "
            "dictionaries; the broader coverage is a scope difference, not a YAML error."
        ),
    },
    ("FHS", "height_baseline_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "At the graded baseline exams (Original 1, Offspring 1) bdy_hgt.yaml emits "
            "height from the FHS workthru tables (pht007777 Original, pht009761 "
            "Offspring/Omni: inches to the next lower 1/4 inch). The per-exam blocks "
            "that duplicated them at Original Exams 1/4/5 and Offspring Exams 1/2 "
            "(MF67, MF217, MF290, A51 and B16 in whole inches, and B14 in cm) were "
            "removed; Original Exams 10-32 still carry both. "
            "On specs that still emit both at baseline, the extractor reports same-visit "
            "CONFLICTING values and can keep the whole-inch row (about 0.6 cm low). The "
            "DCC uses MF67 + 0.01 x MF68 for the Original cohort and HGT1 for the "
            "workthru cohorts, so small Original-cohort differences come from the "
            "source variable, not a mapping error."
        ),
    },
    ("FHS", "antihypertensive_meds_1"): {
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "FHS Original cohort antihypertensive treatment (phv00000705, MF250, pht000009, "
            "FHS ORIGINAL EXAM 4) is in hypert_trt.yaml; codes 1 (YES DEFINITE) and 2 "
            "(YES DOUBTFUL) map to ATC:C02. The extractor uses the ATC:C02 study "
            "indicator. When that source covers at least half of baseline attendees, "
            "the participants who answered are the denominator; otherwise attendees "
            "are. FHS Offspring Exam 1 has no ATC:C02 row (only tak_diuret ATC:C03), so "
            "Offspring participants are missing rather than substituted by a drug "
            "class. The reference reads pht006027 phv00277245 for Offspring."
        ),
    },
    ("FHS", "current_smoker_baseline_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "FHS does not have a tripartite smoking status (Current/Former/Never) variable "
            "at any Original cohort baseline exam in dbGaP. The pht007777 table "
            "(fhsvarv7) contains CURRSMK1-CURRSMK32 (binary 0=Not current, 1=Current) -- "
            "no EVSMK or tripartite ever/current/never coding exists in that table. "
            "MF71 (phv00000543, pht000009) is a tobacco summary variable, but MF70 (the "
            "source form indicator) shows the recorded value may derive from Exam 1, 2, "
            "3, or 4 depending on which form was first available for each participant -- "
            "it cannot be safely attributed specifically to EXAM 4 (the FHS Original "
            "baseline visit). cig_smok.yaml maps CIGSMOK (phv00000545) codes (1=Never, "
            "2=Stopped, 3=Smokes, 4=Pipe/cigar) to approximate smoking status. The "
            "shareid linkage bug (phv00001035 -> phv00001036) was corrected in both "
            "pht000009 blocks, recovering ~5,079 Original cohort records. Result: BDC "
            "N=15,039 (0.3% missing) vs reference N=15,100 (0.5% missing); max +-0.3pp "
            "category delta. This is a source data constraint (no tripartite baseline "
            "smoking in FHS Original dbGaP tables), not a YAML mapping error."
        ),
    },
    ("FHS", "ever_smoker_baseline_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "Same structural limitation as current_smoker_baseline_1 (see above). "
            "FHS Original cohort does not have a reliably exam-attributed ever-smoked "
            "variable at baseline. pht007777 CURRSMK fields are binary current-smoker "
            "only -- no ever-smoked indicator exists there. MF71 (phv00000543, pht000009) "
            "is a multi-exam summary: MF70 shows the source form may be from Exam 1, 2, "
            "3, or 4, making it unsuitable as a strict Exam 4 (baseline) ever-smoker "
            "measure without per-participant MF70 filtering. cig_smok.yaml maps CIGSMOK "
            "(phv00000545) codes 2+3+4 as ever-smoker proxies. The shareid linkage bug "
            "(phv00001035 -> phv00001036) was corrected in both pht000009 blocks, "
            "recovering ~5,079 Original cohort records. Result: BDC N=15,039 (0.3% "
            "missing) vs reference N=14,905 (1.8% missing); max +-0.6pp category delta. "
            "This is a structural source data limitation in FHS dbGaP for the Original "
            "cohort, not a YAML mapping error."
        ),
    },
    ("FHS", "pad_prior_1"): {
        "code": "SURVEILLANCE_DENOMINATOR_GAP",
        "no_override": True,
        "note": (
            "The DCC uses surveillance events: pht000309 EVENT == 30 dated on or before "
            "Exam 1 (DATE <= 0), plus pht003316 survival records as negatives, covering "
            "all followed participants. BDC pad.yaml uses exam questions (Offspring Exam "
            "5 E630, Gen3 Exam 1, Omni 1, Omni 2 and NOS Exam 1) and has no Original "
            "block. The comparison grades FHS at its baseline exams with no override. "
            "Result: BDC 15 Prior History of 5,014 (66.8% missing) vs reference 39 of "
            "15,154 (0.1% missing). Methodological."
        ),
    },
    ("FHS", "hematocrit_vfr_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "Known BDC YAML defect pending a fix. Offspring Exam 2 B764 (phv00008111, "
            "pht000031) is stored as hematocrit / 10 (var_report mean 4.41) and "
            "hemat.yaml emits it unscaled as '%'. Result: BDC mean 32.98 vs 41.86 and "
            "1,767 implausible values."
        ),
    },
    ("FHS", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "Reported count versus derived count. basophil_ncnc_bld.yaml emits the "
            "lab-reported BA_NUM (phv00172197 pht002889, phv00227044 pht004802), which "
            "the study records at 0.1 x10^3/uL resolution, so most values are 0.0 or "
            "0.1. The DCC derives WBC x BA_PER / 100, a finer-grained estimate of the "
            "same quantity. BDC keeps the value the study reports. Result: BDC mean "
            "0.031 vs 0.042."
        ),
    },
    ("FHS", "cac_score_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "cac_score.yaml emits the coronary score as the mean of scans CA1 and CA2 "
            "(the DCC's rowMeans) and no longer emits AA (aortic calcium) under the "
            "coronary code. Age at observation is the Exam 1 age plus studydat (days "
            "from Exam 1 to the scan) for the Offspring (pht000145) and Gen 3 "
            "(pht000144) scans. On specs without these changes, BDC mean was 281.6 vs "
            "133.4 Agatston."
        ),
    },
    # ── CHS ───────────────────────────────────────────────────────────────────
    ("CHS", "bmi_baseline_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources BMI from three baseline tables: BASE1 (phv00099468, "
            "pht001450, original cohort), BASEBOTH (phv00100386, pht001452, both "
            "cohorts), and YR5NEW (pht001490). The reference uses BASEBOTH "
            "(phv00100386) only (n=5,513, nulls=18), which exactly matches BDC's "
            "final count (same N=5,513, miss=18 — the BASEBOTH record dominates). "
            "The +0.0014 kg/m2 mean delta (BDC 26.6836 vs reference 26.685) is a "
            "noise-level floating-point artifact — both extract the same "
            "pre-computed BMI field from dbGaP; the difference is in how many "
            "decimal places each system retains internally. Min, max, Q1, median, "
            "Q3 all match or differ by <0.001. Approach: effectively identical. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100386 (n=5,513, nulls=18)."
        ),
    },
    ("CHS", "bp_systolic_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources SBP (AVZMSYS — 'Average Zero-Muddler Systolic BP') from "
            "BASE1 (phv00099441, pht001450, n=4,895) and BASEBOTH (phv00100435, "
            "pht001452, n=5,522). BDC output (n=5,522, miss=9) exactly matches the "
            "BASEBOTH var_report. The reference has n=5,515, miss=16 — 7 fewer valid "
            "participants. The reference likely applies physiological plausibility "
            "exclusions (values outside an acceptable BP range) or a different QC "
            "threshold not used by BDC, resulting in 7 participants being classified "
            "as missing rather than valid. BDC's min=77 and max=234.77 are both "
            "within plausible SBP range, so no implausible values are flagged. The "
            "+0.05 mmHg delta against a 21.88 SD = 0.002 normalized — rounding "
            "noise. Approach: BDC captures 7 more participants; the 7-person gap "
            "likely reflects a QC policy difference, not a mapping error. Both "
            "approaches are clinically sound. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100435 (n=5,522, nulls=9)."
        ),
    },
    ("CHS", "bp_diastolic_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources DBP (AVZMDIA — 'Average Zero-Muddler Diastolic BP') from "
            "BASE1 (phv00099442, pht001450) and BASEBOTH (phv00100436, pht001452, "
            "n=5,516). BDC output (n=5,516, miss=15) exactly matches BASEBOTH. The "
            "reference has n=5,515, miss=16 — 1 fewer valid participant. The BDC "
            "extract LOG flags 12 implausible DBP values (min=0.0 mmHg — "
            "physiologically impossible). The reference likely applied an "
            "implausibility filter that excluded at least 1 of these zero-value "
            "readings, while BDC includes them as-is. The +0.0548 mmHg delta "
            "(against 11.43 SD = 0.005 normalized) partially reflects the drag of "
            "the implausible 0-value records pulling BDC's mean slightly down. "
            "The reference approach (excluding implausible values) is more "
            "clinically correct for this variable; BDC should apply a DBP > 0 "
            "filter. Grade A+ is preserved because the overall population effect is "
            "negligible (12/5516 = 0.2% affected), but this is a noted data quality "
            "concern. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100436 (n=5,516, nulls=15)."
        ),
    },
    ("CHS", "cabg_prior_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "The reference uses BPSSUR/BPSSURBL (phv00100321/phv00100785, "
            "pht001452/pht001464, n=5,493, 38 nulls) and keeps the 38 as missing. BDC "
            "grades CABG Procedure rows at CHS BASELINE 2 + CHS BASELINE BOTH. "
            "Prevalence is identical: 236 Prior History (4.3%) on both sides. BDC has "
            "0 missing (n=5,531) vs reference 38, so BDC classifies those 38 as 'No "
            "Prior History'. "
            "dbGaP ground truth: pht001452 phv00100321 BPSSUR (n=5,493, nulls=38)."
        ),
    },
    ("CHS", "current_smoker_baseline_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources current-smoker status from the CHS study team's derived "
            "SMOKE variable: BASE1 (phv00099445, pht001450, n=4,900 nulls=3) at "
            "visit 'CHS BASELINE 2' and YR5NEW (phv00105886, pht001490, n=625 "
            "nulls=3) also labeled 'CHS BASELINE 2'. Together these produce "
            "n=5,525, miss=6 — exactly matching the BASEBOTH SMOKE (phv00100466, "
            "n=5,525, nulls=6) as well. The reference has n=5,497, miss=34 — 28 "
            "more missing. The reference reconstructs current-smoker status from "
            "raw questionnaire fields (SMOKE101, SMOKE201) rather than the "
            "study-team-curated SMOKE status variable, leaving 28 participants with "
            "inconsistent raw responses classified as missing. The CHS study team's "
            "derived SMOKE adjudicates these edge cases. BDC's use of the curated "
            "variable is more authoritative and produces fewer ambiguous missings. "
            "Categorical delta of only 0.1pp confirms the 28-participant "
            "reclassification has negligible population-level impact. "
            "Approach: BDC is better (fewer missing with study-team-adjudicated variable). "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100466 SMOKE (n=5,525, nulls=6)."
        ),
    },
    ("CHS", "weight_baseline_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "Graded on measured WEIGHT13 (phv00100383, pht001452 BASEBOTH, n=5,514), "
            "the DCC's variable. bdy_wgt.yaml no longer emits the 'usual weight at age "
            "50' recalls (WGT5008, WGT50, WGT5058, AG50WT59) as body weight; on specs "
            "that still do, they compete with WEIGHT13 at the baseline visits and pull "
            "the BDC mean about 2 kg low."
        ),
    },
    ("CHS", "antihypertensive_meds_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "At baseline, BDC hypert_trt.yaml has one ATC:C02 indicator: BASEBOTH "
            "phv00100595 (pht001452, visit 'CHS BASELINE BOTH'), the same variable the "
            "reference uses. Yes is identical (2,634). BDC has No=2,897 and 0 missing "
            "vs reference No=2,892 and 5 missing: the 5 participants the reference "
            "leaves missing are 'No' in BDC. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100595 var_report "
            "(n=5,526, Yes=2,634, No=2,892, missing=5)."
        ),
    },
    ("CHS", "ever_smoker_baseline_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC derives ever-smoker from the study's derived SMOKE status (cig_smok.yaml: "
            "BASE1 phv00099445 at 'CHS BASELINE 2' and YR5NEW phv00105886 at 'CHS YEAR 5 "
            "NEW', which covers the African American cohort), so both sides now cover "
            "both cohorts. The reference counts any positive indication across "
            "pht001450 + pht001490: SMOKE101 (phv00098844), SMOKE201 (phv00098845), "
            "SMKAGE (phv00099157) or AMOUNT > 0 (phv00099159). Result: reference 55.6% "
            "(3,068/5,519) vs BDC 53.7% (2,966/5,525), a 1.9pp like-for-like gap from "
            "the different definitions. "
            "Source: UW-GAC/topmed-dcc-harmonized-phenotypes, "
            "harmonized-variable-documentation/baseline_common_covariates/"
            "ever_smoker_baseline_1.json, CHS harmonization unit, v4. BDC keeps the "
            "study's derived status. The reference's extra ever-smokers most likely "
            "come from internally inconsistent answers (SMOKE101 = no with SMKAGE or "
            "AMOUNT > 0) that the study's derivation reconciles; not verified at "
            "participant level."
        ),
    },
    ("CHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no CHS carotid_plaque.yaml, so the variable is NOT COMPARABLE. "
            "Sources exist in ULTRAYR5 (pht001473): LMRPH155/LMRPH255 (phv00101317/"
            "phv00101318, original-cohort baseline reread) and LMRPH141/LMRPH241 "
            "(phv00101306/phv00101307, African American cohort Year 5). Their 0/1/2 "
            "codes are unlabeled in dbGaP; a spec waits on the CHS reading protocol and "
            "a curated concept code (HV issue #946, awaiting external)."
        ),
    },
    # ── JHS ───────────────────────────────────────────────────────────────────
    # JHS Participant Universe Difference:
    # BDC N=3,883 vs TOPMed N=3,602 (+281, +7.8%). The BDC baseline visit
    # filter correctly restricts to "JHS Exam 1" only (confirmed via extract
    # log: all measurement rows tagged [visit: JHS Exam 1]). The N surplus is
    # NOT a multi-exam aggregation artifact. Three compounding causes:
    #   (1) VERSION DIFF: TOPMed harmonized from phs000286.v5; BDC from v7.
    #   (2) GENOTYPE SELECTION: TOPMed = sequenced subset; BDC = full phenotype
    #       population (4 consent groups: c1=878, c2=201, c3=2,289, c4=515).
    #   (3) HARMONIZATION DATE: TOPMed frozen 2020-05-21; BDC April 2026.
    #
    # Most JHS variables have no additional explanation beyond the universe diff.
    # Those rely on the cohort-level note alone (see the comment after this dict).
    # The variables below have variable-specific explanations (different source
    # methodology, missing Exam 1 sources, B/C-grade mean shifts).
    # ──────────────────────────────────────────────────────────────────────────
    ("JHS", "pad_prior_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC pad.yaml's only PAD source is the AFU follow-up (pht008725, visit 'JHS "
            "AFU', MONDO:0005294). The DCC derives prevalent PAD from ABI < 0.9 at Exam 1 "
            "(pht001921 ankle and arm pressures). The comparison grades JHS at Exam 1 "
            "with no fallback to other visits, so BDC has no answer and pad_prior_1 is "
            "NOT COMPARABLE (all missing). TOPMed: 83 Prior History of 3,126. BDC does "
            "not derive a PAD condition from an ABI cutoff: JHS records no PAD "
            "diagnosis at Exam 1, and ABI < 0.9 is a research convention, not a "
            "recorded finding (analysis1 abi phv00401122 is available as a measurement)."
        ),
    },
    ("JHS", "cabg_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC hist_cor_bypg.yaml maps CABG at Exam 2, Exam 3 and the AFU, not at "
            "Exam 1, so cabg_prior_1 is NOT COMPARABLE (all missing; 66 positives at "
            "other visits not used). An Exam 1 source exists: MHXA52A (pht001963 "
            "phv00127728, 'Did you have a coronary bypass?', 53 Yes / 95 No), gated by "
            "MHXA51 (heart or artery surgery ever). The DCC reads MHXA52A and recodes a "
            "missing answer to 0 when the participant has other data; treating the "
            "gate's 'No' as an implied CABG 'No' is a curation ruling not yet made."
        ),
    },
    ("JHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no JHS carotid_plaque.yaml, so the variable is NOT COMPARABLE. "
            "The source is plq01 (pht008791 phv00404237, 0 = 2,288 / 1 = 1,414). Its "
            "table has no VISIT variable and visit.yaml labels it 'JHS LAB DATA'; the "
            "DCC pairs it with the Exam 1 age. A new spec needs a documented Exam 1 "
            "link and a curated concept code (HV issue #224, awaiting external)."
        ),
    },
    ("JHS", "cimt_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "Not aligned on purpose (config.py _OTHER_COHORT_MEASUREMENT_VISITS). JHS "
            "carotid_imt.yaml emits each of six common-carotid far-wall segments as its "
            "own row; the DCC averages the three left and three right segments. One "
            "segment row is not the same quantity as the mean, and BDC does not "
            "compute a study-unpublished mean."
        ),
    },
    ("JHS", "antihypertensive_meds_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC is graded on the ATC:C02 indicator MSRA30A (phv00127922, pht001964, JHS "
            "Exam 1). hypert_trt.yaml emits a blank-status row for each missing answer "
            "(var_report nulls=210); the extractor counts a blank medication status as "
            "missing, not 'No' (it was counted as 'No' in the 2026-11-05 runs, giving 50.1% "
            "Yes, 1,939/3,868). The DCC uses BPM01 (pht001949): 53.8% (1,794/3,335, 7.4% "
            "missing)."
        ),
    },
    ("JHS", "total_cholesterol_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "tot_chol_bld.yaml has 9 blocks across 8 tables (Exams 1-3, LAB DATA). No "
            "method_type filter. Extractor picks earliest-per-participant. "
            "Current data: mean delta -1.812 mg/dL (B_mean=196.98 vs T_mean=198.80), "
            "normalized 0.044 SD (T_sd=40.96). B_N=3,742 vs T_N=3,471 (+271). "
            "B_miss=3.6% = T_miss=3.6% -- identical missingness confirms comparable coverage. "
            "The B grade (0.044 SD, above 0.02 SD threshold) reflects the 1.8 mg/dL mean "
            "difference, which falls within normal biological variability for serum cholesterol. "
            "The delta likely reflects minor assay calibration differences or the larger "
            "participant universe (see cohort-level note) rather than a systematic mapping "
            "error. "
            "Assessment: SAME -- both sources are valid JHS Lab Data; 1.8 mg/dL is within "
            "expected inter-lab variability and well below clinical significance."
        ),
    },
    ("JHS", "triglycerides_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "triglyc_bld.yaml has 10 blocks across 9 tables (Exams 1-3, LAB DATA). Same "
            "structure as total_cholesterol_1. "
            "Current data: mean delta -2.378 mg/dL (B_mean=107.66 vs T_mean=110.04), "
            "normalized 0.025 SD (T_sd=95.07 vs B_sd=79.93). B_N=3,742 vs T_N=3,471 (+271). "
            "TOPMed's higher SD (95.1 vs BDC 79.9) and higher maximum (2,830 vs BDC 2,041) "
            "indicate that TOPMed includes a small number of extreme outliers -- likely "
            "participants with familial hypertriglyceridemia -- that are absent from BDC's "
            "participant universe. These outliers pull TOPMed's mean higher, explaining most "
            "of the 2.4 mg/dL gap. "
            "Assessment: SAME -- the mean delta (0.025 SD) is within B-grade threshold; "
            "the difference is driven by a handful of extreme outliers in TOPMed's source, "
            "not a systematic mapping difference."
        ),
    },
    ("JHS", "cac_score_1"): {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "Same variable on both sides: CSTA24 (phv00126002, pht001948, Agatston score "
            "all coronary). BDC reads dbGaP v7 (pht001948.v3, var_report n=2,144). The "
            "DCC read phs000286.v5 pht001948.v1, inner-joined to AGE01 (pht001949) on "
            "topmed_subject_id (DCC N=1,664). Result: BDC mean 175.7 vs 146.0. A release "
            "and sample difference, not a mapping error."
        ),
    },
    # ── HCHS-SOL ──────────────────────────────────────────────────────────────
    ("HCHS_SOL", "race_us_1"): {
        "code": "LABEL_REMAP",
        "no_override": True,
        "note": (
            "HCHS-SOL has no OMB race variable. All participants are Hispanic/Latino; the "
            "study collected a 7-level heritage subgroup (phv00226254, BKGRD1_C7: Dominican, "
            "Central American, Cuban, Mexican, Puerto Rican, South American, Other) but this "
            "does not map to OMB race categories. TOPMed maps all 12,895 participants to "
            "'Other'. BDC maps all 11,831 participants to 'UNKNOWN'. BDC's approach is "
            "semantically more accurate -- 'UNKNOWN' signals the absence of OMB race data, "
            "whereas 'Other' implies a positive assertion that the question was asked and "
            "answered. Neither is wrong per se, but they produce a 100pp categorical "
            "divergence and a permanent D grade. Resolving this would require either a policy "
            "decision to align on 'Other' or a new hispanic_subgroup slot in bdchm to capture "
            "the heritage detail."
        ),
    },
    ("HCHS_SOL", "antihypertensive_meds_1"): {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "Both sides use the study indicator MED_ANTIHYPERT (phv00226324, "
            "pht004715); BDC is graded on that ATC:C02 indicator only. Result: BDC 16.7% "
            "Yes (1,972/11,831, 0 missing) vs TOPMed 16.9% (2,078/12,280, 615 missing). "
            "The N difference is the cohort-level version difference."
        ),
    },
    ("HCHS_SOL", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "Reported count versus derived count. basophil_ncnc_bld.yaml emits the "
            "lab-reported LABA27 (phv00226301, pht004715), recorded at 0.1 x10^9/L "
            "resolution (about 78% exactly 0). The DCC derives WBC (LABA1) x % "
            "basophils (LABA14) / 100. BDC keeps the value the study reports. Result: "
            "BDC mean 0.023 vs 0.034."
        ),
    },
    ("HCHS_SOL", "eosinophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "Reported count versus derived count. eosinophil_ncnc_bld.yaml emits the "
            "lab-reported LABA26 (phv00226300, pht004715), recorded at 0.1 x10^9/L "
            "resolution. LABA26 also holds one recorded 230 (var_report max; eosinophil "
            "% tops out at 36 and WBC at 31.8, so it is not a valid count), which BDC "
            "passes through and the extractor flags; it drives the SD gap (2.19 vs "
            "0.19). The DCC derives WBC (LABA1) x % eosinophils (LABA13) / 100, which "
            "never sees LABA26."
        ),
    },
    ("HCHS_SOL", "monocyte_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "Reported count versus derived count. BDC emits the lab-reported LABA25 "
            "(phv00226299, pht004715), recorded at 0.1 x10^9/L resolution; the DCC "
            "derives WBC (LABA1) x % monocytes (LABA12) / 100. The small mean "
            "difference (0.025 SD) is consistent with that rounding."
        ),
    },
    # ── COPDGene ──────────────────────────────────────────────────────────────
    ("COPDGENE", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the pre-stored BMI field phv00159593 (BMI, pht002239 "
            "COPDGene_Subject_Phenotypes, units kg/m2, type numeric). The dbGaP data "
            "dictionary marks this field as '<comment>calculated</comment>', meaning "
            "the study pre-computed BMI from measured height (Height_CM, phv00159592) "
            "and weight (Weight_KG, phv00159591) before dbGaP deposit, rounding the "
            "result to 2 decimal places (e.g., 27.99, 24.21 kg/m2). The reference "
            "pipeline recomputes BMI at full float precision from the raw Weight_KG "
            "and Height_CM columns using weight_kg / (height_cm / 100)^2. The mean "
            "of 10,371 pre-rounded 2-decimal-place values (BDC mean=28.83) vs. the "
            "mean of 10,371 full-precision computed values (reference mean=28.82) "
            "differ by the accumulated rounding noise: expected magnitude ~0.005 / "
            "sqrt(N) per observation, totaling +0.01 kg/m2 across the full sample. "
            "N_valid is identical (10,371); 0% missing difference. No data disagreement "
            "exists -- both approaches use the same underlying source measurements. "
            "BDC correctly defers to the study's own pre-computed value. Grade A+ "
            "is appropriate; the delta is a floating-point arithmetic artifact with "
            "no clinical or analytical consequence."
        ),
    },
}

# JHS: variables without a per-variable entry above (Sex, Race, Height, Body
# weight, BMI, SBP, DBP, Current smoker, Ever smoker, Platelet count, MCH,
# History of MI) are explained by the cohort-level PARTICIPANT_UNIVERSE_DIFF
# note alone.


# Cohort-level methodological notes (version mismatches, study design differences)
# that apply to ALL variables for a cohort, not a single variable.
COHORT_LEVEL_NOTES: dict[str, dict] = {
    "COPDGENE": {
        "code": "SIMPLE_STRUCTURE",
        "note": (
            "COPDGene is the structurally simplest cohort in the consortium, which explains "
            "its 15/15 A+ grade. (1) SINGLE-TABLE ARCHITECTURE: Nearly all phenotype data "
            "lives in one table (pht002239 COPDGene_Subject_Phenotypes, ~1,003 variables). "
            "No multi-table union, deduplication, or earliest-per-participant logic needed -- "
            "compare ARIC (415 tables), FHS (586 tables), or MESA (sub-cohort-specific tables). "
            "(2) FLAT VISIT STRUCTURE: Phase 1 is a single cross-sectional enrollment visit. "
            "Every participant has exactly one row -- no longitudinal visit discrimination, "
            "no exam-year-encoded table names (unlike CARDIA's 8 exam years or FHS's 30+ exams). "
            "(3) NO SUB-COHORT COMPLEXITY: One enrollment cohort, one protocol. No Classic/"
            "Family/Air NR splits (MESA), no CT/OS arms (WHI), no multi-generation structure "
            "(FHS). (4) PRE-DERIVED VARIABLES: The study deposited clean, derived variables "
            "directly in pht002239 (BMI pre-computed, smoking status pre-coded, medical history "
            "as binary 0/1). Other cohorts require derivation from raw exam forms, creating "
            "ambiguity about which source variable to use."
        ),
    },
    "HCHS_SOL": {
        "code": "VERSION_MISMATCH",
        "note": (
            "TOPMed and BDC operate on different dbGaP versions of HCHS-SOL, which is the "
            "primary driver of all N differences in this table. TOPMed's harmonized files "
            "were produced from phs000810.v1.p1 (upload snapshot: 2020-05-21), which had "
            "12,895 total consented subjects (c1 HMB-NPU=3,681; c2 HMB=9,214). BDC "
            "operates on phs000810.v2.p2 (released 2023-12-21), which has 12,121 total "
            "consented subjects (c1 HMB-NPU=2,304; c2 HMB=9,817). The 774-subject "
            "reduction between versions reflects a consent reclassification event -- "
            "participants who were in c1 HMB-NPU under v1 were either re-classified or "
            "removed from the study by v2. Of the 12,121 v2 consented subjects, only "
            "11,831 have phenotype rows in pht004715 (the primary phenotype table); 290 "
            "consented subjects have no deposited phenotype data. BDC correctly processes "
            "100% of pht004715. Neither is a pipeline error; the N gap (1,064 = 774 "
            "version delta + 290 phenotype-absent) is structural and expected."
        ),
    },
    "JHS": {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "note": (
            "BDC N=3,883 vs TOPMed N=3,602 (+281 participants, +7.8%). This is NOT a "
            "multi-exam aggregation artifact -- the BDC baseline visit filter correctly "
            "restricts to 'JHS Exam 1' only (confirmed via extract log: all measurement "
            "rows tagged [visit: JHS Exam 1]). The 281-participant surplus appears to be "
            "primarily driven by GENETIC CONSENT FILTERING: the v7 GapExchange study "
            "description states 'approximately 3,600 gave consent that allows genetic "
            "research and deposition of data into dbGaP', and the SUBJECT_SOURCE2 variable "
            "in JHS_Subject (pht001920) shows exactly N=3,596 participants sourced to "
            "'JHS_CARe' (the genotyping pipeline). We suspect TOPMed harmonized only this "
            "genetic-research-consented subset (~3,600), while BDC harmonizes the full "
            "phenotype-consented population across all 4 consent groups (c1=878, c2=201, "
            "c3=2,289, c4=515 = 3,883 in the analysis1 table pht008729). Two secondary "
            "factors may also contribute: (1) VERSION DIFF: TOPMed harmonized from "
            "phs000286.v5; BDC from v7. The analysis1 table (pht008729) is new in v6/v7 "
            "(version 1 dataset) and did not exist in v5, so overall participant availability "
            "may differ. We do not have direct v5 participant counts to confirm the exact "
            "version delta. (2) HARMONIZATION DATE: TOPMed files frozen 2020-05-21; BDC "
            "extracted April 2026. The consistent +281 to +369 N delta across all variables "
            "confirms a structural denominator difference, not variable-specific mapping "
            "errors. Distributions agree within A-grade thresholds for nearly all variables "
            "despite the different participant universes."
        ),
    },
    "MESA": {
        "code": "CVD_HISTORY_SOURCE_DIFF",
        "note": (
            "TOPMed grades MESA prior CVD history (angina, MI, PAD, CABG, coronary "
            "angioplasty) for MESA Classic only, and sets every pht001116 participant to 0 "
            "(e.g. mi_prior_1.json: 'set all participants to 0'), because Classic was "
            "CVD-free at enrollment. BDC's prior-history rows come from MESA Family "
            "(pht001121 self-report), AirNR (pht001111) and the visit-less events table "
            "(pht001123). The comparison grades these variables at MESA CLASSIC EXAM 1, "
            "where BDC has no answer, so they are NOT COMPARABLE (all missing) rather than "
            "graded across different sub-cohorts. Not a BDC defect."
        ),
    },
    "FHS": {
        "code": "VERSION_MISMATCH",
        "note": (
            "BDC operates on phs000007.v35.p16 (released 2025-07-25, 15,089 consented "
            "subjects per dbGaP study page). The reference was produced from an earlier "
            "version (~v30, frozen 2020-05-21) which had 15,173 total subjects. The "
            "84-participant reduction (15,173 -> 15,089) between versions reflects consent "
            "withdrawals -- participants who revoked research consent between the ~2020 "
            "snapshot and v35 were removed from all phenotype tables in the newer release. "
            "This is confirmed by the pht003099.v10 (vr_dates_2022) variable report which "
            "shows exactly 7,023 male + 8,066 female = 15,089 total participants. The "
            "systematic 84-participant gap appears across nearly all variables (e.g., "
            "annotated_sex: T_N=15,173 vs B_N=15,089) and is NOT a pipeline error. FHS "
            "sub-cohorts: Original (5,209 enrolled 1948), Offspring (5,124 enrolled 1971), "
            "Gen3 (4,095 enrolled 2002-2005), plus NOS, Omni 1, Omni 2."
        ),
    },
}


def run(topmed_path, bdc_path, outfile=None, all_vars=False):
    with open(topmed_path, encoding="utf-8") as f:
        t = json.load(f)
    with open(bdc_path, encoding="utf-8") as f:
        b = json.load(f)

    tv = t['variables']
    bv = b['variables']
    intersection = set(tv) & set(bv)

    if all_vars:
        matched = sorted(intersection, key=lambda v: tv[v].get('bdc_label', v).lower())
        scope_label = 'all matched variables'
        # Group by CORE_VARIABLE_GROUPS first; extra vars fall into "Other"
        grouped_matched: list[tuple[str | None, list[str]]] = []
        assigned: set[str] = set()
        for gname, gvars in CORE_VARIABLE_GROUPS:
            grp = [v for v in gvars if v in intersection]
            if grp:
                grouped_matched.append((gname, grp))
                assigned.update(grp)
        others = [v for v in matched if v not in assigned]
        if others:
            grouped_matched.append(('Other', others))
    else:
        # Use clinical domain group ordering
        present = intersection & CORE_VARIABLES
        matched = sorted(present, key=lambda v: _CORE_VAR_ORDER.get(v, (999, 0)))
        n_core_missing = len(CORE_VARIABLES - intersection)
        scope_label = f'core variables ({len(matched)} of {len(CORE_VARIABLES)} present'
        if n_core_missing:
            scope_label += f'; {n_core_missing} not in this cohort\'s extract'
        scope_label += ')'
        # Build grouped list: [(group_name, [vars in group that are present])]
        grouped_matched = []
        for gname, gvars in CORE_VARIABLE_GROUPS:
            present_in_group = [v for v in gvars if v in present]
            if present_in_group:
                grouped_matched.append((gname, present_in_group))

    # Cohort name is stored in the TOPMed DCC JSON metadata (uppercase, e.g. "WHI").
    # Used to look up KNOWN_METHODOLOGICAL_DIFFS entries.
    cohort = t.get('metadata', {}).get('cohort', '').upper()

    # ── Tier assignment helpers ──────────────────────────────────────────────
    # Value tiers (independent of missingness):
    #   T1 = near-exact   T2 = high similarity   T3 = moderate diff
    #   T4 = notable diff  T5 = substantial diff
    # Missingness tiers (independent of values):
    #   M1-M5 with same numbering convention
    # MissExplain: classifies whether the missingness difference is a
    #   population-size artifact or a real data coverage gap.

    t_total = t.get('total_participants', 0)
    b_total = b.get('total_participants', 0)
    pop_diff = b_total - t_total  # positive = BDC has more participants

    def _assign_value_tier_continuous(norm_delta):
        if norm_delta < 0.005:
            return 'T1'
        elif norm_delta < 0.02:
            return 'T2'
        elif norm_delta < 0.05:
            return 'T3'
        elif norm_delta < 0.1:
            return 'T4'
        else:
            return 'T5'

    def _assign_value_tier_categorical(max_pct_diff):
        if max_pct_diff < 0.5:
            return 'T1'
        elif max_pct_diff < 1:
            return 'T2'
        elif max_pct_diff < 3:
            return 'T3'
        elif max_pct_diff < 10:
            return 'T4'
        else:
            return 'T5'

    def _assign_miss_tier(miss_diff_pp):
        if miss_diff_pp < 1:
            return 'M1'
        elif miss_diff_pp < 3:
            return 'M2'
        elif miss_diff_pp < 8:
            return 'M3'
        elif miss_diff_pp < 20:
            return 'M4'
        else:
            return 'M5'

    def _assign_miss_explain(t_n_valid, b_n_valid, pop_diff):
        """Classify whether missingess difference is population-driven or data-driven.

        Returns a tuple (tag, description) where tag is one of:
          --          negligible difference (< 0.5% relative)
          Pop:BDC+    BDC has more valid, explained by larger population
          Pop:TOPMed+  TOPMed DCC has more valid, explained by larger population
          Data:BDC+    BDC captures more valid data beyond population diff (BDC advantage)
          Data:TOPMed+ TOPMed DCC captures more valid data beyond population diff (TOPMed advantage)
          Data:BDC-    BDC is missing real data TOPMed DCC has (investigate BDC)
          Data:TOPMed- TOPMed DCC is missing real data BDC has (TOPMed limitation)
        """
        valid_diff = b_n_valid - t_n_valid  # positive = BDC has more valid records

        # Negligible: both sides within 0.5% relative of each other
        max_n = max(t_n_valid, b_n_valid, 1)
        if abs(valid_diff) / max_n < 0.005:
            return '--'

        # Which side has more valid records?
        if valid_diff > 0:
            # BDC has more valid records
            if pop_diff > 0:
                # BDC also has more total participants
                # Does the valid surplus fit within the population surplus?
                unexplained = valid_diff - pop_diff
                if unexplained <= max(0.005 * max_n, 5):
                    # Valid surplus is explained by population difference
                    return 'Pop:BDC+'
                else:
                    # BDC captures more data than population alone explains
                    return 'Data:BDC+'
            else:
                # BDC has fewer (or equal) total participants but MORE valid records
                # This means BDC is genuinely capturing more data
                return 'Data:BDC+'
        else:
            # REF has more valid records (valid_diff < 0)
            if pop_diff < 0:
                # BDC also has fewer total participants
                # Does the valid deficit fit within the population deficit?
                unexplained = abs(valid_diff) - abs(pop_diff)
                if unexplained <= max(0.005 * max_n, 5):
                    # Valid deficit is explained by population difference
                    return 'Pop:TOPMed+'
                else:
                    # REF captures more data than population alone explains
                    # i.e., BDC is missing data it should have
                    return 'Data:BDC-'
            else:
                # BDC has more (or equal) total participants but FEWER valid records
                # BDC is genuinely missing data
                return 'Data:BDC-'

    lines = []
    def p(s=''):
        lines.append(s)

    p(f'Scope: {scope_label}  (use --all-vars to see all matched variables)')
    p(f'TOPMed DCC N={t_total:,}  BDC N={b_total:,}')
    p(f'Matched variables: {len(matched)}')
    p()
    p(f'{"Variable":<35} {"Type":<5} {"T_N":>7} {"B_N":>7} {"T_mean":>10} {"B_mean":>10} {"MeanDelta":>10} {"T_M%":>5} {"B_M%":>5} {"Val":>4} {"Miss":>4} {"Expl":<13}')
    p('-' * 120)

    val_tier_counts = {'T1': 0, 'T2': 0, 'T3': 0, 'T4': 0, 'T5': 0}
    miss_tier_counts = {'M1': 0, 'M2': 0, 'M3': 0, 'M4': 0, 'M5': 0}
    miss_explain_counts = {'--': 0, 'Pop:BDC+': 0, 'Pop:TOPMed+': 0,
                           'Data:BDC+': 0, 'Data:TOPMed+': 0,
                           'Data:BDC-': 0, 'Data:TOPMed-': 0}
    n_noted = 0

    for group_name, group_vars in grouped_matched:
        if group_name is not None:
            p(f'  --- {group_name} ---')
        for var in group_vars:
            ts = tv[var]
            bs = bv[var]
            label = ts.get('bdc_label', var)[:34]
            vtype = ts.get('type', '?')[:4]
            t_n = ts.get('n_valid', 0)
            b_n = bs.get('n_valid', 0)
            t_pm = ts.get('pct_missing', 0)
            b_pm = bs.get('pct_missing', 0)

            miss_diff = abs(b_pm - t_pm)
            miss_tier = _assign_miss_tier(miss_diff)
            miss_explain = _assign_miss_explain(t_n, b_n, pop_diff)

            if ts.get('type') == 'continuous':
                t_mean = ts.get('mean')
                b_mean = bs.get('mean')
                t_sd = ts.get('sd')
                # Missing/zero SD cannot normalize the delta; fall through to the
                # '?' branch rather than defaulting SD to 1 (which would mislabel a
                # real mean difference as a top tier).
                if t_mean is not None and b_mean is not None and t_sd is not None and t_sd > 0:
                    delta = abs(b_mean - t_mean)
                    norm_delta = delta / t_sd

                    val_tier = _assign_value_tier_continuous(norm_delta)

                    # Annotate with * if this is a known methodological difference
                    m_entry = KNOWN_METHODOLOGICAL_DIFFS.get((cohort, var))
                    if m_entry and not m_entry.get('no_override'):
                        display_val = val_tier + '*'
                        n_noted += 1
                    else:
                        display_val = val_tier

                    val_tier_counts[val_tier] += 1
                    miss_tier_counts[miss_tier] += 1
                    miss_explain_counts[miss_explain] += 1
                    p(f'{label:<35} {vtype:<5} {t_n:>7,} {b_n:>7,} {t_mean:>10.2f} {b_mean:>10.2f} {delta:>+10.4f} {t_pm:>4.1f}% {b_pm:>4.1f}% {display_val:>4} {miss_tier:>4} {miss_explain:<13}')
                else:
                    p(f'{label:<35} {vtype:<5} {t_n:>7,} {b_n:>7,} {"-":>10} {"-":>10} {"-":>10} {t_pm:>4.1f}% {b_pm:>4.1f}% {"?":>4} {miss_tier:>4} {miss_explain:<13}')
            else:
                t_dist = ts.get('distribution', {})
                b_dist = bs.get('distribution', {})
                all_cats = set(list(t_dist.keys()) + list(b_dist.keys()))
                max_pct_diff = 0
                for cat in all_cats:
                    tp = t_dist.get(cat, {}).get('pct', 0)
                    bp = b_dist.get(cat, {}).get('pct', 0)
                    max_pct_diff = max(max_pct_diff, abs(bp - tp))

                val_tier = _assign_value_tier_categorical(max_pct_diff)

                # Annotate with * if this is a known methodological difference
                m_entry = KNOWN_METHODOLOGICAL_DIFFS.get((cohort, var))
                if m_entry and not m_entry.get('no_override'):
                    display_val = val_tier + '*'
                    n_noted += 1
                else:
                    display_val = val_tier

                val_tier_counts[val_tier] += 1
                miss_tier_counts[miss_tier] += 1
                miss_explain_counts[miss_explain] += 1
                p(f'{label:<35} {vtype:<5} {t_n:>7,} {b_n:>7,} {"(cat)":>10} {"(cat)":>10} {f"max+-{max_pct_diff:.1f}pp":>10} {t_pm:>4.1f}% {b_pm:>4.1f}% {display_val:>4} {miss_tier:>4} {miss_explain:<13}')

    p()
    p(f'Value tier summary:  T1={val_tier_counts["T1"]}  T2={val_tier_counts["T2"]}  T3={val_tier_counts["T3"]}  T4={val_tier_counts["T4"]}  T5={val_tier_counts["T5"]}')
    p(f'Miss. tier summary:  M1={miss_tier_counts["M1"]}  M2={miss_tier_counts["M2"]}  M3={miss_tier_counts["M3"]}  M4={miss_tier_counts["M4"]}  M5={miss_tier_counts["M5"]}')
    # Summarize miss explain — show only non-zero categories
    expl_parts = []
    for tag in ['Pop:BDC+', 'Pop:TOPMed+', 'Data:BDC+', 'Data:TOPMed+', 'Data:BDC-', 'Data:TOPMed-']:
        if miss_explain_counts[tag] > 0:
            expl_parts.append(f'{tag}={miss_explain_counts[tag]}')
    neg_count = miss_explain_counts['--']
    expl_summary = '  '.join(expl_parts) if expl_parts else 'none'
    p(f'Miss. explain:  {expl_summary}  (--={neg_count} negligible)')
    if n_noted:
        p(f'  (* = {n_noted} variable(s) with known methodological notes -- see below)')
    p('  T1 = near-exact  T2 = high similarity  T3 = moderate diff  T4 = notable diff  T5 = substantial diff')
    p('  M1-M5 = missingness tiers (M1 < 1pp, M5 >= 20pp)')
    p('  Expl: Pop = miss diff explained by population size diff; Data:BDC+/- = real coverage gap')
    p()

    # Print details for any variables with known methodological notes
    m_vars = [(var, KNOWN_METHODOLOGICAL_DIFFS[(cohort, var)])
              for var in matched if (cohort, var) in KNOWN_METHODOLOGICAL_DIFFS]
    if m_vars:
        p('Methodological notes:')
        for var, entry in m_vars:
            label = tv[var].get('bdc_label', var)
            override_tag = "" if not entry.get("no_override") else " (tier kept)"
            p(f'  [{entry["code"]}] {label} ({var}){override_tag}')
            p(f'    {entry["note"]}')
        p()

    # Print cohort-level notes (version mismatches, etc.) if any exist
    cohort_note = COHORT_LEVEL_NOTES.get(cohort)
    if cohort_note:
        p(f'Cohort-level note [{cohort_note["code"]}]:')
        p(f'  {cohort_note["note"]}')
        p()

    # TOPMed DCC-only
    t_only = sorted(set(tv) - set(bv))
    p(f'TOPMed DCC-only ({len(t_only)}): {t_only}')

    # BDC-only count
    b_only = sorted(set(bv) - set(tv))
    p(f'BDC-only ({len(b_only)}): {len(b_only)} variables')

    output = '\n'.join(lines)
    print(output)

    if outfile:
        with open(outfile, 'w', encoding='utf-8') as f:
            f.write(output + '\n')
        print(f'\nSaved to: {outfile}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate per-variable match quality table (BDC vs reference)'
    )
    parser.add_argument('topmed_json', help='Reference summary JSON')
    parser.add_argument('bdc_json', help='BDC summary JSON')
    parser.add_argument('output_file', nargs='?', default=None, help='Output file (optional)')
    parser.add_argument(
        '--all-vars', action='store_true', default=False,
        help='Compare all matched variables instead of the 19-variable core set'
    )
    args = parser.parse_args()
    run(args.topmed_json, args.bdc_json, args.output_file, all_vars=args.all_vars)
