/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_00_Master														*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/06/18															*/
/* Date Last Updated: 2025/07/25													*/
/* Description:	This is the master Stata program for supporting YAML transforms. 	*/
/* It sets global macros before calling the following programs:						*/
/*		1. Import spreadsheet data  												*/
/*		2. Import documentation 													*/
/*		3. Clean data																*/
/*		4. Generate YAML code														*/
/*																					*/
/*		Other (code called in-line of other code)									*/
/*		- units																		*/
/*																					*/
/* Notes:  																			*/
/*		-  			*/
/*																					*/
/* -------------------------------------------------------------------------------- */

clear all 


/* ----- SET MACROS -----*/

/* ----- 1. Dates ----- */
* Today's date *;
local xt: display %td_CCYY_NN_DD date(c(current_date), "DMY")
local today = subinstr(trim("`xt'"), " " , "-", .)
global today "`today'" 
/*global today "2025-04-08" */

/* ----- 2. Filepaths ----- */

global dir "C:\Users\smccutchan\OneDrive - Research Triangle Institute\Documents\DMC\YAMLTransforms"
global raw $dir\Raw
global der $dir\Derived
global prog $dir\Programs
global doc $dir\Documentation
global temp $dir\temp
global out $dir\Output


/* ----- 3. Variable groups ----- */

* -- MeasurementObservation -- *;

* WHI *;
global MeasurementObservation_whi alcohol_servings bdy_hgt bdy_wgt bmi bnp bp_diastolic bp_systolic bun creat_bld factor_7 fibrin fruit_serving glucose_bld hdl hemat hemo hip_circ hrtrt insulin_blood lactate_dehyd ldl med_adher nt_bnp pacem_stat platelet_ct pr_ekg qrs_ekg qt_ekg sleep_duration_daily sodium_blood sodium_intak tot_chol_bld triglyc_bld troponin vege_serving waist_circ waist_hip whtbld_ct 

* FHS *;
global MeasurementObservation_fhs albumin_bld albumin_creatinine albumin_urine alt_sgpt apnea_hypop_index ast_sgot basophil_ncnc_bld bdy_hgt bdy_wgt bilirubin_con bilirubin_tot bmi bnp bp_diastolic bp_systolic bun bun_creatinine cac_score cac_volume carotid_imt carotid_sten_left carotid_sten_right cd40 cesd_score chloride_bld creat_bld creat_urin crp cysc_bld d_dimer eosinophil_ncnc_bld eselectin factor_7 factor_8 fast_gluc_bld fast_lipids ferritin fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt icam il10 il18 il1_beta il6 insulin_blood isoprostane_8_epi_pgf2a lactate_blood lactate_dehyd ldl lppla2_act lppla2_mass lympho_ct mch mchc mcp1 mcv med_adher mmp9 mn_art_pres monocyte_ncnc_bld mpo nt_bnp opg pacem_stat platelet_ct pmv potassium pr_ekg pselectin qrs_ekg qt_ekg rdbld_ct rdw resp_rt sleep_duration_daily sodium_blood sodium_intak spo2 tnfa tnfa_r1 tnfr2 tot_chol_bld triglyc_bld troponin vege_serving waist_circ whtbld_ct willeb_fac

* ARIC *;
global MeasurementObservation_aric albumin_bld albumin_creatinine albumin_urine basophil_ncnc_bld bdy_hgt bdy_wgt bmi bnp bp_diastolic bp_systolic bun carotid_imt carotid_sten_left carotid_sten_right cesd_score chloride_bld creat_bld creat_urin crp cysc_bld d_dimer egfr eosinophil_ncnc_bld factor_7 factor_8 fast_gluc_bld fast_lipids fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt insulin_blood ldl lympho_ct lympho_pct mch mchc mcv med_adher mn_art_pres monocyte_ncnc_bld neutro_ct neutro_pct nt_bnp pacem_stat platelet_ct pmv potassium pr_ekg qrs_ekg qt_ekg rdbld_ct rdw sleep_duration_daily sodium_blood sodium_intak tot_chol_bld triglyc_bld troponin vege_serving waist_circ waist_hip whtbld_ct willeb_fac

* CARDIA *;
global MeasurementObservation_cardia albumin_bld albumin_creatinine albumin_urine alcohol_servings ast_sgot basophil_ncnc_bld bdy_hgt bdy_temp bdy_wgt bilirubin_tot bp_diastolic bp_systolic cac_score creat_bld creat_urin crp eosinophil_ncnc_bld factor_7 factor_8 fast_gluc_bld fast_lipids fev1 fibrin fruit_serving fvc glucose_bld hdl hemat hemo hip_circ hrtrt icam il6 insulin_blood isoprostane_8_epi_pgf2a ldl lympho_ct mch mchc med_adher monocyte_ncnc_bld neutro_ct neutro_pct platelet_ct pmv rdbld_ct sleep_duration_daily sodium_intak tot_chol_bld triglyc_bld troponin vege_serving waist_circ whtbld_ct willeb_fac

* JHS *;
global MeasurementObservation_jhs albumin_creatinine albumin_urine alcohol_servings basophil_ncnc_bld bdy_hgt bdy_wgt bnp bp_diastolic bp_systolic bun cac_score carotid_imt chloride_bld creat_bld creat_urin crp cysc_bld egfr eosinophil_ncnc_bld eselectin fast_gluc_bld ferritin fev1 fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt insulin_blood ldl lympho_ct mch mchc mcv med_adher monocyte_ncnc_bld neutro_ct platelet_ct pmv potassium pr_ekg pselectin qrs_ekg qt_ekg rdbld_ct rdw sleep_duration_daily sodium_blood tot_chol_bld triglyc_bld vege_serving waist_circ whtbld_ct




/* ----- PROGRAMS -----*/

/* ----- 1. Import spreadsheet data ----- */
do "$prog/DMCYAML_01_ImportData.do"

/* ----- 2. Import documentation ----- */
do "$prog/DMCYAML_02_ImportDocs.do"

/* ----- 3. Clean data ----- */
do "$prog/DMCYAML_03_CleanData"

/* ----- 4. Generate YAML code ----- */
do "$prog/DMCYAML_04_GenerateCode.do"


/* ----- Other (called in-line of other programs) ----- */
"$prog/units.do"

