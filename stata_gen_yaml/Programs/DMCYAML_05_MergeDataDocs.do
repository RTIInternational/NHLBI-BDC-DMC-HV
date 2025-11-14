/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_05_MergeDataDocs												*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/11/13															*/
/* Date Last Updated: 2025/11/13													*/
/* Description:	This program merges documentation files from program 2 to curated 	*/
/*	   data. It also generates derived variables used in YAML code generation.		*/
/*		1. Merge data and documentation												*/
/*		2. Update fields from documentation files									*/
/*		3. Prepare for YAML code generation											*/
/*																					*/
/* Notes:  																			*/
/*	- 	*/
/*		 															*/
/*	  																				*/
/* -------------------------------------------------------------------------------- */


use "$temp\alldata_curate.dta", clear


/* ----- 1. Merge data and documentation ----- */
* Merge BDCHM key *;
merge m:1 merge_bdchm_label using "$doc\bdchm_key.dta"
drop if _merge==2
rename _merge merge_bdchm

* Merge pht *;
sort pht
merge m:1 pht using "$doc\pht_visit.dta"
drop if _merge==2
rename _merge merge_pht

* Merge unit conversions *;
gen unit_merge_key=var_units+"_"+bdchm_unit
merge m:1 unit_merge_key using "$doc\conversions.dta"
drop if _merge==2
drop conversion_formula
rename _merge merge_conversionrules

* Merge unit equivalencies *;
merge m:1 unit_merge_key using "$doc\equivalencies.dta", keepusing(equivalent_units)
drop if _merge==2
drop _merge

save "$der\alldata_$today.dta", replace





/* ----- 2. Update fields from documentation files ----- */
use "$der\alldata_$today.dta", clear

* Update units matches requiring more sophisticated rules *;
replace equivalent_units=1 if bdchm_label=="sodium in blood" & var_units=="meq/L" & bdchm_unit=="mmol/L"
replace conversion_rule="* 18" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & inlist(bdchm_label,"glucose in blood","fasting blood glucose")
replace conversion_rule="* 38.67" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & inlist(bdchm_label,"hdl","total cholesterol in blood")
replace conversion_rule="* 88.57" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & bdchm_label=="triglycerides in blood"
replace conversion_rule="* 0.01" if var_units=="%" & bdchm_unit=="[IU]/mL" & bdchm_label=="factor viii"
replace conversion_rule="* 0.3945" if phv=="phv00112974" /*note: goes from ml/day to g/day by multiplying by 0.789, then go from g/day to serving/day dividing by 14, then from serving/day to serving/week by multiplying by 7*/
replace conversion_rule="* 0.016420361" if var_units=="g/mo" & bdchm_unit=="{#}/wk" & bdchm_label=="alcohol" /* divide by 4.35 to get g/wk, then divide by 14 to get servings/week */
replace conversion_rule="* 6" if var_units=="[IU]/mL" & bdchm_unit=="pmol/L" & bdchm_label=="insulin in blood"

* Update unit equivalencies requring more sophisticated rules *;
replace equivalent_units=1 if var_units=="%" & bdchm_unit=="g/dL" & bdchm_label=="mean corpuscular hemoglobin concentration"

* Add manual conversion rule from merged-in fixed data *;
replace conversion_rule=expr_custom if expr_custom!=""




/* ----- 3. Prepare for YAML code generation ----- */
* Create flags for if-then rules*;
gen has_pht=1 if merge_pht==3
gen has_onto=1 if onto_id!=""
gen unit_match=1 if (var_units==bdchm_unit & var_units!="") /* unit matches exactly */
	replace unit_match=1 if equivalent_units==1
gen unit_convert=0 /* row eligible for YAML unit_conversion: statement */
	replace unit_convert=1 if unit_match!=1 & both_valid_ucums==1
gen unit_expr=0 /* use expr statement for everything else that can be converted */
	replace unit_expr=1 if unit_match!=1 & both_valid_ucums!=1 & conversion_rule!=""
gen row_good=0
replace row_good=1 if has_pht==1 & has_onto==1 & (unit_match==1 | unit_convert==1 | unit_expr==1)

* Remove duplicates and unneeded vars *; 
keep bdchm_entity bdchm_label bdchm_varname pht phv phs onto_id var_desc cohort bdchm_unit associatedvisit participantidphv ageinyearsphv var_units bdchm_unit has_pht has_onto unit_match unit_convert unit_expr row_good conversion_rule source_unit target_unit equivalent_units
duplicates drop
duplicates list phv 
		/*browse if inlist(phv,"phv00083163")*/	
save "$der\shortdata_$today.dta", replace /*n=10783*/






/* Future Improvements 
-----------------


Units
	- To handle missing var_units: store bdchm_unit in local macro, search the string of source_variable_description for the unit, then add that unit to the var_units field if it's found 
	
Associated Visits
	- If the pht is a range (ex: FHS Visit 1-4) then search the string of source_variable_description for words like exam or visit followed by a number, using PERL syntax



	