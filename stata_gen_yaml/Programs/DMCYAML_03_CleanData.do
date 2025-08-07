/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_03_CleanData													*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/06/20															*/
/* Date Last Updated: 2025/08/07													*/
/* Description:	This program imports key spreadsheets with metadata.				*/
/*		1. Append & clean data														*/
/*		2. Correct BDCHM variable mappings											*/
/*		3. Save clean data															*/
/*		4. Merge in documentation 													*/
/*		5. Output unit mismatches for improvements to units.do						*/
/*		6. Prepare for YAML code generation											*/
/*																					*/
/* Notes:  																			*/
/*	- 2025/07/14 Step 1 appends FHS and noFHSnoCOPD data							*/
/*	  																				*/
/* -------------------------------------------------------------------------------- */


/* ----- 1. Append & clean data ----- */

* Append *;
clear
foreach dtaset in fhs_$today Export_BDCHM_noFHS-noCOPDGene_phv_mappings_$today {
	append using "$temp\\`dtaset'_drop.dta"
	}
duplicates drop 

* Variables *;
drop bdchm_variable

foreach var in var_id study_id data_table_id {
	split `var', p(".")
	}
rename var_id1 phv
rename study_id1 phs
rename data_table_id1 pht
drop var_id2 var_id3 study_id2 data_table_id2

* Values *; 
foreach var of varlist cohort var_units var_desc {
	replace `var'=lower(`var')
	}

* Cohort *;
replace cohort="hchs_sol" if cohort=="hchs/sol"
	
* Units *;
do "$prog\\units.do" var_units
	
* Type *;
replace var_type="categorical" if (enum_!="" | example_code!="")






/* ----- 2. Correct BDCHM variable mappings ----- */
/* Note: bad BDCHM mappings occurred during a manual process run by curators, and should ideally be fixed in the source data files read in at the top of program 1. They are handled for this processing pipeline by code below*/
replace bdchm_label=lower(bdchm_label) 
replace bdchm_label="stroke" if bdchm_label=="stroke status"
replace bdchm_label="red blood cell count" if bdchm_label=="red blood cell count volume"
replace bdchm_label="copd" if bdchm_label=="copd status"
replace bdchm_label="sleep apnea" if bdchm_label=="sleep apnea status"
replace bdchm_label="history of heart failure" if bdchm_label=="heart failure"

	* dbGap says "no data was collected for this variable" *;
	replace bdchm_label="" if inlist(phv,"phv00507051","phv00507200")

	* BUN *;
	replace bdchm_label="bun" if bdchm_label=="bun creatinine ratio" & inlist(phv,"phv00175987","phv00203866")
	
	* Carotid Stenosis *;
	gen left=0
	gen right=0
	replace left=1 if regexm(var_desc,"left|lft side")
	replace right=1 if regexm(var_desc,"right|rt side")
	replace bdchm_label="carotid stenosis left" if bdchm_label=="carotid stenosis" & left==1
	replace bdchm_label="carotid stenosis right" if bdchm_label=="carotid stenosis" & right==1
	replace bdchm_label="" if bdchm_label=="carotid stenosis" & inlist(var_desc,"age","cohort","calculated age at baseline")
	
	* Fasting lipids *;
	replace bdchm_label="" if bdchm_label=="fasting lipids" & inlist(phv,"phv00253225","phv00083303","phv00084980","phv00087524")
	
	* Height *;
	replace bdchm_label="" if bdchm_label=="height" & phv=="phv00206817"
	
	* Lactate *;
	replace bdchm_label="lactate in blood" if inlist(phv,"phv00166732","phv00172259","phv00255391","phv00521044","phv00521118")
		
	* Medication use - reassign to a more specific med use priority var *;
	foreach x in "ace inhibitor" "aldosterone receptor blocker" "alpha blocker" "angiotensin receptor blocker" "beta blocker" "calcium channel blocker" "centrally acting agent" "diuretic" "oral hypoglycemic agent" "systemic steroid" "vasodilator" {
		replace bdchm_label="taking `x's" if bdchm_label=="taking `x'"
		replace bdchm_label="taking `x's" if bdchm_label=="medication use" & regexm(var_desc,"`x'")==1
		}
	replace bdchm_label="taking angiotensin receptor blockers" if bdchm_label=="medication use" & regexm(var_desc,"angiotensin")==1
	replace bdchm_label="taking diuretics" if bdchm_label=="medication use" & regexm(var_desc,"diurectic")==1
	
	foreach x in "insulin" "non statin" "non-statin" "statin" {
		replace bdchm_label="taking `x'" if bdchm_label=="medication use" & regexm(var_desc,"`x'")==1
		}
	replace bdchm_label="taking statin medication" if bdchm_label=="taking statin"
	replace bdchm_label="taking medication for diabetes" if bdchm_label=="medication use" & regexm(var_desc,"diabetes")==1
	replace bdchm_label="taking alpha blockers" if bdchm_label=="medication use" & regexm(var_desc,"alpha")==1 & regexm(var_desc,"block")==1
	
	* Sleep apnea - define HVs for different apnea indices, then map phvs to those, not directy to Condition sleep apnea *;
	replace bdchm_label=lower("AHI Apnea-Hypopnea Index") if bdchm_label=="sleep apnea" & regexm(var_desc,"apnea/hypopnea index")
	replace bdchm_label="" if bdchm_label=="sleep apnea" & regexm(var_desc," rdi |obstructive|central") /* rdi=respiratory disturbance index */
	
	* White blood cells *;
	replace bdchm_label="" if inlist(phv,"phv00507187")
	
	* Neutrophils percent *;
	/*gen test=0*/
	foreach word in neutrophil lymphocyte {
		/*replace test=1 if regexm(var_desc,"`word'") & regexm(var_desc," % |percent")*/
		replace bdchm_label="`word's percent" if regexm(var_desc,"`word'") & regexm(var_desc," %|percent")
		}
		replace bdchm_label="lymphocytes percent" if phv=="phv00127622"
		replace bdchm_label="neutrophils percent" if inlist(phv,"phv00112694","phv00112697")
		replace bdchm_label="" if inlist(phv,"phv00112695")

	
	* Redact BDCHV mappings if it's a time measurement that got mapped to a non-time measurement BDCHV *;
	gen time_indic_var=1 if regexm(var_desc,"^days |days since| date$|^date |visit year|^age|age at|\(days\)|follow up days|\(years\)")
	/*gen test=1 if regexm(var_desc,"^date ")
	browse bdchm_label var_desc if test==1*/
	replace bdchm_label="" if time_indic_var==1 & !inlist(bdchm_label,"death","age at follow-up")
	replace bdchm_label="" if var_desc=="visit type"
	
	* Misc other problems *;
	replace bdchm_label="" if phv=="phv00206893" & bdchm_label=="mean arterial pressure" /*var in dbgap appears to actually be a measure of % coronary stenosis */
	replace bdchm_label="" if phv=="phv00156409" /*the same dataset has another variable that maps directly to alcohol servings/week, so mapping this var to the target BDCHV is unnecessary duplication */

gen merge_bdchm_label=subinstr(bdchm_label," ","",.)






/* ----- 3. Correct units ----- */
/* Note: bad var_units occur due to data quality issues in dbgap metadata, and should ideally be fixed in the source data files read in at the top of program 1. They are handled for this processing pipeline by code below*/
replace var_units="[IU]/L" if phv=="phv00007567" & bdchm_label=="ast sgot"
replace var_units="mL" if inlist(phv,"phv00083475","phv00083710","phv00087701")
replace var_units="{beats}/min" if phv=="phv00066705"
replace var_units="L" if inlist(phv,"phv00022586","phv00022598","phv00022611","phv00022624","phv00022637","phv00022652")
replace var_units="mmol/L" if inlist(phv,"phv00204734","phv00204735","phv00204738","phv00204765","phv00204766","phv00204767")
replace var_units="pmol/L" if phv=="phv00204739"
replace var_units="%{WBCs}" if inlist(phv,"phv00112694","phv00207259","phv00226284","phv00207274","phv00207261","phv00207276","phv00226285")
replace var_units="mg/d" if inlist(phv,"phv00203258","phv00208361","phv00208588")
replace var_units="pg/{cell}" if inlist(phv,"phv00294960")
replace var_units="g/d" if phv=="phv00156409"
replace var_units="mg/d" if phv=="phv00401150"
replace var_units="{servings}/d" if phv=="phv00112963"
replace var_units="g/mo" if inlist(phv,"phv00113830","phv00113924","phv00117620","phv00117734") /*The dietary history referenced intake for the previous month. */
replace var_units="g/d" if phv=="phv00401149"



gen servday=regexm(var_desc,"serv/day|daily|per day")
gen servweek=regexm(var_desc,"per week|weekly|serv/week")
gen hrs=regexm(var_desc,"how many hours|number of hours|hours")
gen kgm2=regexm(var_desc,"kg/m2")
replace var_units="{servings}/d" if servday==1 & inlist(bdchm_label,"alcohol","fruits","vegetables") & (var_units=="" | var_units=="{servings}")
replace var_units="{servings}/wk" if servweek==1 & inlist(bdchm_label,"alcohol","fruits","vegetables") & (var_units=="" | var_units=="{servings}")
replace var_units="h" if hrs==1 & bdchm_label=="sleep hours" & var_units==""
replace var_units="kg/m2" if kgm2==1 & var_units==""






/* ----- 3. Save clean data ----- */
order cohort bdchm_label phv phs pht var_name var_desc var_units var_type enum* example* 
sort merge_bdchm_label phv enum_code
drop left right time_indic_var servday servweek hrs kgm2
duplicates drop /*n=280 dropped*/
drop if bdchm_label==""
drop if phv==""
save "$temp\alldata_$today.dta", replace /*n=42890*/






/* ----- 4. Merge in documentation ----- */
use "$temp\alldata_$today.dta", clear

* Merge BDCHM key *;
merge m:1 merge_bdchm_label using "$doc\bdchm_key.dta"
/*tab bdchm_label _merge*/
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





/* ----- 5. Output unit mismatches for improvements to units.do ----- */
/* output mismatched unit rows to manually review for conversion rules */
use "$der\alldata_$today.dta", clear
keep if bdchm_entity=="MeasurementObservation" /*n=27928*/
keep bdchm_label phv var_desc var_units bdchm_unit conversion_rule equivalent_units cohort
sort var_units bdchm_unit phv
duplicates drop /*n=6220*/
drop if var_units=="" /*n=2804*/
drop if var_units==bdchm_unit /*n=800*/
drop if conversion_rule!="" /*n=451*/
drop if equivalent_units==1 /*n=233*/
tab var_units
/* isolate cohorts we're working on */
keep if inlist(cohort,"aric","cardia","jhs") /*n=57*/
sort bdchm_label var_units
export excel using "$doc\units_toreview_$today.xlsx", sheet("unit_key") first(var) nolabel keepcellfmt replace

/* Manual step: 
A. open the exported excel file. Do one or more of the following things with var_units values:
	1. If var_units just needs to be rewritten as a standard unit representation: 
		1a. Copy/paste var_units values into source_value col of "$doc\unit_harmonization.xlsx", sheet("unit_key")
		1b. Add the standard representation of the value to the standard_value column.
	2. If var_units (also) needs to be converted:
		2a. Copy/paste the standardized representations of the var_units that are being converted into this_unit col & that_unit col of "$doc\unit_harmonization.xlsx", sheet("conversions")
		2b. Write the YAML language conversion operation in conversion_rule column
		2c. If the conversion relies on other information, such as the biological substance being converted, then add the formula to the conversion_formula column
	3. If var_units are equivalent to another unit, then:
		3a. Add the equivalent units to the "equivalencies" tab.
		3b. Note any conditions that govern the equivalency, e.g. these are only equivalent when the noted condition is true
B. some unit representations or conversions may be dependent on the specific variable. these cases are not handled currently.
	1. conversion example: the entity eosinophils can be converted from a % to a total count if the total white blood cell count is known
	2. representation example: num/min can be validly represented as bpm instead only when the entity is heart rate
	3. IU/dL to percentage: 1 IU/dL equals 1% for some substances (e.g. factor viii) but not for others (e.g. vitamins or hormones)
C. some unit representations cannot be converted to the standard unit. these cases are not handled currently.
	1. data quality issues with var_units extracted from dbgap is the underlying root cause of the issue sometimes. 
	
*/





/* ----- 6. Prepare for YAML code generation ----- */
use "$der\alldata_$today.dta", clear

* Update units matches requiring more sophisticated rules *;
replace equivalent_units=1 if bdchm_label=="sodium in blood" & var_units=="meq/L" & bdchm_unit=="mmol/L"
replace conversion_rule="* 18" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & bdchm_label=="glucose in blood"
replace conversion_rule="* 38.67" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & bdchm_label=="hdl"
replace conversion_rule="* 38.67" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & bdchm_label=="total cholesterol in blood"
replace conversion_rule="* 88.57" if var_units=="mmol/L" & bdchm_unit=="mg/dL" & bdchm_label=="triglycerides in blood"
replace conversion_rule="* 0.3945" if phv=="phv00112974" /*note: goes from ml/day to g/day by multiplying by 0.789, then go from g/day to serving/day dividing by 14, then from serving/day to serving/week by multiplying by 7*/
replace conversion_rule="* 0.016420361" if var_units=="g/mo" & bdchm_unit=="{#}/wk" & bdchm_label=="alcohol" /* divide by 4.35 to get g/wk, then divide by 14 to get servings/week */


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
keep bdchm_entity bdchm_label bdchm_varname pht phv phs onto_id var_desc cohort bdchm_unit associatedvisit participantidphv var_units bdchm_unit has_pht has_onto unit_match unit_convert unit_expr row_good conversion_rule source_unit target_unit
duplicates drop
duplicates list phv 
		/*browse if inlist(phv,"phv00083163")*/	
save "$der\shortdata_$today.dta", replace /*n=11312*/






/* Improvements 
-----------------


Units
	- To handle missing var_units: store bdchm_unit in local macro, search the string of source_variable_description for the unit, then add that unit to the var_units field if it's found 
	
Associated Visits
	- If the pht is a range (ex: FHS Visit 1-4) then search the string of source_variable_description for words like exam or visit followed by a number, using PERL syntax



	