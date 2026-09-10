"""
config.py -- Unified configuration for hv-dcc-compare
=======================================================
Contains:
  Part 1 -- TOPMed DCC side: COHORTS, DATASETS, variable specs, value maps.
            (source: topmed_compare_config.py in scripts/topmed_compare/)
  Part 2 -- BDC DMC side: concept label maps, BDC_MEASUREMENT_MAP,
            BDC_CONDITION_MAP, BDC_PROCEDURE_MAP, smoking maps, baseline
            visit configuration, and cohort normalization utilities.
            (source: extract_bdc_all.py in scripts/topmed_compare/)
"""

from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# SHARED COHORTS (9 studies present in both TOPMed DCC and BDC DMC)
# Keys = TOPMed `topmed_study` column values
# ─────────────────────────────────────────────────────────────────────────────
# NOTE ON bdc_version: this is the dbGaP release the HV harmonization is built
# on -- NOT necessarily the newest release staged in the local dbGaP cache.
# Corrected 2026-09-09: CARDIA v4 -> v3, MESA v15 -> v13, ARIC v9 -> v8.
#
# Do not infer this value from the cache's GapExchange_*.xml alone. A cohort
# mid-migration has both releases staged at once: the ARIC cache carries ~64k
# v9.p3 references alongside ~55k v8.p2, because the v8 -> v9 migration has been
# analysed but not adopted. The harmonization is still on v8 there, and only the
# HV mappings themselves (or the study lead) can settle which release is live.
# The other eight cohorts each have a single dominant version in cache.
#
# This field is provenance only -- no logic branches on it. The BDC extractor
# prefers the accession parsed out of the dm-bip output path (see
# parse_dbgap_version_from_dirs in extract_harmonized_summaries.py) and falls
# back here only when the path carries none, warning on any disagreement.
COHORTS: dict[str, dict] = {
    "ARIC": {
        "full_name": "Atherosclerosis Risk in Communities",
        "phs": "phs000280",
        "topmed_version": "v5",
        "bdc_version": "v8",
    },
    "CARDIA": {
        "full_name": "Coronary Artery Risk Development in Young Adults",
        "phs": "phs000285",
        "topmed_version": "v3",
        "bdc_version": "v3",
    },
    "CHS": {
        "full_name": "Cardiovascular Health Study",
        "phs": "phs000287",
        "topmed_version": "v6",
        "bdc_version": "v7",
    },
    "COPDGene": {
        "full_name": "Genetic Epidemiology of COPD",
        "phs": "phs000179",
        "topmed_version": "v5",
        "bdc_version": "v7",
    },
    "FHS": {
        "full_name": "Framingham Heart Study",
        "phs": "phs000007",
        "topmed_version": "v30",
        "bdc_version": "v35",
    },
    "HCHS_SOL": {
        "full_name": "Hispanic Community Health Study / Study of Latinos",
        "phs": "phs000810",
        "topmed_version": "v1",
        "bdc_version": "v2",
    },
    "JHS": {
        "full_name": "Jackson Heart Study",
        "phs": "phs000286",
        "topmed_version": "v5",
        "bdc_version": "v7",
    },
    "MESA": {
        "full_name": "Multi-Ethnic Study of Atherosclerosis",
        "phs": "phs000209",
        "topmed_version": "v13",
        "bdc_version": "v13",
    },
    "WHI": {
        "full_name": "Women's Health Initiative",
        "phs": "phs000200",
        "topmed_version": "v11",
        "bdc_version": "v12",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZED DISPLAY LABELS  (canonical values for comparison output)
# Shared with whi_compare/shared_constants.py — kept in sync.
# ─────────────────────────────────────────────────────────────────────────────
LABEL_FEMALE = "Female"
LABEL_MALE = "Male"

LABEL_WHITE = "White"
LABEL_BLACK = "Black or African American"
LABEL_ASIAN = "Asian"
LABEL_AIAN = "American Indian or Alaska Native"
LABEL_NHOPI = "Native Hawaiian or Other Pacific Islander"
LABEL_MULTIPLE = "Multiple Races"
LABEL_OTHER = "Other"

LABEL_HISPANIC = "Hispanic or Latino"
LABEL_NOT_HISPANIC = "Not Hispanic or Latino"
LABEL_ETHNICITY_INCONSISTENT = "Both / Inconsistent (TOPMed-only)"

# ─────────────────────────────────────────────────────────────────────────────
# TOPMED DCC RAW VALUE → NORMALIZED LABEL MAPS
# Source: TOPMed DCC harmonized_demographic_v4 variable data dictionary
# ─────────────────────────────────────────────────────────────────────────────
TOPMED_SEX_MAP = {
    "female": LABEL_FEMALE,
    "male": LABEL_MALE,
}

TOPMED_RACE_MAP = {
    "White": LABEL_WHITE,
    "Black": LABEL_BLACK,
    "Asian": LABEL_ASIAN,
    "AI_AN": LABEL_AIAN,
    "HI_PI": LABEL_NHOPI,
    "Multiple": LABEL_MULTIPLE,
    "Other": LABEL_OTHER,
}

TOPMED_ETHNICITY_MAP = {
    "HL": LABEL_HISPANIC,
    "notHL": LABEL_NOT_HISPANIC,
    "both": LABEL_ETHNICITY_INCONSISTENT,
}

# Binary covariate maps (antihypertensive_meds, lipid_lowering_medication, etc.)
TOPMED_BINARY_MAP = {
    "0": "No",
    "1": "Yes",
    "0.0": "No",
    "1.0": "Yes",
}

# Smoking status maps
TOPMED_EVER_SMOKER_MAP = {
    "0": "Never Smoked",
    "1": "Ever Smoked",
    "0.0": "Never Smoked",
    "1.0": "Ever Smoked",
}

TOPMED_CURRENT_SMOKER_MAP = {
    "0": "Not Current Smoker",
    "1": "Current Smoker",
    "0.0": "Not Current Smoker",
    "1.0": "Current Smoker",
}

# Condition prior history maps (angina, MI, PAD, VTE, CABG, angioplasty)
TOPMED_PRIOR_HISTORY_MAP = {
    "0": "No Prior History",
    "1": "Prior History",
    "0.0": "No Prior History",
    "1.0": "Prior History",
}

# VTE case status
TOPMED_VTE_CASE_MAP = {
    "0": "Control",
    "1": "Case",
    "0.0": "Control",
    "1.0": "Case",
}

# ─────────────────────────────────────────────────────────────────────────────
#  VARIABLE DEFINITIONS — organized by TOPMed DCC data set
#
#  Each entry:
#    topmed_var   : str  — variable name in the EAV `variable` column
#    bdc_label    : str  — corresponding BDC priority variable name
#    var_type     : str  — "categorical" or "continuous"
#    value_map    : dict | None  — if categorical, maps raw → display label
#    unit         : str | None   — UCUM unit for continuous variables
#    plausible_lo : float | None — lower plausibility bound (continuous)
#    plausible_hi : float | None — upper plausibility bound (continuous)
# ─────────────────────────────────────────────────────────────────────────────

# Each data set is a dict of { topmed_var_name: variable_spec }
# The "dataset_key" is used as the CLI argument name for --<key>-file.

DATASETS: dict[str, dict] = {
    # ── Demographics ────────────────────────────────────────────────────────
    "demographics": {
        "description": "TOPMed DCC harmonized demographics (v4)",
        "variables": {
            "annotated_sex_1": {
                "bdc_label": "Sex",
                "var_type": "categorical",
                "value_map": TOPMED_SEX_MAP,
            },
            "race_us_1": {
                "bdc_label": "Race",
                "var_type": "categorical",
                "value_map": TOPMED_RACE_MAP,
            },
            "hispanic_or_latino_1": {
                "bdc_label": "Ethnicity",
                "var_type": "categorical",
                "value_map": TOPMED_ETHNICITY_MAP,
            },
        },
    },
    # ── Baseline Common Covariates ──────────────────────────────────────────
    "baseline_covariates": {
        "description": "TOPMed DCC harmonized baseline common covariates",
        "variables": {
            "height_baseline_1": {
                "bdc_label": "Height",
                "var_type": "continuous",
                "unit": "cm",
                "plausible_lo": 120.0,
                "plausible_hi": 220.0,
            },
            "weight_baseline_1": {
                "bdc_label": "Body weight",
                "var_type": "continuous",
                "unit": "kg",
                "plausible_lo": 25.0,
                "plausible_hi": 300.0,
            },
            "bmi_baseline_1": {
                "bdc_label": "BMI",
                "var_type": "continuous",
                "unit": "kg/m2",
                "plausible_lo": 14.0,
                "plausible_hi": 70.0,
            },
            "ever_smoker_baseline_1": {
                "bdc_label": "Ever smoker",
                "var_type": "categorical",
                "value_map": TOPMED_EVER_SMOKER_MAP,
            },
            "current_smoker_baseline_1": {
                "bdc_label": "Current smoker",
                "var_type": "categorical",
                "value_map": TOPMED_CURRENT_SMOKER_MAP,
            },
        },
    },
    # ── Blood Pressure ──────────────────────────────────────────────────────
    "blood_pressure": {
        "description": "TOPMed DCC harmonized blood pressure",
        "variables": {
            "bp_systolic_1": {
                "bdc_label": "Systolic blood pressure",
                "var_type": "continuous",
                "unit": "mmHg",
                "plausible_lo": 60.0,
                "plausible_hi": 260.0,
            },
            "bp_diastolic_1": {
                "bdc_label": "Diastolic blood pressure",
                "var_type": "continuous",
                "unit": "mmHg",
                "plausible_lo": 30.0,
                "plausible_hi": 160.0,
            },
            "antihypertensive_meds_1": {
                "bdc_label": "Hypertension treatment",
                "var_type": "categorical",
                "value_map": TOPMED_BINARY_MAP,
            },
        },
    },
    # ── Lipids ──────────────────────────────────────────────────────────────
    "lipids": {
        "description": "TOPMed DCC harmonized lipids",
        "variables": {
            "hdl_1": {
                "bdc_label": "HDL",
                "var_type": "continuous",
                "unit": "mg/dL",
                "plausible_lo": 5.0,
                "plausible_hi": 200.0,
            },
            "ldl_1": {
                "bdc_label": "LDL",
                "var_type": "continuous",
                "unit": "mg/dL",
                "plausible_lo": 10.0,
                "plausible_hi": 400.0,
            },
            "total_cholesterol_1": {
                "bdc_label": "Total cholesterol",
                "var_type": "continuous",
                "unit": "mg/dL",
                "plausible_lo": 50.0,
                "plausible_hi": 600.0,
            },
            "triglycerides_1": {
                "bdc_label": "Triglycerides",
                "var_type": "continuous",
                "unit": "mg/dL",
                "plausible_lo": 10.0,
                "plausible_hi": 2000.0,
            },
            "lipid_lowering_medication_1": {
                "bdc_label": "Lipid-lowering medication",
                "var_type": "categorical",
                "value_map": TOPMED_BINARY_MAP,
            },
        },
    },
    # ── Blood Cell Count (CBC) ──────────────────────────────────────────────
    "blood_cell_count": {
        "description": "TOPMed DCC harmonized blood cell count",
        "variables": {
            "basophil_ncnc_bld_1": {
                "bdc_label": "Basophils count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 0.0,
                "plausible_hi": 5.0,
            },
            "eosinophil_ncnc_bld_1": {
                "bdc_label": "Eosinophils count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 0.0,
                "plausible_hi": 15.0,
            },
            "lymphocyte_ncnc_bld_1": {
                "bdc_label": "Lymphocytes count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 0.0,
                "plausible_hi": 50.0,
            },
            "monocyte_ncnc_bld_1": {
                "bdc_label": "Monocytes count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 0.0,
                "plausible_hi": 10.0,
            },
            "neutrophil_ncnc_bld_1": {
                "bdc_label": "Neutrophils count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 0.0,
                "plausible_hi": 50.0,
            },
            "hematocrit_vfr_bld_1": {
                "bdc_label": "Hematocrit",
                "var_type": "continuous",
                "unit": "%",
                "plausible_lo": 15.0,
                "plausible_hi": 65.0,
            },
            "hemoglobin_mcnc_bld_1": {
                "bdc_label": "Hemoglobin",
                "var_type": "continuous",
                "unit": "g/dL",
                "plausible_lo": 4.0,
                "plausible_hi": 22.0,
            },
            "mch_entmass_rbc_1": {
                "bdc_label": "MCH",
                "var_type": "continuous",
                "unit": "pg",
                "plausible_lo": 15.0,
                "plausible_hi": 50.0,
            },
            "mchc_mcnc_rbc_1": {
                "bdc_label": "MCHC",
                "var_type": "continuous",
                "unit": "g/dL",
                "plausible_lo": 25.0,
                "plausible_hi": 42.0,
            },
            "mcv_entvol_rbc_1": {
                "bdc_label": "MCV",
                "var_type": "continuous",
                "unit": "fL",
                "plausible_lo": 50.0,
                "plausible_hi": 130.0,
            },
            "pmv_entvol_bld_1": {
                "bdc_label": "Mean platelet volume",
                "var_type": "continuous",
                "unit": "fL",
                "plausible_lo": 4.0,
                "plausible_hi": 16.0,
            },
            "platelet_ncnc_bld_1": {
                "bdc_label": "Platelet count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 10.0,
                "plausible_hi": 1000.0,
            },
            "rbc_ncnc_bld_1": {
                "bdc_label": "Red blood cell count",
                "var_type": "continuous",
                "unit": "10^6/uL",
                "plausible_lo": 1.0,
                "plausible_hi": 10.0,
            },
            "wbc_ncnc_bld_1": {
                "bdc_label": "White blood cell count",
                "var_type": "continuous",
                "unit": "10^3/uL",
                "plausible_lo": 1.0,
                "plausible_hi": 50.0,
            },
            "rdw_ratio_rbc_1": {
                "bdc_label": "Red cell distribution width",
                "var_type": "continuous",
                "unit": "%",
                "plausible_lo": 10.0,
                "plausible_hi": 30.0,
            },
        },
    },
    # ── Inflammation ────────────────────────────────────────────────────────
    "inflammation": {
        "description": "TOPMed DCC harmonized inflammation markers",
        "variables": {
            "crp_1": {
                "bdc_label": "CRP",
                "var_type": "continuous",
                "unit": "mg/L",
                "plausible_lo": 0.0,
                "plausible_hi": 200.0,
            },
            "il6_1": {
                "bdc_label": "Interleukin 6",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 500.0,
            },
            "il1_beta_1": {
                "bdc_label": "Interleukin 1 beta",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 100.0,
            },
            "il10_1": {
                "bdc_label": "Interleukin 10",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 500.0,
            },
            "icam1_1": {
                "bdc_label": "ICAM1",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 2000.0,
            },
            "eselectin_1": {
                "bdc_label": "E-selectin",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 500.0,
            },
            "pselectin_1": {
                "bdc_label": "P-selectin",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 500.0,
            },
            "lppla2_act_1": {
                "bdc_label": "LP-PLA2 activity",
                "var_type": "continuous",
                "unit": "nmol/min/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 1000.0,
            },
            "lppla2_mass_1": {
                "bdc_label": "LP-PLA2 mass",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 2000.0,
            },
            "mcp1_1": {
                "bdc_label": "MCP1",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 5000.0,
            },
            "mmp9_1": {
                "bdc_label": "MMP9",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 5000.0,
            },
            "mpo_1": {
                "bdc_label": "Myeloperoxidase",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 5000.0,
            },
            "opg_1": {
                "bdc_label": "Osteoprotegerin",
                "var_type": "continuous",
                "unit": "pmol/L",
                "plausible_lo": 0.0,
                "plausible_hi": 50000.0,
            },
            "tnfa_1": {
                "bdc_label": "TNFa",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 500.0,
            },
            "tnfa_r1_1": {
                "bdc_label": "TNFa-R1",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 50000.0,
            },
            "isoprostane_8_epi_pgf2a_1": {
                "bdc_label": "8-epi-PGF2a",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 5000.0,
            },
            "cd40_1": {
                "bdc_label": "CD40",
                "var_type": "continuous",
                "unit": "ng/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 50000.0,
            },
            "il18_1": {
                "bdc_label": "Interleukin 18",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 5000.0,
            },
            "tnfr2_1": {
                "bdc_label": "TNFR2",
                "var_type": "continuous",
                "unit": "pg/mL",
                "plausible_lo": 0.0,
                "plausible_hi": 50000.0,
            },
        },
    },
    # ── Atherosclerosis / Imaging ───────────────────────────────────────────
    "atherosclerosis": {
        "description": "TOPMed DCC harmonized atherosclerosis imaging",
        "variables": {
            "cac_score_1": {
                "bdc_label": "CAC Score",
                "var_type": "continuous",
                "unit": "Agatston",
                "plausible_lo": 0.0,
                "plausible_hi": 10000.0,
            },
            "cac_volume_1": {
                "bdc_label": "CAC volume",
                "var_type": "continuous",
                "unit": "mm3",
                "plausible_lo": 0.0,
                "plausible_hi": 10000.0,
            },
            "cimt_1": {
                "bdc_label": "Carotid IMT (variant 1)",
                "var_type": "continuous",
                "unit": "mm",
                "plausible_lo": 0.1,
                "plausible_hi": 5.0,
            },
            "cimt_2": {
                "bdc_label": "Carotid IMT (variant 2)",
                "var_type": "continuous",
                "unit": "mm",
                "plausible_lo": 0.1,
                "plausible_hi": 5.0,
            },
            "carotid_stenosis_1": {
                "bdc_label": "Carotid stenosis",
                "var_type": "categorical",
                # Deliberately still unmapped -- NOT the same shape as
                # carotid_plaque_1. TOPMed grades this 0-5, an ordinal
                # severity scale (MESA: 3,692/1,814/782/30/15/5), and the MESA
                # YAML bands it as '1':'1-24', '2':'25-49', ... Writing labels
                # here means committing to what grades 3-5 stand for, which
                # needs the DCC data dictionary rather than inference from the
                # pattern. It would change no grade today regardless: BDC
                # emits 0 valid values for this variable in the only cohort
                # that has it, so its D is a coverage gap, not a label
                # mismatch.
                "value_map": None,
            },
            "carotid_plaque_1": {
                "bdc_label": "Carotid plaque",
                "var_type": "categorical",
                # TOPMed emits raw 0/1 while BDC emits the prior-history
                # labels, so with no map the two sides shared no category at
                # all and every cohort carrying it graded D on a ~66pp
                # "difference". The counts already agreed: MESA had TOPMed
                # 1 = 2,657 against BDC "Prior History" = 2,657 exactly.
                # Binary with the same semantics as the *_prior_1 family, so
                # it takes the same map.
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
        },
    },
    # ── VTE ──────────────────────────────────────────────────────────────────
    "vte": {
        "description": "TOPMed DCC harmonized venous thromboembolism",
        "variables": {
            "vte_case_status_1": {
                "bdc_label": "VTE case status",
                "var_type": "categorical",
                "value_map": TOPMED_VTE_CASE_MAP,
            },
            "vte_prior_history_1": {
                "bdc_label": "VTE prior history",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
        },
    },
    # ── Atherosclerosis Events — Prior (repo addition) ──────────────────────
    "atherosclerosis_events_prior": {
        "description": "TOPMed DCC atherosclerosis events — prior history (GitHub repo)",
        "variables": {
            "angina_prior_1": {
                "bdc_label": "Angina",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "mi_prior_1": {
                "bdc_label": "History of MI",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "pad_prior_1": {
                "bdc_label": "PAD",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "cabg_prior_1": {
                "bdc_label": "CABG",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "coronary_angioplasty_prior_1": {
                "bdc_label": "Coronary angioplasty",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "coronary_revascularization_prior_1": {
                "bdc_label": "Coronary revascularization",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
        },
    },
    # ── Atherosclerosis Events — Incident ───────────────────────────────────
    "atherosclerosis_events_incident": {
        "description": "TOPMed DCC atherosclerosis events — incident during follow-up",
        "variables": {
            "angina_incident_1": {
                "bdc_label": "Angina (incident)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "cabg_incident_1": {
                "bdc_label": "CABG (incident)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "coronary_angioplasty_incident_1": {
                "bdc_label": "Coronary angioplasty (incident)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "chd_death_definite_1": {
                "bdc_label": "CHD death (definite)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "chd_death_probable_1": {
                "bdc_label": "CHD death (probable or definite)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "mi_incident_1": {
                "bdc_label": "MI (incident)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
            "pad_incident_1": {
                "bdc_label": "PAD (incident)",
                "var_type": "categorical",
                "value_map": TOPMED_PRIOR_HISTORY_MAP,
            },
        },
    },
    # ── Sleep (repo addition) ───────────────────────────────────────────────
    "sleep": {
        "description": "TOPMed DCC harmonized sleep (GitHub repo)",
        "variables": {
            "sleep_duration_1": {
                "bdc_label": "Sleep hours",
                "var_type": "continuous",
                "unit": "hours",
                "plausible_lo": 0.0,
                "plausible_hi": 24.0,
            },
        },
    },
}


def get_all_variable_names() -> list[str]:
    """Return a flat list of all TOPMed DCC variable names across all data sets."""
    names = []
    for ds in DATASETS.values():
        names.extend(ds["variables"].keys())
    return names


def get_variable_spec(var_name: str) -> dict | None:
    """Look up the spec for a single TOPMed variable, searching all data sets."""
    for ds in DATASETS.values():
        if var_name in ds["variables"]:
            return ds["variables"][var_name]
    return None


def get_dataset_for_variable(var_name: str) -> str | None:
    """Return the dataset key that contains the given variable."""
    for ds_key, ds in DATASETS.items():
        if var_name in ds["variables"]:
            return ds_key
    return None


def get_variables_by_type(var_type: str) -> list[str]:
    """Return all variable names with the given type ('categorical' or 'continuous')."""
    result = []
    for ds in DATASETS.values():
        for var_name, spec in ds["variables"].items():
            if spec["var_type"] == var_type:
                result.append(var_name)
    return result


# Quick summary stats
TOTAL_MATCHED_VARS = sum(len(ds["variables"]) for ds in DATASETS.values())
TOTAL_CONTINUOUS = len(get_variables_by_type("continuous"))
TOTAL_CATEGORICAL = len(get_variables_by_type("categorical"))

# =============================================================================
# PART 2 -- BDC DMC SIDE
# =============================================================================
# Concept label maps, variable mapping dictionaries, smoking observation config,
# baseline visit configuration, and cohort normalization helpers.
# Migrated from extract_bdc_all.py (scripts/topmed_compare/).
# =============================================================================

# OMOP / OBA CONCEPT LABEL MAPS
# ─────────────────────────────────────────────────────────────────────────────
# These map BDC OMOP concept IDs → normalized display labels that match the
# TOPMed DCC extraction output format.

OMOP_SEX_MAP = {
    "OMOP:8532": "Female", "OMOP:8507": "Male",
    "8532": "Female", "8507": "Male",
}

# NOTE ON "UNKNOWN": BDC-HM declares UNKNOWN as a permissible value name for
# Demography.race (label "Unknown") alongside the OMOP CURIEs. config accepted
# only the CURIEs, so it collapsed to UNMAPPED -- 100% of HCHS/SOL (11,831) and
# 26% of MESA (2,177), which graded both cohorts D on race.
#
# Those are the same participants the reference files under "Other": MESA's
# 2,177 UNKNOWN are exactly its 2,177 TOPMed "Other", and are exactly its 2,177
# Hispanic participants, with Asian, White and Black agreeing to within 2.
# Mapped to Other to match the reference convention for comparison purposes
# (agreed 2026-09-10).
#
# This asserts equivalence of CONVENTION, not of meaning: "unknown race" and
# "other race" are different claims and only the former is what BDC-HM records.
# It is the right call for scoring against TOPMed and the wrong one to carry
# into anything that reports race on its own.
OMOP_RACE_MAP = {
    "OMOP:8527": "White", "OMOP:8515": "Asian",
    "OMOP:8516": "Black or African American",
    "OMOP:8657": "American Indian or Alaska Native",
    "OMOP:8557": "Native Hawaiian or Other Pacific Islander",
    "OMOP:45880900": "Multiple Races", "OMOP:8552": "Other",
    # Bare numeric fallbacks
    "8527": "White", "8515": "Asian",
    "8516": "Black or African American",
    "8657": "American Indian or Alaska Native",
    "8557": "Native Hawaiian or Other Pacific Islander",
    "45880900": "Multiple Races", "8552": "Other",
    # Permissible value name rather than a CURIE -- see the note above.
    "UNKNOWN": "Other",
}

# Ethnicity has its own UNKNOWN permissible value in BDC-HM, deliberately left
# unmapped: the reference's ethnicity vocabulary is HL / notHL / both with no
# "Other" bucket, so there is nothing to align it to and inventing one would
# manufacture agreement. No cohort emitted it in the 2026-09-10 run.
OMOP_ETHNICITY_MAP = {
    "OMOP:38003563": "Hispanic or Latino",
    "OMOP:38003564": "Not Hispanic or Latino",
    "38003563": "Hispanic or Latino",
    "38003564": "Not Hispanic or Latino",
    "HISPANIC_OR_LATINO": "Hispanic or Latino",
    "NOT_HISPANIC_OR_LATINO": "Not Hispanic or Latino",
}

# ─────────────────────────────────────────────────────────────────────────────
# BDC observation_type → TOPMed variable mapping
# Maps OBA/OMOP codes used in MeasurementObservation.tsv to the equivalent
# TOPMed DCC variable names defined in topmed_compare_config.py
# ─────────────────────────────────────────────────────────────────────────────
BDC_MEASUREMENT_MAP: dict[str, dict] = {
    # ── Baseline Covariates ──────────────────────────────────────────────────
    "OBA:VT0001253": {
        "topmed_var": "height_baseline_1",
        "bdc_label": "Height",
        "var_type": "continuous",
        "unit": "cm",
        "plausible_lo": 120.0,
        "plausible_hi": 220.0,
        # MESA bdy_hgt.yaml uses OMOP:607590 (SNOMED 1153637007, body height).
        "aliases": ["OMOP:607590"],
    },
    "OBA:VT0001259": {
        "topmed_var": "weight_baseline_1",
        "bdc_label": "Body weight",
        "var_type": "continuous",
        "unit": "kg",
        "plausible_lo": 25.0,
        "plausible_hi": 300.0,
        # MESA bdy_wgt.yaml uses OMOP:4099154 (SNOMED 27113001, body weight).
        "aliases": ["OMOP:4099154"],
        # MESA bdy_wgt.yaml includes recalled weight at age 20/40 alongside current
        # measured weight. All blocks share the same observation_type. Filter to
        # "Current measured" for DCC comparison so recalled weights don't pull the
        # mean down (~71 kg vs TOPMed 79.5 kg).
        "preferred_method": "Current measured",
        # CARDIA bdy_wgt.yaml has multi-exam blocks; Year 10 blocks with active
        # age_at_observation win the sort, biasing weight upward (+5.3 kg).
        # Filter to "Year 0" baseline weight.
        "preferred_method_override": {"CARDIA": "Year 0"},
    },
    "OBA:2045455": {
        "topmed_var": "bmi_baseline_1",
        "bdc_label": "BMI",
        "var_type": "continuous",
        "unit": "kg/m2",
        "plausible_lo": 14.0,
        "plausible_hi": 70.0,
        # MESA bmi.yaml uses OMOP:3038553 (LOINC 39156-5, BMI).
        "aliases": ["OMOP:3038553"],
    },
    # ── Blood Pressure ───────────────────────────────────────────────────────
    "OMOP:4152194": {
        "topmed_var": "bp_systolic_1",
        "bdc_label": "Systolic blood pressure",
        "var_type": "continuous",
        "unit": "mmHg",
        "plausible_lo": 60.0,
        "plausible_hi": 260.0,
        "preferred_method": "Analysis derived",
        # ARIC bp_systolic.yaml has 48 blocks spanning 6 visit labels and 10+ method
        # types — none use "Analysis derived". Without an override, the method filter
        # silently falls through and the extractor mixes supine ABI readings (pht004041
        # Dinamap supine, pht004027/28/29/6414 ABI, pht004079 echocardiogram context)
        # with seated clinical BP, inflating the mean by ~12 mmHg (+12.45 in testing).
        # TOPMed DCC used pht004192 SBPA21 (phv00210290) — the ARIC-team pre-computed
        # zero-corrected average of seated readings 2 and 3. This maps to method_type
        # "Seated random-zero average" in our YAML. See bp_systolic_1.json in the
        # UW-GAC/topmed-dcc-harmonized-phenotypes repo, ARIC harmonization unit.
        #
        # JHS bp_systolic.yaml has analysis-derived blocks from the Omron automated
        # device (pht008729/8730/8731) which reads systematically higher than the
        # sphygmomanometer used by TOPMed. TOPMed used pht001974 SBPA19 (phv00128376),
        # the seated sphygmomanometer net average. This matches the JHS DBP override
        # below — both BP components should use the same instrument (sphygmomanometer).
        "preferred_method_override": {"ARIC": "Seated random-zero average", "JHS": "Sphygmomanometer average"},
        # What the reference pipeline used, so a report reader can confirm the
        # two sides measured the same thing. Transcribed from the comments
        # above; absent for any cohort where it was never documented.
        "reference_method": {
            "ARIC": "pht004192 SBPA21 (phv00210290) -- ARIC-team pre-computed "
                    "zero-corrected average of seated readings 2 and 3",
            "JHS": "pht001974 SBPA19 (phv00128376) -- seated sphygmomanometer "
                   "net average",
        },
    },
    "OMOP:4154790": {
        "topmed_var": "bp_diastolic_1",
        "bdc_label": "Diastolic blood pressure",
        "var_type": "continuous",
        "unit": "mmHg",
        "plausible_lo": 30.0,
        "plausible_hi": 160.0,
        "preferred_method": "Analysis derived",
        # JHS analysis-derived DBP blocks source from the Omron automated device
        # (pht008729/8730/8731), which reads ~3 mmHg lower than sphygmomanometer.
        # TOPMed used pht001974 SBPA20 (random-zero sphygmomanometer).  Use the
        # sphygmomanometer average for JHS to match the cross-cohort device standard.
        # Full domain science discussion deferred; see CHANGELOG.md session 6.
        # Same ARIC fallthrough issue as SBP (see OMOP:4152194 above). ARIC DBP
        # preferred source is pht004192 SBPA22 (phv00210291), method_type
        # "Seated random-zero average". Without the override, 7.1% BDC missing vs
        # 0.8% TOPMed and +1.7 mmHg mean elevation from mixed positional readings.
        "preferred_method_override": {"JHS": "Sphygmomanometer average", "ARIC": "Seated random-zero average"},
        # See the note on reference_method for bp_systolic_1.
        "reference_method": {
            "ARIC": "pht004192 SBPA22 (phv00210291) -- seated random-zero average",
            "JHS": "pht001974 SBPA20 -- random-zero sphygmomanometer",
        },
    },
    # ── Lipids ───────────────────────────────────────────────────────────────
    "OBA:VT0000184": {
        "topmed_var": "hdl_1",
        "bdc_label": "HDL",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 5.0,
        "plausible_hi": 200.0,
        "preferred_method": "Analysis derived",
        # MESA (and potentially other cohorts) split HDL into fasting vs
        # non-fasting observation_type codes via case() on fasting hours.
        # OMOP:4041720 = fasting HDL; both codes represent the same measurement.
        "aliases": ["OMOP:4041720"],
    },
    # NOTE — EXTRACTOR MAP BUG (discovered 2026-04-01):
    # This entry was originally keyed as OBA:VT0001815, which is NOT the CURIE
    # used by any HV YAML file. All 8 cohorts (ARIC, CARDIA, CHS, FHS, HCHS,
    # JHS, MESA, WHI) consistently use OBA:VT0000181 for LDL in their
    # ldl.yaml observation_type. OBA:VT0001815 was dead — it never matched
    # any pipeline output. This is a bug in this comparison map, NOT a problem
    # with the YAML data or the production pipeline.
    #
    # The correct primary key is OBA:VT0000181. OBA:VT0001815 is retained as
    # the map key (not changed) to avoid disrupting any external tooling that
    # might reference it, but OBA:VT0000181 is added as the first alias so it
    # will match actual pipeline output.
    #
    # OMOP:4041721 = fasting LDL (FHS/MESA ldl.yaml case() branches).
    # OMOP:4042061 = non-fasting LDL (FHS/MESA ldl.yaml case() branches).
    # These are correct YAML CURIEs — aliases here so this map recognizes them.
    "OBA:VT0001815": {
        "topmed_var": "ldl_1",
        "bdc_label": "LDL",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 10.0,
        "plausible_hi": 400.0,
        "aliases": ["OBA:VT0000181", "OMOP:4041721", "OMOP:4042061"],
    },
    "OBA:VT0000180": {
        "topmed_var": "total_cholesterol_1",
        "bdc_label": "Total cholesterol",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 50.0,
        "plausible_hi": 600.0,
    },
    "OBA:VT0002644": {
        "topmed_var": "triglycerides_1",
        "bdc_label": "Triglycerides",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 10.0,
        "plausible_hi": 2000.0,
        # MESA splits triglycerides into fasting vs non-fasting codes.
        # OMOP:4041722 = fasting triglycerides.
        "aliases": ["OMOP:4041722"],
        # CARDIA triglyc_bld.yaml has multi-exam blocks with no age; Year 10
        # block appears first in file and wins the tie-breaker (+17.8 mg/dL
        # delta). Filter to "Year 0" baseline triglycerides.
        "preferred_method_override": {"CARDIA": "Year 0"},
    },
    # ── CBC ───────────────────────────────────────────────────────────────────
    "OBA:2045381": {
        "topmed_var": "hematocrit_vfr_bld_1",
        "bdc_label": "Hematocrit",
        "var_type": "continuous",
        "unit": "%",
        "plausible_lo": 15.0,
        "plausible_hi": 65.0,
        # MESA hemat.yaml uses OMOP:4151358 (SNOMED 28317006, hematocrit).
        "aliases": ["OMOP:4151358"],
    },
    "OBA:2060175": {
        "topmed_var": "hemoglobin_mcnc_bld_1",
        "bdc_label": "Hemoglobin",
        "var_type": "continuous",
        "unit": "g/dL",
        "plausible_lo": 4.0,
        "plausible_hi": 22.0,
        # MESA hemo.yaml uses OMOP:4094758 (SNOMED 441655000, hemoglobin).
        "aliases": ["OMOP:4094758"],
    },
    "OMOP:4267147": {
        "topmed_var": "platelet_ncnc_bld_1",
        "bdc_label": "Platelet count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 10.0,
        "plausible_hi": 1000.0,
    },
    "OBA:VT0000217": {
        "topmed_var": "wbc_ncnc_bld_1",
        "bdc_label": "White blood cell count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 1.0,
        "plausible_hi": 50.0,
    },
    "OBA:VT0002607": {
        "topmed_var": "basophil_ncnc_bld_1",
        "bdc_label": "Basophils count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 0.0,
        "plausible_hi": 5.0,
        # MESA basophil_ncnc_bld.yaml uses OMOP:3006315 (LOINC 704-7, basophils).
        "aliases": ["OMOP:3006315"],
    },
    "OMOP:37208634": {
        "topmed_var": "eosinophil_ncnc_bld_1",
        "bdc_label": "Eosinophils count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 0.0,
        "plausible_hi": 15.0,
        # MESA eosinophil_ncnc_bld.yaml uses OMOP:3013115 (LOINC 711-2, eosinophils).
        "aliases": ["OMOP:3013115"],
    },
    "OBA:VT0000223": {
        "topmed_var": "monocyte_ncnc_bld_1",
        "bdc_label": "Monocytes count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 0.0,
        "plausible_hi": 10.0,
    },
    "OBA:2045301": {
        "topmed_var": "mch_entmass_rbc_1",
        "bdc_label": "MCH",
        "var_type": "continuous",
        "unit": "pg",
        "plausible_lo": 15.0,
        "plausible_hi": 50.0,
        # MESA mch.yaml uses OMOP:37398674 (LOINC 28539-5, MCH).
        "aliases": ["OMOP:37398674"],
        # ARIC never conducted CBC labs at Exams 1 or 2; the earliest MCH data
        # is at Exam 3. Use earliest-per-participant across Exams 3/4/5, matching
        # the TOPMed DCC's own "first available" convention for this variable.
        "visit_override": {"ARIC": ["ARIC EXAM 3", "ARIC EXAM 4", "ARIC EXAM 5"]},
    },
    "OMOP:37393850": {
        "topmed_var": "mchc_mcnc_rbc_1",
        "bdc_label": "MCHC",
        "var_type": "continuous",
        "unit": "g/dL",
        "plausible_lo": 25.0,
        "plausible_hi": 42.0,
    },
    "OBA:0003460": {
        "topmed_var": "mcv_entvol_rbc_1",
        "bdc_label": "MCV",
        "var_type": "continuous",
        "unit": "fL",
        "plausible_lo": 50.0,
        "plausible_hi": 130.0,
    },
    "OBA:VT0001586": {
        "topmed_var": "rbc_ncnc_bld_1",
        "bdc_label": "Red blood cell count",
        "var_type": "continuous",
        "unit": "10^6/uL",
        "plausible_lo": 1.0,
        "plausible_hi": 10.0,
        # MESA rdbld_ct.yaml uses OMOP:4030871 (SNOMED 14089001, RBC count).
        "aliases": ["OMOP:4030871"],
    },
    "OMOP:37397924": {
        "topmed_var": "rdw_ratio_rbc_1",
        "bdc_label": "Red cell distribution width",
        "var_type": "continuous",
        "unit": "%",
        "plausible_lo": 10.0,
        "plausible_hi": 30.0,
    },
    # ── Inflammation ─────────────────────────────────────────────────────────
    "OBA:0000061": {
        "topmed_var": "fibrinogen_1",
        "bdc_label": "Fibrinogen",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 50.0,
        "plausible_hi": 1000.0,
    },
    "OMOP:4208414": {
        "topmed_var": "crp_1",
        "bdc_label": "CRP",
        "var_type": "continuous",
        "unit": "mg/L",
        "plausible_lo": 0.0,
        "plausible_hi": 200.0,
    },
    # ── Other labs ───────────────────────────────────────────────────────────
    "OBA:VT0000188": {
        "topmed_var": "fasting_glucose_1",
        "bdc_label": "Fasting glucose",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 20.0,
        "plausible_hi": 600.0,
    },
    "OMOP:4156660": {
        "topmed_var": "fasting_glucose_1",
        "bdc_label": "Fasting glucose",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 20.0,
        "plausible_hi": 600.0,
    },
    "OBA:2050096": {
        "topmed_var": "serum_creatinine_1",
        "bdc_label": "Serum creatinine",
        "var_type": "continuous",
        "unit": "mg/dL",
        "plausible_lo": 0.1,
        "plausible_hi": 20.0,
    },
    # NOTE — INCOMPLETE MAP (entries added 2026-04-01):
    # The three entries below (IL-6, ICAM-1, sleep) were simply missing from
    # this map — the HV YAML files and the production pipeline use these CURIEs
    # correctly. The YAMLs are NOT wrong. This map was incomplete, so the
    # comparison script showed these variables as "TOPMed-only" when in fact
    # BDC was producing them under their correct ontology codes.
    # Adding them here makes the comparison script aware of them so it can
    # match and grade them. No change to any YAML or pipeline behavior.
    # ── Inflammation (additional) ─────────────────────────────────────────────
    "OBA:2052890": {
        "topmed_var": "il6_1",
        "bdc_label": "Interleukin 6",
        "var_type": "continuous",
        "unit": "pg/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 500.0,
    },
    "OMOP:4284103": {
        "topmed_var": "icam1_1",
        "bdc_label": "ICAM1",
        "var_type": "continuous",
        "unit": "ng/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 2000.0,
    },
    # ── Sleep ─────────────────────────────────────────────────────────────────
    "OBA:2040171": {
        "topmed_var": "sleep_duration_1",
        "bdc_label": "Sleep hours",
        "var_type": "continuous",
        "unit": "hours",
        "plausible_lo": 0.0,
        "plausible_hi": 24.0,
    },
    # ── CBC differential (entries added 2026-04-01) ───────────────────────────
    # MESA lympho_ct.yaml (OMOP:37208689) and neutro_ct.yaml (OMOP:37208699)
    # were simply missing from this map.
    "OMOP:37208689": {
        "topmed_var": "lymphocyte_ncnc_bld_1",
        "bdc_label": "Lymphocytes count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 0.0,
        "plausible_hi": 20.0,
    },
    "OMOP:37208699": {
        "topmed_var": "neutrophil_ncnc_bld_1",
        "bdc_label": "Neutrophils count",
        "var_type": "continuous",
        "unit": "10^3/uL",
        "plausible_lo": 0.0,
        "plausible_hi": 30.0,
    },
    # ── Inflammation / biomarkers (entries added 2026-04-01) ──────────────────
    # MESA eselectin.yaml, tnfa.yaml, tnfa_r1.yaml use OBA codes; missing from map.
    "OBA:2052778": {
        "topmed_var": "eselectin_1",
        "bdc_label": "E-selectin",
        "var_type": "continuous",
        "unit": "ng/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 500.0,
    },
    "OBA:2051979": {
        "topmed_var": "tnfa_1",
        "bdc_label": "TNFa",
        "var_type": "continuous",
        "unit": "pg/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 500.0,
    },
    "OBA:2051975": {
        "topmed_var": "tnfa_r1_1",
        "bdc_label": "TNFa-R1",
        "var_type": "continuous",
        "unit": "pg/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 5000.0,
    },
    # MESA lppla2_act.yaml and lppla2_mass.yaml use OMOP codes; missing from map.
    "OMOP:36305170": {
        "topmed_var": "lppla2_act_1",
        "bdc_label": "LP-PLA2 activity",
        "var_type": "continuous",
        "unit": "nmol/min/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 500.0,
    },
    "OMOP:3041450": {
        "topmed_var": "lppla2_mass_1",
        "bdc_label": "LP-PLA2 mass",
        "var_type": "continuous",
        "unit": "ng/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 1000.0,
    },
    "OMOP:4209737": {
        "topmed_var": "cd40_1",
        "bdc_label": "CD40",
        "var_type": "continuous",
        "unit": "ng/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 50.0,
    },
    "OMOP:40761106": {
        "topmed_var": "mmp9_1",
        "bdc_label": "MMP9",
        "var_type": "continuous",
        "unit": "ng/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 2000.0,
    },
    "OMOP:3004578": {
        "topmed_var": "il10_1",
        "bdc_label": "Interleukin 10",
        "var_type": "continuous",
        "unit": "pg/mL",
        "plausible_lo": 0.0,
        "plausible_hi": 500.0,
    },
    # ── Imaging (entries added 2026-04-01) ────────────────────────────────────
    # MESA carotid_imt.yaml uses OMOP:4138462 for both Exam 1 (Classic) and
    # Air Exam 5 blocks. TOPMed exposes two variants (cimt_1 = Mean of mean
    # far wall IMT; cimt_2 = Mean of max far wall IMT). BDC cannot distinguish
    # the two variants because MESA uses the same observation_type code for
    # both measurement methods. We map to cimt_1 (the more commonly reported
    # variant); cimt_2 will remain TOPMed-only.
    "OMOP:4138462": {
        "topmed_var": "cimt_1",
        "bdc_label": "Carotid IMT (variant 1)",
        "var_type": "continuous",
        "unit": "mm",
        "plausible_lo": 0.3,
        "plausible_hi": 3.0,
    },
    # MESA carotid_sten_left.yaml and carotid_sten_right.yaml each measure
    # carotid stenosis (left vs right side). TOPMed merges into one binary
    # variable (carotid_stenosis_1). We treat both side-codes as aliases here.
    # var_type is categorical: YAML uses value_concept to store coded scale
    # (value_mappings: '1':'1-24', '2':'25-49', ..., '6':'0', '7':None).
    # TOPMed uses integer grade 0-5. Label mismatch is expected.
    "OMOP:43020498": {
        "topmed_var": "carotid_stenosis_1",
        "bdc_label": "Carotid stenosis",
        "var_type": "categorical",
        # OMOP:43021859 = carotid stenosis right side
        "aliases": ["OMOP:43021859"],
    },
    # MESA cac_score.yaml and cac_volume.yaml; previously missing from map.
    "OMOP:42872742": {
        "topmed_var": "cac_score_1",
        "bdc_label": "CAC Score",
        "var_type": "continuous",
        "unit": "Agatston",
        "plausible_lo": 0.0,
        "plausible_hi": 10000.0,
    },
    "OMOP:4166120": {
        "topmed_var": "cac_volume_1",
        "bdc_label": "CAC volume",
        "var_type": "continuous",
        "unit": "mm3",
        "plausible_lo": 0.0,
        "plausible_hi": 10000.0,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# BDC Condition concept → TOPMed variable mapping
# Maps MONDO/HP codes used in Condition.tsv to TOPMed DCC comparison variables
# TOPMed uses binary prior/incident status; BDC uses condition_concept codes
# ─────────────────────────────────────────────────────────────────────────────
BDC_CONDITION_MAP: dict[str, dict] = {
    # Prior conditions (compare with atherosclerosis_events_prior)
    "HP:0001681": {
        "topmed_var": "angina_prior_1",
        "bdc_label": "Angina",
        "category_label": "Prior History",
    },
    "MONDO:0005068": {
        "topmed_var": "mi_prior_1",
        "bdc_label": "History of MI",
        "category_label": "Prior History",
    },
    "MONDO:0005386": {
        "topmed_var": "pad_prior_1",
        "bdc_label": "PAD",
        "category_label": "Prior History",
    },
    # Alias: COPDGene uses MONDO:0005294 (peripheral vascular disease) for PAD
    "MONDO:0005294": {
        "topmed_var": "pad_prior_1",
        "bdc_label": "PAD",
        "category_label": "Prior History",
    },
    # CABG — MESA hist_cor_bypg.yaml maps as Condition (condition_concept:
    # OMOP:4336464), so records go to Condition.tsv, not Procedure.tsv.
    # Also present in BDC_PROCEDURE_MAP for cohorts that use Procedure entity.
    "OMOP:4336464": {
        "topmed_var": "cabg_prior_1",
        "bdc_label": "CABG",
        "category_label": "Prior History",
    },
    # Coronary angioplasty — MESA uses Condition entity for this as well.
    "OMOP:4184832": {
        "topmed_var": "coronary_angioplasty_prior_1",
        "bdc_label": "Coronary angioplasty",
        "category_label": "Prior History",
    },
    # Carotid plaque — MESA carotid_plaque.yaml maps as Condition entity.
    # OMOP:4102124 = carotid calcification / carotid plaque on imaging.
    "OMOP:4102124": {
        "topmed_var": "carotid_plaque_1",
        "bdc_label": "Carotid plaque",
        "category_label": "Prior History",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# BDC Procedure concept → TOPMed variable mapping
# ─────────────────────────────────────────────────────────────────────────────
BDC_PROCEDURE_MAP: dict[str, dict] = {
    "OMOP:4336464": {
        "topmed_var": "cabg_prior_1",
        "bdc_label": "CABG",
        "category_label": "Prior History",
    },
    "OMOP:4184832": {
        "topmed_var": "coronary_angioplasty_prior_1",
        "bdc_label": "Coronary angioplasty",
        "category_label": "Prior History",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# BDC Smoking observation → TOPMed variable mapping
# ─────────────────────────────────────────────────────────────────────────────
SMOKING_OBSERVATION_TYPE = "OMOP:4282779"

# OMOP coded values for smoking → TOPMed-compatible labels
# All codes verified against Athena (https://athena.ohdsi.org) on 2026-03-23.
# WARNING: OMOP concept IDs ≠ SNOMED codes. Always verify on Athena directly.
OMOP_SMOKING_MAP = {
    # Current smoker values
    "OMOP:40766945": "Current Smoker",     # Athena: "Current smoker" (LOINC 64234-8)
    "40766945": "Current Smoker",
    # Former smoker values
    "OMOP:45883458": "Former Smoker",      # Athena: "Former smoker" (LOINC LA15920-4)
    "45883458": "Former Smoker",
    # Never smoker values
    "OMOP:45883537": "Never Smoked",       # Athena: "Never smoker" (LOINC LA14458-6)
    "45883537": "Never Smoked",
    # Unknown
    "OMOP:45885135": "Unknown",            # Athena: "Unknown if ever smoked" (LOINC LA18980-5)
    "45885135": "Unknown",
    # NOTE: OMOP:45883459 = "11-20 (1 point)" Fagerström Test answer — NOT a smoking status.
    # NOTE: OMOP:40766929 = "How many cigarettes per day" — NOT a smoking status.
    #       HCHS cig_smok.yaml uses 40766929 for TBEA3==2 ("Some days") which is incorrect.
    #       That HV bug should be fixed separately; values with this code will show as UNMAPPED.
}

# ─────────────────────────────────────────────────────────────────────────────
# BASELINE VISIT CONFIGURATION (per-cohort)
# ─────────────────────────────────────────────────────────────────────────────
# Each cohort has DIFFERENT visit naming conventions in its visit.yaml. This
# table encodes the correct baseline visit labels for each cohort, verified
# against the actual visit.yaml `id: value:` strings as of 2026-03-31.
#
# HOW MATCHING WORKS (see resolve_baseline_visits()):
#   1. Case-insensitive exact match against "exact" list → preferred
#   2. Regex "pattern" match against all available visits → fallback
#   3. If neither matches → WARNING logged, falls through to all-visits
#
# WHY THIS EXISTS:
#   The TOPMed DCC reference measures baseline/pre-enrollment data only (the
#   "_1" suffix variables). Our BDC extraction must filter to baseline visits
#   before computing prevalence comparisons. Without correct per-cohort
#   baseline labels, the filter falls through to all-visits and we overcount
#   conditions that have longitudinal/incident-event blocks.
#
# HOW TO UPDATE:
#   When a cohort's visit.yaml labels change, update the "exact" list here.
#   Run the extraction with --cohort <name> and check for the diagnostic:
#     "[baseline filter] WARNING: No baseline visit match for <COHORT>"
#   If that fires, the exact list needs updating. The regex pattern is a
#   safety net and should catch most reasonable label variations.
#
# Keys MUST be UPPERCASE — cohort arg is uppercased at entry (line ~1526).
BASELINE_VISIT_CONFIG: dict[str, dict] = {
    "ARIC": {
        # visit.yaml labels: ARIC EXAM 1 through EXAM 7, plus ARIC AFQ, Cohort, etc.
        # Baseline is Exam 1 (1987-89). Old config had "ARIC Visit 1" which never matched.
        "exact": ["ARIC EXAM 1"],
        "pattern": r"(?i)ARIC\s+(EXAM|VISIT)\s+1$",
    },
    "CARDIA": {
        # visit.yaml labels: CARDIA YEAR 0, CARDIA YEAR 2, etc.
        # Year 0 = baseline (1985-86). "CARDIA EXAM 0" was a YAML authoring error;
        # corrected in fix/cardia-chr-20260330 — all YAML files now use YEAR 0 only.
        "exact": ["CARDIA YEAR 0"],
        "pattern": r"(?i)CARDIA\s+YEAR\s+0$",
    },
    "CHS": {
        # visit.yaml labels: CHS BASELINE, CHS BASELINE 2, CHS BASELINE BOTH, CHS YEAR 3-11, etc.
        # CHS has 3 "baseline" visits for different sub-populations:
        #   - CHS BASELINE (pht001449): original cohort only
        #   - CHS BASELINE 2 (pht001450/1451): new cohort enrolled later
        #   - CHS BASELINE BOTH (pht001452): combined measures for both sub-cohorts
        # Old config had "CHS Baseline" (wrong case, missing BASELINE 2/BOTH).
        "exact": ["CHS BASELINE", "CHS BASELINE 2", "CHS BASELINE BOTH"],
        "pattern": r"(?i)CHS\s+BASELINE",
    },
    "COPDGENE": {
        # visit.yaml labels: COPDGene P1, P2, P3, P3B
        # Phase 1 (P1) is baseline enrollment. "Phase 1" label doesn't exist in YAML.
        "exact": ["COPDGene P1"],
        "pattern": r"(?i)COPDGene\s+(P1|Phase\s*1)$",
    },
    "FHS": {
        # visit.yaml labels: FHS ORIGINAL EXAM 1-17, FHS OFFSPRING EXAM 1-10,
        #   FHS GENERATION 3 EXAM 1-9, FHS OMNI 1 EXAM 1-10, FHS OMNI 2 EXAM 1-3,
        #   FHS NEW OFFSPRING SPOUSE EXAM 1-3
        # Multi-generational: each sub-cohort has its own exam as baseline.
        # FHS Original uses Exam 4 (not Exam 1) because antihypertensive medication
        # was not recorded before Exam 4. This matches the TOPMed DCC decision
        # documented in bp_systolic_1.json and bp_diastolic_1.json.
        # All other sub-cohorts use their Exam 1 as baseline.
        # Note: "FHS GEN3 EXAM 1" abbreviation does NOT exist — full name is
        # "FHS GENERATION 3 EXAM 1". Pattern catches both as safety net.
        "exact": [
            "FHS ORIGINAL EXAM 4", "FHS OFFSPRING EXAM 1",
            "FHS GENERATION 3 EXAM 1", "FHS OMNI 1 EXAM 1",
            "FHS OMNI 2 EXAM 1", "FHS NEW OFFSPRING SPOUSE EXAM 1",
        ],
        # Pattern excludes ORIGINAL (handled explicitly above as Exam 4) and
        # excludes any visit containing SHHS (safety net from prior sessions).
        "pattern": r"(?i)FHS\s+(?!ORIGINAL)(?!.+SHHS).+\s+EXAM\s+1$",
    },
    "HCHS_SOL": {
        # visit.yaml label: HCHS EXAM (single cross-sectional exam)
        "exact": ["HCHS EXAM"],
        "pattern": r"(?i)HCHS\s+EXAM$",
    },
    "JHS": {
        # visit.yaml labels: JHS Exam 1, JHS Exam 2, JHS Exam 3, JHS AFU, etc.
        # Exam 1 = baseline (2000-04). Old config had "JHS Visit 1" which never matched.
        # NOTE: JHS uses mixed case "Exam" not "EXAM" — case-insensitive match handles this.
        "exact": ["JHS Exam 1"],
        "pattern": r"(?i)JHS\s+(Exam|Visit)\s+1$",
    },
    "MESA": {
        # visit.yaml labels: MESA CLASSIC EXAM 1-4, MESA AIR EXAM, MESA AIR EXAM 5,
        #   MESA LUNG SPIROMETRY, MESA FAMILY, MESA FAMILY SPIROMETRY, MESA LUNG CT
        # DCC row-binds 3 subcohort Exam 1 tables as baseline:
        #   - pht001116 (Classic Exam 1)  -> "MESA CLASSIC EXAM 1"
        #   - pht001111 (Family)          -> "MESA FAMILY"
        #   - pht001121 (AirNR)           -> "MESA AIR EXAM"
        # Old config had "MESA Exam 1" which never matched any of these.
        "exact": ["MESA CLASSIC EXAM 1", "MESA FAMILY", "MESA AIR EXAM"],
        "pattern": r"(?i)MESA\s+(CLASSIC\s+EXAM\s+1|FAMILY|AIR\s+EXAM)$",
    },
    "SPIROMICS": {
        # visit.yaml labels: SPIROMICS Visit 1-4
        # Visit 1 = baseline enrollment.
        "exact": ["SPIROMICS Visit 1"],
        "pattern": r"(?i)SPIROMICS\s+Visit\s+1$",
    },
    "WHI": {
        # visit.yaml labels: WHI SCREENING, WHI YEAR 1-14, WHI EXTENSION, WHI LONG LIFE STUDY
        # Screening visit is the enrollment baseline. Old config included "WHI PM 80",
        # "WHI CORE", "WHI ELIGIBILITY" — those are form/table names, NOT visit labels
        # in the visit.yaml; they never matched.
        "exact": ["WHI SCREENING"],
        "pattern": r"(?i)WHI\s+SCREEN",
    },
}

# ── Cohort name alias maps ───────────────────────────────────────────────────
# Centralized so discovery, directory lookup, and CLI normalization all use the
# same mapping (I-2 fix: previously duplicated in two functions).
#
# _FOLDER_TO_CANONICAL: folder name variants → canonical config key
# _CANONICAL_TO_ALIASES: canonical config key → folder name variants to try
COHORT_FOLDER_TO_CANONICAL: dict[str, str] = {
    "HCHS": "HCHS_SOL",
}
COHORT_CANONICAL_TO_ALIASES: dict[str, list[str]] = {}
for _alias, _canon in COHORT_FOLDER_TO_CANONICAL.items():
    COHORT_CANONICAL_TO_ALIASES.setdefault(_canon, []).append(_alias)


def normalize_cohort_name(name: str) -> str:
    """Normalize a cohort name to its canonical config key.

    E.g., 'HCHS' -> 'HCHS_SOL', 'aric' -> 'ARIC', 'copdgene' -> 'COPDGene'.
    """
    upper = name.upper()
    # Check alias map first (e.g., HCHS -> HCHS_SOL)
    if upper in COHORT_FOLDER_TO_CANONICAL:
        return COHORT_FOLDER_TO_CANONICAL[upper]
    # Case-insensitive lookup against canonical COHORTS keys to preserve casing
    cohort_key_map = {k.upper(): k for k in COHORTS}
    return cohort_key_map.get(upper, upper)


def cohort_lookup(mapping: dict, cohort: str, default=None):
    """Case-insensitive cohort-keyed lookup.

    The cohort-keyed dicts in this file do not agree on capitalisation --
    COHORTS uses "COPDGene" while BASELINE_VISIT_CONFIG and
    BASELINE_VISIT_PREFS use "COPDGENE". Whichever spelling flows in from a
    directory name, one of the two lookups used to miss silently: an uppercased
    name lost the COHORTS metadata, and the exact config key lost the baseline
    visits (which skips every measurement for the cohort). Resolve by name, not
    by spelling.
    """
    if cohort in mapping:
        return mapping[cohort]
    want = cohort.upper()
    for key, value in mapping.items():
        if isinstance(key, str) and key.upper() == want:
            return value
    return default


def resolve_baseline_visits(cohort: str, available_visits: set[str]) -> list[str]:
    """Resolve which available visits are baseline for this cohort.

    Uses BASELINE_VISIT_CONFIG for per-cohort matching:
      1. Case-insensitive exact match against "exact" list
      2. Regex "pattern" match as fallback
      3. Returns empty list if no match (caller handles fallback)

    Args:
        cohort: Uppercase cohort name (e.g., "CHS", "ARIC")
        available_visits: Set of visit labels found in the TSV data

    Returns:
        List of matched visit labels (preserving original case from available_visits)
    """
    config = cohort_lookup(BASELINE_VISIT_CONFIG, cohort, {})
    if not config:
        return []

    # Step 1: Case-insensitive exact match
    # Build lookup: upper(available) -> original label
    upper_to_original = {v.upper(): v for v in available_visits}
    exact_prefs = config.get("exact", [])
    matched = []
    for pref in exact_prefs:
        original = upper_to_original.get(pref.upper())
        if original:
            matched.append(original)

    if matched:
        return matched

    # Step 2: Regex pattern fallback
    # Only fires if no exact match — catches label variations like
    # "ARIC Visit 1" vs "ARIC EXAM 1" or future renames.
    pattern = config.get("pattern")
    if pattern:
        for visit in sorted(available_visits):
            if re.search(pattern, visit):
                matched.append(visit)

    if matched:
        print(f"    [baseline] Matched via pattern fallback: {matched}")

    return matched


# Backward-compatible alias for code that still references the old dict.
# Returns the "exact" list from BASELINE_VISIT_CONFIG.
BASELINE_VISIT_PREFS: dict[str, list[str]] = {
    cohort: cfg["exact"] for cohort, cfg in BASELINE_VISIT_CONFIG.items()
}

# ─────────────────────────────────────────────────────────────────────────────
# SMOKING VISIT OVERRIDE (per-cohort)
# ─────────────────────────────────────────────────────────────────────────────
# Some cohorts collect smoking status at a different visit than the primary
# baseline defined in BASELINE_VISIT_CONFIG. FHS Original uses Exam 4 as
# general baseline (for medication data), but smoking (MF71, phv00000543) is
# recorded in pht000009 at Exam 1 with full tripartite coding
# (Current/Former/Never). The pht007777 CURRSMK at Exam 4 is binary only
# (current yes/no) and loses former-vs-never distinction. Using Exam 1 for
# smoking matches the TOPMed DCC approach (FHS_Original current_smoker and
# ever_smoker both use MF71 from pht000009).
SMOKING_VISIT_OVERRIDE: dict[str, list[str]] = {
    "FHS": [
        "FHS ORIGINAL EXAM 1",
        "FHS OFFSPRING EXAM 1",
        "FHS GENERATION 3 EXAM 1",
        "FHS OMNI 1 EXAM 1",
        "FHS OMNI 2 EXAM 1",
        "FHS NEW OFFSPRING SPOUSE EXAM 1",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# PER-VARIABLE VISIT OVERRIDES FOR CONDITIONS AND PROCEDURES
# ─────────────────────────────────────────────────────────────────────────────
# Some condition/procedure variables are only available at later exams, not at
# the BASELINE_VISIT_CONFIG visit.  This dict maps topmed_var -> cohort ->
# list of visit labels to use INSTEAD of the global baseline visits.
#
# CABG: FHS hist_cor_bypg.yaml maps Original Cohort to Exam 21 and Offspring
# to Exam 5 — the earliest exams with CABG questions (surgery wasn't widespread
# before the 1970s).  Earlier exams maximize participant coverage since the
# question is cumulative ("HISTORY OF coronary bypass surgery").
# Without this override, only Gen3 Exam 1 matches the standard baseline config.
CONDITION_PROCEDURE_VISIT_OVERRIDE: dict[str, dict[str, list[str]]] = {
    "cabg_prior_1": {
        "FHS": [
            "FHS ORIGINAL EXAM 21",
            "FHS OFFSPRING EXAM 5",
            "FHS GENERATION 3 EXAM 1",
            "FHS OMNI 1 EXAM 1",
            "FHS OMNI 2 EXAM 1",
            "FHS NEW OFFSPRING SPOUSE EXAM 1",
        ],
    },
    # PAD: FHS pad.yaml maps Offspring to Exam 5 (CDI-PVD, pht000034) and adds
    # pht000309 joins block (EVENT=30, IC) for Original cohort.  Offspring Exam 5
    # is not in standard baseline config so needs override.
    "pad_prior_1": {
        "FHS": [
            "FHS ORIGINAL EXAM 4",
            "FHS OFFSPRING EXAM 5",
            "FHS GENERATION 3 EXAM 1",
            "FHS OMNI 1 EXAM 1",
            "FHS OMNI 2 EXAM 1",
            "FHS NEW OFFSPRING SPOUSE EXAM 1",
        ],
    },
}


# =============================================================================
# PART 3 -- dm-bip OUTPUT LAYOUT DISCOVERY
# =============================================================================
# dm-bip has emitted two different output layouts. Both are supported so a
# comparison can be run against an older extract without reorganising it.
#
# CURRENT (seen 2026-08-31 "FinalAlignmentTest" onward) -- the run directory is
# named for the cohort alone, and consent groups are nested one level deeper
# under a consent_groups/ directory:
#
#   <base>/DMC_<COHORT>_<YYYYMMDD>_<HHMMSS>/
#       consent_groups/
#           <consent-group>/
#               <consent-group>_BDCHM/
#                   mapped-data/*.tsv
#
#   e.g. DMC_ARIC_20260831_202820/consent_groups/
#            nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1/
#            nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1_BDCHM/mapped-data
#
# LEGACY -- one run directory per consent group, cohort embedded mid-name, and
# a literal "_Processed_" segment:
#
#   <base>/DMC_<consent-group>_<COHORT>_Processed_<timestamp>/
#       <consent-group>_BDCHM/
#           mapped-data/*.tsv
#
# Consent-group directory naming is NOT consistent across cohorts -- compare
# "nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1" against
# "parent-CHS_DS-CVD-MDS_-phs000287-v7-p1-c3" and "copdgene_phs000179_v7_r1_c1".
# Nothing here should parse that name beyond pulling out the accession; treat it
# as an opaque label.
# =============================================================================

# Run dir named for the cohort alone, with a date_time suffix.
_DMC_RUN_CURRENT = re.compile(r"^DMC_(?P<cohort>.+?)_\d{8}_\d{6}$", re.IGNORECASE)

# Legacy run dir: cohort sits immediately before the "_Processed_" marker.
_DMC_RUN_LEGACY = re.compile(
    r"^DMC_.*?(?:^|[-_])(?P<cohort>[A-Za-z][A-Za-z0-9]*)_Processed_\d+",
    re.IGNORECASE,
)


def _cohort_aliases(cohort: str) -> list[str]:
    """Canonical cohort name plus any directory aliases (HCHS_SOL -> HCHS)."""
    up = cohort.upper()
    return [cohort] + [a for a in COHORT_CANONICAL_TO_ALIASES.get(up, []) if a.upper() != up]


def cohort_from_dmc_dir_name(name: str) -> str | None:
    """Recover the cohort from a dm-bip run directory name, or None.

    Returns the canonical config key where the folder uses a known alias
    (DMC_HCHS_... -> HCHS_SOL).
    """
    # Legacy first: it requires the literal "_Processed_" marker, so it is the
    # more specific of the two. Legacy names also end in _<date>_<time>
    # (DMC_..._WHI_Processed_20260322_141514), which the current-layout pattern
    # would otherwise match, swallowing "..._WHI_Processed" as the cohort.
    for pattern in (_DMC_RUN_LEGACY, _DMC_RUN_CURRENT):
        m = pattern.match(name)
        if m:
            raw = m.group("cohort").upper()
            canon = COHORT_FOLDER_TO_CANONICAL.get(raw, raw)
            # Return the exact COHORTS key so metadata lookups resolve --
            # the folder says COPDGene/copdgene, the key is "COPDGene", and
            # an uppercased "COPDGENE" silently misses COHORTS.get().
            for key in COHORTS:
                if key.upper() == canon.upper():
                    return key
            return canon
    return None


def _phs_to_cohort() -> dict:
    """phs accession -> canonical cohort key."""
    return {meta["phs"].lower(): name for name, meta in COHORTS.items() if meta.get("phs")}


def looks_like_run_dir(path) -> bool:
    """True if this directory IS a dm-bip run directory.

    Recognised either by name or by structure, so a run directory that has been
    renamed or copied still resolves. Structure is the reliable signal: a run
    directory holds consent_groups/ (current layout) or *_BDCHM/ (legacy).
    """
    try:
        if not path.is_dir():
            # A name-only match on a path that does not exist would be reported
            # as "run directory with no output" instead of "bad path".
            return False
        if cohort_from_dmc_dir_name(path.name):
            return True
        if (path / "consent_groups").is_dir():
            return True
        return any(path.glob("*_BDCHM"))
    except OSError:
        return False


def cohort_for_run_dir(path) -> str | None:
    """Cohort owning a run directory, from its name or its contents.

    Falls back to the phs accession embedded in the consent-group directory
    names, so a renamed run directory still identifies itself.
    """
    named = cohort_from_dmc_dir_name(path.name)
    if named:
        return named
    phs_map = _phs_to_cohort()
    try:
        for bdchm in path.rglob("*_BDCHM"):
            haystack = str(bdchm).lower()
            for phs, cohort in phs_map.items():
                if phs in haystack:
                    return cohort
    except OSError:
        pass
    return None


def find_dmc_run_dirs(base_dir, cohort: str | None = None) -> list:
    """Find dm-bip run directories under base_dir.

    With `cohort`, returns only that cohort's runs (case-insensitive, aliases
    included). Without it, returns every run directory found.

    base_dir may be any of three levels, so a path that is "obviously right" to
    a human resolves rather than returning nothing:

      1. a single run directory  .../DMC_ARIC_20260831_202820
      2. the directory holding them  .../20260831_FinalAlignmentTest
      3. one level above that  .../project-files

    Level 1 is the common case when comparing one cohort; level 2 is what the
    wrapper uses to sweep every cohort in a run.
    """
    from pathlib import Path

    base = Path(base_dir)
    wanted = {a.upper() for a in _cohort_aliases(cohort)} if cohort else None

    # base_dir IS a run directory -- the natural thing to pass when working on
    # one cohort. Scanning beneath it would find only consent_groups/ and
    # report "no output found" for a path that plainly has output in it.
    if looks_like_run_dir(base):
        if wanted is None:
            return [base]
        owner = cohort_for_run_dir(base)
        # An unidentifiable run dir is accepted on the caller's say-so:
        # an explicit --cohort outranks a name we could not parse.
        if owner is None or owner.upper() in wanted:
            return [base]
        return []

    def scan(root) -> list:
        hits = []
        try:
            entries = sorted(root.iterdir())
        except OSError:
            return hits
        for entry in entries:
            if not entry.is_dir():
                continue
            found = cohort_from_dmc_dir_name(entry.name)
            if found is None:
                continue
            if wanted is None or found.upper() in wanted:
                hits.append(entry)
        return hits

    dirs = scan(base)
    if dirs:
        return dirs

    # One level down: base_dir points at the parent of a dated run folder.
    nested = []
    try:
        for child in sorted(base.iterdir()):
            if child.is_dir():
                nested.extend(scan(child))
    except OSError:
        pass
    return nested


def find_mapped_data_dirs(base_dir, cohort: str) -> list:
    """Return every mapped-data directory for a cohort, as strings.

    Walks each run directory for *_BDCHM/mapped-data at any depth, which covers
    the consent_groups/ level in the current layout and the flat legacy layout
    with one expression. Falls back to a _BDCHM directory holding TSVs directly
    when mapped-data/ is absent.
    """
    hits = []
    for run_dir in find_dmc_run_dirs(base_dir, cohort):
        for bdchm in sorted(run_dir.rglob("*_BDCHM")):
            if not bdchm.is_dir():
                continue
            mapped = bdchm / "mapped-data"
            if mapped.is_dir():
                hits.append(mapped)
            elif any(bdchm.glob("*.tsv")):
                hits.append(bdchm)
    # Deduplicate while preserving order; rglob can revisit via odd nesting.
    seen = set()
    ordered = []
    for h in hits:
        key = str(h)
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def consent_group_from_path(tsv_path) -> str:
    """Label a TSV with the consent group it came from.

    Uses the nearest *_BDCHM ancestor with the suffix stripped -- that directory
    is named for the consent group in both layouts. Falls back to the
    grandparent directory name when no such ancestor exists.
    """
    from pathlib import Path

    p = Path(tsv_path)
    for parent in p.parents:
        if parent.name.endswith("_BDCHM"):
            return parent.name[: -len("_BDCHM")]
    parts = p.parts
    return parts[-4] if len(parts) >= 4 else p.parent.name


# =============================================================================
# PART 4 -- BDC-HM DATA DICTIONARY (optional label resolver)
# =============================================================================
# The BDC-HM data dictionary export maps every code the pipeline can emit to a
# human label:
#
#   output_table,output_column,code_in_data,label,definition,vocabulary,code_form
#   Condition,condition_concept,MONDO:0005002,chronic obstructive pulmonary disease,...
#
# It is used for DISPLAY ONLY. A concept absent from BDC_MEASUREMENT_MAP and
# friends stays out of the TOPMed comparison whether or not it has a label here
# -- the dictionary says what a code means, not whether it is equivalent to a
# TOPMed variable. That equivalence is a curation judgement and stays in the
# hand-maintained maps above.
#
# Without it, unmapped concepts print as bare CURIEs ("MONDO:0005002"), which is
# what a COPDGene report looked like on 2026-09-10. It is optional: absent, the
# toolkit behaves exactly as before.
# =============================================================================

DATA_DICTIONARY_GLOB = "BDC-HM-*DataDictionary*.csv"

_DATA_DICTIONARY_CACHE: dict | None = None


def find_data_dictionary(explicit: str | None = None):
    """Locate the BDC-HM data dictionary CSV, or None.

    Search order: an explicit path, then the toolkit root and its data/
    subdirectory, newest first when several are present.
    """
    from pathlib import Path

    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None

    here = Path(__file__).resolve().parent
    candidates = []
    for folder in (here, here / "data"):
        try:
            candidates.extend(folder.glob(DATA_DICTIONARY_GLOB))
        except OSError:
            pass
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name, reverse=True)[0]


def load_data_dictionary(explicit: str | None = None, verbose: bool = True) -> dict:
    """Load the dictionary into {(table, column, code): label} plus {code: label}.

    The bare-code fallback exists because a code's meaning does not change with
    the column it lands in; the qualified key wins when both are present, so a
    value_enum and an observation_type sharing a code cannot collide.

    Returns {} when no dictionary is available -- callers fall back to codes.
    """
    import csv

    global _DATA_DICTIONARY_CACHE
    if _DATA_DICTIONARY_CACHE is not None and explicit is None:
        return _DATA_DICTIONARY_CACHE

    path = find_data_dictionary(explicit)
    if path is None:
        if verbose:
            print("    [dictionary] none found - unmapped concepts will print as codes")
        if explicit is None:
            _DATA_DICTIONARY_CACHE = {}
        return {}

    lookup: dict = {}
    try:
        # utf-8-sig: the export carries a BOM.
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("code_in_data") or "").strip()
                label = (row.get("label") or "").strip()
                definition = (row.get("definition") or "").strip()
                # 26 OBA rows in the 2026-08-31 export carry a label that is
                # just the CURIE re-cased ("OBA:VT0001253" -> "Oba:vt0001253")
                # with the real name stranded in definition ("Height"). Prefer
                # the definition's first clause in exactly that case. Narrowly
                # scoped to CURIE codes whose label differs from the code only
                # by case, so permissible value names like ABSENT -> "Absent"
                # keep their perfectly good labels.
                if ":" in code and label.lower() == code.lower() and definition:
                    first_clause = definition.split("|")[0].strip()
                    if first_clause:
                        label = first_clause
                if not code or not label:
                    continue
                table = (row.get("output_table") or "").strip()
                column = (row.get("output_column") or "").strip()
                lookup[(table, column, code)] = label
                lookup.setdefault(code, label)
    except (OSError, csv.Error) as exc:
        print(f"    [dictionary] WARNING: could not read {path}: {exc}", file=__import__("sys").stderr)
        return {}

    if verbose:
        n_codes = sum(1 for k in lookup if isinstance(k, str))
        print(f"    [dictionary] {path.name}: {n_codes:,} codes")
    if explicit is None:
        _DATA_DICTIONARY_CACHE = lookup
    return lookup


def label_for_code(code: str, table: str = "", column: str = "",
                   dictionary: dict | None = None) -> str | None:
    """Human label for a code, or None. Qualified match preferred."""
    if not code:
        return None
    d = load_data_dictionary() if dictionary is None else dictionary
    if not d:
        return None
    return d.get((table, column, code)) or d.get(code)


def display_label(code: str, table: str = "", column: str = "",
                  dictionary: dict | None = None) -> str:
    """Label with the code retained, or the bare code when unknown.

    Keeps the code visible ("chronic obstructive pulmonary disease
    [MONDO:0005002]") so a report stays traceable back to the extract.
    """
    label = label_for_code(code, table, column, dictionary)
    return f"{label} [{code}]" if label else code
