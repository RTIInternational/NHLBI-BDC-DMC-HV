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
        # hdl_1 and ldl_1 are outside the 19-variable core set; --all-vars grades them.
        "total_cholesterol_1",
        "triglycerides_1",
    ]),
    ("CBC", [
        # Hematocrit, hemoglobin, WBC and RBC are outside the 19-variable core set;
        # --all-vars grades them.
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
            "phv00078559, 'Do you now take pills for high blood pressure?'), "
            "which dbGaP describes as a sub-question of the hypertension item "
            "HYPT (phv00078556) and as not collected on all Form 30 versions. "
            "In phs000200.v12, HYPTPILN has 35,517 Yes, 10,071 No and 97,535 "
            "null; HYPT has 47,826 Yes, 94,214 No and 1,083 null. If HYPTPILN "
            "was asked only after HYPT = Yes (inferred from totals, not "
            "confirmed from the Form 30 CRF), the nulls are the HYPT = No "
            "women, the HYPT-null women, and 2,238 of the HYPT = Yes women. BDC "
            "Yes is then a proportion among women answering the sub-question, "
            "not among all women, so the Yes shares shown above are not on the "
            "same base. The DCC derives the variable from the Form 44 "
            "medication inventory, not restricted by reported hypertension "
            "(pht002754 TCCODE antihypertensive classes at F44VTYP == 1, women "
            "with a baseline Form 80 BP reading, medication-start window). BDC "
            "does not infer 'No' from a skipped sub-question and maps pht002754 "
            "only for corticosteroids (tak_steroid.yaml). HV #954."
        ),
    },
    ("WHI", "angina_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read Form 30 ANGINA (pht000999 phv00078560). In "
            "phs000200.v12 it has 7,868 Yes, 134,382 No and 873 null. The DCC "
            "counts non-null answers only. The comparison counts a blank "
            "condition status as answered, so women with a null answer count as "
            "No Prior History for BDC. Women with no Form 30 row are missing on "
            "both sides."
        ),
    },
    ("WHI", "mi_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read Form 2 MI (pht000998 phv00078482). In "
            "phs000200.v12 it has 3,279 Yes, 139,857 No and 77 null. The DCC "
            "counts non-null answers only. The comparison counts a blank "
            "condition status as answered, so women with a null answer count as "
            "No Prior History for BDC."
        ),
    },
    ("WHI", "cabg_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read Form 30 CABG (pht000999 phv00078535). In "
            "phs000200.v12 it has 1,226 Yes, 139,880 No and 2,017 null. The DCC "
            "counts non-null answers only. The comparison counts a blank "
            "procedure status as answered, so women with a null answer count as "
            "No Prior History for BDC. Women with no Form 30 row are missing on "
            "both sides."
        ),
    },
    ("WHI", "pad_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read Form 30 PAD (pht000999 phv00078562). In "
            "phs000200.v12 it has 2,893 Yes, 139,323 No and 907 null. The DCC "
            "counts non-null answers only. The comparison counts a blank "
            "condition status as answered, so women with a null answer count as "
            "No Prior History for BDC. Other PAD blocks in pad.yaml carry no "
            "screening visit and are not read at baseline."
        ),
    },
    ("WHI", "current_smoker_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-stored Form 34 SMOKING (pht001003 phv00078825, "
            "computed from Form 34 questions 1, 1.2 and 1.5). The DCC "
            "recomputes from SMOKEVR (phv00078774) and SMOKNOW (phv00078776): "
            "not current if SMOKEVR = 0, otherwise SMOKNOW. In phs000200.v12, "
            "SMOKING has 9,802 Current and 131,561 not current (Never 71,847 "
            "plus Past 59,714), while SMOKNOW has 9,821 Yes. The 19 women who "
            "answered SMOKNOW = Yes and have no SMOKING value account for the "
            "difference (established from dbGaP totals, not matched by "
            "participant)."
        ),
    },
    ("WHI", "ever_smoker_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "The DCC reads SMOKEVR (pht001003 phv00078774), which in "
            "phs000200.v12 has 70,213 Yes, 71,847 No and 995 null. BDC reads "
            "the study-stored SMOKING (phv00078825), whose Past plus Current is "
            "69,516 and which has 1,692 null. Never Smoked is 71,847 in both. "
            "The 697-woman difference in Ever Smoked equals 678 women with "
            "SMOKEVR = Yes and no SMOKNOW answer plus 19 with SMOKNOW = Yes "
            "(established from dbGaP totals, not matched by participant)."
        ),
    },
    ("WHI", "bp_diastolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "dbGaP Form 80 (pht001019) records two readings, DIASBP1 "
            "(phv00079855) and DIASBP2 (phv00079857). BDC holds them as "
            "separate observations at WHI SCREENING; where values tie at the "
            "graded visit, the comparison keeps the first row in file order, so "
            "which reading is retained cannot be determined without participant "
            "data. The DCC keeps baseline Form 80 rows (F80VTYP = 1), sets a "
            "reading's diastolic value to missing when that reading's SBP is "
            "below its DBP or the paired value is missing, averages readings 1 "
            "and 2 (rowMeans), and drops records with no age. The two sides "
            "therefore compare one reading with a two-reading mean; the BDC N "
            "difference shown above is consistent with the DCC per-reading and "
            "age rules (inferred from totals, not matched by participant)."
        ),
    },
    ("WHI", "bp_systolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "dbGaP Form 80 (pht001019) records two readings, SYSTBP1 "
            "(phv00079854) and SYSTBP2 (phv00079856). BDC holds them as "
            "separate observations at WHI SCREENING; where values tie at the "
            "graded visit, the comparison keeps the first row in file order, so "
            "which reading is retained cannot be determined without participant "
            "data. The DCC keeps baseline Form 80 rows (F80VTYP = 1), sets a "
            "reading's systolic value to missing when that reading's SBP is "
            "below its DBP or the paired value is missing, averages readings 1 "
            "and 2 (rowMeans), and drops records with no age. The two sides "
            "therefore compare one reading with a two-reading mean; the BDC N "
            "difference shown above is consistent with the DCC per-reading and "
            "age rules (inferred from totals, not matched by participant)."
        ),
    },
    ("WHI", "hispanic_or_latino_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC derives ethnicity from Form 2 RACE (pht000998 phv00078450) "
            "alone: Hispanic/Latino if code 4, otherwise Not Hispanic for any "
            "non-null RACE. Its code comment records investigator guidance that "
            "Form 2 takes precedence and that if Form 41 is Hispanic and Form 2 "
            "is not, Form 2 wins. In phs000200.v12, RACE has 5,468 code 4, "
            "119,539 code 5 (White), 17,858 codes 1, 2, 3 and 8, and 348 null. "
            "The BDC Form 2 block emits ethnicity only for RACE 4 (Hispanic) "
            "and 5 (White, not of Hispanic origin); women coded 1, 2, 3 or 8 "
            "receive ethnicity only from Form 41 SPANISH (pht001009 "
            "phv00079316) where present, which is the source of BDC Hispanic "
            "women beyond Form 2 code 4. The higher BDC missingness shown above "
            "is the women with Form 2 RACE 1, 2, 3, 8 or null who have no Form "
            "41 SPANISH answer (inferred from the mapping, not matched by "
            "participant)."
        ),
    },
    ("WHI", "race_us_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC takes Form 2 RACE (pht000998 phv00078450, at 'WHI SCREENING') "
            "first and uses Form 41 (pht001009 per-race checkboxes, no visit) "
            "only where Form 2 is null; the extractor takes the first non-null "
            "value per column. In phs000200.v12 RACE has 5,468 Hispanic (4), "
            "1,595 Other (8), 3,498 Asian or Pacific Islander (2) and 348 null. "
            "Form 2 has no NHOPI code (2 is mapped to Asian), and BDC maps "
            "codes 4 and 8 to OMOP:8552, which BDC-HM labels Unknown and the "
            "comparison reports as Other. The DCC applies the same Form 2 "
            "precedence and, per a comment in its code citing WHI "
            "study-investigator guidance, uses Form 41 to assign a specific "
            "race to Form 2 Hispanic and Other women with a single race group "
            "and to separate Pacific Islander from Asian; Form 2 Hispanic or "
            "Other women without a single Form 41 group stay Other. BDC does "
            "not apply that refinement, which accounts for the higher BDC "
            "Other, the zero BDC NHOPI, and the lower BDC counts in the "
            "specific categories shown above. Form 41 counts race groups, so "
            "two ticks within one group are one race; the DCC has no Multiple "
            "category for WHI, and BDC Multiple arises only among women with no "
            "Form 2 race. HV #949. This item is under review with the study's "
            "guidance."
        ),
    },
    # ── ARIC ──────────────────────────────────────────────────────────────────
    ("ARIC", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At ARIC Exam 1, BDC (hypert_trt.yaml) reads three ATC:C02 "
            "indicators: HYPTMD01 (phv00204754, pht004063), HYPTMDCODE01 "
            "(phv00204798, pht004063, medication-code based) and MSRA08A "
            "(phv00207913, pht004129, medication survey item for high blood "
            "pressure); a participant positive on any of the three is Yes. The "
            "DCC reads HYPTMD01 only, with T set to missing. In phs000280.v8, "
            "HYPTMD01 has 3,710 Yes and 85 T, and HYPTMDCODE01 has 4,504 Yes, "
            "794 more than HYPTMD01; this is consistent with the higher BDC Yes "
            "share (inferred from totals, not matched by participant). The DCC "
            "function omits records with no V1AGE01 (phv00204712, pht004063)."
        ),
    },
    ("ARIC", "mch_entmass_rbc_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "In v8, MCH is recorded at Exam 3 (HMTC7, pht004109, phv00207290), "
            "Exam 4 (HMTC7, pht004110, phv00207302) and Exam 5 (CBC9, "
            "pht006422, phv00294960); the Exam 1 and 2 hematology forms "
            "(pht004107, pht004108) have no MCH variable. The DCC documents MCH "
            "as measured at visits 3, 4 and 5 only and reads the same three "
            "variables. Both sides take the visit with the most non-missing "
            "values first, then the next in succession; the comparison applies "
            "that rule to the BDC rows. BDC passes source values through. In "
            "v8, CBC9 has a maximum of 584.5 pg (SD 7.724); the DCC code "
            "removes codes A and O and records without age and applies no range "
            "filter, so the lower DCC SD shown above indicates that its output "
            "contains no value of that size. A single value of 584.5 among "
            "roughly 9,000 values is enough to raise an SD of about 2 to about "
            "6, which is consistent with the higher BDC SD shown above. The "
            "cause of the N difference is not established."
        ),
    },
    ("ARIC", "pad_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "pad_prior_1 is graded at ARIC Exam 1. BDC (pad.yaml) reads pad01 "
            "and pad02 from the ABI form (pht004027, phv00202848 and "
            "phv00202847) and PAD01 and PAD02 from DERIVE13 (pht004063, "
            "phv00204796 and phv00204795). The DCC reads PAD02 (phv00204795) "
            "only, with T set to missing. In v8, pht004027 pad02 has 14,504 "
            "values and 560 blanks, and DERIVE13 PAD02 has 13,939 values and "
            "538 blanks. The comparison counts a blank condition status as "
            "answered, so participants whose Exam 1 PAD values are all blank "
            "count as No Prior History and BDC shows no missing; the DCC drops "
            "them. A second BDC code, MONDO:0005294 (hist_cvd.yaml, HFAA11M "
            "phv00206807, pht004102), has no Exam 1 rows and adds nothing. The "
            "DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063)."
        ),
    },
    ("ARIC", "annotated_sex_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC (demography.yaml) reads sex from 26 tables, including DERIVE13 "
            "GENDER (phv00204711, pht004063) at Exam 1. The DCC reads GENDER "
            "only and drops records where it is missing. In v8, GENDER has "
            "14,477 values and no blanks, and RACEGRP also has 14,477 values "
            "and no blanks. The DCC missing counts for sex and race are equal, "
            "so those records lack both; the DCC release held participants "
            "without DERIVE13 values or rows (inferred from totals; that "
            "release is not in the material reviewed). The category "
            "distributions agree."
        ),
    },
    ("ARIC", "hispanic_or_latino_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "bdc_only": True,
        "note": (
            "BDC only; the DCC hispanic_or_latino_1 documentation has no ARIC "
            "unit. BDC (demography.yaml) emits Hispanic from the ECG race field "
            "ECGRA282 (pht012821 to pht012824, Exams 1 to 4; HISPANIC has 5, 2, "
            "2 and 1 values in v8) and from PULP24 code H (pht006468, Exam 5; 1 "
            "value). The spec emits no Not Hispanic value, and the comparison "
            "treats the ECG code ********* (OMOP:8552) as missing ethnicity, so "
            "nearly all participants are missing by construction."
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
            "to ABSENT, 4 = Positive to PRESENT). In v8, RANGNA01 has 13,687 "
            "code 4, 753 code 1 and 37 blanks; the comparison counts a blank "
            "condition status as answered, so the No Prior History count "
            "includes those 37. Under the documented coding, 13,687 of the "
            "14,440 v8 answers (code 4) are Positive; the coding is awaiting a "
            "response from the study (HV #945). The spec follows the "
            "documentation."
        ),
    },
    ("ARIC", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-computed BMI01 (phv00204719, pht004063 "
            "DERIVE13, Exam 1). The DCC computes BMI from its harmonized "
            "baseline height and weight. In v8, DERIVE13 holds 14,477 "
            "participants and BMI01 has 14,452 values and 25 blanks; BDC "
            "participants with no DERIVE13 row (590 in v8) have no BMI. The BDC "
            "missing count shown above equals those 590 plus the 25 blanks "
            "(established). The DCC valid count equals its body-weight valid "
            "count, which is consistent with a BMI computed from its own height "
            "and weight."
        ),
    },
    ("ARIC", "bp_diastolic_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads SBPA22 (phv00210291, pht004192; dictionary: 2nd and 3rd "
            "diastolic) at Exam 1, filtered to the method Seated random-zero "
            "average. The DCC recomputes the value from the individual readings "
            "(SBPA15 to SBPA20, pht004192, phv00210284 to phv00210289): it "
            "subtracts the zero readings, sets both members of a "
            "systolic/diastolic pair to missing when systolic is below "
            "diastolic, and averages the second and third readings that remain. "
            "In v8, SBPA22 has 15,050 values and 2 blanks. The DCC function "
            "omits records with no V1AGE01 (phv00204712, pht004063). The cause "
            "of the N difference is not established."
        ),
    },
    ("ARIC", "bp_systolic_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads SBPA21 (phv00210290, pht004192; dictionary: computed net "
            "average of second and third blood pressure measurement) at Exam 1, "
            "filtered to the method Seated random-zero average. The DCC "
            "recomputes the value from the individual readings (SBPA15 to "
            "SBPA20, pht004192, phv00210284 to phv00210289): it subtracts the "
            "zero readings, sets both members of a systolic/diastolic pair to "
            "missing when systolic is below diastolic, and averages the second "
            "and third readings that remain. In v8, SBPA21 has 15,050 values "
            "and 2 blanks. The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063). The cause of the N difference is not "
            "established."
        ),
    },
    ("ARIC", "cabg_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read PHEA07A (phv00208846, pht004143, coronary bypass, "
            "a sub-item of the heart or artery surgery question PHEA06; Exam "
            "1). In v8, PHEA07A has 402 values (Y 236, N 165, T 1) and 14,658 "
            "blanks. BDC maps T to UNKNOWN; the comparison counts a blank "
            "condition status as answered, so nearly all BDC participants count "
            "as answered and the BDC missing count is small. The DCC also reads "
            "PHEA06 and PHEA08 (phv00208845, phv00208853), sets T and a missing "
            "PHEA07A to 0 for records with fewer than three missing values "
            "among age, PHEA06, PHEA07A and PHEA08, and drops the rest. In v8, "
            "PHEA06 has 123 blanks and PHEA08 has 125; a record blank in both "
            "has three blank columns together with PHEA07A and is dropped, and "
            "records with no V1AGE01 (phv00204712, pht004063) are also dropped. "
            "The DCC missing count is consistent with these two rules (inferred "
            "from totals, not matched by participant)."
        ),
    },
    ("ARIC", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads CIGT01 (phv00204713, pht004063 DERIVE13; 1 current, 2 "
            "former, 3 never, 4 unknown) and the Home Interview items HOM28 and "
            "HOM30 (phv00207368, phv00207370, pht004111) at Exam 1. The DCC "
            "reads pht004111 only (HOM28, HOM30 and HOM32, phv00207368, "
            "phv00207370, phv00207372): current smoker if HOM30 is Y or "
            "cigarettes per day (HOM32) is positive. The DCC function omits "
            "records with no V1AGE01 (phv00204712, pht004063). The cause of the "
            "N difference is not established."
        ),
    },
    ("ARIC", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the same Exam 1 sources as current smoker: CIGT01 "
            "(phv00204713, pht004063) and HOM28 and HOM30 (pht004111). The DCC "
            "reads pht004111 only (HOM28, HOM29, HOM30, HOM35 and HOM36; "
            "phv00207368, phv00207369, phv00207370, phv00207375, phv00207376). "
            "The DCC function omits records with no V1AGE01 (phv00204712, "
            "pht004063). The cause of the N difference is not established."
        ),
    },
    ("ARIC", "height_baseline_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read ANTA01 (phv00203151, pht004032, standing height in "
            "cm, Exam 1). In v8, ANTA01 has 15,045 values and 2 blanks. The DCC "
            "sets the code A, which the dictionary does not list, to missing "
            "and omits records with no V1AGE01 (phv00204712, pht004063); BDC "
            "has no age requirement. The cause of the N difference is not "
            "established."
        ),
    },
    ("ARIC", "mi_prior_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "mi_prior_1 is graded at ARIC Exam 1 only. BDC (hist_my_inf.yaml) "
            "unions eight Exam 1 variables: DERIVE13 (pht004063) MDDXMI02 "
            "(phv00204748), HXOFMI02 (phv00204749), ECGMI04 (phv00204704, "
            "adjudicated ECG), PREVMI05 (phv00204705, ECG or medical history) "
            "and MACHMI02 (phv00204709, machine-coded ECG); HOM10C (pht004111, "
            "phv00207313); MHXA28 (pht004126, phv00207776); and v1ecg21 "
            "(pht004231, phv00215643, Minnesota-coded ECG). The DCC reads "
            "PREVMI05 only, with T set to missing. In v8 the Yes counts are "
            "PREVMI05 640, HOM10C 741, v1ecg21 581, HXOFMI02 604, MHXA28 331, "
            "MDDXMI02 282, MACHMI02 166 and ECGMI04 108, so the union exceeds "
            "any one source; the contribution of each source to the difference "
            "is not tabulated. The comparison counts a blank condition status "
            "as answered (305 blanks in MHXA28, 6 in HOM10C, 1 in MDDXMI02). "
            "Whether the unadjudicated ECG-derived items belong in prior MI is "
            "open (HV #947). The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063). This item is under review with the "
            "study's guidance."
        ),
    },
    ("ARIC", "platelet_ncnc_bld_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read HMTA04 (phv00207258, pht004107, Exam 1), HMTB04 "
            "(pht004108, Exam 2), HMTC10 (pht004109 Exam 3, pht004110 Exam 4) "
            "and CBC7 (pht006422, Exam 5), and both take the visit with the "
            "most non-missing values first, then the next in succession; the "
            "comparison applies that rule to the BDC rows. In v8, HMTA04 has "
            "14,808 values and 88 blanks. The DCC code removes codes A and O "
            "and records without age at the visit. The cause of the N "
            "difference is not established."
        ),
    },
    ("ARIC", "race_us_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC reads RACEGRP (pht004063, phv00204710; pht004062, "
            "phv00204633; pht004065, phv00204962); its code maps A to Asian and "
            "I to AI_AN and assigns Multiple when visits disagree. In v8, "
            "DERIVE13 RACEGRP holds only W (10,748) and B (3,729). BDC "
            "(demography.yaml) additionally reads race fields the DCC does not, "
            "including RACEGRP in pht012853 (phv00519792; v8: W 11,040, B "
            "3,979, A 31, I 14) and the ECG race fields (pht012821 to "
            "pht012824). Other is OMOP:8552 (ECG codes UNKNOWN and *********); "
            "the comparison labels it Other, counts it as answered, and keeps "
            "the first non-blank race value in file order without first "
            "blanking unknown race. In v8, DERIVE37 (pht004064, Visit 3) "
            "RACEGRP, which BDC reads and the DCC does not, holds A 25 and I "
            "10, and DERIVE13 holds only W and B. Why no DCC participant falls "
            "in an Asian, American Indian or Multiple category is not "
            "documented in the material reviewed."
        ),
    },
    ("ARIC", "total_cholesterol_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads three sources: TCHSIU01 (phv00204735, "
            "pht004063; SI value x 38.67), LIPA01 (phv00207635, pht004121) and "
            "TOTCHOL_V1 (phv00519812, pht012853). The DCC reads TCHSIU01 only, "
            "dividing by 0.02586 (the same factor). In v8, TCHSIU01 has 14,256 "
            "values and 221 blanks, LIPA01 14,835 and 3, and TOTCHOL_V1 14,835 "
            "and 229, so the additional BDC sources add values that DERIVE13 "
            "lacks. The DCC valid count shown above exceeds the v8 TCHSIU01 "
            "count, so its release held more values. The sources give differing "
            "values for nearly all participants (rounding of the converted SI "
            "value); the comparison keeps the first row in file order where "
            "values tie. The DCC function omits records with no V1AGE01 "
            "(phv00204712, pht004063)."
        ),
    },
    ("ARIC", "triglycerides_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads TRGSIU01 (phv00204738, pht004063; SI value x "
            "88.57) and LIPA02 (phv00207636, pht004121). The DCC reads TRGSIU01 "
            "only, dividing by 0.01129 (the same factor). In v8, TRGSIU01 has "
            "14,258 values and 219 blanks and LIPA02 has 14,838 and none, so "
            "LIPA02 adds values that DERIVE13 lacks. The DCC valid count shown "
            "above exceeds the v8 TRGSIU01 count, so its release held more "
            "values. The sources give differing values for nearly all "
            "participants (rounding of the converted SI value); the comparison "
            "keeps the first row in file order where values tie. The DCC "
            "function omits records with no V1AGE01 (phv00204712, pht004063)."
        ),
    },
    ("ARIC", "weight_baseline_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read ANTA04 (phv00203154, pht004032, weight to the "
            "nearest lb, Exam 1) and convert to kg (x 0.453592). In v8, ANTA04 "
            "has 15,039 values and 9 blanks. The DCC sets the code A, which the "
            "dictionary does not list, to missing; BDC sets A, O, M, R, N, U, "
            "T, L, H and empty strings to missing before converting. The DCC "
            "omits records with no V1AGE01 (phv00204712, pht004063); BDC has no "
            "age requirement. The cause of the N difference is not established."
        ),
    },
    # ── CARDIA ────────────────────────────────────────────────────────────────
    ("CARDIA", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-stored BMI A20BMI (phv00113661, "
            "pht001583/A4F20, 'BODY MASS INDEX, KG/M**2') at CARDIA YEAR 0. The "
            "DCC computes weight/height^2 from its harmonized height (A20HGT, "
            "phv00113634, cm) and weight (A20WGT, phv00113635, lbs x 0.45359). "
            "The BDC value is higher by a near-constant proportion across the "
            "distribution, equal to the ratio 2.20462/2.2 (1.0021), which is "
            "consistent with the stored value having used 2.2 lb/kg. The dbGaP "
            "dictionary does not document the study formula, so the cause is "
            "not established."
        ),
    },
    ("CARDIA", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads A10SMOKE (phv00113224, pht001573/A4F10, 'CIGARETTE "
            "SMOKING STATUS', Year 0). The codes are unlabeled in dbGaP; the "
            "spec maps 0 = Never, 1 = Former, 2 = Current, and the counts of "
            "codes 1 and 2 in phs000285.v3 (489, 992) equal the counts of "
            "A09SMKNW answers 1 and 2. The DCC reads A09SMKNW (phv00113168, "
            "pht001572, 'STILL SMOKES CIGARETTES REGULARLY?'; 489 No, 992 Yes, "
            "6 M) and codes A10CIGS (phv00113213) = No with a blank A09SMKNW as "
            "not current; M codes become missing and age (A01AGE2) is required. "
            "Current-smoker counts agree. Not Current differs because A10SMOKE "
            "code 0 (2,122) exceeds A10CIGS No (2,079) by 43, and the DCC "
            "missing count is consistent with the 44 M codes of A10CIGS plus "
            "the 18 participants with A10CIGS = Yes and no A09SMKNW answer "
            "(inferred from totals, not matched by participant)."
        ),
    },
    ("CARDIA", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads A10SMOKE (phv00113224, pht001573/A4F10; codes unlabeled "
            "in dbGaP). The spec maps 0, 1 and 2 to Never, Former and Current, "
            "and the comparison counts Former or Current as Ever Smoked. The "
            "DCC reads A10CIGS (phv00113213, 'SUBJECT HAS SMOKED CIGARETTES. Q "
            "2'; phs000285.v3: 1 = No 2,079, 2 = Yes 1,499, M 44). A10SMOKE "
            "codes 1 and 2 (489, 992) equal the counts of answered A09SMKNW "
            "(phv00113168), so BDC Ever Smoked equals the number of A09SMKNW "
            "answers, 18 fewer than A10CIGS Yes; BDC therefore reports fewer "
            "Ever Smoked than the DCC. A10SMOKE codes 0 for 43 more "
            "participants than A10CIGS = No, and has 25 fewer missing than the "
            "44 A10CIGS M codes; both are consistent with the 18 participants "
            "being coded 0 and 25 of the 44 M codes being coded 0 (inferred "
            "from totals, not matched by participant). Neither side uses "
            "A01SM100."
        ),
    },
    ("CARDIA", "il6_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "Both sides read FL6IL6 (phv00121064, pht001862, Year 15). The DCC "
            "sets il6 = 12 where FL6IL6CM is 'High > 12' (6 rows in "
            "phs000285.v3); il6.yaml does not impute those rows, which are "
            "blank in FL6IL6. Adding six values of 12 to the BDC values "
            "reproduces the DCC N and mean, so the imputed values account for "
            "the whole difference in N, mean and upper quantiles."
        ),
    },
    ("CARDIA", "platelet_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "A05PLATL (phv00112690, pht001563, Year 0) has dictionary range "
            "0..7.54 and no unit in dbGaP; platelet_ct.yaml and the DCC both "
            "multiply by 100 to give 10*3/uL. One participant has a recorded 0 "
            "(dbGaP minimum 0). BDC passes it through. The DCC code removes 'M' "
            "codes and incomplete records (na.omit) and applies no range "
            "filter, so it also keeps the 0. The extractor flags the 0 as "
            "implausible."
        ),
    },
    ("CARDIA", "crp_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read FL6CRPBN (phv00120759, pht001853, 'RERUN CRP "
            "(uG/ml - BNII METHOD)', Year 15). crp.yaml also emits FL6CRP "
            "(phv00120758, 'C-REACTIVE PROTEIN IN uG PER ML') under "
            "OMOP:4208414 with method_type 'Original assay (FL6CRP)'; FL6CRPBN "
            "carries 'BNII method rerun (FL6CRPBN)'. Where values tie at the "
            "graded visit the comparison keeps the first row in file order, so "
            "it selects the BNII label (config.py preferred_method_override) to "
            "match the variable the DCC reads. Original-assay values are not "
            "part of the comparison."
        ),
    },
    ("CARDIA", "sleep_duration_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "F67SLPHR (phv00120534, pht001839, Year 15, 'PAST MONTH AVG "
            "SLEEPING HOURS. Q 7') has dictionary range 1..280. BDC passes the "
            "recorded values through, including values of 24 hours or more that "
            "the extractor flags as implausible. The DCC keeps only values "
            "below 24 hours. The N difference shown above equals the number of "
            "such values (inferred from totals), and those values account for "
            "the SD difference and for the higher BDC mean; median, quartiles "
            "and P99 agree."
        ),
    },
    # ── MESA ──────────────────────────────────────────────────────────────────
    ("MESA", "hispanic_or_latino_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "For MESA Family (pht001121) both sides read scrhispf (phv00087659; "
            "0 = not Hispanic, 1 = Hispanic) and racefc (phv00087074). The DCC "
            "codes notHL for scrhispf = 0 with racefc not 4, HL for scrhispf = "
            "1 (or racefc = 4 with scrhispf missing), and both for scrhispf = 0 "
            "with racefc = 4. BDC demography.yaml tests racefc = 4 first, so "
            "that last combination is Hispanic. For MESA Classic and AirNR the "
            "DCC codes HL from race1c = 4 and leaves other participants "
            "missing; the BDC Exam 1 blocks emit Hispanic only from race1c = 4 "
            "and leave non-Hispanic missing, because a race code alone does not "
            "identify Not Hispanic. The two sides agree in the table above."
        ),
    },
    ("MESA", "platelet_ncnc_bld_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC platelet_ct.yaml maps two sources: pht001984 (MESA "
            "Inflammation, phv00128760; in phs000209.v13, 894 values) and "
            "pht004319 (MESA Epigenomic CBC, Exam 5, phv00218991, 2,750 "
            "values). The DCC reads pht004319 plt5 with the Exam 5 age. The "
            "comparison grades BDC at the Epigenomic exam through a visit "
            "override, so both sides read the same variable and agree."
        ),
    },
    ("MESA", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC hypert_trt.yaml emits two ATC:C02 records per exam, htnmed1c "
            "(computed) and bpmed1 ('taking meds for hypertension'): Classic "
            "Exam 1 phv00085324 and phv00085236, AirNR phv00083163 and "
            "phv00082998. Family has htnmedfc (phv00087093) only. The "
            "comparison counts a participant as Yes when either record is "
            "PRESENT. The DCC reads htnmed1c (htnmedfc for Family) only, so BDC "
            "Yes is higher where a participant has bpmed1 = 1 and htnmed1c = 0 "
            "(inferred from totals, not matched by participant)."
        ),
    },
    # ── FHS ───────────────────────────────────────────────────────────────────
    ("FHS", "total_cholesterol_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "The comparison compares both sides at Offspring Exam 1, Generation "
            "3 Exam 1, New Offspring Spouse (NOS) Exam 1 and Omni 2 Exam 1; it "
            "does not compare Original or Omni 1. BDC tot_chol_bld.yaml reads "
            "TC1 in pht009761 (phv00423929) for Offspring, G3A712 in pht000074 "
            "(phv00021391) for Generation 3, and TC1 in pht006026 (phv00277047) "
            "for Generation 3, NOS and Omni 2. The DCC documents that it "
            "excludes the Original cohort because its analysts could not "
            "confirm that the Original-cohort data in dbGaP should be used, and "
            "reads TC1 in pht006026 (phv00277047) for Generation 3, NOS and "
            "Omni 2 and TC1 in pht006027 (phv00277194) for Offspring; it has no "
            "Omni 1 unit. The N difference shown above is of the order of the "
            "cohort-level participant difference; no per-variable cause has "
            "been established."
        ),
    },
    ("FHS", "triglycerides_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "The comparison compares both sides at the same exams as total "
            "cholesterol (Offspring Exam 1, Generation 3 Exam 1, NOS Exam 1, "
            "Omni 2 Exam 1). BDC triglyc_bld.yaml reads TRIG1 in pht009761 "
            "(phv00423933) for Offspring, G3A714 in pht000074 (phv00021393) for "
            "Generation 3, TRIG in pht005143 (phv00255342) for NOS and Omni 2, "
            "and TRIG1 in pht006026 (phv00277049) for Generation 3, NOS and "
            "Omni 2. The DCC documents that it excludes the Original cohort "
            "because its analysts could not confirm that the Original-cohort "
            "data in dbGaP should be used, and reads TRIG1 in pht006026 "
            "(phv00277049) for Generation 3, NOS and Omni 2 and TRIG1 in "
            "pht006027 for Offspring; it has no Omni 1 unit. The N difference "
            "shown above is of the order of the cohort-level participant "
            "difference; no per-variable cause has been established."
        ),
    },
    ("FHS", "cabg_prior_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "The DCC counts a CABG when pht000389 VESSEL > 0 and PROCDATE <= 0 "
            "(on or before Exam 1); participants whose pht000389 rows show no "
            "CABG, or who have cvd == 0 in pht003316 (phv00190817), are "
            "negatives, and participants with neither have no DCC value. BDC "
            "hist_cor_bypg.yaml maps cumulative exam questions (Original Exam "
            "21, Offspring Exam 5, Generation 3 Exam 1). The comparison "
            "compares FHS at its baseline exams, so only Generation 3 Exam 1 "
            "(pht000074 G3A255, phv00021084) contributes; Original and "
            "Offspring participants have no BDC value. The comparison counts a "
            "blank procedure status as answered (G3A255 has 2 null values in "
            "v35). The higher BDC missingness shown above is the Original, "
            "Offspring, NOS and Omni participants without a Generation 3 value."
        ),
    },
    ("FHS", "angina_prior_1"): {
        "code": "COVERAGE_DIFF",
        "no_override": True,
        "note": (
            "The DCC codes angina from pht000309 EVENT == 6 with DATE <= 0; "
            "participants with any other pht000309 row, or with cvd == 0 in "
            "pht003316 (phv00190817), are negatives, and participants with "
            "neither have no DCC value. BDC angina.yaml reads only pht000309: "
            "EVENT == 6 with DATE <= 0 is PRESENT and every other pht000309 "
            "event row has a blank status. The comparison counts a blank "
            "condition status as answered, so participants with any other "
            "pht000309 row are No Prior History; participants with no pht000309 "
            "row have no BDC value, and BDC has no pht003316 source. The "
            "difference in missingness shown above is this denominator "
            "difference; Prior History comes from the same pht000309 event."
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
            "answers across visits are coded both. BDC ethnicity comes from "
            "pht000074 (phv00021245), pht000747 (H700/H701, Exam 8), pht003094 "
            "(phv00177597), pht004815 (h700/h701, Exam 3), pht009760 "
            "(phv00423856, phv00423857, phv00423859) and pht016162 "
            "(vr_racesum_2011) eth_sum (phv00568195). It does not read g3a484 "
            "in pht006005 or pht006006. In pht016162 v35, eth_sum is 0 (Not "
            "Hispanic) for 7,247 participants, 1 (Hispanic) for 401, and 88 "
            "(Defaulted ethnicity, Not Hispanic or Latino) for 7,417. BDC maps "
            "88 to OMOP:8552 and the comparison counts it as missing. The BDC "
            "pht016162 and pht009760 sources are not read by the DCC."
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
            "pht000074, pht006005, pht006006 and pht003094. BDC reads pht016162 "
            "(vr_racesum_2011) race_sum (phv00568194), pht009760 "
            "(vr_raceall_2011), pht000074, pht003094, pht000747 and pht004815. "
            "In pht016162 v35, code 88 (Defaulted race, White) covers 7,121 "
            "participants and BDC maps it to White. In v35, the Offspring Exam "
            "8 table (pht000747) has 2,976 rows against 4,979 Offspring "
            "participants in pht003099 (idtype 1), so at least 2,003 Offspring "
            "participants have no row in the DCC only Offspring race source; "
            "this is consistent with the higher DCC missingness shown above "
            "(inferred from totals, not matched by participant)."
        ),
    },
    ("FHS", "height_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC bdy_hgt.yaml converts heights recorded in inches to the next "
            "lower 1/4 inch into cm (x 2.54): pht007777 HGT1 (phv00369944) for "
            "Original; pht009761 HGT1 (phv00423918) for Offspring and Omni 1; "
            "pht006026 HGT1 (phv00277042) for Generation 3, NOS and Omni 2. At "
            "Generation 3 Exam 1 it also emits pht000074 G3A446 (phv00021231), "
            "and at NOS Exam 1 pht006005 g3a446 (phv00274053), so those two "
            "visits carry two blocks; where the comparison finds tied values at "
            "the compared visit it keeps the first row in file order. This "
            "duplication is tracked in HV #951; Original Exams 10-32 also carry "
            "both a per-exam block and a workthru block. The DCC reads 2.54 x "
            "(MF67 + 0.01 x MF68) (pht000009 phv00000539, phv00000540) for "
            "Original, 2.54 x HGT1 (pht006026, pht006027) for Generation 3, "
            "NOS, Omni 2 and Offspring, and 2.54 x e025 (pht004813) for Omni 1. "
            "Original height therefore differs in source variable and "
            "resolution between the two sides."
        ),
    },
    ("FHS", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original (Exam 4): both sides read MF250 (phv00000705, pht000009). "
            "The DCC recodes 2 (YES, DOUBTFUL; 13 values in v35) to 0; BDC "
            "hypert_trt.yaml maps 0 to ABSENT, 1 to PRESENT and 2 to UNKNOWN. "
            "Offspring Exam 1: the DCC reads HRX1 in pht006027 (phv00277245); "
            "BDC reads HRX1 in pht009761 (phv00423953; 0/1). Generation 3, NOS "
            "and Omni 2: the DCC reads HRX1 in pht006026 (phv00277059), while "
            "BDC reads g3a012 (phv00020877 in pht000074, phv00273711 in "
            "pht006005, phv00565874 in pht006006; ever taken medication for "
            "hypertension), mapping 1 to PRESENT and 2 (yes, not now) to "
            "HISTORICAL. Omni 1: both sides read e221 in pht004813 (phv00250358 "
            "in the DCC unit, phv00565505 in BDC)."
        ),
    },
    ("FHS", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original: both sides read MF71 (phv00000543, pht000009) at Exam 1 "
            "(MF70 shows the source form may come from Exams 1-4). The DCC "
            "codes MF71 = 1 or 3 as current and 2, 5 or 7 as not current; BDC "
            "cig_smok.yaml maps 7 (62 values in v35) to OMOP:45885135 and the "
            "comparison counts it as missing (the non-null counts in v35, 5,046 "
            "MF71 and 9,993 STATUS1, less these 62 give the BDC valid count "
            "shown above). Other sub-cohorts: the DCC reads Offspring A99 "
            "(pht000030, phv00007612), Omni 1 e319 (pht004813), and for "
            "Generation 3, NOS and Omni 2 it codes current when g3a071 (smoked "
            "in the past year) or g3a072 (smoke now) is 1 (pht000074, "
            "pht006005, pht006006). BDC reads pht012916 STATUS1 (phv00525298; 0 "
            "Never, 1 Former, 2 Current) for these sub-cohorts. The remaining "
            "per-cohort differences are not established."
        ),
    },
    ("FHS", "ever_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "Original: both sides read MF71 (phv00000543, pht000009) at Exam 1. "
            "The DCC codes 1, 2 or 3 as ever and 5 or 7 as never; BDC maps 7 "
            "(62 values in v35) to OMOP:45885135 and the comparison counts it "
            "as missing. Other sub-cohorts: the DCC reads Offspring A99 "
            "(pht000030) and g3a070 for Generation 3, NOS and Omni 2; BDC reads "
            "pht012916 STATUS1 (phv00525298). For Omni 1 the DCC documents that "
            "Exam 1 current smokers (e319 = 1) are coded ever, Exam 2 "
            "never-smokers (g675 = 0) are coded never, and all other subjects "
            "are set to missing; in v35 that leaves about 190 of the 490 Omni 1 "
            "participants without a DCC value (62 with e319 = 1; 237 with g675 "
            "= 0), the size of the higher DCC missingness here relative to its "
            "current-smoker variable (inferred from totals, not matched by "
            "participant)."
        ),
    },
    ("FHS", "pad_prior_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC codes PAD from pht000309 EVENT == 30 (IC, first episode "
            "only) with DATE <= 0 and documents that FHS PAD is based on "
            "intermittent claudication; participants with any other pht000309 "
            "row, or with cvd == 0 in pht003316, are negatives. BDC pad.yaml "
            "reads the clinical diagnostic impression other peripheral vascular "
            "disease and emits MONDO:0005294; the two sides measure related but "
            "not identical concepts. At the compared exams BDC has Generation 3 "
            "G3A392 (phv00021192), Omni 1 e630 (phv00565843), NOS g3a392 "
            "(phv00274014) and Omni 2 g3a392 (phv00566177). Its Offspring block "
            "(Exam 5 E630, phv00009530) is not at a compared exam and it has no "
            "Original block, so the Original (5,079) and Offspring (4,979) "
            "participants in pht003099 v35 have no BDC value. Code 2 (maybe; 17 "
            "values across G3A392 and the NOS and Omni 2 g3a392) maps to "
            "UNKNOWN, and the comparison counts a blank condition status as "
            "answered (11 null values across the four sources)."
        ),
    },
    ("FHS", "hematocrit_vfr_bld_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "For Offspring the DCC takes the most recent exam available (Exam 9 "
            "pht004802, then Exam 2 pht000031, then Exam 1 pht000030) and reads "
            "Exam 2 B764 (phv00008111) as recorded. B764 has a dictionary unit "
            "of percentage and a dbGaP v35 mean of 4.409 (3,584 values); "
            "hemat.yaml multiplies it by 10 before emitting %. The dictionary "
            "does not state the scaling factor. The DCC divides the other Exam "
            "2 items B763 (hemoglobin) and B767 (MCHC) by 10 but not B764; the "
            "scale of B764 in the DCC release (v29) is not available in the "
            "cached metadata."
        ),
    },
    ("FHS", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC emits the study-reported count BA_NUM (phv00172197 in "
            "pht002889; phv00227044 in pht004802); BDC keeps the value the "
            "study reports. The DCC derives WBC x BA_PER / 100 from the same "
            "two tables (pht002889 for Generation 3, NOS and Omni 2; pht004802 "
            "for Offspring and Omni 1) and documents the choice as avoiding "
            "round-off effects. In phs000007.v35 the variable reports list "
            "BA_NUM only in 0.1 x10^3/uL steps, with 1,771 of 2,794 (pht002889) "
            "and 1,917 of 2,493 (pht004802) values equal to 0, which is "
            "consistent with the lower BDC median and mean shown above."
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
            "(CAC_S, scan_date; IDTYPE 7 and 72). In pht005161 v35, IDTYPE 7 "
            "has 124 participants and IDTYPE 72 has 146, 270 in total. The BDC "
            "pht005161 block, like its pht000147 block, carries no visit and is "
            "not selected at the compared visits. The Omni table can account "
            "for at most 270 of the N difference shown above; the remainder is "
            "not established."
        ),
    },
    # ── CHS ───────────────────────────────────────────────────────────────────
    ("CHS", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-calculated BMI at CHS BASELINE BOTH (BASEBOTH "
            "phv00100386, pht001452, 'BODY MASS INDEX (kg/m2)'; 5,513 values "
            "and 18 blanks in phs000287.v7); bmi.yaml has no BASE1 or YR5NEW "
            "BMI block. The DCC documents BMI as weight/height^2 from its "
            "harmonized baseline height and weight. The residual difference "
            "between the stored and the computed value is small, and its source "
            "is not established."
        ),
    },
    ("CHS", "bp_systolic_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "BDC reads AVZMSYS (phv00100435, pht001452, 'AVE ZERO MUD SYSTOL "
            "(mm Hg)') and also BASE1 phv00099441. The DCC reads BASEBOTH and "
            "sets an SBP/DBP pair to missing unless both are present and SBP is "
            "at least DBP; its code has no value-range filter. In phs000287.v7, "
            "BASEBOTH has 5,522 SBP and 5,516 DBP values and AGEBL "
            "(phv00100487) has no blanks, so at least 6 of the participants in "
            "the N difference shown above have SBP without DBP, and the "
            "remainder is consistent with SBP below DBP (inferred from totals, "
            "not matched by participant). Overlapping BASE1 and BASEBOTH "
            "sources are tracked in HV #956."
        ),
    },
    ("CHS", "bp_diastolic_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC maps AVZMDIA from BASE1 (phv00099442, 'AVE ZERO MEDDLER "
            "DIASTOLIC BP', dictionary range 0-116) and BASEBOTH (phv00100436, "
            "'AVE ZERO MUD DIASTOL-adj', range 40-116). Where values tie at the "
            "graded visit the comparison keeps the first row in file order; the "
            "extractor log reports 31 participants with conflicting values. The "
            "BDC values below the 30 mmHg plausibility bound of the extractor "
            "cannot come from BASEBOTH (dictionary minimum 40) and so come from "
            "BASE1; this is consistent with the higher BDC SD (inferred from "
            "totals, not matched by participant). The DCC reads BASEBOTH only, "
            "with the SBP at least DBP pair rule. The remaining mean difference "
            "is not decomposed. The two overlapping sources are tracked in HV "
            "#956."
        ),
    },
    ("CHS", "cabg_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC maps CABG (OMOP:4336464) from BASE1 (phv00099031), BASEBOTH "
            "BPSSUR (phv00100321), EVENT_SUMMARY BPSSURBL (phv00100785) and "
            "YR5NEW (phv00105974); the DCC reads BPSSURBL only, with AGEBL. In "
            "phs000287.v7, BPSSUR and BPSSURBL each have 5,493 values (236 Yes, "
            "5,257 No) and 38 blanks. The Prior History counts agree. The spec "
            "maps only codes 0 and 1, so the 38 blanks reach the output with no "
            "status, and the comparison counts a blank condition or procedure "
            "status as answered, which gives BDC no missing values."
        ),
    },
    ("CHS", "current_smoker_baseline_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the study-derived SMOKE (1 Never, 2 Former, 3 Current): "
            "BASE1 phv00099445 (pht001450) at 'CHS BASELINE 2' and YR5NEW "
            "phv00105886 (pht001490) at 'CHS YEAR 5 NEW'. The DCC derives the "
            "variable from the raw items SMOKE101 ('SMOKED IN LIFETIME') and "
            "SMOKE201 ('SMOKED CIGARETTES LAST 30 DAYS') of pht001450 and "
            "pht001490: SMOKE101 = 0 with SMOKE201 blank is coded 0, otherwise "
            "SMOKE201; rows with neither item, or without age, are dropped. In "
            "phs000287.v7 the current-smoker difference follows from the "
            "sources: SMOKE code 3 counts 570 (BASE1) + 94 (YR5NEW), SMOKE201 = "
            "YES counts 565 + 91. BASE1 SMOKE101 has 4,884 values against 4,900 "
            "for SMOKE, and SMOKE201 has 2,631 against 2,635 SMOKE101 = YES, so "
            "the derived variable is populated for some participants whose raw "
            "items are blank; that is consistent with the higher DCC "
            "missingness (inferred from totals, not matched by participant)."
        ),
    },
    ("CHS", "weight_baseline_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "BDC reads measured WEIGHT13 (phv00100383, pht001452 BASEBOTH, "
            "'WEIGHT - LBS') at CHS BASELINE BOTH, the variable the DCC reads "
            "(x 0.453592); BDC applies 0.45359237, which accounts for the very "
            "small mean difference. bdy_wgt.yaml maps no age-50 recall "
            "variables. Measured weights at other visits are not mapped (HV "
            "#950)."
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
            "AMOUNT above 0 (phv00099159) across pht001450 and pht001490. BDC "
            "reports fewer Ever Smoked than the DCC. In phs000287.v7 the "
            "pht001450 dictionary gives AMOUNT08 a code 99 = UNKNOWN, and the "
            "DCC code tests the row sum without recoding it, so a 99 counts as "
            "ever; the number of participants affected is not given in the "
            "variable report. The cause of the difference is not established; "
            "participants were not matched."
        ),
    },
    ("CHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no CHS carotid_plaque.yaml, so the variable is not "
            "comparable (BDC has no value at the graded visit). Sources exist "
            "in ULTRAYR5 (pht001473): LMRPH155/LMRPH255 "
            "(phv00101317/phv00101318, original-cohort baseline reread) and "
            "LMRPH141/LMRPH241 (phv00101306/phv00101307, African American "
            "cohort Year 5). Their 0/1/2 codes are unlabeled in dbGaP. The DCC "
            "codes plaque as present when either side code is above 0, by "
            "sub-cohort. A spec waits on the CHS reading protocol and a curated "
            "concept code (HV #946, awaiting external)."
        ),
    },
    # ── JHS ───────────────────────────────────────────────────────────────────
    # JHS universe difference: see COHORT_LEVEL_NOTES['JHS'].
    # ──────────────────────────────────────────────────────────────────────────
    ("JHS", "pad_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "pad.yaml reads one PAD source: the annual follow-up item PADEVER "
            "(pht008725 phv00400971, visit 'JHS AFU'), mapped to MONDO:0005294 "
            "(HV #801). The DCC derives prevalent PAD at Exam 1 from the "
            "ankle-brachial index: the maximum of four ankle pressures "
            "(ABBA8-ABBA11) over the maximum of two arm pressures (ABBA7, "
            "ABBA12) in pht001921, with ABI below 0.9 coded as prior PAD. The "
            "comparison grades JHS at Exam 1 without falling back to other "
            "visits, so BDC has no value at the graded visit and the variable "
            "is not comparable; PAD values recorded at other visits are not "
            "used. BDC does not derive a PAD condition from an ABI cutoff; the "
            "index itself is available in analysis1 (pht008729 phv00401122)."
        ),
    },
    ("JHS", "cabg_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "hist_cor_bypg.yaml maps CABG at Exam 2 (pht001948 CSTA93; "
            "pht008764 MHXB52A), Exam 3 (pht008765) and the annual follow-up "
            "(pht008725 phv00400930), and has no Exam 1 block, so the variable "
            "is not comparable at the graded visit. An Exam 1 source exists: "
            "MHXA52A (pht001963 phv00127728, 'Did you have a coronary "
            "bypass?'), which in phs000286.v7 holds 53 Yes and 95 No, asked "
            "after the gate MHXA51 (surgery on heart or arteries ever). The DCC "
            "reads MHXA52A with MHXA51, MHXA52E1, MHXA55A and MHXA52C, keeps a "
            "participant when fewer than 5 columns of the joined table are NA, "
            "and sets a missing CABG answer to 0. Whether a 'No' on the gate "
            "implies a CABG 'No' is under curation review (HV #948). This item "
            "is under review with the study's guidance."
        ),
    },
    ("JHS", "carotid_plaque_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "BDC has no JHS carotid plaque spec, so the variable is not "
            "comparable. In phs000286.v7 the source is plq01 (pht008791 "
            "phv00404237; 0 = 2,288, 1 = 1,414). That table has no VISIT "
            "variable and visit.yaml labels it 'JHS LAB DATA'. The DCC reads "
            "plq01 from pht001978 (phv00128573) and pairs it with the Exam 1 "
            "age (AGE01, pht001949). A spec needs a documented Exam 1 link and "
            "a concept code (HV #224)."
        ),
    },
    ("JHS", "cimt_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "carotid_imt.yaml emits each of six common-carotid far-wall segment "
            "averages from pht008791 (phv00404195-phv00404200, method 'carotid "
            "ultrasound', visit 'JHS LAB DATA') as its own row. The DCC "
            "averages the three left (lcl, lca, lcp) and three right (rcl, rca, "
            "rcp) far-wall averages from pht001978 and then the left and right "
            "means, paired with the Exam 1 age. One segment row is not the same "
            "quantity as that mean, and the comparison does not align the visit "
            "for this variable. The study summary cca45_1 (pht008791 "
            "phv00404240) is a separate variable that BDC does not map to this "
            "concept."
        ),
    },
    ("JHS", "antihypertensive_meds_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the ATC:C02 item MSRA30A (pht001964 phv00127922, 'Past 2 "
            "wks took high blood pressure medications?', visit JHS Exam 1). In "
            "phs000286.v7 it has 1,939 Y, 1,719 N, 1 D and 210 nulls among the "
            "3,869 participants of pht001964. hypert_trt.yaml emits a "
            "blank-status row for each blank answer, and the comparison counts "
            "a blank medication status as missing. BDC missing values are "
            "therefore the 210 blanks, the one D (mapped to UNKNOWN) and the 14 "
            "participants with no pht001964 row. The DCC reads BPM01 (pht001949 "
            "phv00126038) and sets 'X' to missing; what BPM01 records is not "
            "documented in the DCC harmonization code beyond 'use of "
            "antihypertensive medication at the time of blood pressure "
            "measurement'. The difference in Yes share and in missingness is "
            "between two different source variables; the cause is not "
            "established."
        ),
    },
    ("JHS", "total_cholesterol_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "tot_chol_bld.yaml has 8 blocks across 8 tables (Exams 1-3 and LAB "
            "DATA). At Exam 1 it reads CHR (pht001945 phv00125927), the "
            "variable the DCC reads, and the fasting value totchol in analysis1 "
            "(pht008729 phv00401137); where values tie at the graded visit the "
            "comparison keeps the first row in file order. The BDC distribution "
            "shown above matches the CHR summary in the v7 var_report, so the "
            "graded values are CHR. The DCC joins CHR to AGE01 (pht001949) and "
            "removes NA. The N and missingness differences follow the "
            "participant-universe difference described in the cohort note "
            "(inferred from totals, not matched by participant)."
        ),
    },
    ("JHS", "triglycerides_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "triglyc_bld.yaml has 9 blocks across 9 tables (Exams 1-3 and LAB "
            "DATA). At Exam 1 it reads TRR (pht001945 phv00125933), the "
            "variable the DCC reads, and the fasting value trigs in analysis1 "
            "(pht008729 phv00401136); where values tie at the graded visit the "
            "comparison keeps the first row in file order. The BDC distribution "
            "shown above matches the TRR summary in the v7 var_report, so the "
            "graded values are TRR. The DCC joins TRR to AGE01 (pht001949) and "
            "removes NA. The N and missingness differences follow the "
            "participant-universe difference described in the cohort note "
            "(inferred from totals, not matched by participant)."
        ),
    },
    ("JHS", "cac_score_1"): {
        "code": "UNATTRIBUTED",
        "no_override": True,
        "note": (
            "Both sides read CSTA24 (phv00126002, Agatston score all coronary). "
            "BDC reads pht001948.v3 of phs000286.v7, where every row carries "
            "VISIT = 6 (phv00401812); cac_score.yaml assigns that protocol "
            "visit to JHS Exam 2 and the comparison grades CAC there. The DCC "
            "reads pht001948.v1 of phs000286.v5, inner-joins it to AGE01 "
            "(pht001949) and removes NA. The participant-universe difference "
            "can account for part of the N difference shown above but not all "
            "of it, and the v5 and v7 table contents were not compared, so the "
            "cause of the N and mean differences is not established."
        ),
    },
    # ── HCHS-SOL ──────────────────────────────────────────────────────────────
    ("HCHS_SOL", "race_us_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "HCHS-SOL has no OMB race variable; all participants are "
            "Hispanic/Latino, and the study collected a 7-level heritage "
            "subgroup (BKGRD1_C7, phv00226254) that is not an OMB race. BDC "
            "demography.yaml records race as UNKNOWN for every participant. The "
            "DCC sets race to Other for every participant in pht004713 with "
            "CONSENT not 0. The comparison reports BDC UNKNOWN as Other, so the "
            "two sides agree in the table; the underlying statements differ "
            "(race not recorded, BDC; race recorded as Other, the DCC)."
        ),
    },
    ("HCHS_SOL", "antihypertensive_meds_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "Both sides read MED_ANTIHYPERT (pht004715 phv00226324); BDC is "
            "graded on the ATC:C02 item only. In phs000810.v2 the variable has "
            "9,637 No, 1,972 Yes and 222 blanks among the 11,831 rows of "
            "pht004715, which are the BDC missing values. The DCC removes NA "
            "rows and its universe is the v1 consented set, so the N difference "
            "reflects the participant-universe difference described in the "
            "cohort note together with the DCC missing values; it is not "
            "matched by participant."
        ),
    },
    ("HCHS_SOL", "basophil_ncnc_bld_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported count LABA27 (pht004715 phv00226301), "
            "whose values appear on a 0.1 x10^9/L grid; in phs000810.v2, 8,670 "
            "of its 11,063 values are exactly 0 and the maximum is 0.5. The DCC "
            "derives the count as WBC (LABA1) x % basophils (LABA14) / 100, "
            "which is not on the 0.1 grid. The lower BDC mean and median are "
            "consistent with reporting the count on that grid (inferred from "
            "the distributions, not matched by participant)."
        ),
    },
    ("HCHS_SOL", "eosinophil_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported count LABA26 (pht004715 phv00226300), "
            "whose values appear on a 0.1 x10^9/L grid. In phs000810.v2 LABA26 "
            "has a maximum of 230, while % eosinophils (LABA13) has a maximum "
            "of 36 and WBC (LABA1) a maximum of 31.8, so that value exceeds any "
            "WBC in the table. BDC passes it through and the comparison flags "
            "it as implausible. That one value accounts for the SD difference "
            "and for most of the mean difference shown above. The DCC derives "
            "the count as WBC (LABA1) x % eosinophils (LABA13) / 100 and does "
            "not read LABA26. The comparison scores the mean difference against "
            "the DCC SD."
        ),
    },
    ("HCHS_SOL", "monocyte_ncnc_bld_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "BDC emits the lab-reported count LABA25 (pht004715 phv00226299), "
            "whose values appear on a 0.1 x10^9/L grid; the DCC derives the "
            "count as WBC (LABA1) x % monocytes (LABA12) / 100. In phs000810.v2 "
            "LABA25 has a maximum of 14.8, which the comparison flags as "
            "implausible. That one value accounts for the SD difference shown "
            "above and contributes to the mean difference. The comparison "
            "scores the mean difference against the DCC SD."
        ),
    },
    # ── COPDGene ──────────────────────────────────────────────────────────────
    ("COPDGENE", "bmi_baseline_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-calculated BMI (phv00159593, pht002239 v5, "
            "dictionary comment 'calculated', kg/m2) at COPDGene P1. The DCC "
            "computes weight/height^2 from its harmonized Weight_KG "
            "(phv00159591) and Height_CM (phv00159592), read from pht002239 v4 "
            "(phs000179.v5). BDC mean weight is higher than the DCC mean "
            "weight, which raises BDC BMI, and BDC mean height is slightly "
            "higher, which lowers it; the net difference is consistent with the "
            "weight difference. Rounding of stored values to two decimals (the "
            "variable report examples show two decimals) changes a mean over "
            "about 10,000 participants by about 0.00003, so it does not account "
            "for the difference. The cause of the weight and height differences "
            "is not established; the table versions differ."
        ),
    },
    ("ARIC", "lipid_lowering_medication_1"): {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "At Exam 1 BDC reads two DERIVE13 (pht004063) indicators: "
            "STATINCODE01 (phv00204695, ATC:C10AA) and CHOLMDCODE01 "
            "(phv00204802, ATC:C10A; the spec maps T to UNKNOWN); a participant "
            "positive on either is Yes. The DCC reads CHOLMDCODE01 only, with T "
            "set to missing, and omits records with no V1AGE01. In v8, "
            "CHOLMDCODE01 has 0 = 13,943, 1 = 426 and T = 108. The BDC No and "
            "Yes counts shown above equal these, and the BDC missing count "
            "equals the 590 participants with no v8 DERIVE13 row plus the 108 "
            "coded T. The DCC valid count exceeds the 14,369 non-T values in "
            "v8, so its release of pht004063 held more participants."
        ),
    },
    ("FHS", "mi_prior_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "The DCC codes prior MI from pht000309 EVENT 1-5 with DATE <= 0 "
            "(phv00036469, phv00036471); participants with any other pht000309 "
            "row, or with cvd == 0 in pht003316 (phv00190817), are negatives, "
            "and participants with neither have no DCC value. BDC "
            "hist_my_inf.yaml reads one item per baseline exam: Original Exam 4 "
            "MF279 (phv00000734; codes 3 and 4 map to UNKNOWN), Offspring Exam "
            "1 A163 (phv00007665), and Generation 3, NOS and Omni 2 Exam 1 "
            "G3A184 / g3a184 (phv00021036, phv00273870, phv00566033; code 2 "
            "maps to UNKNOWN). At Omni 1 Exam 1 (pht004813) it emits only "
            "ECG-location codes, which the comparison does not count as "
            "mi_prior_1. In v35, pht003099 has 490 Omni 1 participants (idtype "
            "7), and the UNKNOWN answers number 50 (27 MF279, 11 A163, 12 "
            "g3a184); together these reconcile with the BDC missing count shown "
            "above (inferred from totals, not matched by participant). The "
            "comparison counts a blank condition status as answered: in v35 the "
            "null source values are 658 MF279, 2 A163 and 1 Omni 2 g3a184. "
            "Prior History comes from different sources on the two sides; "
            "participant-level reconciliation has not been run."
        ),
    },
    ("HCHS_SOL", "height_baseline_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC bdy_hgt.yaml emits two height rows per participant at HCHS "
            "EXAM: measured height HEIGHT (pht004715 phv00226281, method_type "
            "anthropometry) and recalled height at age 21 WHEA2A_CM "
            "(phv00527446, method_type 'height recalled at age 21'). The "
            "comparison selects the measured block, which is the variable the "
            "DCC reads (HEIGHT, corrected, joined to AGE with NA removed). In "
            "phs000810.v2 HEIGHT has 11,815 values and 16 nulls among the "
            "11,831 rows of pht004715, which are the BDC missing values. The "
            "higher DCC missingness is consistent with DCC universe "
            "participants that have no pht004715 row (inferred from totals, not "
            "matched by participant)."
        ),
    },
    ("HCHS_SOL", "weight_baseline_1"): {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "BDC bdy_wgt.yaml emits the measured weight ANTA4 (pht004715 "
            "phv00253218, method_type anthropometry) and recalled weights at "
            "ages 21, 45 and 65 (WHEA3A_KG phv00527442, WHEA4A_KG phv00527443, "
            "WHEA5A_KG phv00527444; method_type 'self-report questionnaire') at "
            "HCHS EXAM. The comparison selects the measured block, which is the "
            "variable the DCC reads (ANTA4, joined to AGE with NA removed). In "
            "phs000810.v2 ANTA4 has 11,807 values and 24 nulls among the 11,831 "
            "rows of pht004715, which are the BDC missing values. The higher "
            "DCC missingness is consistent with DCC universe participants that "
            "have no pht004715 row (inferred from totals, not matched by "
            "participant)."
        ),
    },
    ("JHS", "ldl_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the stored fasting LDL at Exam 1 (analysis1, pht008729 "
            "phv00401134), which in phs000286.v7 has 3,504 values and 379 "
            "nulls. ldl.yaml has no Exam 1 block for pht001945 LDLC "
            "(phv00125931). The DCC computes LDL with the Friedewald formula "
            "from its own harmonized total cholesterol, HDL and triglycerides, "
            "sets LDL to NA when triglycerides are 400 or more or when the "
            "result is negative, and removes NA. The higher BDC missingness "
            "shown above matches the analysis1 nulls: BDC missing values are "
            "the source nulls."
        ),
    },
    ("JHS", "lipid_lowering_medication_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC reads the self-reported statin item at Exam 1 "
            "(tak_statin.yaml, analysis1 pht008729 phv00401114 statinMedsSelf, "
            "ATC:C10AA), which in phs000286.v7 has 3,802 values and 81 nulls; "
            "the comparison counts a blank drug status as missing, so BDC "
            "missing values equal the source nulls. The DCC reads LPM01 "
            "(pht001949 phv00126053) and sets 'X' to missing; its documentation "
            "states that the variable is not restricted to a single class of "
            "medications and includes drugs such as statins and fibrates. The "
            "two sides therefore differ in medication scope and in source "
            "variable; the cause of the missingness difference is not "
            "established."
        ),
    },
    ("MESA", "angina_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited, and its "
            "exclusion list includes physician-diagnosed angina or taking "
            "nitroglycerin. The comparison grades MESA Classic Exam 1 "
            "(pht001116), which holds no self-reported angina history item; the "
            "DCC code reads only age1c (phv00084442) and sets angina_prior to 0 "
            "for every pht001116 participant, stating no rationale. BDC "
            "angina.yaml maps angina from the events table pht001123 (ang "
            "phv00087859, no visit, follow-up events) and Family pht001121 "
            "(anginaf phv00087143, MESA FAMILY); no AirNR source is mapped. "
            "pht001123 also records 3 pre-baseline angina events (prebase "
            "phv00087850). BDC has no row at MESA CLASSIC EXAM 1, so the "
            "variable is not comparable (all missing)."
        ),
    },
    ("MESA", "cabg_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited, and its "
            "exclusion list includes having undergone CABG. The comparison "
            "grades MESA Classic Exam 1 (pht001116), which holds no CABG "
            "history item; the DCC code reads only age1c (phv00084442) and sets "
            "cabg_prior to 0 for every pht001116 participant, stating no "
            "rationale. BDC hist_cor_bypg.yaml maps CABG as a Procedure from "
            "AirNR pht001111 (coronct1 phv00082876, MESA AIR EXAM) and the "
            "events table pht001123 (cbg phv00087865, no visit, follow-up "
            "events); Family corobyf (pht001121 phv00087146) is not mapped. BDC "
            "has no row at MESA CLASSIC EXAM 1, so the variable is not "
            "comparable (all missing)."
        ),
    },
    ("MESA", "coronary_angioplasty_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited, and its "
            "exclusion list includes having undergone angioplasty. The "
            "comparison grades MESA Classic Exam 1 (pht001116), which holds no "
            "angioplasty history item; the DCC code reads only age1c "
            "(phv00084442) and sets coronary_angioplasty_prior to 0 for every "
            "pht001116 participant, stating no rationale. MESA-ingest has no "
            "coronary angioplasty spec, so BDC has no angioplasty data at any "
            "visit. dbGaP holds angioplasty items that BDC does not map: AirNR "
            "angct1 (pht001111 phv00082875), Family ballnf (pht001121 "
            "phv00087147), events ptca (pht001123 phv00087862) and Exam 5 "
            "angct5 (pht003091 phv00176172). The variable is not comparable "
            "(all missing). HV #955."
        ),
    },
    ("MESA", "icam1_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC sets Classic icam11M (pht001116 phv00085118) codes -333 to "
            "0.35 and -555 to 900, and AirNR icam1m (pht001111 phv00082964) "
            "-333 to 20, so participants coded outside the measurement limits "
            "receive the limit values. BDC icam.yaml maps only the measured "
            "icam1 values (pht001116 phv00085117; pht001111 phv00082963). In "
            "phs000209.v13, icam11M has 53 values of -333 and 5 of -555, and "
            "icam1m has 3 of -333. Adding these 61 values to the BDC values "
            "reproduces the DCC N, mean and SD shown above (established from "
            "totals, not matched by participant)."
        ),
    },
    ("MESA", "il6_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC sets il61M (pht001116 phv00085010) code -333 to 0.09 and "
            "-555 to 13.0, so participants coded outside the measurement limits "
            "receive the limit values; code -777 (invalid result) stays missing "
            "on both sides. BDC il6.yaml maps measured il61 only (phv00085009). "
            "In phs000209.v13, il61M has 1 value of -333, 16 of -555 and 2 of "
            "-777. Adding the 17 limit values to the BDC values reproduces the "
            "DCC N and mean shown above (established from totals, not matched "
            "by participant)."
        ),
    },
    ("MESA", "lipid_lowering_medication_1"): {
        "code": "SOURCE_VARIABLE_DIFF",
        "no_override": True,
        "note": (
            "BDC tak_statin.yaml emits two ATC:C10A records per exam, lipid1c "
            "(computed 'any lipid-lowering medication') and cholmed1 ('taking "
            "meds for high cholesterol'): Classic phv00085407 and phv00085235, "
            "AirNR phv00083162 and phv00083002. Family has lipidfc "
            "(phv00087104) only. The comparison counts a participant as Yes "
            "when either record is PRESENT. The DCC reads lipid1c (lipidfc for "
            "Family) only, so BDC Yes is higher where a participant has "
            "cholmed1 = 1 and lipid1c = 0 (inferred from totals, not matched by "
            "participant)."
        ),
    },
    ("MESA", "mi_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited, and its "
            "exclusion list includes physician-diagnosed heart attack. The "
            "comparison grades MESA Classic Exam 1 (pht001116), which holds no "
            "self-reported MI history item; the DCC code reads only age1c "
            "(phv00084442) and sets mi_prior to 0 for every pht001116 "
            "participant, stating no rationale. BDC hist_my_inf.yaml maps MI "
            "from the events table pht001123 (mi phv00087853, no visit, "
            "follow-up events) and Family pht001121 (heartaf phv00087142, MESA "
            "FAMILY); no AirNR source is mapped. pht001123 also records 1 "
            "pre-baseline MI event (prebase phv00087850). BDC has no row at "
            "MESA CLASSIC EXAM 1, so the variable is not comparable (all "
            "missing)."
        ),
    },
    ("MESA", "pad_prior_1"): {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited; its "
            "exclusion list has no PAD item but includes any surgery on the "
            "heart or arteries. The comparison grades MESA Classic Exam 1 "
            "(pht001116), which holds a claudication symptom item (claud1t "
            "phv00084455) but no PAD history item; the DCC code reads only "
            "age1c (phv00084442) and sets pad_prior to 0 for every pht001116 "
            "participant, stating no rationale. BDC pad.yaml maps PAD only from "
            "the events table pht001123 (pvd phv00087873 and the pre-baseline "
            "PVD exclusion flag expvd phv00087852; no visit, follow-up events); "
            "no Family or AirNR source is mapped. pht001123 also records 4 "
            "pre-baseline PVD events (prebase phv00087850). BDC has no row at "
            "MESA CLASSIC EXAM 1, so the variable is not comparable (all "
            "missing)."
        ),
    },
    ("WHI", "coronary_angioplasty_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "Both sides read Form 30 PTCA (pht000999 phv00078536). In "
            "phs000200.v12 it has 1,467 Yes, 139,657 No and 1,999 null. The DCC "
            "counts non-null answers only. The comparison counts a blank "
            "procedure status as answered, so women with a null answer count as "
            "No Prior History for BDC. Women with no Form 30 row are missing on "
            "both sides."
        ),
    },
    ("ARIC", "carotid_plaque_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC (carotid_plaque.yaml) reads the composite PLAQUE01 "
            "(phv00204791, pht004063, plaque with or without shadowing in any "
            "carotid site) at Exam 1, mapping 0 to ABSENT, 1 to PRESENT and T "
            "to UNKNOWN. The DCC reads the same variable, with T set to "
            "missing. In v8, PLAQUE01 has 6,956 code 0, 3,901 code 1, 3,267 "
            "code T and 353 blanks. The comparison counts a blank condition "
            "status as answered, so the BDC No Prior History count equals the "
            "6,956 plus the 353 blanks, and the BDC missing count equals the "
            "3,267 T plus the 590 participants with no v8 DERIVE13 row "
            "(established). The DCC counts differ from v8, so its release of "
            "DERIVE13 held different values. Site-level plaque variables (for "
            "example BIFPLQ01, phv00204776) are not represented in BDC; that "
            "question is tracked in HV #960."
        ),
    },
    ("ARIC", "coronary_angioplasty_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC (hist_cor_angio.yaml) reads PHEA09A (phv00208854, pht004143, "
            "coronary angioplasty probe, Exam 1), mapping Y to PRESENT, N to "
            "ABSENT and T to UNKNOWN. In v8, PHEA09A has 304 values (Y 96, N "
            "208) and 14,756 blanks. The comparison counts a blank condition "
            "status as answered, so nearly all BDC participants count as "
            "answered and the BDC missing count is small. The DCC reads "
            "PHEA09A, PHEA06 and PHEA08 (phv00208854, phv00208845, "
            "phv00208853), sets a missing PHEA09A to 0 for records with fewer "
            "than three missing values among age, PHEA06, PHEA08 and PHEA09A, "
            "and drops the rest. In v8, PHEA06 has 123 blanks and PHEA08 has "
            "125, and records with no V1AGE01 (phv00204712, pht004063) are also "
            "dropped; the DCC missing count is consistent with these rules "
            "(inferred from totals, not matched by participant)."
        ),
    },
    ("CARDIA", "antihypertensive_meds_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC hypert_trt.yaml reads the Year 0 medication follow-up rows of "
            "pht001571 where A09MDTYP = HBP (phv00113154) and maps A09MDNOW "
            "(phv00113155) 2 to PRESENT, 1 to ABSENT and M to UNKNOWN. The "
            "comparison takes attendees as the denominator and counts a "
            "participant with no HBP row as not taking, so BDC has no missing "
            "values. The DCC starts from A08BPMED (phv00113012, pht001569; "
            "codes unlabeled in phs000285.v3: 1 = 3,535, 2 = 84, 8 = 1, and 2 "
            "other values): 1 becomes 0, 2 is resolved from the A09MDNOW values "
            "of HBP records, and other codes and unresolved 2s become missing. "
            "The difference in missing values is consistent with those "
            "participants; the difference in the Yes count is not established."
        ),
    },
    ("CARDIA", "ldl_1"): {
        "code": "DERIVED_VS_STORED",
        "no_override": True,
        "note": (
            "BDC reads the study-stored LDL AL1LDL (phv00113703, pht001588, "
            "'LDL CHOLESTEROL (MG/DL)') at CARDIA YEAR 0; the dbGaP dictionary "
            "does not state the study formula. The DCC does not read LDL; it "
            "computes the Friedewald formula (total cholesterol - HDL - "
            "triglycerides/5) from its harmonized lipid variables, sets LDL to "
            "missing where triglycerides are 400 or more or the result is "
            "negative, and requires all three inputs. The N difference shown "
            "above is consistent with one participant who has an LDL value and "
            "no triglyceride value, and the remainder with the DCC triglyceride "
            "and negative-value rules (inferred from totals, not matched by "
            "participant)."
        ),
    },
    ("CHS", "cac_score_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "BDC reads CACSCORE (phv00100691, pht001459, Agatston score) at "
            "'CHS CAC' and takes age from a join to pht001475 AGEY11 "
            "(phv00102583). The DCC inner-joins pht001459 with pht001475 and "
            "removes records with a missing score or age. In phs000287.v7 "
            "CACSCORE has 554 values and AGEY11 has 1,924 blanks, so the N "
            "difference shown above is consistent with participants who have a "
            "score and no AGEY11 (inferred from totals, not matched by "
            "participant)."
        ),
    },
    ("CHS", "coronary_angioplasty_prior_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC maps coronary angioplasty (OMOP:4184832) from BASE1 "
            "(phv00099038), BASEBOTH CORART (phv00100322), EVENT_SUMMARY "
            "CORARTBL (phv00100782), YR5NEW (phv00105981) and PSG 1 "
            "(phv00197455); the DCC reads CORART (phv00100322, pht001452) with "
            "AGEBL. In phs000287.v7, CORART has 5,482 values and 49 blanks "
            "(dictionary code . = Missing). The spec maps only codes 0 and 1, "
            "and the comparison counts a blank procedure status as answered, so "
            "BDC has no missing values while the DCC has 49; the Prior History "
            "counts agree."
        ),
    },
    ("JHS", "cimt_2"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC averages four maxima: the maximum of the three left "
            "far-wall values, the right far-wall values, and the left and right "
            "near-wall values (_mx45 and _mx23 variables of pht001978), paired "
            "with the Exam 1 age. carotid_imt.yaml reads only the six far-wall "
            "average segments (_av45) of pht008791 and no maximum or near-wall "
            "variable, so BDC has no row for this quantity."
        ),
    },
    ("MESA", "il10_1"): {
        "code": "DERIVATION_DIFF",
        "no_override": True,
        "note": (
            "The DCC sets il10a1m (pht002099 phv00142667) code -333 (Low < "
            "0.13) to 0.13 and code -555 (High > 10,000) to 10000. BDC "
            "il10.yaml maps measured il10a1 (phv00142666) only and records the "
            "range limits 0.13 and 10,000 pg/mL. In phs000209.v13, il10a1m has "
            "3 values of -333 and 1 of -555. Adding those 4 values to the BDC "
            "values reproduces the DCC N and mean shown above (established from "
            "totals); the single 10,000 accounts for the mean and SD "
            "difference, and the median and quartiles are unaffected."
        ),
    },
    ("MESA", "race_us_1"): {
        "code": "COMPARISON_CONVENTION",
        "no_override": True,
        "note": (
            "BDC demography.yaml maps MESA race code 4 (Hispanic) to UNKNOWN "
            "(BDC-HM unknown race, OMOP:8552) at every exam block, and codes 1, "
            "2 and 3 to White, Asian and Black. The DCC documents that when a "
            "source race variable offers a Hispanic/Latino option, Other is "
            "assigned unless more specific information exists. The comparison "
            "reports OMOP:8552 and UNKNOWN as Other, which is why the two sides "
            "agree in the Other category; BDC itself records these participants "
            "as unknown race."
        ),
    },
    ("MESA", "tnfa_r1_1"): {
        "code": "DATA_QUALITY_FLAG",
        "no_override": True,
        "note": (
            "BDC tnfa_r1.yaml reads tnfri1 (pht001116 phv00085029), passes "
            "numeric values through, excludes -888, and sets -555 to 5000 pg/mL "
            "with the qualifier GREATER_THAN. The phs000209.v13 metadata lists "
            "no coded values for tnfri1 (var_report maximum 5,544 pg/mL), so "
            "neither the -555 code nor the 5000 value has a dbGaP source; 5000 "
            "is the DCC's documented MESA rule (values still above the upper "
            "limit of detection after dilution are set to a 10-fold diluted "
            "limit), and BDC applies the same value, so agreement on these "
            "participants reflects a shared rule, not independent derivation. "
            "HV #959."
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
            "The graded phenotypes come from one table (pht002239 "
            "COPDGene_Subject_Phenotypes v5, 1,003 variable entries in "
            "phs000179.v7). The table holds several phases, and the specs map "
            "each row to its phase visit through phase_study (phv00568798: "
            "COPDGene P1, P2, P3, P3B); the comparison selects COPDGene P1. The "
            "DCC read an earlier version of this table (pht002239 v4, "
            "phs000179.v5)."
        ),
    },
    "HCHS_SOL": {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "The DCC used phs000810.v1; its race_us_1 function keeps every "
            "participant of pht004713 (HCHS_SOL_Cohort_Subject) with CONSENT "
            "not 0. BDC uses phs000810.v2.p2, where pht004713 has 12,121 "
            "participants with consent (c1 HMB-NPU 2,304, c2 HMB 9,817) and "
            "pht004715 has 11,831 participants with a phenotype row; the BDC N "
            "counts the latter, so 290 consented participants have no BDC row. "
            "The v1 consent breakdown is not in the cached metadata. The N "
            "difference shown above combines the version difference in the "
            "consented set with the 290 participants without a phenotype row, "
            "and for measured variables with the DCC missing values (inferred "
            "from totals, not matched by participant)."
        ),
    },
    "JHS": {
        "code": "PARTICIPANT_UNIVERSE_DIFF",
        "no_override": True,
        "note": (
            "The DCC used phs000286.v5; its race_us_1 function keeps every "
            "JHS_Subject (pht001920) participant with CONSENT not 0 and assigns "
            "Black. BDC uses v7, where pht001920 has 3,889 participants with "
            "CONSENT not 0 (c1 883, c2 201, c3 2,289, c4 516); the BDC N is the "
            "3,883 with a row in analysis1 (pht008729; c1 878, c2 201, c3 "
            "2,289, c4 515), and BDC grades JHS Exam 1 for every compared "
            "variable except CAC (Exam 2). The v7 study description states that "
            "approximately 3,600 participants consented to genetic research and "
            "data deposition, and JHS_Subject SUBJECT_SOURCE2 lists 3,596 "
            "participants as JHS_CARe; the v5 participant list was not "
            "available to compare membership. The DCC set appears to include "
            "participants with no Exam 1 record: the DCC sex variable is read "
            "from Exam 1 pht001949 GENDER, and its missing count is close to "
            "the DCC missing count on most Exam 1 variables (inferred from "
            "totals, not matched by participant). The N difference for each "
            "variable combines this universe difference with the "
            "variable-specific missingness shown in the rows above."
        ),
    },
    "MESA": {
        "code": "STRUCTURAL_GAP",
        "no_override": True,
        "note": (
            "The comparison grades MESA prior MI, angina, PAD, CABG and "
            "coronary angioplasty at Classic Exam 1 (pht001116). The "
            "phs000209.v13 study description states that participants with "
            "known clinical cardiovascular disease were not recruited, listing "
            "physician-diagnosed heart attack, angina, and CABG or angioplasty "
            "among the exclusions; pht001116 holds no self-reported history "
            "item for these conditions. The DCC code reads only age1c "
            "(phv00084442), states no rationale, and sets each variable to 0 "
            "for every pht001116 participant. The events table pht001123 "
            "records 9 pre-baseline events (prebase phv00087850: PVD 4, angina "
            "3, MI 1, CHF 1). BDC maps these conditions from Family "
            "(pht001121), AirNR (pht001111) and pht001123 follow-up events (no "
            "visit), and has no coronary angioplasty spec. None of these gives "
            "BDC a row at MESA CLASSIC EXAM 1, so all five variables are not "
            "comparable (all missing)."
        ),
    },
    "FHS": {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "BDC reads phs000007.v35.p16; its participant universe is the "
            "15,089 participants in pht003099.v10 (vr_dates_2022), and BDC N "
            "counts the participants with a phenotype row for the variable. The "
            "DCC harmonized FHS from earlier releases (its FHS units cite "
            "phs000007.v29 and v30 tables); its participant list includes 19 "
            "records with no sex and no cardiovascular-event data, so its N for "
            "most variables counts the participants with a value, not the "
            "listed participants. The participant difference shown above "
            "therefore combines the release difference with these 19 records. "
            "The cause of the release difference is not documented in the "
            "material reviewed. FHS has Original, Offspring, Generation 3, New "
            "Offspring Spouse, Omni 1 and Omni 2 sub-cohorts, each with its own "
            "exam numbering."
        ),
    },
    'ARIC': {
        "code": "VERSION_MISMATCH",
        "no_override": True,
        "note": (
            "Matched ARIC variables are graded at Exam 1, except CRP, which the "
            "DCC reads at Exam 5 only (LIP33, pht006444), and the "
            "blood-cell-count variables, which follow the DCC rule of taking "
            "the visit with the most non-missing values first. BDC uses "
            "phs000280.v8; the DCC ARIC functions cite phs000280.v3, v4 and v5, "
            "and those releases are not in the material reviewed. In v8, "
            "DERIVE13 (pht004063.v3) holds 14,477 participants (V1AGE01 has "
            "14,477 values). The BDC Exam 1 universe is every participant with "
            "an Exam 1 row in any mapped table, which is 590 participants more "
            "than DERIVE13 in v8, so BDC variables read only from DERIVE13 (for "
            "example BMI, lipid-lowering medication, carotid plaque and angina) "
            "are missing for those 590. The DCC functions drop records with no "
            "V1AGE01. The participant-count difference between the sides shown "
            "at the top of the report carries into every N difference. For "
            "several DERIVE13 variables the DCC valid counts shown above exceed "
            "the v8 counts, so the DCC release of DERIVE13 held more "
            "participants (inferred from totals). The DCC sex and race missing "
            "counts are equal, and why those records have no data is not "
            "documented in the material reviewed. The comparison counts a blank "
            "condition status as answered, which removes BDC missingness for "
            "prior-history variables whose v8 sources have blanks."
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
    p('  Continuous tier: |BDC mean - reference mean| / reference SD (T1 < 0.005, T2 < 0.02, T3 < 0.05,')
    p('    T4 < 0.1). MeanDelta is BDC minus reference in raw units. Categorical tier: largest')
    p('    category difference in percentage points (T1 < 0.5, T2 < 1, T3 < 3, T4 < 10).')
    p('  Comparison conventions that can move a result:')
    p('    - A Condition or Procedure row with a blank status counts as answered (not Present).')
    p('    - A medication (DrugExposure) row with a blank status counts as missing.')
    p('    - Where a participant has different values at the graded visit and no method rule')
    p('      selects one, the first row in file order is kept.')
    p('    - OMOP:8552 (unknown race) is reported as Other.')
    p('    - A variable with no BDC row at the graded visit is NOT COMPARABLE but is tiered T5/M5.')
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
