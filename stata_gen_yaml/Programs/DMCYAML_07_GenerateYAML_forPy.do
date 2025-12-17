/* -------------------------------------------------------------------------------- */
/* Date Last Updated: 2025/12/15													*/
/* Description:	This program is a version of DMCYAML_07_GenerateYAML.do that has	*/
/* global macros from the master .do included also. Extraneous comments and archived*/
/* code has been removed for a cleaner LLM translation.								*/
/* -------------------------------------------------------------------------------- */

/* ----- SET MACROS -----*/

* Today's date *;
local xt: display %td_CCYY_NN_DD date(c(current_date), "DMY")
local today = subinstr(trim("`xt'"), " " , "-", .)
global today "`today'" 

* Filepaths *;
global dir "C:\Users\smccutchan\OneDrive - Research Triangle Institute\Documents\DMC\YAMLTransforms"
global raw $dir\Raw
global der $dir\Derived
global prog $dir\Programs
global doc $dir\Documentation
global temp $dir\temp
global out $dir\Output


* Variable groups *;
* ARIC MeasObs *;
global MeasurementObservation_aric albumin_bld albumin_urine basophil_ncnc_bld bdy_hgt bdy_wgt bmi bnp bp_diastolic bp_systolic bun cesd_score chloride_bld creat_bld creat_urin cysc_bld d_dimer egfr factor_7 factor_8 fast_gluc_bld fev1 fibrin fvc glucose_bld hdl hemat hemo hemo_a1c hip_circ hrtrt insulin_blood ldl lympho_ct lympho_pct mch mchc mcv mn_art_pres monocyte_ncnc_bld neutro_pct nt_bnp platelet_ct pmv potassium pr_ekg qrs_ekg qt_ekg rdbld_ct rdw sleep_duration_daily sodium_blood sodium_intak tot_chol_bld triglyc_bld waist_circ waist_hip whtbld_ct willeb_fac


/* Note: change value of cohort local macro to desired cohort before running */
local entity = "MeasurementObservation"
local cohort = "aric"
local macroname = "`entity'_`cohort'"


/* ----- 0. Prepare ----- */

* -- Generate global macros of entity_cohort variable names -- *;
use "$der\shortdata_$today.dta", clear
keep if bdchm_entity=="`entity'"
keep if cohort=="`cohort'"
gen macroname=bdchm_entity+"_"+cohort
keep macroname bdchm_varname
sort bdchm_varname
duplicates drop

gen count=_n
summ count
local numvars = "bdchm_varname`r(max)'"
reshape wide bdchm_varname, i(macroname) j(count)
egen vars=concat(bdchm_varname1-`numvars'), p(" ")
keep macroname vars
gen code="global "+macroname+" "+vars
keep code
export delimited "$temp\\`cohort'\mcr_`entity'.txt", delimiter(tab) novarnames noquote replace


* -- Check uniqueness of rows -- *;
use "$der\shortdata_$today.dta", clear
keep if bdchm_entity=="`entity'"
keep if cohort=="`cohort'"
sort phv bdchm_entity bdchm_varname
gen pair_id=phv+bdchm_varname
duplicates list pair_id /* No duplicates allowed */




/* ----- 1. Split data rows into good/bad candidates for automation ----- */
/* Note: output files must be one row per phv */

foreach bdchm in $`macroname' {	
	use "$der\shortdata_$today.dta", clear
	keep if bdchm_entity=="`entity'"
	keep if cohort=="`cohort'"
	keep if bdchm_varname=="`bdchm'"
	keep if row_good==1
	save "$temp\\`cohort'\good\\`bdchm'.dta", replace

	use "$der\shortdata_$today.dta", clear
	keep if bdchm_entity=="`entity'"
	keep if cohort=="`cohort'"
	keep if bdchm_varname=="`bdchm'"
	keep if row_good!=1
	count
	save "$temp\\`cohort'\bad\\`bdchm'.dta", replace 
}

	


/* ----- 2. Write good YAML codelines ----- */
file close _all

foreach bdchm in $`macroname' {	
use "$temp\\`cohort'\good\\`bdchm'.dta", clear 
count
if r(N) > 0 {

file open `bdchm'_good using "$out\\`cohort'\good\\`bdchm'.yaml", write replace

local nobs = _N
forv i = 1/`nobs' { 
	local phv=phv[`i']
	local entity=bdchm_entity[`i']
	local pht=pht[`i']
	local onto=onto_id[`i']
	local unit=bdchm_unit[`i']
	local visit=associatedvisit[`i']
	local participant=participantidphv[`i']
	local age=ageinyearsphv[`i']
	local convert=conversion_rule[`i']
	local source_unit=source_unit[`i']
	local target_unit=target_unit[`i']

if unit_match[`i']==1 {
file write `bdchm'_good "- class_derivations:" _n ///
	_column(5) "`entity'" ":" _n ///
			_column(7) "populated from: " "`pht'" _n ///
			_column(7) "slot_derivations:" _n ///
				_column(9) "associated_participant: " _n ///
					_column(11) "populated_from: " "`participant'" _n ///
				_column(9) "associated_visit: " _n ///		
					_column(11) "value: " "`visit'" _n ///
				_column(9) "age_at_observation: " _n ///
					_column(11) "expr: {" "`age'" "} * 365" _n ///
				_column(9) "observation_type: " _n ///
					_column(11) "value: " "`onto'" _n ///
				_column(9) "value_quantity:" _n ///
					_column(11) "object_derivations:" _n ///
					_column(11) "- class_derivations:" _n ///
							_column(15) "Quantity:" _n ///
								_column(17) "populated_from: " "`pht'" _n ///
								_column(17) "slot_derivations:" _n ///
									_column(19) "value_decimal:" _n ///
										_column(21) "populated_from: " "`phv'" _n ///
									_column(19) "unit: " _n ///
										_column(21) "value: " _char(34) "`unit'" _char(34) _n	

	}
else if unit_convert[`i']==1 {
file write `bdchm'_good "- class_derivations:" _n ///
	_column(5) "`entity'" ":" _n ///
			_column(7) "populated from: " "`pht'" _n ///
			_column(7) "slot_derivations:" _n ///
				_column(9) "associated_participant: " _n ///
					_column(11) "populated_from: " "`participant'" _n ///
				_column(9) "associated_visit: " _n ///		
					_column(11) "value: " "`visit'" _n ///
				_column(9) "age_at_observation: " _n ///
					_column(11) "expr: {" "`age'" "} * 365" _n ///
				_column(9) "observation_type: " _n ///
					_column(11) "value: " "`onto'" _n ///
				_column(9) "value_quantity:" _n ///
					_column(11) "object_derivations:" _n ///
					_column(11) "- class_derivations:" _n ///
							_column(15) "Quantity:" _n ///
								_column(17) "populated_from: " "`pht'" _n ///
								_column(17) "slot_derivations:" _n ///
									_column(19) "value_decimal:" _n ///
										_column(21) "populated_from: " "`phv'" _n ///
										_column(21)	"unit_conversion:" _n ///
											_column(23)	"source_unit: " _char(34) "`source_unit'" _char(34) _n ///
											_column(23) "target_unit: " _char(34) "`target_unit'" _char(34) _n ///
									_column(19) "unit: " _n ///
										_column(21) "value: " _char(34) "`unit'" _char(34) _n ///
										_column(21)	"range: string" _n
	
	}
else if unit_expr[`i']==1 {
file write `bdchm'_good "- class_derivations:" _n ///
	_column(5) "`entity'" ":" _n ///
			_column(7) "populated from: " "`pht'" _n ///
			_column(7) "slot_derivations:" _n ///
				_column(9) "associated_participant: " _n ///
					_column(11) "populated_from: " "`participant'" _n ///
				_column(9) "associated_visit: " _n ///		
					_column(11) "value: " "`visit'" _n ///
				_column(9) "age_at_observation: " _n ///
					_column(11) "expr: {" "`age'" "} * 365" _n ///
				_column(9) "observation_type: " _n ///
					_column(11) "value: " "`onto'" _n ///
				_column(9) "value_quantity:" _n ///
					_column(11) "object_derivations:" _n ///
					_column(11) "- class_derivations:" _n ///
							_column(15) "Quantity:" _n ///
								_column(17) "populated_from: " "`pht'" _n ///
								_column(17) "slot_derivations:" _n ///
									_column(19) "value_decimal:" _n ///
										_column(21) "expr: {" "`phv'" "} " "`convert'" _n ///
									_column(19) "unit: " _n ///
										_column(21) "value: " _char(34) "`unit'" _char(34) _n ///
										_column(21)	"range: string" _n
}
}
file close `bdchm'_good
}
}









/* ----- 3. Write bad YAML codelines ----- */
file close _all

foreach bdchm in $`macroname' {	
use "$temp\\`cohort'\bad\\`bdchm'.dta", clear 
count
if r(N) > 0 {

file open `bdchm'_bad using "$out\\`cohort'\bad\\`bdchm'.yaml", write replace

local nobs = _N
forv i = 1/`nobs' { 
	local phv=phv[`i']
	local entity=bdchm_entity[`i']
	local pht=pht[`i']
	local onto=onto_id[`i']
	local unit=bdchm_unit[`i']
	local visit=associatedvisit[`i']
	local participant=participantidphv[`i']
	local age=ageinyearsphv[`i']
	local convert=conversion_rule[`i']

file write `bdchm'_bad "- class_derivations:" _n ///
	_column(5) "`entity'" ":" _n ///
			_column(7) "populated from: " "`pht'" _n ///
			_column(7) "slot_derivations:" _n ///
				_column(9) "associated_participant: " _n ///
					_column(11) "populated_from: " "`participant'" " #CHECK" _n ///
				_column(9) "associated_visit: " _n ///		
					_column(11) "value: " "`visit'" _n ///
				_column(9) "age_at_observation: " _n ///
					_column(11) "expr: {" "`age'" "} * 365" _n ///
				_column(9) "observation_type: " _n ///
					_column(11) "value: " "`onto'" _n ///
				_column(9) "value_quantity:" _n ///
					_column(11) "object_derivations:" _n ///
					_column(11) "- class_derivations:" _n ///
							_column(15) "Quantity:" _n ///
								_column(17) "populated_from: " "`pht'" _n ///
								_column(17) "slot_derivations:" _n ///
									_column(19) "value_decimal:" _n ///
										_column(21) "populated_from: " "`phv'" " #CHECK" _n ///
									_column(19) "unit: " _n ///
										_column(21) "value: " _char(34) "`unit'" _char(34) " #CHECK" _n
									
	}		

file close `bdchm'_bad
}
}