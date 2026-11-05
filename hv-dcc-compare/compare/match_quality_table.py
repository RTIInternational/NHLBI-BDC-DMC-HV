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
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At WHI SCREENING, BDC reads only Form 30 HYPTPILN (pht000999 "
            "phv00078559, 'Do you now take pills for high blood pressure?'), a "
            "sub-question of the hypertension item that is not collected on all "
            "Form 30 versions. dbGaP holds 35,517 Yes, 10,071 No and 97,535 "
            "null; 90 further women have no Form 30 row, so BDC is missing for "
            "97,625 (68.2%). BDC Yes is 35,517 of 45,588 answered (77.9%), "
            "computed among about a third of participants. The DCC derives the "
            "variable from the Form 44 medication inventory (pht002754 TCCODE "
            "antihypertensive classes at F44VTYP == 1, women with a baseline BP "
            "reading, medication-start window): 41,444 Yes of 138,732 (29.9%). "
            "BDC does not infer 'No' from a skipped sub-question."
        ),
    },
    ("WHI", "angina_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Prior History is identical (7,868). TOPMed has 142,250 answered "
            "(0.7% missing, 963); BDC has 143,123 (0.1% missing, 90). 873 women "
            "have a Form 30 row (pht000999 phv00078560) with a null answer, and "
            "the comparison counts a blank condition status as answered without "
            "history. The other 90 women have no Form 30 row and are missing on "
            "both sides."
        ),
    },
    ("WHI", "mi_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Prior History is identical (3,279). BDC N is 143,213 and TOPMed N "
            "is 143,136: 77 women have a null Form 2 MI answer (pht000998 "
            "phv00078482), and the comparison counts a blank condition status "
            "as answered without history."
        ),
    },
    ("WHI", "cabg_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Prior History is identical (1,226). TOPMed has 141,106 answered "
            "(1.5% missing); BDC has 143,123 (0.1%). 2,017 women have a null "
            "Form 30 CABG answer (pht000999 phv00078535), and the comparison "
            "counts a blank condition status as answered without history. The "
            "other 90 women have no Form 30 row and are missing on both sides. "
            "Tier T1 / M2."
        ),
    },
    ("WHI", "pad_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Prior History is identical (2,893, 2.0%). BDC has 143,123 answered "
            "against 142,216 in TOPMed: 907 women have a null Form 30 PAD "
            "answer (pht000999 phv00078562), and the comparison counts a blank "
            "condition status as answered without history. Other WHI PAD blocks "
            "in the specs carry no screening visit and are not graded at "
            "baseline."
        ),
    },
    ("WHI", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the Form 34 derived SMOKING (pht001003 phv00078825, "
            "computed from Form 34 questions 1, 1.2 and 1.5): 9,802 current and "
            "131,561 not current. The DCC reads SMOKEVR (phv00078774) and "
            "SMOKNOW (phv00078776): 9,821 current and 131,561 not current. The "
            "19-participant difference is consistent with women who answered "
            "SMOKNOW = Yes having no SMOKING value; this was inferred from "
            "totals, not matched by participant. Missing is 1.3% on both sides."
        ),
    },
    ("WHI", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Never Smoked is identical (71,847). The DCC reads SMOKEVR "
            "(pht001003 phv00078774: 70,213 Yes, 995 null); BDC reads the "
            "derived SMOKING (phv00078825: 69,516 ever, 1,692 null). The 697 "
            "difference is consistent with women who have SMOKEVR = Yes and a "
            "null SMOKING: about 678 with no SMOKNOW answer and 19 with SMOKNOW "
            "= Yes (inferred from totals, not matched by participant)."
        ),
    },
    ("WHI", "bp_diastolic_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "dbGaP Form 80 (pht001019) records two readings, DIASBP1 "
            "(phv00079855) and DIASBP2 (phv00079857). BDC holds them as "
            "separate observations and the comparison keeps one per "
            "participant, the first by file order (94,499 participants have "
            "differing values). The DCC averages readings 1 and 2 and sets a "
            "pair to missing when SBP is below DBP. BDC mean is 75.00 against "
            "75.18 (delta -0.18 mmHg, 0.02 SD) and SD 9.36 against 9.25. Which "
            "reading BDC retains is not verified at row level."
        ),
    },
    ("WHI", "bp_systolic_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Same structure as diastolic. dbGaP Form 80 (pht001019) records "
            "SYSTBP1 (phv00079854) and SYSTBP2 (phv00079856). BDC holds both as "
            "separate observations and the comparison keeps one per "
            "participant, the first by file order (107,172 participants have "
            "differing values); the DCC averages the two. BDC mean is 126.96 "
            "against 127.24 (delta -0.28 mmHg, 0.016 SD) and SD 17.88 against "
            "17.70."
        ),
    },
    ("WHI", "hispanic_or_latino_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC derives ethnicity from Form 2 RACE (pht000998 "
            "phv00078450): Hispanic/Latino for code 4 (5,468) and Not Hispanic "
            "for every other non-null code (137,397); the 348 with null RACE "
            "are missing. The BDC Form 2 block emits ethnicity only for RACE 4 "
            "(Hispanic) and 5 (White, not of Hispanic origin); the 17,858 women "
            "coded 1, 2, 3 or 8 receive ethnicity only from Form 41 SPANISH "
            "(pht001009 phv00079316) when present. After that fill, 4,400 "
            "(3.1%) remain missing against 348 (0.2%), a gap of 4,052. BDC has "
            "379 more Hispanic women, all from Form 41 (5,847 against 5,468)."
        ),
    },
    ("WHI", "race_us_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "BDC takes Form 2 RACE (pht000998 phv00078450, at 'WHI SCREENING') "
            "first and uses Form 41 (pht001009 per-race checkboxes, no visit) "
            "only where Form 2 is null (275 of 348 women); the extractor takes "
            "the first non-null value per column. Form 2 has no NHOPI code (2 = "
            "Asian or Pacific Islander, mapped to Asian) and maps Hispanic (4: "
            "5,468) and Other (8: 1,595) to OMOP:8552, which BDC-HM labels "
            "Unknown and this comparison reports as Other: 7,063 plus 13 Form "
            "41 fills gives 7,076. The DCC applies the same Form 2 precedence "
            "and, per a comment in its code citing WHI study-investigator "
            "guidance, uses Form 41 to assign a specific race to Form 2 "
            "Hispanic and Other women with a single race group and to separate "
            "Pacific Islander from Asian. DCC minus BDC: Other -4,188 (2,888 "
            "against 7,076), NHOPI +111, White +3,832, Black +140, Asian +66, "
            "AIAN +41. BDC cells under 5 are pooled ('Other, n under 5' = 2). "
            "Form 41 counts race groups, so two ticks within one group are one "
            "race; the DCC has no Multiple for WHI and BDC has 13, all among "
            "women with no Form 2 race. This item is under review with the "
            "study's guidance."
        ),
    },
    # ── ARIC ──────────────────────────────────────────────────────────────────
    ("ARIC", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At ARIC Exam 1, BDC grades three ATC:C02 indicators in "
            "hypert_trt.yaml: HYPTMD01 (phv00204754, pht004063), HYPTMDCODE01 "
            "(phv00204798, pht004063, medication-code based) and MSRA08A "
            "(phv00207913, pht004129, medication survey item for high blood "
            "pressure); a participant positive on any of the three is Yes. The "
            "DCC reads HYPTMD01 only (phv00204754), with T set to missing. "
            "Result: BDC 30.9% Yes (4,618 of 14,953 answered); the DCC 25.7% "
            "Yes (3,823 of 14,854), a 5.2pp difference (T4). This run does not "
            "tabulate how much each indicator adds to the difference. The DCC "
            "function omits records with no V1AGE01 (phv00204712, pht004063); "
            "the number of participants this affects is not documented in the "
            "material reviewed."
        ),
    },
    ("ARIC", "mch_entmass_rbc_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "In the v8 tables BDC maps, MCH is recorded at Exam 3 (HMTC7, "
            "pht004109, phv00207290), Exam 4 (HMTC7, pht004110, phv00207302) "
            "and Exam 5 (CBC9, pht006422, phv00294960); the DCC documents MCH "
            "as measured at visits 3, 4 and 5 only and reads the same three "
            "variables. Both sides select the visit with the most non-missing "
            "values first, then the next, in succession; the comparison applies "
            "that rule to the BDC rows (BDC order Exam 5 > 4 > 3). Result: "
            "valid N 8,957 (BDC) vs 8,710 (DCC), +247; missing 40.6% vs 42.1%; "
            "means 30.51 vs 30.48; SD 6.27 vs 2.23, with 4 vs 3 implausible "
            "values. The DCC function drops codes A and O and drops records "
            "with no age at that visit. The cause of the +247 and of the SD "
            "difference is not established in this run."
        ),
    },
    ("ARIC", "pad_prior_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "pad_prior_1 is graded at ARIC Exam 1. BDC reads pad01 and pad02 "
            "from the ABI form (pht004027, phv00202848 and phv00202847) and "
            "PAD01 and PAD02 from DERIVE13 (pht004063, phv00204796 and "
            "phv00204795). The DCC reads PAD02 (phv00204795, pht004063) only, "
            "with T set to missing. A second BDC code, MONDO:0005294 "
            "(hist_cvd.yaml, HFAA11M phv00206807, pht004102 heart-failure "
            "hospital record abstraction), has no Exam 1 rows and adds 0 here. "
            "Prior History: 615 (4.1%) BDC vs 613 (4.3%) DCC. Missing: 0 BDC vs "
            "656 (4.4%) DCC (M3). The comparison counts a blank condition "
            "status as answered; how many BDC Exam 1 rows have a blank status "
            "is not logged, and the cause of the missingness difference is not "
            "established. The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063); the number of participants this affects "
            "is not documented in the material reviewed."
        ),
    },
    ("ARIC", "annotated_sex_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "BDC sources sex from 26 tables in demography.yaml, including "
            "DERIVE13 GENDER (phv00204711, pht004063) at Exam 1: 15,067 valid, "
            "0 missing. The DCC reads GENDER (phv00204711) only and drops "
            "records where it is missing: 14,940 valid, 104 missing (0.7%) of "
            "15,044. Distributions are the same (54.6% F, 45.4% M in both; T1). "
            "Why GENDER is missing for those 104 records is not documented in "
            "the material reviewed."
        ),
    },
    ("ARIC", "hispanic_or_latino_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "bdc_only": True,
        "note": (
            "BDC only. The DCC hispanic_or_latino_1 documentation has no ARIC "
            "unit. BDC demography.yaml emits hispanic_or_latino_1 from "
            "ethnicity fields in pht006468 (phv00511026, Exam 5) and "
            "pht012821-pht012824 (Exams 1-4); 8 of 15,067 participants have a "
            "value (99.9% missing). Which of these blocks supplies the 8 is not "
            "tabulated in this run."
        ),
    },
    ("ARIC", "angina_prior_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "bdc_only": True,
        "note": (
            "BDC only; the DCC angina_prior_1 documentation has no ARIC unit. "
            "angina.yaml maps RANGNA01 (phv00204724, pht004063 DERIVE13, Rose "
            "angina, Visit 1) as the v8 dictionary documents it (1 = Negative "
            "-> ABSENT, 4 = Positive -> PRESENT): 13,687 Prior History of "
            "14,477 answered (94.5%), 790 No, 590 missing. Under the documented "
            "coding, 94.5% of answered participants are positive; the "
            "dictionary coding is awaiting a response from the study (HV #945). "
            "The spec follows the documentation."
        ),
    },
    ("ARIC", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-computed BMI01 (phv00204719, pht004063 "
            "DERIVE13, Exam 1): 14,452 valid (615 missing, 4.1%; M3). The DCC "
            "computes BMI from its harmonized baseline height and weight: "
            "14,915 valid (129 missing, 0.9%), the same N as its body-weight "
            "variable. Means: 27.72 (BDC) vs 27.65 (DCC), +0.07 (T2). At least "
            "587 BDC participants with a valid Exam 1 weight (15,039) have no "
            "BMI01 value (14,452 valid); BMI01 is typed string in the "
            "dictionary with no missing code documented, and the reason for the "
            "blanks is not established."
        ),
    },
    ("ARIC", "bp_diastolic_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads SBPA22 (phv00210291, pht004192; dictionary: '2nd and 3rd "
            "diastolic') at Exam 1. The DCC recomputes the value from the "
            "individual readings (SBPA15-SBPA20, pht004192, "
            "phv00210284-phv00210289): it subtracts the zero readings, sets "
            "both members of a systolic/diastolic pair to missing when systolic "
            "is below diastolic, and takes the mean of the second and third "
            "readings that remain (one reading if only one remains). BDC: "
            "15,050 valid (17 missing, 0.1%); the DCC: 14,926 valid (118 "
            "missing, 0.8%), +124. Means 73.71 vs 73.71 (delta -0.002; T1). The "
            "DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063); the number of participants this affects is not "
            "documented in the material reviewed. The cause of the +124 is not "
            "established."
        ),
    },
    ("ARIC", "bp_systolic_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads SBPA21 (phv00210290, pht004192; dictionary: 'Computed "
            "net average of second and third blood pressure measurement', "
            "systolic) at Exam 1. The DCC recomputes the value from the "
            "individual readings (SBPA15-SBPA20, pht004192, "
            "phv00210284-phv00210289): it subtracts the zero readings, sets "
            "both members of a systolic/diastolic pair to missing when systolic "
            "is below diastolic, and takes the mean of the second and third "
            "readings that remain (one reading if only one remains). BDC: "
            "15,050 valid (17 missing, 0.1%); the DCC: 14,926 valid (118 "
            "missing, 0.8%), +124. Means 121.49 vs 121.44 (+0.04; T1). The DCC "
            "function omits records with no V1AGE01 (phv00204712, pht004063); "
            "the number of participants this affects is not documented in the "
            "material reviewed. The cause of the +124 is not established."
        ),
    },
    ("ARIC", "cabg_prior_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Both sides read PHEA07A (phv00208846, pht004143, coronary bypass "
            "question, Exam 1). BDC maps T to UNKNOWN: 15,059 answered, 8 "
            "missing (0.1%). The DCC also reads PHEA06 and PHEA08 (phv00208845, "
            "phv00208853), sets a missing PHEA07A to 0 when either is answered, "
            "and drops records with all three missing: 14,817 valid, 227 "
            "missing (1.5%). Prior History is 1.6% in both (236 BDC, 232 DCC; "
            "T1). The DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063); the number of participants this affects is not "
            "documented in the material reviewed. The cause of the 227 DCC "
            "missing is not established."
        ),
    },
    ("ARIC", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads CIGT01 (phv00204713, pht004063 DERIVE13) and the Home "
            "Interview items HOM28 and HOM30 (phv00207368, phv00207370, "
            "pht004111) at Exam 1. The DCC reads pht004111 only (HOM28, HOM30 "
            "and HOM32, phv00207368, phv00207370, phv00207372): current smoker "
            "if HOM30 is Y or cigarettes per day (HOM32) is positive. BDC: "
            "15,052 valid (15 missing, 0.1%); the DCC: 14,926 valid (118 "
            "missing, 0.8%), +126. Current smoker 26.6% vs 26.5% (0.1pp, T1). "
            "The DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063); the number of participants this affects is not "
            "documented in the material reviewed."
        ),
    },
    ("ARIC", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the same Exam 1 sources as current smoker: CIGT01 "
            "(phv00204713, pht004063) and HOM28/HOM30 (pht004111). The DCC "
            "reads pht004111 only (HOM28, HOM29, HOM30, HOM35, HOM36; "
            "phv00207368, phv00207369, phv00207370, phv00207375, phv00207376). "
            "BDC: 15,052 valid (15 missing, 0.1%); the DCC: 14,930 valid (114 "
            "missing, 0.8%), +122. Ever Smoked 58.8% in both; Never Smoked "
            "41.2% in both (T1). The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063); the number of participants this affects "
            "is not documented in the material reviewed."
        ),
    },
    ("ARIC", "height_baseline_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read ANTA01 (phv00203151, pht004032, standing height in "
            "cm, Exam 1); the DCC sets the undocumented code A to missing. BDC: "
            "15,045 valid (22 missing, 0.1%); the DCC: 14,921 valid (123 "
            "missing, 0.8%), +124. Means 168.51 vs 168.56 cm (-0.05; T2). The "
            "DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063); the number of participants this affects is not "
            "documented in the material reviewed. The cause of the +124 is not "
            "established."
        ),
    },
    ("ARIC", "mi_prior_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "mi_prior_1 is graded at ARIC Exam 1 only (1,142 Prior History at "
            "that visit vs 5,183 across all visits). BDC unions eight Exam 1 "
            "variables in hist_my_inf.yaml: DERIVE13 (pht004063) MDDXMI02 "
            "(phv00204748), HXOFMI02 (phv00204749), ECGMI04 (phv00204704, "
            "adjudicated ECG), PREVMI05 (phv00204705, ECG or medical history) "
            "and MACHMI02 (phv00204709, machine-coded ECG); HOM10C (pht004111, "
            "phv00207313); MHXA28 (pht004126, phv00207776); and v1ecg21 "
            "(pht004231, phv00215643, Minnesota-coded ECG). The DCC reads "
            "PREVMI05 only (phv00204705), with T set to missing. BDC: 1,142 "
            "(7.6%) of 15,067, 0 missing; the DCC: 641 (4.4%) of 14,717, 327 "
            "missing (2.2%); 3.2pp difference (T4). The contribution of each "
            "BDC source to the difference is not tabulated in this run. The DCC "
            "function omits records with no V1AGE01 (phv00204712, pht004063); "
            "the number of participants this affects is not documented in the "
            "material reviewed. This item is under review with the study's "
            "guidance."
        ),
    },
    ("ARIC", "platelet_ncnc_bld_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read HMTA04 (phv00207258, pht004107, Exam 1), HMTB04 "
            "(pht004108, Exam 2), HMTC10 (pht004109 Exam 3, pht004110 Exam 4) "
            "and CBC7 (pht006422, Exam 5), and both choose the visit with the "
            "most non-missing values first, then the next in succession; the "
            "comparison applies that rule to the BDC rows (BDC order Exam 1 > "
            "Exam 5 > Exam 2). Valid N 14,847 (BDC) vs 14,815 (DCC), +32; "
            "missing 1.5% in both; means 257.62 vs 257.57 (+0.05; T1). The "
            "cause of the +32 is not established."
        ),
    },
    ("ARIC", "race_us_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "The DCC reads RACEGRP (pht004063, phv00204710; pht004062, "
            "phv00204633; pht004065, phv00204962) and its code maps A to Asian "
            "and I to AI_AN and assigns Multiple when visits disagree; in this "
            "run the DCC has Black 26.1% (3,896) and White 73.9% (11,044) only, "
            "with 104 missing (0.7%). Why no DCC participant falls in another "
            "category is not documented in the material reviewed. BDC has "
            "15,067 valid, 0 missing: Black 26.3% (3,963), White 73.4% "
            "(11,055), American Indian or Alaska Native 10, Asian 25, Other 14. "
            "The largest category difference is 0.5pp (T2). BDC maps only W and "
            "B from RACEGRP at Exam 1 (demography.yaml); the other categories "
            "come from other race fields mapped there."
        ),
    },
    ("ARIC", "total_cholesterol_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads three sources: TCHSIU01 (phv00204735, "
            "pht004063; SI value x 38.67), LIPA01 (phv00207635, pht004121) and "
            "TOTCHOL_V1 (phv00519812, pht012853). The DCC reads TCHSIU01 only, "
            "dividing by 0.02586 (the same factor). BDC: 14,837 valid (230 "
            "missing, 1.5%); the DCC: 14,705 valid (339 missing, 2.3%), +132. "
            "Means 214.97 vs 215.06 mg/dL (-0.10; T1). The DCC function omits "
            "records with no V1AGE01 (phv00204712, pht004063); the number of "
            "participants this affects is not documented in the material "
            "reviewed. How much each additional BDC source adds is not "
            "tabulated in this run."
        ),
    },
    ("ARIC", "triglycerides_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads TRGSIU01 (phv00204738, pht004063; SI value x "
            "88.57) and the LIPA triglyceride variable phv00207636 (pht004121). "
            "The DCC reads TRGSIU01 only, dividing by 0.01129 (the same "
            "factor). BDC: 14,840 valid (227 missing, 1.5%); the DCC: 14,707 "
            "valid (337 missing, 2.2%), +133. Means 132.47 vs 132.44 mg/dL "
            "(+0.03; T1). The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063); the number of participants this affects "
            "is not documented in the material reviewed. How much the "
            "additional BDC source adds is not tabulated in this run."
        ),
    },
    ("ARIC", "weight_baseline_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read ANTA04 (phv00203154, pht004032, weight to the "
            "nearest lb, Exam 1) and convert to kg (x 0.453592); the DCC sets "
            "the undocumented code A to missing. BDC: 15,039 valid (28 missing, "
            "0.2%); the DCC: 14,915 valid (129 missing, 0.9%), +124. Means "
            "78.70 vs 78.71 kg (-0.01; T1). The DCC function omits records with "
            "no V1AGE01 (phv00204712, pht004063); the number of participants "
            "this affects is not documented in the material reviewed. The cause "
            "of the +124 is not established."
        ),
    },
    # ── CARDIA ────────────────────────────────────────────────────────────────
    ("CARDIA", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-stored BMI A20BMI (phv00113661, "
            "pht001583/A4F20, 'BODY MASS INDEX, KG/M**2'), mean 24.536. The DCC "
            "computes weight/height^2 from its harmonized height (A20HGT, "
            "phv00113634, cm) and weight (A20WGT, phv00113635, lbs x 0.45359), "
            "mean 24.484. N is 3,612 on both sides and the mean delta is +0.052 "
            "(T2). The difference is proportional across the distribution "
            "(median +0.049, P99 +0.090); the ratio of means, 1.0021, equals "
            "2.20462/2.2, which would arise if the stored value used 2.2 lb/kg. "
            "The dbGaP dictionary does not document the study formula, so the "
            "cause is not established."
        ),
    },
    ("CARDIA", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads A10SMOKE (phv00113224, pht001573/A4F10, 'CIGARETTE "
            "SMOKING STATUS', Year 0). The codes are unlabeled in dbGaP; the "
            "spec maps 0 = Never, 1 = Former, 2 = Current (the 489 and 992 "
            "counts equal the A09SMKNW counts for codes 1 and 2). BDC N is "
            "3,603 (19 missing): Current 992, Not Current 2,611. The DCC uses "
            "A09SMKNW (phv00113168, pht001572, 'STILL SMOKES CIGARETTES "
            "REGULARLY?') and codes participants with A10CIGS (phv00113213) = "
            "No as not current: N 3,560 (62 missing), Current 992, Not Current "
            "2,568. Current-smoker counts are identical; the 43-participant gap "
            "is in Not Current and in missing. Participant-level reconciliation "
            "was not run."
        ),
    },
    ("CARDIA", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads A10SMOKE (phv00113224, pht001573/A4F10); the spec maps "
            "codes 1 and 2 to Ever Smoked and 0 to Never Smoked. N 3,603, Ever "
            "1,481 (41.1%), Never 2,122, 19 missing. The DCC reads A10CIGS "
            "(phv00113213, 'SUBJECT HAS SMOKED CIGARETTES. Q 2'; dbGaP 1 = No "
            "2,079, 2 = Yes 1,499, M 44): N 3,578, Ever 1,499 (41.9%), Never "
            "2,079, 44 missing. Neither side uses A01SM100. BDC has 43 more "
            "Never, 18 fewer Ever and 25 fewer missing; A10SMOKE and A10CIGS "
            "were not reconciled at participant level, so the cause of the "
            "difference is not established."
        ),
    },
    ("CARDIA", "il6_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Both sides read FL6IL6 (phv00121064, pht001862, Year 15). The DCC "
            "sets il6 = 12 where FL6IL6CM == 'High > 12' (6 rows in dbGaP); "
            "il6.yaml does not impute. Run 0820: N 689 (BDC) vs 695 (DCC), mean "
            "1.74 vs 1.83 pg/mL, P99 8.17 vs 10.84. The 6 imputed values "
            "account for the whole mean difference: (689 x 1.7409 + 6 x 12)/695 "
            "= 1.8295."
        ),
    },
    ("CARDIA", "platelet_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "A05PLATL (phv00112690, pht001563, Year 0) has dictionary range "
            "0..7.54 and no unit in dbGaP; values average 2.71. "
            "platelet_ct.yaml and the DCC both multiply by 100 to give 10*3/uL. "
            "One participant has a recorded 0, which BDC passes through as "
            "recorded (the dictionary documents no missing code for A05PLATL); "
            "the DCC code filters only 'M' and also keeps it. N is 3,581 on "
            "both sides and the mean is 271.31 (T1)."
        ),
    },
    ("CARDIA", "crp_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "crp.yaml emits both Year 15 assays under OMOP:4208414, separated "
            "by method_type. FL6CRP (phv00120758; dbGaP 'C-REACTIVE PROTEIN IN "
            "uG PER ML', n=3,261) is labelled 'Original assay (FL6CRP)'. "
            "FL6CRPBN (phv00120759; dbGaP 'RERUN CRP (uG/ml - BNII METHOD)', "
            "n=3,170) is labelled 'BNII method rerun (FL6CRPBN)'. The extractor "
            "selects the BNII label (config.py preferred_method_override), "
            "which is the variable the DCC reads. N is 3,170 and the mean is "
            "3.30 mg/L on both sides; original-assay values are not part of the "
            "comparison."
        ),
    },
    ("CARDIA", "sleep_duration_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "F67SLPHR (phv00120534, pht001839, Year 15, 'PAST MONTH AVG "
            "SLEEPING HOURS. Q 7') has dictionary range 1..280. BDC passes the "
            "recorded values through, including 8 above 24 hours that the "
            "extractor flags as implausible. The DCC keeps only values < 24 (N "
            "3,269 vs 3,277 for BDC). The 8 values account for the SD gap (8.29 "
            "vs 1.29) and move the mean from 6.53 to 6.90 hours; median, "
            "quartiles and P99 are identical."
        ),
    },
    # ── MESA ──────────────────────────────────────────────────────────────────
    ("MESA", "hispanic_or_latino_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Across MESA both sides report Hispanic 2,177 and Not Hispanic 919, "
            "with 62.7% missing on both. For MESA Family (pht001121) both sides "
            "use scrhispf (phv00087659; 919 = 0, 659 = 1) together with racefc "
            "(phv00087074) = 4, and all 919 Not Hispanic values come from "
            "Family. For MESA Classic (race1c == 4: 1,450) and AirNR (51), both "
            "sides label Hispanic only from race1c and leave everyone else "
            "missing."
        ),
    },
    ("MESA", "platelet_ncnc_bld_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "BDC platelet_ct.yaml maps two sources: pht001984 (MESA "
            "Inflammation, phv00128760, N=894) and pht004319 (MESA Epigenomic "
            "CBC, Exam 5, phv00218991, N=2,750). The comparison grades BDC at "
            "the Epigenomic exam, the source the DCC uses (pht004319 plt5): "
            "N=2,750 and mean 228.23 on both sides, 66.9% missing on both."
        ),
    },
    ("MESA", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC hypert_trt.yaml unions two ATC:C02 indicators at the same "
            "exam, htnmed1c (computed) and bpmed1 ('taking meds for "
            "hypertension'): Classic Exam 1 phv00085324 / phv00085236, AirNR "
            "phv00083163 / phv00082998. Family has htnmedfc (phv00087093) only. "
            "The DCC uses htnmed1c (htnmedfc for Family). BDC Yes is 3,307 of "
            "8,258 answered (40.0%) against 3,236 of 8,254 (39.2%) for the DCC."
        ),
    },
    # ── FHS ───────────────────────────────────────────────────────────────────
    ("FHS", "total_cholesterol_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "The comparison compares both sides at the same exams (Offspring "
            "Exam 1, Generation 3 Exam 1, New Offspring Spouse Exam 1, Omni 2 "
            "Exam 1). The DCC documents that it excludes the Original cohort "
            "and reads pht006026 TC1 (phv00277047) for Generation 3, NOS and "
            "Omni 2 and pht006027 TC1 (phv00277194) for Offspring. BDC N=9,428 "
            "(37.5% missing) vs DCC N=9,507 (37.3% missing); means are 194.24 "
            "and 194.23 mg/dL (delta +0.004). The 79-participant N difference "
            "is of the same size as the 84-participant difference in the cohort "
            "universe (see the cohort-level note); no per-variable cause has "
            "been established."
        ),
    },
    ("FHS", "triglycerides_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "The comparison compares both sides at the same exams as total "
            "cholesterol (Offspring Exam 1, Generation 3 Exam 1, NOS Exam 1, "
            "Omni 2 Exam 1). The DCC documents that it excludes the Original "
            "cohort and reads pht006026 TRIG1 (phv00277049) for Generation 3, "
            "NOS and Omni 2 and pht006027 for Offspring. BDC N=9,426 (37.5% "
            "missing) vs DCC N=9,505 (37.4% missing); means are 107.28 mg/dL on "
            "both sides (delta +0.004). The 79-participant N difference is of "
            "the same size as the 84-participant difference in the cohort "
            "universe; no per-variable cause has been established."
        ),
    },
    ("FHS", "cabg_prior_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "The DCC counts a CABG when pht000389 VESSEL > 0 and PROCDATE <= 0 "
            "(on or before Exam 1), and takes participants with cvd == 0 in "
            "pht003316 as negatives; participants with neither have no DCC "
            "value (3,359, 22.1% missing). BDC hist_cor_bypg.yaml maps "
            "cumulative exam questions (Original Exam 21, Offspring Exam 5, "
            "Generation 3 Exam 1). The comparison compares FHS at its baseline "
            "exams, so only Generation 3 Exam 1 (pht000074 G3A255, phv00021084) "
            "contributes. BDC has 7 Prior History among 4,036 answered (the "
            "comparison counts a blank condition status as answered; 2 G3A255 "
            "values are null) (73.3% missing) vs DCC 17 among 11,814."
        ),
    },
    ("FHS", "angina_prior_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "The DCC codes angina from pht000309 EVENT == 6 with DATE <= 0 and "
            "takes participants with cvd == 0 in pht003316 as negatives, so "
            "every followed participant has a value. BDC angina.yaml reads only "
            "pht000309: EVENT == 6 with DATE <= 0 is PRESENT and every other "
            "pht000309 event row has a blank status; the comparison counts a "
            "blank condition status as answered, giving 8,626 No Prior History. "
            "Participants with no pht000309 row have no BDC value. Prior "
            "History is 104 on both sides. BDC N=8,730 (42.1% missing) vs DCC "
            "N=15,154 (0.1% missing)."
        ),
    },
    ("FHS", "hispanic_or_latino_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC has no Original-cohort ethnicity. It reads Offspring Exam "
            "8 (pht000747 H700/H701), Omni 1 Exam 3 (pht004815 h700/h701), and "
            "Generation 3, NOS and Omni 2 from the race item g3a484 (pht000074, "
            "pht006005, pht006006) plus g3b0624 in pht003094; discordant "
            "answers across visits are coded 'both' (7 participants). BDC reads "
            "these tables and also pht016162 (vr_racesum_2011) eth_sum "
            "(phv00568195): 0 = Not Hispanic (7,247), 1 = Hispanic (401), 88 = "
            "'Defaulted ethnicity (Not Hispanic or Latino)' (7,417). BDC maps "
            "88 to OMOP:8552 and the comparison counts it as missing. BDC "
            "N=7,669 (49.2% missing) vs DCC N=6,665 (56.1% missing)."
        ),
    },
    ("FHS", "race_us_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC reads Original from pht003099 (idtype 0, assigned White; "
            "the DCC function comment records that an FHS investigator "
            "confirmed this), Offspring from Exam 8 only (pht000747 H702-H707), "
            "Omni 1 from pht004815, and Generation 3, NOS and Omni 2 from "
            "pht000074/pht006005/pht006006 plus pht003094. BDC reads pht016162 "
            "(vr_racesum_2011) race_sum (phv00568194) together with pht009760, "
            "pht000074, pht003094, pht000747 and pht004815; the 14,892 BDC "
            "values equal the race_sum non-null count, but the category counts "
            "differ from race_sum (for example 7 American Indian or Alaska "
            "Native, which race_sum does not code separately), so the other "
            "tables supply some values. In pht016162, code 88 'Defaulted race "
            "(White)' covers 7,121 participants and maps to White. In v35, "
            "2,003 of the 4,979 Offspring participants (pht003099 idtype 1) "
            "have no row in the Offspring Exam 8 table (pht000747, 2,976 rows), "
            "the DCC's only Offspring race source; this is of the same order as "
            "the 2,128-participant difference in missing counts, but a "
            "per-cohort breakdown has not been run. BDC N=14,892 (1.3% missing) "
            "vs DCC N=12,848 (15.3% missing)."
        ),
    },
    ("FHS", "height_baseline_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "At the compared exams BDC bdy_hgt.yaml emits the workthru heights, "
            "in inches to the next lower 1/4 inch (pht007777 HGT1 phv00369944 "
            "for Original; pht009761 HGT1 phv00423918 for Offspring and Omni). "
            "One height source applies at Original Exams 1/4/5 and Offspring "
            "Exams 1/2; Original Exams 10-32 carry both a per-exam block and a "
            "workthru block. The DCC reads 2.54 x (MF67 + 0.01 x MF68) "
            "(pht000009 phv00000539, phv00000540) for Original, 2.54 x HGT1 "
            "(pht006026, pht006027) for Generation 3, NOS, Omni 2 and "
            "Offspring, and 2.54 x e025 (pht004813) for Omni 1. BDC N=15,072 "
            "(0.1% missing), mean 167.442 cm vs DCC N=15,141 (0.2% missing), "
            "mean 167.446 cm (delta -0.004 cm); quartiles and P1/P99 are "
            "identical."
        ),
    },
    ("FHS", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original (Exam 4): both sides read MF250 (phv00000705, pht000009). "
            "The DCC recodes 2 (YES, DOUBTFUL; n=13) to 0; BDC hypert_trt.yaml "
            "maps 0 to ABSENT, 1 to PRESENT and 2 to UNKNOWN. Offspring Exam 1: "
            "the DCC reads HRX1 in pht006027 (phv00277245); BDC reads HRX1 in "
            "pht009761 (phv00423953; 0/1). For Generation 3, NOS and Omni 2 the "
            "DCC reads HRX1 in pht006026 (phv00277059). For Omni 1 the DCC "
            "reads e221 (phv00250358, pht004813). BDC N=14,290 (5.3% missing) "
            "vs DCC N=14,377 (5.2% missing); Yes 880 (6.2%) vs 878 (6.1%)."
        ),
    },
    ("FHS", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original: both sides read MF71 (phv00000543, pht000009) at Exam 1 "
            "(MF70 shows the source form may come from Exams 1-4). The DCC "
            "codes MF71 = 1 or 3 as current and 2, 5 or 7 as not current; BDC "
            "cig_smok.yaml maps 7 (n=62) to OMOP:45885135 and the comparison "
            "counts it as missing (5,046 MF71 + 9,993 STATUS1 - 62 = 14,977). "
            "Other sub-cohorts: the DCC reads Offspring A99 (pht000030 "
            "phv00007612), Generation 3/NOS/Omni 2 g3a071/g3a072 (pht000074, "
            "pht006005, pht006006) and Omni 1 e319 (pht004813); BDC reads "
            "pht012916 STATUS1 (phv00525298; 0 Never, 1 Former, 2 Current). BDC "
            "N=14,977 (0.7% missing) vs DCC N=15,100 (0.5% missing); maximum "
            "category difference 0.4pp. The remaining per-cohort differences "
            "have not been attributed."
        ),
    },
    ("FHS", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original: both sides read MF71 (phv00000543, pht000009) at Exam 1. "
            "The DCC codes 1, 2 or 3 as ever and 5 or 7 as never; BDC maps 7 "
            "(n=62) to OMOP:45885135 and the comparison counts it as missing. "
            "Other sub-cohorts: the DCC reads Offspring A99 (pht000030), g3a070 "
            "(Generation 3, NOS, Omni 2) and, for Omni 1, e319 and g675-g677 "
            "(pht004813, pht004814); BDC reads pht012916 STATUS1 (phv00525298). "
            "BDC N=14,977 (0.7% missing) vs DCC N=14,905 (1.8% missing); "
            "maximum category difference 0.5pp. The cause of the larger DCC "
            "missing count has not been attributed."
        ),
    },
    ("FHS", "pad_prior_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC codes PAD from pht000309 EVENT == 30 ('IC, first episode "
            "only') with DATE <= 0 and takes participants with cvd == 0 in "
            "pht003316 as negatives, so every followed participant has a value. "
            "BDC pad.yaml reads the clinical diagnostic impression 'CDI - other "
            "peripheral vascular disease' (Offspring Exam 5 E630 phv00009530; "
            "Generation 3, Omni 1, NOS and Omni 2 Exam 1) and emits "
            "MONDO:0005294 (peripheral vascular disease); it has no Original "
            "block. The two sides measure related but not identical concepts. "
            "BDC has 15 Prior History among 5,014 answered (66.8% missing) vs "
            "DCC 39 among 15,154 (0.1% missing)."
        ),
    },
    ("FHS", "hematocrit_vfr_bld_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "For Offspring the DCC takes the most recent exam available (Exam 9 "
            "pht004802, then Exam 2 pht000031, then Exam 1 pht000030). "
            "Offspring Exam 2 B764 (phv00008111, pht000031) has a dictionary "
            "unit of 'percentage' and a dbGaP mean of 4.409 (n=3,584); "
            "hemat.yaml multiplies it by 10 before emitting %. The scaling "
            "factor is not stated in the dictionary. BDC mean 41.87 vs DCC "
            "41.86 (delta +0.011); N=7,994 vs 8,065. The DCC function uses B764 "
            "as recorded, without scaling."
        ),
    },
    ("FHS", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC emits the study-reported count BA_NUM (phv00172197 pht002889; "
            "phv00227044 pht004802), recorded at 0.1 x10^3/uL resolution; BDC "
            "keeps the value the study reports. The DCC derives WBC x BA_PER / "
            "100 from the same two tables (pht002889 for Generation 3, NOS and "
            "Omni 2; pht004802 for Offspring and Omni 1) and documents the "
            "choice as avoiding round-off effects. BDC median 0.0 vs DCC "
            "0.0385; mean 0.031 vs 0.042; BDC Q3 and P99 are 0.1."
        ),
    },
    ("FHS", "cac_score_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "Both sides average the coronary scans CA1 and CA2 for Generation 3 "
            "(pht000144) and Offspring (pht000145) and compute age as age1 plus "
            "days since Exam 1 (studydat). BDC emits no aortic score (AA) under "
            "the coronary code. The DCC also reads the Omni CT table pht005161 "
            "(IDTYPE 7 and 72; 124 and 146 participants in the dbGaP variable "
            "report, 270 in total). The BDC pht005161 block carries no visit "
            "and is not selected at the compared visits. BDC N=3,381 (77.6% "
            "missing) vs DCC N=3,686 (75.7% missing), a 305-participant "
            "difference; the Omni table accounts for up to 270 of them and the "
            "remaining difference has not been attributed. Mean 134.64 vs "
            "133.37 Agatston (+1.27); P99 2,409 vs 2,321."
        ),
    },
    # ── CHS ───────────────────────────────────────────────────────────────────
    ("CHS", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-calculated BMI at CHS BASELINE BOTH (BASEBOTH "
            "phv00100386, pht001452, 'BODY MASS INDEX (kg/m2)'; dbGaP n=5,513, "
            "18 missing); bmi.yaml has no BASE1 or YR5NEW BMI block. The DCC "
            "documents BMI as weight/height^2 from its harmonized baseline "
            "height and weight. N is 5,513 on both sides. Mean 26.684 (BDC) vs "
            "26.685 (DCC), a difference of -0.0014; median 26.075 vs 26.083 "
            "(-0.009), Q1 -0.004, Q3, P1 and P99 within 0.001. The source of "
            "the residual difference between stored and computed BMI was not "
            "examined."
        ),
    },
    ("CHS", "bp_systolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "BDC reads AVZMSYS (phv00100435, pht001452, 'AVE ZERO MUD SYSTOL "
            "(mm Hg)'; BASE1 phv00099441 is also mapped); N 5,522 equals the "
            "dbGaP BASEBOTH count. The DCC reads BASEBOTH and sets an SBP/DBP "
            "pair to missing unless both are present and SBP >= DBP, and "
            "requires age; its code has no value-range filter. dbGaP BASEBOTH "
            "has 5,522 SBP and 5,516 DBP values, so at least 6 of the 7 "
            "participants in the N gap (5,522 vs 5,515) have SBP without DBP. "
            "The seventh was not identified. Mean 136.58 vs 136.53 (+0.050)."
        ),
    },
    ("CHS", "bp_diastolic_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC maps AVZMDIA from BASE1 (phv00099442, 'AVE ZERO MEDDLER "
            "DIASTOLIC BP', dictionary range 0-116) and BASEBOTH (phv00100436, "
            "'AVE ZERO MUD DIASTOL-adj', range 40-116). For 31 participants the "
            "two disagree and the extractor takes the first by row order. The "
            "12 zero values in the BDC output, which the extractor flags as "
            "implausible, cannot come from BASEBOTH (minimum 40), so they come "
            "from BASE1. The DCC reads BASEBOTH only, with the SBP >= DBP pair "
            "rule. Run 0820: N 5,516 vs 5,515; mean 70.639 vs 70.694; SD 11.65 "
            "vs 11.43 (dbGaP BASEBOTH SD 11.44). The mean gap was not "
            "decomposed further."
        ),
    },
    ("CHS", "cabg_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC maps CABG from BASE1 (phv00099031), BASEBOTH BPSSUR "
            "(phv00100321) and EVENT_SUMMARY BPSSURBL (phv00100785); the DCC "
            "reads BPSSURBL only. Both BPSSUR and BPSSURBL have dbGaP n=5,493 "
            "(236 Yes, 5,257 No, 38 missing). Prevalence is identical (236, "
            "4.3%). The 38 are missing in the DCC data. In BDC they carry a "
            "blank status because the spec maps only codes 0 and 1, and the "
            "comparison counts a blank procedure status as answered and not "
            "Present, so BDC shows 0 missing."
        ),
    },
    ("CHS", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the study-derived SMOKE (1 Never, 2 Former, 3 Current): "
            "BASE1 phv00099445 (pht001450, n=4,900, 3 missing) at 'CHS BASELINE "
            "2' and YR5NEW phv00105886 (pht001490, n=625, 3 missing) at 'CHS "
            "YEAR 5 NEW'; N 5,525 (6 missing). The DCC derives the variable "
            "from the raw items SMOKE101 ('SMOKED IN LIFETIME') and SMOKE201 "
            "('SMOKED CIGARETTES LAST 30 DAYS'): SMOKE101 = 0 with SMOKE201 "
            "blank is coded 0, otherwise SMOKE201; rows with neither item, or "
            "without age, are dropped. N 5,497 (34 missing); Current 664 (BDC) "
            "vs 656 (DCC), Not Current 4,861 vs 4,841. In BASE1, SMOKE101 has "
            "n=4,884 against SMOKE n=4,900, so the derived variable is "
            "populated for some participants whose raw items are blank. The "
            "28-participant difference was not reconciled at participant level."
        ),
    },
    ("CHS", "weight_baseline_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Graded on measured WEIGHT13 (phv00100383, pht001452 BASEBOTH, "
            "'WEIGHT - LBS', n=5,514), the variable the DCC reads (x 0.453592). "
            "bdy_wgt.yaml maps no age-50 recall variables. N is 5,514 on both "
            "sides; mean 72.791 vs 72.791 (+0.0001, consistent with the "
            "conversion constants 0.45359237 and 0.453592)."
        ),
    },
    ("CHS", "antihypertensive_meds_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "At baseline, hypert_trt.yaml has one ATC:C02 indicator: BASEBOTH "
            "HTNMED06 (phv00100595, pht001452, 'Any hypertension medication', "
            "visit 'CHS BASELINE BOTH'), the variable the DCC reads. Run 0820: "
            "Yes 2,634, No 2,892 and 5 missing on both sides (T1)."
        ),
    },
    ("CHS", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC derives ever-smoker from the study-derived SMOKE status "
            "(cig_smok.yaml: BASE1 phv00099445 at 'CHS BASELINE 2'; YR5NEW "
            "phv00105886 at 'CHS YEAR 5 NEW'). The DCC (ever_smoker_baseline_1 "
            "v4) uses the questionnaire items rather than the study-derived "
            "variable and codes any positive indication as ever: SMOKE101 "
            "(phv00098844), SMOKE201 (phv00098845), SMKAGE (phv00099157) or "
            "AMOUNT > 0 (phv00099159) across pht001450 and pht001490. DCC 55.6% "
            "Ever (3,068/5,519) vs BDC 53.7% (2,966/5,525), a 1.9pp gap (Ever "
            "-102, Never +108). The cause was not examined at participant "
            "level."
        ),
    },
    ("CHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no CHS carotid_plaque.yaml, so the variable is not "
            "comparable (BDC 100% missing; DCC 4,305 Prior History, 1,154 No, "
            "72 missing). Sources exist in ULTRAYR5 (pht001473): "
            "LMRPH155/LMRPH255 (phv00101317/phv00101318, original-cohort "
            "baseline reread) and LMRPH141/LMRPH241 (phv00101306/phv00101307, "
            "'YEAR 5 LESION MORPHOLOGY'), which the DCC uses for the African "
            "American sub-cohort (PERSTAT = 2). Their 0/1/2 codes are unlabeled "
            "in dbGaP. The DCC codes plaque as present when either side code is "
            "> 0, by sub-cohort. A spec waits on the CHS reading protocol and a "
            "curated concept code (HV issue #946, awaiting external)."
        ),
    },
    # ── JHS ───────────────────────────────────────────────────────────────────
    # JHS universe difference: see COHORT_LEVEL_NOTES['JHS'].
    # ──────────────────────────────────────────────────────────────────────────
    ("JHS", "pad_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "pad.yaml's only PAD source is the annual follow-up (pht008725, "
            "visit 'JHS AFU', MONDO:0005294). The DCC derives prevalent PAD "
            "from ABI < 0.9 at Exam 1 (pht001921 arm and ankle pressures). The "
            "comparison grades JHS at Exam 1 with no fallback to other visits, "
            "so BDC has no value and pad_prior_1 is NOT COMPARABLE (all "
            "missing; 234 positives at other visits are not used). TOPMed: 83 "
            "Prior History of 3,126. BDC does not derive a PAD condition from "
            "an ABI cutoff and does not map the ABI (analysis1 pht008729 "
            "phv00401122, n = 3,426 in dbGaP) in this run."
        ),
    },
    ("JHS", "cabg_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "hist_cor_bypg.yaml maps CABG at Exam 2, Exam 3 and the AFU, not at "
            "Exam 1, so cabg_prior_1 is NOT COMPARABLE (all missing; 66 "
            "positives at other visits are not used). An Exam 1 source exists: "
            "MHXA52A (pht001963 phv00127728, 'Did you have a coronary bypass?', "
            "53 Yes / 95 No), preceded by MHXA51 (heart or artery surgery "
            "ever). The DCC reads MHXA52A and recodes a missing answer to 0 "
            "when the participant has other data; whether a 'No' on MHXA51 "
            "implies a CABG 'No' has not been decided. This item is under "
            "review with the study's guidance."
        ),
    },
    ("JHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no JHS carotid plaque spec, so the variable is NOT "
            "COMPARABLE. The source is plq01 (pht008791 phv00404237, 0 = 2,288 "
            "/ 1 = 1,414). Its table has no VISIT variable and visit.yaml "
            "labels it 'JHS LAB DATA'; the DCC reads plq01 from pht001978 and "
            "pairs it with the Exam 1 age (AGE01, pht001949). A spec would "
            "require a documented Exam 1 link and a concept code (HV issue "
            "#224)."
        ),
    },
    ("JHS", "cimt_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "Not aligned in the comparison (config.py "
            "_OTHER_COHORT_MEASUREMENT_VISITS). JHS carotid_imt.yaml emits each "
            "of six common-carotid far-wall segments from pht008791 as its own "
            "row; the DCC averages the three left and three right segments "
            "(pht001978). One segment row is not the same quantity as that "
            "mean. The study's own summary cca45_1 (phv00404240) is a separate "
            "variable and is not mapped to this concept."
        ),
    },
    ("JHS", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the ATC:C02 indicator MSRA30A (phv00127922, pht001964, "
            "JHS Exam 1; Y 1,939 / N 1,719 / D 1). hypert_trt.yaml emits a "
            "blank-status row for each missing answer (var_report nulls=210), "
            "and the extractor counts a blank medication status as missing. "
            "BDC: 53.0% Yes (1,939/3,658), 225 missing (5.8%). The DCC reads "
            "BPM01 (pht001949 phv00126038): 53.8% Yes (1,794/3,335), 267 "
            "missing (7.4%). The 0.8 pp difference is between different source "
            "variables; the question wording of BPM01 is not documented in the "
            "material reviewed."
        ),
    },
    ("JHS", "total_cholesterol_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "tot_chol_bld.yaml has 8 blocks across 8 tables (Exams 1-3, LAB "
            "DATA). Exam 1 rows come from two tables (pht001945, pht008729; "
            "7,707 rows for 3,883 participants) and the log reports no "
            "conflicting duplicates. TOPMed: N 3,471, mean 198.80 mg/dL, SD "
            "40.96, 3.6% missing. BDC: N 3,813, mean 199.00, SD 40.87, 1.8% "
            "missing. The mean difference is +0.20 mg/dL (0.005 SD, tier T1); "
            "the N difference follows the cohort-level participant-universe "
            "difference."
        ),
    },
    ("JHS", "triglycerides_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "triglyc_bld.yaml has 9 blocks across 9 tables (Exams 1-3, LAB "
            "DATA), the same structure as total cholesterol. TOPMed: N 3,471, "
            "mean 110.04 mg/dL, SD 95.07. BDC: N 3,813, mean 110.11, SD 92.87. "
            "The mean difference is +0.07 mg/dL (0.0008 SD, tier T1). Each side "
            "has 2 values outside the plausibility range."
        ),
    },
    ("JHS", "cac_score_1"): {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "Both sides read CSTA24 (phv00126002, pht001948, Agatston score all "
            "coronary). BDC reads dbGaP v7 pht001948.v3 at JHS Exam 2 (visit "
            "override; n=2,144). The DCC read phs000286.v5 pht001948.v1, "
            "inner-joined to AGE01 (pht001949) with missing values removed "
            "(N=1,664). BDC mean 175.7 (SD 532.9) vs TOPMed 146.0 (SD 426.4). "
            "The v5 and v7 table contents were not compared, so the cause of "
            "the N and mean difference is not established."
        ),
    },
    # ── HCHS-SOL ──────────────────────────────────────────────────────────────
    ("HCHS_SOL", "race_us_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "The HCHS-SOL dbGaP tables (pht004713, pht004715) contain no OMB "
            "race variable. All participants are Hispanic/Latino; the study "
            "collected a 7-level heritage subgroup (BKGRD1_C7, phv00226254) "
            "that is not an OMB race. BDC records race as UNKNOWN for all "
            "11,831 participants; TOPMed records Other for all 12,895. For "
            "scoring, the comparison tool maps BDC UNKNOWN to Other, so Race "
            "shows tier T1 (0.0 pp). The two values are different statements: "
            "race not recorded (BDC) and race recorded as Other (TOPMed)."
        ),
    },
    ("HCHS_SOL", "antihypertensive_meds_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "Both sides read MED_ANTIHYPERT (phv00226324, pht004715); BDC is "
            "graded on that ATC:C02 indicator only. BDC: 17.0% Yes "
            "(1,972/11,609), 222 missing (1.9%). TOPMed: 16.9% Yes "
            "(2,078/12,280), 615 missing (4.8%). The valid-N difference (-671) "
            "combines the cohort-level participant-universe difference with the "
            "difference in missing counts."
        ),
    },
    ("HCHS_SOL", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported LABA27 (phv00226301, pht004715), "
            "recorded at 0.1 x10^9/L resolution and at least three quarters of "
            "the 11,063 values are 0 (Q1 and Q3 are both 0.000). The DCC "
            "derives WBC (LABA1) x % basophils (LABA14) / 100. BDC mean 0.023 "
            "vs 0.034 for TOPMed (median 0.000 vs 0.029)."
        ),
    },
    ("HCHS_SOL", "eosinophil_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported LABA26 (phv00226300, pht004715), "
            "recorded at 0.1 x10^9/L resolution. LABA26 holds one recorded "
            "value of 230 (var_report max; % eosinophils (LABA13) tops out at "
            "36 and WBC (LABA1) at 31.8, so it exceeds any WBC in the table). "
            "BDC passes it through and the extractor flags it; it accounts for "
            "the SD difference (2.19 vs 0.19). The DCC derives WBC (LABA1) x % "
            "eosinophils (LABA13) / 100, which does not use LABA26."
        ),
    },
    ("HCHS_SOL", "monocyte_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported LABA25 (phv00226299, pht004715), "
            "recorded at 0.1 x10^9/L resolution; the DCC derives WBC (LABA1) x "
            "% monocytes (LABA12) / 100. The mean difference is 0.005 (0.025 "
            "SD). The SD is 0.229 vs 0.183 because LABA25 holds one value of "
            "14.8 (var_report max), which the extractor flags as implausible; "
            "that single value accounts for the SD difference."
        ),
    },
    # ── COPDGene ──────────────────────────────────────────────────────────────
    ("COPDGENE", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-calculated BMI (phv00159593, pht002239 v5, "
            "dictionary comment 'calculated', kg/m2, stored to 2 decimals) at "
            "COPDGene P1. The DCC computes weight/height^2 from its harmonized "
            "Weight_KG (phv00159591) and Height_CM (phv00159592), read from "
            "pht002239 v4 (phs000179.v5). N is 10,371 on both sides; mean 28.83 "
            "vs 28.82 (+0.011, T1). Weight (83.62 vs 83.58 kg, +0.042) and "
            "height (+0.004 cm) differ in the same direction; 0.042 kg "
            "corresponds to about 0.015 BMI units. Rounding of the stored BMI "
            "to 2 decimals would change the mean by about 0.00003 and does not "
            "account for the gap. The cause of the component differences was "
            "not examined; the table versions differ."
        ),
    },
    ("ARIC", "lipid_lowering_medication_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads two DERIVE13 (pht004063) indicators: "
            "STATINCODE01 (phv00204695, ATC:C10AA) and CHOLMDCODE01 "
            "(phv00204802, ATC:C10A; the spec maps T to UNKNOWN); a participant "
            "positive on either is Yes. The DCC reads CHOLMDCODE01 only "
            "(phv00204802), with T set to missing. BDC: 14,369 answered, 698 "
            "missing (4.6%); the DCC: 14,827 valid, 217 missing (1.4%) (M3). "
            "Yes: 426 (3.0%) BDC vs 433 (2.9%) DCC (T1), so the difference is "
            "in missingness, not prevalence. The DCC function omits records "
            "with no V1AGE01 (phv00204712, pht004063); the number of "
            "participants this affects is not documented in the material "
            "reviewed. The source of the 698 BDC missing is not established in "
            "this run."
        ),
    },
    ("FHS", "mi_prior_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "The DCC codes prior MI from pht000309 EVENT 1-5 with DATE <= 0 "
            "(phv00036469, phv00036471) and takes participants with cvd == 0 in "
            "pht003316 as negatives; participants with neither have no DCC "
            "value. BDC hist_my_inf.yaml reads one item per baseline exam: "
            "Original Exam 4 MF279 (phv00000734, pht000009; 3 and 4 map to "
            "UNKNOWN), Offspring Exam 1 A163 (phv00007665, pht000030), "
            "Generation 3, NOS and Omni 2 Exam 1 self-report items (e.g. "
            "pht000074 G3A184 phv00021036), and ECG location items at Omni 1 "
            "Exam 1 (pht004813), which emit MONDO:0006652, MONDO:0006803 and "
            "MONDO:0003672 and are not counted as mi_prior_1 by the comparison. "
            "Prior History is 103 (BDC) vs 99 (DCC). BDC N=14,549 (3.6% "
            "missing) vs DCC N=15,154 (0.1% missing). Omni 1 therefore has no "
            "graded MI source, so its 490 participants (pht003099 idtype 7) "
            "have no BDC value; this is within the 540 participants without a "
            "BDC answer, but participant-level reconciliation was not run."
        ),
    },
    ("HCHS_SOL", "height_baseline_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "TOPMed has 391 missing (3.0% of 12,895); BDC has 2 (0.0% of "
            "11,831). The 1,064-participant universe difference exceeds the "
            "TOPMed missing count, but the missing participants were not "
            "matched, so the cause is not established."
        ),
    },
    ("HCHS_SOL", "weight_baseline_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "TOPMed has 400 missing (3.1% of 12,895); BDC has 3 (0.0% of "
            "11,831). The 1,064-participant universe difference exceeds the "
            "TOPMed missing count, but the missing participants were not "
            "matched, so the cause is not established."
        ),
    },
    ("JHS", "ldl_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-stored Exam 1 LDL from analysis1 (pht008729 "
            "phv00401134, 'Fasting LDL Cholesterol Level'); its 379 missing "
            "(9.8% of 3,883) equal the 379 nulls for that variable in dbGaP. "
            "The DCC computes LDL with the Friedewald formula from its "
            "harmonized total cholesterol, HDL and triglycerides, and sets it "
            "missing when triglycerides are 400 mg/dL or higher: 169 missing "
            "(4.7%) of 3,602. Valid N differs by +71 (total cholesterol: +342). "
            "Means are 126.59 against 125.94 mg/dL (0.017 SD, tier T2). Why "
            "phv00401134 is null for 379 participants is not documented in the "
            "material reviewed."
        ),
    },
    ("JHS", "lipid_lowering_medication_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the self-reported statin indicator at Exam 1 "
            "(tak_statin.yaml, analysis1 pht008729 phv00401114, ATC:C10AA). The "
            "DCC reads LPM01 (pht001949); its drug-class scope is not "
            "documented in the material reviewed. Yes: 13.2% (502/3,802) BDC vs "
            "13.4% (432/3,234) TOPMed. Missing: 81 (2.1%) vs 368 (10.2%); the "
            "cause of the missingness difference is not established."
        ),
    },
    ("MESA", "angina_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC grades MESA Classic Exam 1 (pht001116) and sets all 6,429 "
            "participants to 0; dbGaP pht001116 has no angina history item. BDC "
            "angina.yaml maps angina from the adjudicated events table "
            "pht001123 (ang phv00087859, no visit, follow-up events) and Family "
            "pht001121 (anginaf phv00087143, MESA FAMILY); no AirNR source is "
            "mapped. BDC has no row at MESA CLASSIC EXAM 1, so the variable is "
            "not comparable (all missing); 331 positive participants sit at "
            "other visits or with no visit and are not graded."
        ),
    },
    ("MESA", "cabg_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC grades MESA Classic Exam 1 (pht001116) and sets all 6,429 "
            "participants to 0; dbGaP pht001116 has no CABG history item. BDC "
            "hist_cor_bypg.yaml maps CABG as a Procedure from AirNR pht001111 "
            "(coronct1 phv00082876, MESA AIR EXAM) and the adjudicated events "
            "table pht001123 (cbg phv00087865, no visit); Family corobyf "
            "(phv00087146) is not mapped. BDC has no row at MESA CLASSIC EXAM "
            "1, so the variable is not comparable (all missing); 132 positive "
            "participants sit at other visits or with no visit and are not "
            "graded."
        ),
    },
    ("MESA", "coronary_angioplasty_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC sets all 6,429 MESA Classic Exam 1 (pht001116) "
            "participants to 0; dbGaP pht001116 has no angioplasty history "
            "item. MESA-ingest has no coronary angioplasty spec, so BDC has no "
            "angioplasty data at any visit (0 rows). dbGaP holds angioplasty "
            "items that BDC does not map: AirNR angct1 (pht001111 phv00082875), "
            "Family ballnf (pht001121 phv00087147), events ptca (pht001123 "
            "phv00087862) and Exam 5 angct5 (pht003091 phv00176172). The "
            "variable is not comparable (all missing)."
        ),
    },
    ("MESA", "icam1_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC assigns limit-of-detection values to 61 participants coded "
            "as exceptional missing (Classic icam11M phv00085118: 53 at -333 "
            "set to 0.35 and 5 at -555 set to 900; AirNR icam1m phv00082964: 3 "
            "at -333 set to 20). BDC icam.yaml maps only the measured icam1 "
            "values (pht001116 phv00085117, 2,506; pht001111 phv00082963, 248; "
            "total 2,754). The 61 equals the N difference (2,815 against 2,754) "
            "and is consistent with the tail differences (P1 0.35 against "
            "114.56; SD 91.66 against 80.05); the comparison has not matched "
            "these participants individually."
        ),
    },
    ("MESA", "il6_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC assigns limit-of-detection values to participants with "
            "il61M (pht001116 phv00085010) codes -333 (1, set to 0.09) and -555 "
            "(16, set to 13.0); the 2 coded -777 (invalid result) stay missing. "
            "BDC il6.yaml maps measured il61 only (phv00085009, 6,261) and "
            "records range limits of 0.09 and 13 pg/mL. The N difference (6,278 "
            "against 6,261) equals those 17 participants, and the higher DCC "
            "P99 (6.78 against 6.44) is consistent with this; the comparison "
            "has not matched them individually."
        ),
    },
    ("MESA", "lipid_lowering_medication_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC tak_statin.yaml unions two ATC:C10A indicators at the same "
            "exam, lipid1c (computed 'any lipid-lowering medication') and "
            "cholmed1 ('taking meds for high cholesterol'): Classic phv00085407 "
            "/ phv00085235, AirNR phv00083162 / phv00083002. Family has lipidfc "
            "(phv00087104) only. The DCC uses lipid1c / lipidfc (1,033 + 71 + "
            "376 = 1,480 Yes). BDC Yes is 1,581 of 8,258 answered (19.1%) "
            "against 1,480 of 8,254 (17.9%)."
        ),
    },
    ("MESA", "mi_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC grades MESA Classic Exam 1 (pht001116) and sets all 6,429 "
            "participants to 0; dbGaP pht001116 has no MI history item. BDC "
            "hist_my_inf.yaml maps MI from the adjudicated events table "
            "pht001123 (mi phv00087853, no visit, follow-up events) and Family "
            "pht001121 (heartaf phv00087142, MESA FAMILY); no AirNR source is "
            "mapped. BDC has no row at MESA CLASSIC EXAM 1, so the variable is "
            "not comparable (all missing); 247 positive participants sit at "
            "other visits or with no visit and are not graded."
        ),
    },
    ("MESA", "pad_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC grades MESA Classic Exam 1 (pht001116) and sets all 6,429 "
            "participants to 0; dbGaP pht001116 has a claudication symptom item "
            "(claud1t phv00084455) but no PAD history item. BDC pad.yaml maps "
            "PAD only from the adjudicated events table pht001123 (pvd "
            "phv00087873 and expvd phv00087852, no visit, 12,858 rows); no "
            "Family or AirNR source is mapped. BDC has no row at MESA CLASSIC "
            "EXAM 1, so the variable is not comparable (all missing); 86 "
            "positive participants sit with no visit and are not graded."
        ),
    },
    ("WHI", "coronary_angioplasty_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Prior History is identical (1,467). TOPMed has 141,124 answered "
            "(1.5% missing); BDC has 143,123 (0.1%). 1,999 women have a null "
            "Form 30 PTCA answer (pht000999 phv00078536), and the comparison "
            "counts a blank condition status as answered without history. The "
            "other 90 women have no Form 30 row and are missing on both sides. "
            "Tier T1 / M2."
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
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "COPDGene matched set is 15 variables, all T1 and M1 in run 0820. "
            "The graded phenotypes come from one table (pht002239 "
            "COPDGene_Subject_Phenotypes v5, 1,003 variable entries). The table "
            "holds several phases (P1, P2, P3, P3B), and the specs select Phase "
            "1 through the visit column (phv00568798). The DCC read an earlier "
            "version of this table (pht002239 v4, phs000179.v5)."
        ),
    },
    "HCHS_SOL": {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "TOPMed used phs000810.v1 (12,895 participants; the DCC variable "
            "files cite v1). BDC uses phs000810.v2.p2: 12,121 participants with "
            "consent (c1 HMB-NPU=2,304, c2 HMB=9,817), of whom 11,831 have a "
            "row in pht004715 (290 have none). BDC N=11,831 vs TOPMed N=12,895 "
            "is a difference of 1,064: 774 fewer consented participants in v2 "
            "and 290 consented participants with no phenotype row. The v1 "
            "breakdown could not be checked against the cached v2 metadata. "
            "Valid-N differences for the other variables are 635 to 697, "
            "smaller than 1,064 because the DCC has more missing values (about "
            "3% against about 0% for most variables; 9.1-9.3% against 6.3-6.5% "
            "for the white-cell differential counts)."
        ),
    },
    "JHS": {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC N=3,883 vs TOPMed N=3,602 (+281, +7.8%). BDC grades JHS Exam 1 "
            "for every compared variable except CAC (Exam 2) and the NOT "
            "COMPARABLE rows. The TOPMed N is close to the genetic-research "
            "consent subset: the v7 study description states that approximately "
            "3,600 participants consented to genetic research and data "
            "deposition, and JHS_Subject (pht001920) SUBJECT_SOURCE2 lists "
            "3,596 participants as JHS_CARe. This is consistent with the TOPMed "
            "set being that subset, but the TOPMed participant list was not "
            "available to confirm it. BDC N is the 3,883 participants in "
            "analysis1 (pht008729; consent groups c1=878, c2=201, c3=2,289, "
            "c4=515). TOPMed used phs000286.v5 and BDC used v7; v5 participant "
            "counts were not available. Valid-N differences are +281 to +376 "
            "for 25 of 28 variables with BDC data; the exceptions (LDL +71, CAC "
            "+480, lipid-lowering medication +568) reflect different "
            "missingness."
        ),
    },
    "MESA": {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The DCC sets prior MI, angina, PAD, CABG and coronary angioplasty "
            "to 0 for every MESA Classic Exam 1 participant (pht001116, 6,429 "
            "rows); dbGaP pht001116 holds no such history items. BDC maps MI "
            "and angina from Family (pht001121) and the events table "
            "(pht001123), PAD from pht001123 only, CABG from AirNR (pht001111) "
            "and pht001123, and has no coronary angioplasty spec. None of these "
            "gives BDC a row at MESA CLASSIC EXAM 1, so all five variables are "
            "not comparable (all missing)."
        ),
    },
    "FHS": {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "BDC reads phs000007.v35.p16 (pht003099.v10 vr_dates_2022: 7,023 "
            "male + 8,066 female = 15,089 participants). The DCC harmonized FHS "
            "from earlier releases (its FHS units cite phs000007.v29 and v30 "
            "tables) and has 15,173 participants. The net difference of 84 "
            "participants appears across nearly all variables (for example Sex: "
            "15,154 vs 15,089 valid). The material reviewed does not document "
            "its cause. FHS has Original, Offspring, Generation 3 (4,036 "
            "participants at Exam 1 in v35), New Offspring Spouse, Omni 1 and "
            "Omni 2 sub-cohorts."
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
                    # Signed (BDC minus reference) for display; the tier uses the magnitude.
                    delta = b_mean - t_mean
                    norm_delta = abs(delta) / t_sd

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
