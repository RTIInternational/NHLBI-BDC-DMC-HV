* This program merges the dbGaP metadata together with documentation files. It then creates indicators for whether a phv is ready to be written as a YAML code block and drops extraneous variables from the data file. *;

use "$temp\variable_mappings_short.dta", clear
sort merge_bdchm_label

/* ----- 1. Merge data and documentation ----- */
* Merge BDCHM key *;
merge m:1 merge_bdchm_label using "$doc\bdchv_defs.dta"
drop if _merge==2
rename _merge merge_bdchm
foreach var in bdchm_varname bdchm_unit {
	replace `var'=`var'_fixed if `var'_fixed!=""
	}

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

* Merge descriptor vars by pht *;
sort pht
merge m:1 pht using "$doc\contextual_variables_key.dta"
drop if _merge==2
rename _merge merge_pht

* If there is a curator override for a value, take the override value instead *;
capture confirm file "$doc\fixed_bdchm_mappings.dta" 
if _rc == 0 {
	foreach var of varlist participantidphv associatedvisit associatedvisit_expr ageinyearsphv conversion_rule {
		replace `var'=`var'_fixed if `var'_fixed!=""
		drop `var'_fixed
		}
	}
else {
	display "File fixed_bdchm_mappings not found"
	}





/* ----- 2. Update rows from documentation files ----- */
* Note: drops when the whole pht/table no longer exists in dbgap *;
drop if drop_table=="1"
drop drop_table




/* ----- 3. Update fields from documentation files ----- */

* Update units matches requiring more sophisticated rules *;
replace conversion_rule="* 38.67" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & inlist(bdchm_label,"hdl","total cholesterol in blood")
replace conversion_rule="* 0.01" if var_units=="%" & bdchm_unit=="[IU]/mL" & bdchm_label=="factor viii"

* Update unit equivalencies requring more sophisticated rules *;
replace equivalent_units=1 if var_units=="%" & bdchm_unit=="g/dL" & bdchm_label=="mean corpuscular hemoglobin concentration"
replace equivalent_units=1 if bdchm_label=="sodium in blood" & var_units=="meq/L" & bdchm_unit=="mmol/L"

capture confirm file "$doc\fixed_bdchm_mappings.dta" 
if _rc == 0 {
* Add manual conversion rule from merged-in fixed data *;
replace conversion_rule=unit_expr_custom if unit_expr_custom!=""
	}
else {
	display "File fixed_bdchm_mappings not found"
}



/* ----- 4. Generate good/bad YAML writing readiness indicators ----- */
* Create flags for if-then rules*;
gen has_pht=1 if merge_pht==3
gen has_onto=1 if onto_id!=""
gen unit_match=0
	replace unit_match=1 if (var_units==bdchm_unit & var_units!="") /* unit matches exactly */
	replace unit_match=1 if equivalent_units==1
gen unit_convert=0
	replace unit_convert=1 if unit_match!=1 & both_valid_ucums==1
gen unit_expr=0 
	replace unit_expr=1 if unit_match!=1 & both_valid_ucums!=1 & conversion_rule!=""
gen unit_casestmt=0

capture confirm file "$doc\fixed_bdchm_mappings.dta" 
if _rc == 0 {
replace unit_casestmt=1 if unit_casestmt_custom!=""
	}
else {
	display "File fixed_bdchm_mappings not found"
	gen unit_casestmt_custom=""
}

replace associatedvisit_expr="" if associatedvisit!="" & associatedvisit_expr!=""
gen has_visit=1 if strtrim(associatedvisit)!=""
gen has_visit_expr=1 if strtrim(associatedvisit_expr)!=""
  gen var_desc_exam=regexs(0) if regexm(var_desc, "exam\s+\d+")
gen has_age=1 if strtrim(ageinyearsphv)!=""

gen row_good=0
replace row_good=1 if has_pht==1 & has_onto==1 & /*(has_visit==1 | has_visit_expr==1) & */(unit_match==1 | unit_convert==1 | unit_expr==1 | unit_casestmt==1)




/* ----- 5. Output ----- */
order row_good cohort bdchm_entity bdchm_label bdchm_varname has_onto onto_id bdchm_unit phv var_desc var_units has_pht pht participantidphv has_visit associatedvisit has_visit_expr associatedvisit_expr xassociatedvisit var_desc_exam has_age ageinyearsphv contextvars_notes unit_match unit_convert unit_expr conversion_rule  unit_casestmt unit_casestmt_custom source_unit target_unit

keep row_good cohort bdchm_entity bdchm_label bdchm_varname has_onto onto_id bdchm_unit phv var_desc var_units has_pht pht participantidphv has_visit associatedvisit has_visit_expr associatedvisit_expr xassociatedvisit var_desc_exam has_age ageinyearsphv contextvars_notes unit_match unit_convert unit_expr conversion_rule  unit_casestmt unit_casestmt_custom source_unit target_unit

duplicates drop
keep if bdchm_entity=="MeasurementObservation"
duplicates list phv 
save "$der\shortdata_$today.dta", replace /*n=4149*/
export delimited using "$der\shortdata_$today.csv", nolabel quote replace






/* Future Improvements 
-----------------


Units
	- To handle missing var_units: store bdchm_unit in local macro, search the string of source_variable_description for the unit, then add that unit to the var_units field if it's found 
	
Associated Visits
	- If the pht is a range (ex: FHS Visit 1-4) then search the string of source_variable_description for words like exam or visit followed by a number, using PERL syntax



	