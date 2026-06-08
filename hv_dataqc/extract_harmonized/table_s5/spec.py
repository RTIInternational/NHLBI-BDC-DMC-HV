"""Table S5 row spec — labels, ordering, and alias map.

This module captures the S5 spreadsheet's column-A label set and the row
order it expects, plus aliases for cases where the spreadsheet's label
diverges from ``harmonized_vars.tsv``'s ``var_label`` column (mostly
casing or word-order drift).

The spec is shipped as Python constants rather than a TSV/CSV config so
edits go through code review. If the alias list grows past ~20 entries,
worth moving to a TSV alongside ``harmonized_vars.tsv``.
"""

from __future__ import annotations

# S5 column-A labels whose form doesn't match harmonized_vars.tsv's
# var_label.  Maps S5 spreadsheet form -> harmonized_vars.tsv form.
# When looking up a stat for an S5 label, try the aliased form first,
# then the literal label.  The spreadsheet form is the user-facing one
# we preserve in TABLE_S5_LABELS below.
S5_LABEL_ALIASES: dict[str, str] = {
    "Alcohol Consumption": "Alcohol",
    "Basophils Count": "basophils count",
    "CRP c-reactive protein": "c-reactive protein CRP",
    "Fruit consumption": "Fruits",
    "Mean corpuscular hemoglobin": "mean corpuscular hemoglobin",
    "Mean corpuscular hemoglobin concentration": "mean corpuscular hemoglobin concentration",
    "Mean corpuscular volume": "mean corpuscular volume",
    "Mean platelet volume": "mean platelet volume",
    "Monocytes count": "monocytes count",
    "Vegetable consumption": "Vegetables",
    "Von Willebrand factor": "von Willebrand factor",
}

# Ordered list of priority variable labels for Table S5.  Defines the
# exact row order for the paste-ready output that goes into cell B3 of
# the template spreadsheet.
TABLE_S5_LABELS: list[str] = [
    "8-epi-PGF2a in urine",
    "Activity LP-PLA2 in blood",
    "AHI Apnea-Hypopnea Index",
    "Albumin creatinine ratio in urine",
    "Albumin in blood",
    "Albumin in urine",
    "Alcohol Consumption",
    "ALT SGPT",
    "AST SGOT",
    "Basophils Count",
    "Bilirubin Conjugated Direct",
    "Bilirubin total",
    "BMI",
    "BNP",
    "Body weight",
    "BUN",
    "BUN Creatinine ratio",
    "CRP c-reactive protein",
    "CAC Score",
    "CAC volume",
    "Carotid IMT",
    "Carotid stenosis left",
    "Carotid stenosis right",
    "CD40 in blood",
    "CESD score",
    "Chloride in blood",
    "Cigarette smoking",
    "Creatinine in blood",
    "Creatinine in urine",
    "Cystatin C in blood",
    "D-Dimer",
    "Diastolic blood pressure",
    "E-selectin in blood",
    "EGFR",
    "Eosinophils count",
    "Factor VII",
    "Factor VIII",
    "Fasting blood glucose",
    "Fasting lipids",
    "Ferritin",
    "FEV1 - Forced Expiratory Volume in 1 sec",
    "FEV1 FVC",
    "Fibrinogen",
    "Fruit consumption",
    "FVC - Forced Vital Capacity",
    "GFR",
    "Glucose in blood",
    "HDL",
    "Heart rate",
    "Height",
    "Hematocrit",
    "Hemoglobin",
    "Hemoglobin A1c",
    "Hip circumference",
    "ICAM1 in blood",
    "Insulin in blood",
    "Interleukin 1 beta in blood",
    "Interleukin 10 in blood",
    "interleukin 6 in blood",
    "Lactate Dehydrogenase LDH",
    "Lactate in blood",
    "LDL",
    "Lymphocytes count",
    "Lymphocytes percent",
    "Mass LP-PLA2 in blood",
    "MCP1 in blood",
    "Mean arterial pressure",
    "Mean corpuscular hemoglobin",
    "Mean corpuscular hemoglobin concentration",
    "Mean corpuscular volume",
    "Mean platelet volume",
    "MMP9 in blood",
    "Monocytes count",
    "Myeloperoxidase in blood",
    "Neutrophils count",
    "Neutrophils percent",
    "NT pro BNP",
    "Osteoprotegerin in blood",
    "P-selectin in blood",
    "Platelet count",
    "Potassium in blood",
    "PR interval",
    "QRS interval",
    "QT interval",
    "Red blood cell count",
    "Red cell distribution width",
    "Sleep hours",
    "Sodium in blood",
    "Sodium intake",
    "SpO2",
    "Systolic blood pressure",
    "Temperature",
    "TNFa in blood",
    "TNFa-R1 in blood",
    "Total cholesterol in blood",
    "Triglycerides in blood",
    "Troponin all types",
    "Vegetable consumption",
    "Von Willebrand factor",
    "Waist circumference",
    "Waist-hip ratio",
    "White blood cell count",
]

# Output column order for the paste-ready TSV.  Matches Table S5's
# column layout starting at cell B3.
SHEET_COLUMNS: list[str] = [
    "n",
    "nulls_missing",
    "mean",
    "median",
    "max",
    "min",
    "sd",
    "enums",
    "participants",
]
