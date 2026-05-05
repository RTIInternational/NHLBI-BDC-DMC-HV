
clear all 


/* ----- SET MACROS -----*/

/* ----- 1. Dates ----- */
* Today's date *;
local xt: display %td_CCYY_NN_DD date(c(current_date), "DMY")
local today = subinstr(trim("`xt'"), " " , "-", .)
/*global today "`today'"*/
global today "2026-04-02" 

/* ----- 2. Filepaths ----- */

global dir "C:\Users\smccutchan\OneDrive - Research Triangle Institute\Documents\DMC\YAMLTransforms"
global raw $dir\Raw
global der $dir\Derived
global prog $dir\Programs
global doc $dir\Documentation
global temp $dir\temp
global out $dir\Output
global templates $dir\templates


/* ----- 3. Variable groups ----- */

* -- MeasurementObservation -- *;
* Note: These global macros are lists of Measurement Observations harmonized variables (HVs) that have >=1 phv mapped to them for the cohort. These are explicitly listed to prevent the Stata YAML-authoring program from crashing. In Python, it may be possible instead to loop over a list of all currently defined HVs, if Python will simply ignore/skip files when no phv candidate is found matching a given HV *;

* ARIC *;
global MeasurementObservation_aric albumin_bld albumin_urine basophil_ncnc_bld bdy_hgt bdy_wgt bmi bnp bp_diastolic bp_systolic bun bun_creatinine carotid_imt carotid_sten_left carotid_sten_right cesd_score chloride_bld creat_bld creat_urin crp cysc_bld d_dimer egfr factor_7 factor_8 fast_gluc_bld fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt insulin_blood ldl lympho_ct lympho_pct mch mchc mcv mn_art_pres monocyte_ncnc_bld neutro_pct nt_bnp platelet_ct pmv potassium pr_ekg qrs_ekg qt_ekg rdbld_ct rdw sleep_duration_daily sodium_blood sodium_intak tot_chol_bld triglyc_bld troponin vege_serving waist_circ waist_hip whtbld_ct willeb_fac

* CARDIA *;
global MeasurementObservation_cardia albumin_bld albumin_creatinine albumin_urine alcohol_servings ast_sgot bdy_hgt bdy_temp bdy_wgt bilirubin_tot bp_diastolic bp_systolic cac_score creat_bld creat_urin crp factor_7 factor_8 fast_gluc_bld fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hip_circ hrtrt icam il6 insulin_blood isoprostane_8_epi_pgf2a ldl lympho_ct mch mchc neutro_pct platelet_ct rdbld_ct sleep_duration_daily sodium_intak tot_chol_bld triglyc_bld vege_serving waist_circ whtbld_ct willeb_fac

* FHS *;
global MeasurementObservation_fhs albumin_bld albumin_creatinine albumin_urine alt_sgpt apnea_hypop_index ast_sgot basophil_ncnc_bld bdy_hgt bdy_wgt bilirubin_con bilirubin_tot bmi bnp bp_diastolic bp_systolic bun bun_creatinine cac_score cac_volume carotid_imt carotid_sten_left carotid_sten_right cd40 cesd_score chloride_bld creat_bld creat_urin crp cysc_bld d_dimer eosinophil_ncnc_bld eselectin factor_7 factor_8 fast_gluc_bld fast_lipids ferritin fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt icam il10 il18 il1_beta il6 insulin_blood isoprostane_8_epi_pgf2a lactate_blood lactate_dehyd ldl lppla2_act lppla2_mass lympho_ct mch mchc mcp1 mcv mmp9 mn_art_pres monocyte_ncnc_bld mpo nt_bnp opg platelet_ct pmv potassium pr_ekg pselectin qrs_ekg qt_ekg rdbld_ct rdw sleep_duration_daily sodium_blood sodium_intak spo2 tnfa tnfa_r1 tot_chol_bld triglyc_bld troponin vege_serving waist_circ whtbld_ct willeb_fac

* JHS *;
global MeasurementObservation_jhs albumin_creatinine albumin_urine alcohol_servings basophil_ncnc_bld bdy_hgt bdy_wgt bnp bp_diastolic bp_systolic bun cac_score carotid_imt chloride_bld creat_bld creat_urin crp cysc_bld egfr eselectin fast_gluc_bld ferritin fev1 fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt insulin_blood ldl lympho_ct lympho_pct mch mchc mcv platelet_ct pmv potassium pr_ekg pselectin qrs_ekg qt_ekg rdbld_ct sleep_duration_daily sodium_blood tot_chol_bld triglyc_bld vege_serving waist_circ whtbld_ct

* WHI *;
global MeasurementObservation_whi alcohol_servings bdy_hgt bdy_wgt bmi bnp bp_diastolic bp_systolic bun creat_bld factor_7 fibrin fruit_serving glucose_bld hdl hemat hemo hip_circ hrtrt insulin_blood ldl nt_bnp platelet_ct pr_ekg qrs_ekg qt_ekg sleep_duration_daily sodium_blood sodium_intak tot_chol_bld triglyc_bld troponin vege_serving waist_circ waist_hip whtbld_ct



/* ----- PROGRAMS -----*/

/* ----- 1. Import documentation ----- */
do "$prog/DMCYAML_01_ImportDocs.do"

/* ----- 2. Import spreadsheet data ----- */
do "$prog/DMCYAML_02_ImportData.do"

/* ----- 3. Clean data ----- */
do "$prog/DMCYAML_03_CleanData.do"

/* ----- 4. Merge data and documentation ----- */
do "$prog/DMCYAML_04_MergeDataDocs.do"

/* ----- 5. Peform QC ----- */
* Note: manual data processes are performed by human curators at this stage, enabled by the code *;
do "$prog/DMCYAML_05_QC.do"

/* ----- 6. Generate YAML code ----- */
do "$prog/DMCYAML_06_GenerateYAML.do"


/* ----- Other (called in-line of other programs) ----- */
"$prog/units.do"

