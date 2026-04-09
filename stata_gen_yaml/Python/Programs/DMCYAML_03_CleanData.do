* This program cleans dbGaP metadata. If the YAML authoring QC program (#5) has been run before, it merges in manual curation fixes from that human-in-the-loop step. 

use "$temp\variable_mappings.dta", clear



/* ----- 1. Exclude rows/variables ----- */
/* drop things that aren't BDC harmonized variables */
drop if bdchm_label=="medication adherence"

/* drop mappings that shouldn't be used */
replace transform_comment=lower(transform_comment)
gen dropmap=0
replace dropmap=1 if inlist(transform_comment,"bad phv map","not going to include","phv doesn't exist")
replace dropmap=1 if regexm(transform_comment, "out of scope")==1
replace dropmap=1 if regexm(transform_comment, "not a measurement")==1

drop if dropmap==1 /*n=6069 dropped*/
drop dropmap



/* ----- 2. Correct BDCHM variable mappings ----- */
/* Note: bad BDCHM mappings occurred during a manual process run by curators, and should ideally be fixed in the source data files read in at the top of program 1. They are handled for this processing pipeline by code below*/

tab bdchm_label
/* all values should match a BDC HV value lable */

replace bdchm_label="stroke" if bdchm_label=="stroke status"
replace bdchm_label="copd" if bdchm_label=="copd status"
replace bdchm_label="sleep apnea" if bdchm_label=="sleep apnea status"
replace bdchm_label="alcohol servings" if bdchm_label=="alcohol consumption"
replace bdchm_label="fruit servings" if bdchm_label=="fruit consumption"
replace bdchm_label="vegetable servings" if bdchm_label=="vegetable consumption"
	
	* Redact mapping if a time measurement got mapped to a non-time measurement BDCHV *;
	gen time_indic_var=1 if regexm(var_desc,"^days |days since| date$|^date |visit year|^age|age at|\(days\)|follow up days|\(years\)")
	/*gen test=1 if regexm(var_desc,"^date ")
	browse bdchm_label var_desc if test==1*/
	replace bdchm_label="" if time_indic_var==1 & !inlist(bdchm_label,"death","age at follow-up")
	replace bdchm_label="" if var_desc=="visit type"
	
	* Blood pressure mappings correct for diastolic & systolic *;
	gen diastolic=1 if regexm(lower(var_desc),"diastolic")
	gen systolic=1 if regexm(lower(var_desc),"systolic")
	gen bp=1 if regexm(bdchm_label,"blood pressure")
	replace bdchm_label="diastolic blood pressure" if bp==1 & diastolic==1
	replace bdchm_label="systolic blood pressure" if bp==1 & systolic==1



/* ----- 3. Correct units ----- */
/* Note: bad var_units occur due to data quality issues in dbgap metadata, and should ideally be fixed in the source data files read in at the top of program 1. They are handled for this processing pipeline by code below*/
gen servday=regexm(var_desc,"serv/day|daily|per day")
gen servweek=regexm(var_desc,"per week|weekly|serv/week")
replace var_units="{#}/d" if servday==1 & inlist(bdchm_label,"alcohol servings","fruit servings","vegetable servings") & (var_units=="" | var_units=="{servings}")
replace var_units="{#}/wk" if servweek==1 & inlist(bdchm_label,"alcohol servings","fruit servings","vegetable servings") & (var_units=="" | var_units=="{servings}")

gen hrs=regexm(var_desc,"how many hours|number of hours|hours")
gen kgm2=regexm(var_desc,"kg/m2")
replace var_units="h" if hrs==1 & bdchm_label=="sleep hours" & var_units==""
replace var_units="kg/m2" if kgm2==1 & var_units==""



/* ----- 4. Merge in key files of fixes from human-in-the-loop curation QC ----- */
/* Note: These key files are generated for the first time in DMCYAML_05_QC_forPy. */
capture confirm file "$doc\fixed_bdchm_mappings.dta" 
if _rc == 0 {
	sort phv bdchm_label
	gen pair_id=phv+bdchm_label
	merge m:1 pair_id using "$doc\fixed_bdchm_mappings.dta" 
	drop if _merge==2 /* n=0 */
	replace var_units=var_units_fixed if var_units_fixed!=""
	replace bdchm_label="" if bad_map=="1"
	drop _merge var_units_fixed bad_map
	}
else {
	display "File fixed_bdchm_mappings not found"
	}

* Add new phvs found during human in the loop curation *;
capture confirm file "$doc\add_phvs.dta"
if _rc == 0 {
	append using "$doc\add_phvs.dta"
	}
else {
	display "File add_phvs found"
	}




/* ----- 5. Save data ----- */
drop time_indic_var diastolic systolic bp hrs kgm2 servday servweek
duplicates drop /*n=100 dropped*/
drop if phv==""
drop if bdchm_label==""
gen merge_bdchm_label=subinstr(bdchm_label," ","",.)
order cohort bdchm_label phv phs pht var_name var_desc var_units var_type enum* example* 
sort bdchm_label phv enum_code
save "$temp\variable_mappings_short.dta", replace /*n=40,058*/
