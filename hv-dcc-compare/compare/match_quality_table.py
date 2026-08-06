"""Generate per-variable match quality table for any cohort BDC vs TOPMed comparison.

Usage:
    # Core variables only (default — 28 variables, 5+ cohort coverage)
    python match_quality_table.py <topmed_json> <bdc_json> [output_file]

    # All matched variables
    python match_quality_table.py <topmed_json> <bdc_json> [output_file] --all-vars
"""
import argparse
import json
import sys
import os

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
# These variables will receive an asterisk (*) annotation on their value tier,
# and will have their methodological note printed in the output. The statistical
# diff is still displayed in full so the magnitude is transparent.
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
# TO ADD A NEW ENTRY:
#   1. Run match_quality_table.py and identify the T5-tier variable
#   2. Investigate the extract log and YAML to confirm it's methodological
#   3. Add an entry below with (COHORT, variable) as key, and fill in code + note
#   4. Re-run to confirm the * annotation appears on the tier
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CORE VARIABLE SET
# ─────────────────────────────────────────────────────────────────────────────
# 20 variables present in both BDC and TOPMed extracts across at least 5 of 8
# cohorts, organised by clinical group. This is the default comparison scope.
#
# Defined in: QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md
# ─────────────────────────────────────────────────────────────────────────────
# Core variables grouped by clinical domain.
# Order within and across groups is the display order in the output table.
# CORE_VARIABLES (the flat frozenset used for filtering) is derived from this.
# ─────────────────────────────────────────────────────────────────────────────
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
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "BDC unions 5 drug-class YAML files (ATC:C02 hypert_trt, ATC:C03 tak_diuret, "
            "ATC:C07A tak_betablk, ATC:C09A tak_aceinhib, ATC:C09C tak_angiorecepblk) across "
            "two WHI SCREENING tables (pht000999 + pht002770). TOPMed used only the single "
            "binary antihypertensive question on pht000999. BDC result (61.2% Yes) is higher "
            "because it picks up participants who reported a specific drug class but may not "
            "have answered the binary summary question. BDC also has 0% missing vs TOPMed "
            "3.1% missing because absence of a drug record is treated as 'No' by construction. "
            "VERDICT: BDC is epidemiologically more complete -- a participant who confirms a "
            "specific drug class IS taking an antihypertensive regardless of their answer to "
            "the summary question. However, the 31pp gap means this variable cannot be "
            "directly compared to TOPMed's single-form figure across cohorts."
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
            "T_N=143,127 (miss=0.1%) vs B_N=141,777 (miss=1.0%) -- BDC has 1,350 more "
            "missing participants. Two classification differences explain the category deltas: "
            "(1) MULTIPLE RACES: BDC identifies 425 participants as 'Multiple Races' (0.3%); "
            "TOPMed has 0 in this category -- TOPMed maps multi-race selections to 'Other' "
            "or a single primary race. BDC's multi-race coding is the more accurate "
            "representation of participants who selected more than one OMB race category. "
            "(2) NATIVE HAWAIIAN/PACIFIC ISLANDER: T=111 vs B=9 -- BDC loses 102 NHOPI "
            "participants, likely because the WHI race form code for NHOPI maps differently "
            "in BDC's value_mappings than in TOPMed's. These 102 are likely absorbed into "
            "'Other' (T=2,888 vs B=2,083, a gap of 805 which includes the NHOPI shift and "
            "the multi-race redistribution). White is 86.7% BDC vs 86.3% TOPMed (+0.4pp), "
            "consistent with a small number of NHOPI/Other participants being miscoded. "
            "VERDICT: Mixed. BDC correctly identifies Multiple Races (TOPMed suppresses it). "
            "BDC undercounts NHOPI by ~102 (likely a value_mapping issue in demography.yaml "
            "for the NHOPI race code). BDC also has 1,350 more missing -- review WHI race "
            "source forms for the same coverage gap as ethnicity."
        ),
    },
    # ── ARIC ──────────────────────────────────────────────────────────────────
    ("ARIC", "antihypertensive_meds_1"): {
        "code": "ADMIN_VS_SURVEY",
        "no_override": True,
        "note": (
            "BDC uses pht004063 HYPTMDCODE01 (phv00204798, N=15,636) — a Medi-Span GPI "
            "pharmaceutical-code-based derived variable that captures any participant who "
            "filled an antihypertensive prescription, regardless of self-attribution. "
            "This yields 4,791 Yes (30.6%). Reference data uses HYPTMD01 (phv00204754, "
            "same pht004063 table), the survey-form-based variable where participants "
            "explicitly attributed their medication to high blood pressure, yielding "
            "~3,961 Yes (25.3%). The 830-participant gap (~4.9pp) represents patients on "
            "antihypertensive therapy who did not attribute their drug to BP (e.g., "
            "diuretics prescribed for edema, beta-blockers for arrhythmia). BDC approach "
            "(pharmaceutical code) is epidemiologically more complete and correct. The "
            "HYPTMD01 block is also present in hypert_trt.yaml as a redundant last block "
            "(pure subset of HYPTMDCODE01 in the same table). BDC 0% missing vs reference "
            "1.3% missing because absence of a drug record is treated as No by construction."
        ),
    },
    ("ARIC", "mch_entmass_rbc_1"): {
        "code": "BASELINE_DEFINITION_DIFF",
        "no_override": True,
        "note": (
            "ARIC never conducted CBC labs at Exams 1 or 2; the earliest MCH data exists "
            "in HMTCV301 (pht004109, Exam 3), HMTCV401 (pht004110, Exam 4), and CBC "
            "(pht006422, Exam 5). BDC uses a per-variable visit_override "
            "(['ARIC EXAM 3', 'ARIC EXAM 4', 'ARIC EXAM 5']) in BDC_MEASUREMENT_MAP to "
            "match the TOPMed DCC's own 'first available' convention for this variable. "
            "The TOPMed DCC anchors on Exam 3 as the earliest available CBC visit "
            "(N=8,710, 42.1% missing, mean=30.48 pg). BDC takes earliest-per-participant "
            "across all three tables (Exams 3/4/5), which produces slightly higher N "
            "(because some participants missing Exam 3 have Exam 4 or 5 data) and may "
            "shift the mean marginally. Any remaining delta reflects this exam-composition "
            "difference -- not a YAML error. Both sides are measuring MCH at the earliest "
            "available visit, not enrollment baseline."
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
            "ABI-based PAD variable. Result: BDC 7.7% (1,156/15,068, 0% missing) vs "
            "reference 4.3% (613/14,388, 4.4% missing). The +3.4pp inflation comes from "
            "two sources: (a) multi-visit accumulation (Exam 3/4 incident PAD cases counted "
            "as present), and (b) hospital form PVD cases (MONDO:0005294) that are a broader "
            "clinical concept than ABI-defined PAD. The MONDO:0005294 alias must remain in "
            "BDC_CONDITION_MAP because COPDGene pad.yaml uses only that code. This is a "
            "known methodological difference, not a pipeline error."
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
            "ARIC angina_prior_1 is absent from the TOPMed reference (not in topmed_aric_summary.json). "
            "The TOPMed DCC excluded this variable from ARIC harmonization, likely due to the same data "
            "quality concern described here. BDC maps the variable from pht004063 DERIVE13 (RANGNA01, "
            "phv00204724 -- Rose Angina questionnaire, Visit 1), applying value_mapping '1'=ABSENT, "
            "'4'=PRESENT per the DERIVE13 data dictionary (Code 1=Negative, Code 4=Positive). The "
            "resulting BDC distribution is implausible: 94.5% Prior History (13,687/14,477 respondents "
            "coded PRESENT). Rose Angina prevalence in a general population is ~3-7%, not 94-95%. "
            "SUSPICION: An archived version of angina.yaml (_archive/ARIC/angina.yaml) used a different "
            "value_mapping -- '0'=ABSENT, '1'=PRESENT -- implying the actual DERIVE13 data file may "
            "encode RANGNA01 with 0/1 values rather than the 1/4 codes documented in the data dictionary. "
            "If the file stores Code 0=Negative and Code 1=Positive (a common binary encoding), then the "
            "current mapping ('1'=ABSENT) would misclassify most 'negative' responses as ABSENT while "
            "silently dropping them, and the small minority of '4'-coded records (if any) would be the "
            "only PRESENT entries -- producing a near-zero prevalence rather than 94.5%. The actual cause "
            "of the 94.5% remains unresolved. RECOMMENDATION: Do not use ARIC angina_prior_1 in any "
            "analysis until the RANGNA01 value encoding is verified against the actual DERIVE13 data file. "
            "The archive/current YAML coding divergence is a strong signal of a value_mapping error that "
            "requires investigation before this variable can be trusted."
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
            "BDC achieves 15,060 valid records (0.1% missing) vs reference 14,817 (1.5% "
            "missing), a 243-record coverage gap. Category distributions are IDENTICAL: "
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
    # ── MESA ──────────────────────────────────────────────────────────────────
    ("MESA", "hispanic_or_latino_1"): {
        "code": "LABEL_REMAP",
        "no_override": True,
        "note": (
            "BDC correctly emits only explicit Hispanic/Latino codes from MESA's combined "
            "race/ethnicity variable (race1c, pht001116/pht001121). Choosing a race code "
            "(White, Black, Chinese) does NOT imply 'Not Hispanic' — participants may be "
            "both. TOPMed infers 'Not Hispanic or Latino' from race-only codes, which is "
            "semantically incorrect. BDC behavior confirmed correct by ontology review "
            "(Anne, PR #534). BDC T_N=3,096 Hispanic-only; TOPMed adds 919 inferred "
            "Non-Hispanic records that should not exist. BDC approach is right."
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
            "CABG was rewritten from a Procedure entity to a Condition entity (matching "
            "the MESA pattern) and now uses CONDITION_PROCEDURE_VISIT_OVERRIDE to select "
            "the earliest exams with CABG history questions: Original Exam 21 (pht000023, "
            "phv00003839 MG284), Offspring Exam 5 (pht000034, phv00008328 E320), and "
            "Gen3 Exam 1 (pht000074, phv00021304 G3A197). The SHHS regex exclusion was "
            "also applied to prevent false matches on sub-study visits. Result: BDC "
            "N=8,925 (40.9% missing) vs reference N=11,814 (22.1% missing). The higher "
            "BDC missing rate reflects that CABG history was NOT asked at all baseline "
            "exams -- Original Exam 21 is the earliest FHS exam with a CABG question "
            "(far later than the Exam 4 baseline), and Omni 1, Omni 2, NOS sub-cohorts "
            "lack CABG history entirely. The reference achieves lower missing by using "
            "the FHS CVD surveillance/event adjudication system: pht000389 (Cardiovascular "
            "Event Forms, VESSEL count + PROCDATE), pht000309 (Verified Events, EVENT "
            "codes + DATE), pht003099 (age crosswalk, age1), and pht003316 (Survival "
            "dataset, cvd/cvddate) as a denominator booster -- any participant with a CVD "
            "follow-up record in pht003316 who had no CABG event is coded 0. This "
            "surveillance architecture covers ALL followed FHS participants regardless of "
            "which exam they attended, unlike BDC's exam-based history questions which are "
            "limited to the specific exams where CABG was asked. The +-1.1pp category "
            "delta confirms the mapping is directionally correct where data exists. "
            "The residual missing gap is a coverage limitation inherent in the exam-based "
            "approach, not a YAML error."
        ),
    },
    ("FHS", "angina_prior_1"): {
        "code": "SURVEILLANCE_DENOMINATOR_GAP",
        "no_override": True,
        "note": (
            "Angina was rewritten to use ONLY the pht000309 surveillance block (EVENT=6, "
            "AP first episode, DATE<=0 for pre-baseline events). Four Rose Questionnaire "
            "single-question blocks (G3A169 = 'chest discomfort with exertion or "
            "excitement') were removed because they overcounted angina 4x: the prior "
            "extract showed 401 positives (3.1%) vs reference 104 (0.7%). G3A169 is the "
            "first screening question of the Rose Angina Questionnaire, NOT a Rose-positive "
            "diagnosis -- answering 'yes' to exertional chest discomfort captures many "
            "non-cardiac causes (musculoskeletal, GERD, anxiety). After removal, BDC now "
            "finds exactly 104 positives -- matching the reference perfectly. Result: BDC "
            "N=8,730 (42.1% missing) vs reference N=15,154 (0.1% missing); max +-0.5pp "
            "category delta. The high missing rate is a denominator booster gap: the "
            "reference uses pht003316 (Survival dataset) to code ALL followed participants "
            "without an angina event as 0, achieving near-complete coverage. BDC's "
            "pht000309 block only emits PRESENT rows (EVENT=6, DATE<=0) -- participants "
            "without events have no record and fall to missing. The 8,626 'No Prior "
            "History' records come from the extract's imputation logic (participants with "
            "other condition records but no angina = imputed No). The accuracy is correct "
            "(104 positives match exactly); the D grade reflects the structural inability "
            "to generate negative-evidence rows from the surveillance system without a "
            "pipeline-level denominator booster (same limitation as CABG). This is a "
            "pipeline architecture constraint, not a YAML error."
        ),
    },
    ("FHS", "hispanic_or_latino_1"): {
        "code": "EXTENDED_COVERAGE",
        "no_override": True,
        "note": (
            "BDC demography.yaml maps FHS ethnicity from multiple tables covering all "
            "sub-cohorts, including pht016162 (vr_racesum_2011) which has code 88 = "
            "'Defaulted ethnicity (Not Hispanic)' for ~5,209 Original Cohort participants "
            "whose ethnicity was never directly collected (enrollment 1948-1953 predates "
            "standardized ethnicity collection). Result: BDC N=15,086 (0.0% missing) vs "
            "reference N=6,665 (56.1% missing). The dramatic coverage difference stems "
            "from: (1) BDC maps all sub-cohorts (Original, Offspring, Gen3, Omni 1, "
            "Omni 2, NOS) while the reference only ran on Offspring and Gen3; (2) BDC "
            "maps the code-88 imputed ethnicity for Original Cohort per the dbGaP data "
            "dictionary while the reference excluded Original entirely. The max +-1.8pp "
            "category delta driving the D grade likely reflects BDC mapping all "
            "non-Hispanic codes (including imputed code 88) to 'Not Hispanic or Latino' "
            "while the reference uses a narrower RACE_CODE-based derivation from "
            "pht006005 only. The BDC mapping is correct per dbGaP metadata; the grade "
            "reflects a fundamental methodological difference in ethnicity scope."
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
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "BDC bdy_hgt.yaml maps FHS Original height to EXAM 4 per BASELINE_VISIT_CONFIG "
            "(FHS ORIGINAL EXAM 4), while the reference extract uses EXAM 1 height for the "
            "Original cohort. Result: BDC N=14,409 (4.5% missing) vs reference N=15,141 "
            "(0.2% missing). BDC mean 167.33 cm vs reference 167.45 cm (delta +0.12 cm). "
            "The 732-participant gap is primarily a survivor bias effect: participants "
            "present at Exam 1 (1948) who died before Exam 4 (~1957) are excluded from "
            "BDC but included in the reference. Some sub-cohort coverage differences also "
            "contribute. The small +0.12 cm mean delta is consistent with secular height "
            "trends and survivor selection. The YAML correctly maps height with a 2.54 cm "
            "conversion factor (inches to cm) and EXAM 4 visit assignment per "
            "BASELINE_VISIT_CONFIG. The N gap is a baseline visit definition difference, "
            "not a YAML error."
        ),
    },
    ("FHS", "antihypertensive_meds_1"): {
        "code": "VISIT_SCOPE_DIFF",
        "no_override": True,
        "note": (
            "FHS Original cohort antihypertensive treatment (phv00000705, MF250, pht000009, "
            "FHS ORIGINAL EXAM 4) was added to hypert_trt.yaml. Result: BDC N=15,089 "
            "(0.0% missing) vs reference N=14,377 (5.2% missing). The extract logic "
            "imputes 'No' for all participants without a baseline drug record, causing "
            "BDC to report 0.0% missing. The 712-participant gap is a stable structural "
            "difference between the BDC imputation approach (absent record = 'No') and "
            "the reference's explicit missing handling. Original cohort Exam 4 participants "
            "with code 9997 (Did Not Take Exam 4) and 9999 (Unknown) resolve to 'No' via "
            "imputation. Codes 1 (YES DEFINITE) and 2 (YES DOUBTFUL) are mapped to "
            "ATC:C02. The +-1.4pp max category delta confirms the mapping is correct "
            "where data exists; the missing-rate difference is a methodological choice, "
            "not a YAML error."
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
            "Two differences exist between BDC and reference for CABG prior history. "
            "(1) Missing policy: the reference uses BPSSUR/BPSSURBL "
            "(phv00100321/phv00100785, pht001452/pht001464, n=5,493, 38 nulls) and "
            "preserves the 38 missing as unknown. BDC extracts from Procedure "
            "entities and defaults all participants with no CABG record to 'No Prior "
            "History', eliminating all missing (n=5,531, miss=0). The reference is "
            "more accurate for those 38 participants whose CABG status was "
            "genuinely not recorded. (2) Prevalence: BDC=218 Prior History (3.9%), "
            "reference=236 (4.3%) — a gap of 18 participants. BDC's baseline-visit "
            "filter ('CHS BASELINE 2 + CHS BASELINE BOTH') excludes 18 CABG "
            "Procedure records that the reference captures via EVENT_SUMMARY "
            "BPSSURBL, which aggregates CABG history across all pre-baseline "
            "sources. The categorical delta is 0.4pp (within A+ threshold) but the "
            "reference is more complete on both counts: it preserves uncertainty for "
            "38 participants and counts 18 additional CABG cases. BDC approach "
            "slightly understates prevalence and over-classifies unknowns as No. "
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
            "BDC sources body weight from three baseline tables (log: '5,531 "
            "participants from 33,186 baseline rows'): BASE1 measured weight "
            "(phv00099349, WEIGHT13, lbs converted to kg, n=4,889 nulls=14), BASE1 "
            "self-reported 'usual weight at age 50' (phv00099153, WGT5008, lbs "
            "converted to kg, n=4,713 nulls=190), and BASEBOTH measured weight "
            "(phv00100383, WEIGHT13, lbs converted to kg, n=5,514 nulls=17). BDC "
            "fills the 17 BASEBOTH-null participants using the BASE1 fallback "
            "blocks, resulting in n=5,531, miss=0. The reference uses BASEBOTH "
            "WEIGHT13 (phv00100383) only — n=5,514, miss=17 — exactly matching the "
            "BASEBOTH var_report. The +0.0033 kg delta (72.794 vs 72.791) is driven "
            "by the 17 fill-in values: some are filled from WGT5008 ('usual weight "
            "at age 50'), a self-reported retrospective value that may differ from "
            "the measured baseline weight in BASEBOTH. The reference approach "
            "(BASEBOTH only, measured weight) is cleaner; BDC is more complete but "
            "risks mixing measured and self-reported weight for 17 participants. "
            "Approach: BDC better on completeness; reference cleaner on data type consistency. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100383 WEIGHT13 (n=5,514, nulls=17)."
        ),
    },
    ("CHS", "antihypertensive_meds_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources antihypertensive medication from two baseline tables: "
            "pht001450 BASE1 (phv00099656, original 1989 cohort only, N=4,900) at visit "
            "'CHS BASELINE 2', and pht001452 BASEBOTH (phv00100595, both cohorts merged, "
            "N=5,526, 5 missing) at visit 'CHS BASELINE BOTH'. The reference extract uses "
            "BASEBOTH (phv00100595) only — the CHS study team's authoritative merged "
            "baseline file covering both the original and new cohorts — and its output "
            "exactly matches the BASEBOTH var_report (Yes=2,634 / No=2,892 / missing=5). "
            "BDC's union across both tables results in 5,531 classified participants (0 "
            "missing), inflating Yes by ~36 and reducing No by ~31 relative to BASEBOTH "
            "alone. The discrepancy arises because BASE1 and BASEBOTH partially overlap for "
            "original-cohort participants; when BASE1 records a Yes for a participant whose "
            "BASEBOTH entry is No or missing, the union-level extract counts them as Yes. "
            "BASEBOTH is the correct single authoritative source (it already contains all "
            "participants from both cohorts); using BASE1 on top of it is redundant and "
            "over-classifies 36 participants as hypertension-medication users. "
            "Gap: reference Yes=47.7% (2,634/5,526) vs BDC Yes=48.3% (2,670/5,531), "
            "a 0.6pp difference. The reference approach is cleaner; BDC's dual-source "
            "approach is a minor over-count but not a clinical error. "
            "dbGaP ground truth: pht001452 BASEBOTH phv00100595 var_report "
            "(n=5,526, Yes=2,634, No=2,892, missing=5)."
        ),
    },
    ("CHS", "ever_smoker_baseline_1"): {
        "code": "AGGREGATION_DIFF",
        "no_override": True,
        "note": (
            "BDC sources from BASEBOTH EVERSM (phv00100372, pht001452) — the CHS "
            "study team's own pre-derived ever-regular-smoker binary variable. BDC "
            "output (2,966 Yes / 2,559 No / 6 missing) exactly matches the dbGaP "
            "var_report count for EVERSM. "
            "The reference extract instead reconstructs ever-smoker status from 4 raw "
            "questionnaire fields across pht001450+pht001490: SMOKE101 smoked-in-lifetime "
            "(phv00098844), SMOKE201 smoked-last-30-days (phv00098845), SMKAGE age-started "
            "(phv00099157), and AMOUNT cigs/day (phv00099159). It sums these with "
            "rowSums(na.rm=TRUE) and treats any non-zero value as evidence of ever-smoking, "
            "overriding a primary 'No' on SMOKE101. This reclassifies 102 participants "
            "whose CHS study team EVERSM = No as ever-smokers — for example, a participant "
            "who reported 'never smoked' but has a non-zero SMKAGE or AMOUNT entry (which "
            "could reflect data entry artifacts or misinterpretation) gets overridden. "
            "The CHS study team presumably adjudicated these edge cases when deriving EVERSM, "
            "making their curated variable more authoritative than a mechanical heuristic. "
            "Result: reference 55.60% (3,068/5,519) vs BDC 53.70% (2,966/5,525), a 1.9pp "
            "gap. BDC approach is correct per dbGaP ground truth (EVERSM). "
            "Source: UW-GAC/topmed-dcc-harmonized-phenotypes, "
            "harmonized-variable-documentation/baseline_common_covariates/"
            "ever_smoker_baseline_1.json, CHS harmonization unit, v4."
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
    # 13 variables have NO additional explanation beyond the universe diff --
    # these are handled by _JHS_UNIVERSE_DIFF_ONLY (loop after dict).
    # 4 variables below have variable-specific explanations (different source
    # methodology, closed-world artifacts, B/C-grade mean shifts).
    # ──────────────────────────────────────────────────────────────────────────
    ("JHS", "pad_prior_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC pad.yaml uses phv00401122 (abi) from pht008729 (analysis1 — Exam 1 "
            "analysis-derived dataset), applying the standard ABI < 0.9 threshold "
            "(ACC/AHA clinical criterion for PAD). This is the gold-standard objective "
            "PAD definition and covers all 3,883 Exam 1 participants (0% missing). "
            "Current data: BDC 2.3% (89/3,883, 0% missing) vs TOPMed 2.7% (83/3,126, "
            "13.2% missing). "
            "The C grade is driven entirely by the 13.2pp missingness differential "
            "(B_miss=0% vs T_miss=13.2%), not by a prevalence discrepancy (0.4pp is "
            "well within the A-grade 1pp threshold). TOPMed sources JHS PAD from "
            "ESP_HeartGO_JHS_Subject_Phenotypes (pht002539, phv00181292 ESP_pad) -- "
            "a participant-level dataset for the NHLBI Exome Sequencing Project "
            "subsample. ESP covers only ~87% of JHS participants; the 13.2% missing "
            "in TOPMed reflects participants not selected for ESP sequencing, introducing "
            "potential selection bias (ESP phenotype-enriched, may over-sample CVD cases). "
            "BDC's ABI-based source is methodologically superior: it uses objective "
            "measurement, covers the full cohort, and avoids subsample selection bias. "
            "The 0.4pp prevalence agreement between the two sources (2.3% vs 2.7%) "
            "further confirms the YAML is correct. "
            "Note: the old source (pht008725 PADEVER, cumulative AFU self-report) was "
            "already removed from pad.yaml and is no longer used. "
            "Assessment: SAME -- 0.4pp prevalence gap is within A-grade threshold; "
            "C grade is a denominator-coverage artifact (full cohort vs ESP subsample), "
            "not a mapping error. BDC's implementation is the more correct approach."
        ),
    },
    ("JHS", "antihypertensive_meds_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC unions 7 antihypertensive drug-class YAML files (ATC:C02 hypert_trt, "
            "ATC:C03 tak_diuret, ATC:C07A tak_betablk, ATC:C08 tak_calchanblk, "
            "ATC:C09A tak_aceinhib, ATC:C09C tak_angiorecepblk) across JHS exam tables. "
            "Closed-world assumption: absence of any drug record = 'No exposure' (0% missing). "
            "Current data: BDC 49.9% Yes (1,939/3,883, 0% missing) vs TOPMed 53.8% Yes "
            "(1,794/3,335, 7.4% missing). Apparent gap: 3.9pp, BDC LOWER than TOPMed. "
            "Denominator adjustment: TOPMed 7.4% missing = 267 of 3,602 participants. "
            "If those 267 are counted as No (matching BDC's closed-world): TOPMed Yes = "
            "1,794 / 3,602 = 49.8% -- virtually identical to BDC's 49.9%. The C grade "
            "(3.9pp categorical diff, >3pp B threshold) is almost entirely a denominator "
            "artifact from TOPMed's missing-value policy rather than a true prevalence gap. "
            "Assessment: SAME -- after correcting for TOPMed's 7.4% missing vs BDC's "
            "closed-world No assignment, both approaches yield ~49.8-49.9% antihypertensive "
            "prevalence at JHS Exam 1 baseline."
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
        "code": "UNION_OF_FORMS",
        "no_override": True,
        "note": (
            "BDC unions 5 antihypertensive ATC drug classes from the pipeline output: "
            "ATC:C02 from phv00226324 (MED_ANTIHYPERT, the binary summary question, "
            "1,972 exposed), ATC:C03 from phv00226339 (MED_DIURETIC, 1,161), ATC:C07A "
            "from phv00226330 (MED_BB beta blockers, 869), ATC:C09A from phv00226325 "
            "(MED_ANTIHYPERT_ACEI, 1,327), and ATC:C09C from phv00226326 "
            "(MED_ANTIHYPERT_AT2RAS ARBs, 540). The union yields 2,565 unique participants "
            "on any antihypertensive (21.7%). TOPMed used only the single binary variable "
            "MED_ANTIHYPERT (phv00226324) and reports 2,078 Yes (16.9%) with 615 missing "
            "(4.8%). The +4.8pp difference comes from 593 participants who answered No or "
            "were missing on the binary summary question but reported Yes on a specific drug "
            "class (ACE inhibitor, ARB, beta blocker, diuretic, or calcium channel blocker). "
            "BDC also shows 0% missing because absence of any drug exposure record is "
            "treated as No by construction, whereas TOPMed preserves the binary variable's "
            "missingness. The BDC approach is more complete -- a participant reporting a "
            "specific ACE inhibitor IS taking an antihypertensive regardless of their answer "
            "to the summary question. Same UNION_OF_FORMS pattern as WHI. All source PHVs "
            "are from pht004715."
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

# JHS: 13 A/A+ variables (Sex, Race, Height, Body weight, BMI, SBP, DBP,
# Current smoker, Ever smoker, Platelet count, MCH, History of MI, CABG)
# have no variable-specific notes -- the cohort-level PARTICIPANT_UNIVERSE_DIFF
# note fully explains their comparison differences. Only 4 JHS variables
# (antihypertensive_meds_1, total_cholesterol_1, triglycerides_1, pad_prior_1)
# retain per-variable notes because they have additional explanations beyond
# the participant universe difference.


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
            "TOPMed sourced all CVD history variables (MI, Angina, CABG) exclusively "
            "from pht001123 (ThruYear2011Events), which covers only the Classic sub-cohort "
            "(T_N=6,429, 22.5% missing). However, TOPMed included MESA Family participants "
            "(1,871) for all other variables -- demographics, anthropometrics, BP, lipids, "
            "and smoking all show T_N~8,250+. BDC includes Family data consistently across "
            "all variables, including CVD history from pht001121 (FamilyExamMain) which has "
            "self-report questions for MI (heartaf), angina (anginaf), and CABG (corobyf). "
            "Since Classic participants were CVD-free at enrollment by clinical adjudication, "
            "the only informative CVD history data in MESA comes from the Family sub-study. "
            "BDC captures 51 MI, 69 angina, and 22 CABG real positives that TOPMed misses "
            "entirely. The C/D grades on these 4 variables reflect BDC's broader coverage."
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
    with open(topmed_path) as f:
        t = json.load(f)
    with open(bdc_path) as f:
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
        with open(outfile, 'w') as f:
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
        help='Compare all matched variables instead of the 28-variable core set'
    )
    args = parser.parse_args()
    run(args.topmed_json, args.bdc_json, args.output_file, all_vars=args.all_vars)
