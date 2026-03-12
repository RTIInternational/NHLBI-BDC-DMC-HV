"""
Date Last Updated: 2026/03/12
Description: Python translation of DMCYAML_07_GenerateYAML_forPy.do
This script generates YAML files from filtered/reshaped metadata.
MVP version of script tested in local directory on 12/16/2025 - output appears correct.
Ref: GitHub pull request #349
"""

import pandas as pd
import jinja2
import os
from datetime import datetime
from pathlib import Path

# ----- SET PATHS -----

# Today's date in YYYY-MM-DD format
#today = datetime.now().strftime("%Y-%m-%d")
today = "2026-03-12"  # hardcoding for testing purposes - update as needed

# Filepaths
base_dir = r"C:\\Users\smccutchan\Documents\DMC\\NHLBI-BDC-DMC-HV\stata_gen_yaml"
raw_dir = os.path.join(base_dir, "Raw")
der_dir = os.path.join(base_dir, "Python\\Derived")
prog_dir = os.path.join(base_dir, "Python\\Programs")
templates_dir = os.path.join(base_dir, "Python\\templates")
doc_dir = os.path.join(base_dir, "Documentation")
temp_dir = os.path.join(base_dir, "Python\\temp")
out_dir = os.path.join(base_dir, "Python\\Output")

# ----- VARIABLE GROUPS -----

# ARIC MeasObs variable list
measurement_observation_aric = [
    "albumin_bld", "albumin_urine", "basophil_ncnc_bld", "bdy_hgt", "bdy_wgt", 
    "bmi", "bnp", "bp_diastolic", "bp_systolic", "bun", "bun_creatinine", 
    "carotid_imt", "carotid_sten_left", "carotid_sten_right", "cesd_score", "chloride_bld", 
    "creat_bld", "creat_urin", "crp", "cysc_bld", "d_dimer", "egfr", 
    "eosinophil_ncnc_bld", "factor_7", "factor_8", "fast_gluc_bld", "fev1", "fibrin", 
    "fruit_serving", "fvc", "glucose_bld", "hdl", "hemat", "hemo", "hemo_a1c", 
    "hip_circ", "hrtrt", "insulin_blood", "ldl", "lympho_ct", "lympho_pct", "mch", 
    "mchc", "mcv", "mn_art_pres", "monocyte_ncnc_bld", "neutro_ct", "neutro_pct", 
    "nt_bnp", "platelet_ct", "pmv", "potassium", "pr_ekg", "qrs_ekg", "qt_ekg", 
    "rdbld_ct", "rdw", "sleep_duration_daily", "sodium_blood", "sodium_intak", 
    "tot_chol_bld", "triglyc_bld", "troponin", "vege_serving", "waist_circ", "waist_hip", 
    "whtbld_ct", "willeb_fac"
]

# Configuration (change these values as needed)
entity = "MeasurementObservation"
cohort = "aric"
macroname = f"{entity}_{cohort}"
print(macroname)

# Load Stata file
# The input file can be formatted as .csv instead of .dta
input_file = os.path.join(der_dir, f"shortdata_{today}.csv")
df = pd.read_csv(input_file)

# check data loaded correctly 
df.head()

# ----- 0. PREPARE -----
# Note that all this splitting into subfiles may not be needed. The overall logic is:
# if cohort = aric and entity = MeasurementObservation
#   then for each bdchm_varname that exists in that cohort/entity (i.e. >=1 phv numbers associated with the bdchm_varname)
#       if row_good == 1 then write to good subfile by cohort/bdchm_varname
#       else write to bad subfile by cohort/bdchm_varname
# code could also be looped over all cohort, and potentially in future over all entities

# Filter for entity and cohort
df_filtered = df[(df['bdchm_entity'] == entity) & (df['cohort'] == cohort)].copy()

# check data filtered correctly 
df_filtered.head()

# Create list of HVs present in entity/cohort
df_macro = df_filtered[['bdchm_varname']].drop_duplicates().sort_values('bdchm_varname').reset_index(drop=True)
df_macro.head()
df_macro['macroname'] = macroname
vars_list = df_macro['bdchm_varname'].tolist()

# check which vars are selected for inclusion in the entity_cohort macro
print(vars_list)


# Check uniqueness of (phv, bdchm_entity, bdchm_varname) pairs
df_sorted = df_filtered.sort_values(['phv', 'bdchm_entity', 'bdchm_varname'])
df_sorted['pair_id'] = df_sorted['phv'].astype(str) + df_sorted['bdchm_varname'].astype(str)
duplicates = df_sorted[df_sorted.duplicated(subset=['pair_id'], keep=False)]
if len(duplicates) > 0:
    print("WARNING: Duplicate (phv, bdchm_varname) pairs found:")
    print(duplicates[['phv', 'bdchm_varname']])

# check the resulting duplicates dataframe is empty. must be empty for following code to produce expected results
duplicates.head()


# ----- 1. SPLIT DATA ROWS INTO GOOD/BAD CANDIDATES -----
#this writes blank files for any bdchm_varname that has no candidates. 
for bdchm in vars_list:
    # Good candidates (row_good == 1)
    good_data = df_filtered[(df_filtered['bdchm_varname'] == bdchm) & 
                            (df_filtered['row_good'] == 1)].copy()
    
    # Create output directory for good files
    good_dir = os.path.join(temp_dir, cohort, "good")
    os.makedirs(good_dir, exist_ok=True)
    good_file = os.path.join(good_dir, f"{bdchm}.csv")
    good_data.to_csv(good_file, index=False)
    
    # Bad candidates (row_good != 1)
    bad_data = df_filtered[(df_filtered['bdchm_varname'] == bdchm) & 
                           (df_filtered['row_good'] != 1)].copy()
    
    # Create output directory for bad files
    bad_dir = os.path.join(temp_dir, cohort, "bad")
    os.makedirs(bad_dir, exist_ok=True)
    bad_file = os.path.join(bad_dir, f"{bdchm}.csv")
    bad_data.to_csv(bad_file, index=False)



# ----- 2. WRITE GOOD YAML CODELINES -----
#the if condition ensures that no yaml file is written if there are no candidates for that bdchm_varname
from jinja2 import Environment, FileSystemLoader

environment = Environment(loader=FileSystemLoader(templates_dir), trim_blocks=True, lstrip_blocks=True)
template = environment.get_template("yaml_measobs.j2")

for bdchm in vars_list:
    good_file = os.path.join(temp_dir, cohort, "good", f"{bdchm}.csv")
    good_data = pd.read_csv(good_file)

    if len(good_data) > 0:
        # Create output directory
        out_good_dir = os.path.join(out_dir, cohort, "good")
        os.makedirs(out_good_dir, exist_ok=True)

        yaml_file = os.path.join(out_good_dir, f"{bdchm}.yaml")

        with open(yaml_file, 'w', encoding="utf-8") as f:
            for idx, row in good_data.iterrows():
                f.write(template.render(**row.to_dict()))
            print(f"... wrote {yaml_file}")





# ----- 3. WRITE BAD YAML CODELINES -----
#the if condition ensures that no yaml file is written if there are no candidates for that bdchm_varname
for bdchm in vars_list:
    bad_file = os.path.join(temp_dir, cohort, "bad", f"{bdchm}.csv")
    bad_data = pd.read_csv(bad_file)

    if len(bad_data) > 0:
        # Create output directory
        out_bad_dir = os.path.join(out_dir, cohort, "bad")
        os.makedirs(out_bad_dir, exist_ok=True)

        yaml_file = os.path.join(out_bad_dir, f"{bdchm}.yaml")

        with open(yaml_file, 'w', encoding="utf-8") as f:
            for idx, row in bad_data.iterrows():
                f.write(template.render(**row.to_dict()))
            print(f"... wrote {yaml_file}")