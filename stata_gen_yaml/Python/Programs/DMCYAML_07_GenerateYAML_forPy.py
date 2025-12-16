"""
Date Last Updated: 2025/12/16
Description: Python translation of DMCYAML_07_GenerateYAML_forPy.do
This script generates YAML files from filtered/reshaped metadata.
MVP version of script tested in local directory on 12/16/2025 - output appears correct.
"""

import pandas as pd
import os
from datetime import datetime
from pathlib import Path

# ----- SET PATHS -----

# Today's date in YYYY-MM-DD format
today = datetime.now().strftime("%Y-%m-%d")

# Filepaths
base_dir = r"C:\Users\smccutchan\OneDrive - Research Triangle Institute\Documents\DMC\YAMLTransforms"
raw_dir = os.path.join(base_dir, "Raw")
der_dir = os.path.join(base_dir, "Derived")
prog_dir = os.path.join(base_dir, "Python\Programs")
doc_dir = os.path.join(base_dir, "Documentation")
temp_dir = os.path.join(base_dir, "Python\\temp")
out_dir = os.path.join(base_dir, "Python\Output")

# ----- VARIABLE GROUPS -----

# ARIC MeasObs variable list
measurement_observation_aric = [
    "albumin_bld", "albumin_urine", "basophil_ncnc_bld", "bdy_hgt", "bdy_wgt", 
    "bmi", "bnp", "bp_diastolic", "bp_systolic", "bun", "cesd_score", "chloride_bld", 
    "creat_bld", "creat_urin", "crp", "cysc_bld", "d_dimer", "egfr", 
    "eosinophil_ncnc_bld", "factor_7", "factor_8", "fast_gluc_bld", "fev1", "fibrin", 
    "fruit_serving", "fvc", "glucose_bld", "hdl", "hemat", "hemo", "hemo_a1c", 
    "hip_circ", "hrtrt", "insulin_blood", "ldl", "lympho_ct", "lympho_pct", "mch", 
    "mchc", "mcv", "mn_art_pres", "monocyte_ncnc_bld", "neutro_ct", "neutro_pct", 
    "nt_bnp", "platelet_ct", "pmv", "potassium", "pr_ekg", "qrs_ekg", "qt_ekg", 
    "rdbld_ct", "rdw", "sleep_duration_daily", "sodium_blood", "sodium_intak", 
    "tot_chol_bld", "triglyc_bld", "vege_serving", "waist_circ", "waist_hip", 
    "whtbld_ct", "willeb_fac"
]

# Configuration (change these values as needed)
entity = "MeasurementObservation"
cohort = "aric"
macroname = f"{entity}_{cohort}"

# Load Stata file
# The input file can be formatted as .csv instead of .dta
input_file = os.path.join(der_dir, f"shortdata_{today}.dta")
df = pd.read_stata(input_file)

# ----- 0. PREPARE -----

# Filter for entity and cohort
df_filtered = df[(df['bdchm_entity'] == entity) & (df['cohort'] == cohort)].copy()

# Generate macro variable names
df_macro = df_filtered[['bdchm_varname']].drop_duplicates().sort_values('bdchm_varname').reset_index(drop=True)
df_macro['macroname'] = macroname
vars_list = df_macro['bdchm_varname'].tolist()

# Check uniqueness of (phv, bdchm_entity, bdchm_varname) pairs
df_sorted = df_filtered.sort_values(['phv', 'bdchm_entity', 'bdchm_varname'])
df_sorted['pair_id'] = df_sorted['phv'].astype(str) + df_sorted['bdchm_varname'].astype(str)
duplicates = df_sorted[df_sorted.duplicated(subset=['pair_id'], keep=False)]
if len(duplicates) > 0:
    print("WARNING: Duplicate (phv, bdchm_varname) pairs found:")
    print(duplicates[['phv', 'bdchm_varname']])

# ----- 1. SPLIT DATA ROWS INTO GOOD/BAD CANDIDATES -----

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

for bdchm in vars_list:
    good_file = os.path.join(temp_dir, cohort, "good", f"{bdchm}.csv")
    good_data = pd.read_csv(good_file)
    
    if len(good_data) > 0:
        # Create output directory
        out_good_dir = os.path.join(out_dir, cohort, "good")
        os.makedirs(out_good_dir, exist_ok=True)
        
        yaml_file = os.path.join(out_good_dir, f"{bdchm}.yaml")
        
        with open(yaml_file, 'w') as f:
            for idx, row in good_data.iterrows():
                phv = row['phv']
                entity_val = row['bdchm_entity']
                pht = row['pht']
                onto = row['onto_id']
                unit = row['bdchm_unit']
                visit = row['associatedvisit']
                participant = row['participantidphv']
                age = row['ageinyearsphv']
                convert = row['conversion_rule']
                source_unit = row.get('source_unit', '')
                target_unit = row.get('target_unit', '')
                unit_match = row['unit_match']
                unit_convert = row.get('unit_convert', 0)
                unit_expr = row.get('unit_expr', 0)
                
                if unit_match == 1:
                    # Write unit match YAML
                    f.write("- class_derivations:\n")
                    f.write(f"     {entity_val}:\n")
                    f.write(f"       populated from: {pht}\n")
                    f.write(f"       slot_derivations:\n")
                    f.write(f"         associated_participant:\n")
                    f.write(f"           populated_from: {participant}\n")
                    f.write(f"         associated_visit:\n")
                    f.write(f"           value: {visit}\n")
                    f.write(f"         age_at_observation:\n")
                    f.write(f"           expr: {{{age}}} * 365\n")
                    f.write(f"         observation_type:\n")
                    f.write(f"           value: {onto}\n")
                    f.write(f"         value_quantity:\n")
                    f.write(f"           object_derivations:\n")
                    f.write(f"           - class_derivations:\n")
                    f.write(f"               Quantity:\n")
                    f.write(f"                 populated_from: {pht}\n")
                    f.write(f"                 slot_derivations:\n")
                    f.write(f"                   value_decimal:\n")
                    f.write(f"                     populated_from: {phv}\n")
                    f.write(f"                   unit:\n")
                    f.write(f"                     value: \"{unit}\"\n")
                
                elif unit_convert == 1:
                    # Write unit conversion YAML
                    f.write("- class_derivations:\n")
                    f.write(f"     {entity_val}:\n")
                    f.write(f"       populated from: {pht}\n")
                    f.write(f"       slot_derivations:\n")
                    f.write(f"         associated_participant:\n")
                    f.write(f"           populated_from: {participant}\n")
                    f.write(f"         associated_visit:\n")
                    f.write(f"           value: {visit}\n")
                    f.write(f"         age_at_observation:\n")
                    f.write(f"           expr: {{{age}}} * 365\n")
                    f.write(f"         observation_type:\n")
                    f.write(f"           value: {onto}\n")
                    f.write(f"         value_quantity:\n")
                    f.write(f"           object_derivations:\n")
                    f.write(f"           - class_derivations:\n")
                    f.write(f"               Quantity:\n")
                    f.write(f"                 populated_from: {pht}\n")
                    f.write(f"                 slot_derivations:\n")
                    f.write(f"                   value_decimal:\n")
                    f.write(f"                     populated_from: {phv}\n")
                    f.write(f"                     unit_conversion:\n")
                    f.write(f"                       source_unit: \"{source_unit}\"\n")
                    f.write(f"                       target_unit: \"{target_unit}\"\n")
                    f.write(f"                   unit:\n")
                    f.write(f"                     value: \"{unit}\"\n")
                    f.write(f"                     range: string\n")
                
                elif unit_expr == 1:
                    # Write unit expression YAML
                    f.write("- class_derivations:\n")
                    f.write(f"     {entity_val}:\n")
                    f.write(f"       populated from: {pht}\n")
                    f.write(f"       slot_derivations:\n")
                    f.write(f"         associated_participant:\n")
                    f.write(f"           populated_from: {participant}\n")
                    f.write(f"         associated_visit:\n")
                    f.write(f"           value: {visit}\n")
                    f.write(f"         age_at_observation:\n")
                    f.write(f"           expr: {{{age}}} * 365\n")
                    f.write(f"         observation_type:\n")
                    f.write(f"           value: {onto}\n")
                    f.write(f"         value_quantity:\n")
                    f.write(f"           object_derivations:\n")
                    f.write(f"           - class_derivations:\n")
                    f.write(f"               Quantity:\n")
                    f.write(f"                 populated_from: {pht}\n")
                    f.write(f"                 slot_derivations:\n")
                    f.write(f"                   value_decimal:\n")
                    f.write(f"                     expr: {{{phv}}} {convert}\n")
                    f.write(f"                   unit:\n")
                    f.write(f"                     value: \"{unit}\"\n")
                    f.write(f"                     range: string\n")


# ----- 3. WRITE BAD YAML CODELINES -----

for bdchm in vars_list:
    bad_file = os.path.join(temp_dir, cohort, "bad", f"{bdchm}.csv")
    bad_data = pd.read_csv(bad_file)
    
    if len(bad_data) > 0:
        # Create output directory
        out_bad_dir = os.path.join(out_dir, cohort, "bad")
        os.makedirs(out_bad_dir, exist_ok=True)
        
        yaml_file = os.path.join(out_bad_dir, f"{bdchm}.yaml")
        
        with open(yaml_file, 'w') as f:
            for idx, row in bad_data.iterrows():
                phv = row['phv']
                entity_val = row['bdchm_entity']
                pht = row['pht']
                onto = row['onto_id']
                unit = row['bdchm_unit']
                visit = row['associatedvisit']
                participant = row['participantidphv']
                age = row['ageinyearsphv']
                
                f.write("- class_derivations:\n")
                f.write(f"     {entity_val}:\n")
                f.write(f"       populated from: {pht}\n")
                f.write(f"       slot_derivations:\n")
                f.write(f"         associated_participant:\n")
                f.write(f"           populated_from: {participant} #CHECK\n")
                f.write(f"         associated_visit:\n")
                f.write(f"           value: {visit}\n")
                f.write(f"         age_at_observation:\n")
                f.write(f"           expr: {{{age}}} * 365\n")
                f.write(f"         observation_type:\n")
                f.write(f"           value: {onto}\n")
                f.write(f"         value_quantity:\n")
                f.write(f"           object_derivations:\n")
                f.write(f"           - class_derivations:\n")
                f.write(f"               Quantity:\n")
                f.write(f"                 populated_from: {pht}\n")
                f.write(f"                 slot_derivations:\n")
                f.write(f"                   value_decimal:\n")
                f.write(f"                     populated_from: {phv} #CHECK\n")
                f.write(f"                   unit:\n")
                f.write(f"                     value: \"{unit}\" #CHECK\n")

print("Script completed successfully!")
print(f"Output files written to: {out_dir}/{cohort}/")
