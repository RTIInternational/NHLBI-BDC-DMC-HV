/* --------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									 */
/* RTI PI: Chris Siege																 */
/* Program: DMCYAML_06_QC													 		 */
/* Programmer: Sabrina McCutchan (CDMS)												 */
/* Date Created: 2025/07/22															 */
/* Date Last Updated: 2025/11/13													 */
/* Description:	This program identifies rows that fail readiness checks for YAML code*/
/*   auto-generation. 																 */
/*		1. Output "bad" phvs to a spreadsheet										 */
/*		2. Manually curate "bad" phvs								 				 */
/*		3. Compile all "fixed_bdchm_mappings" spreadsheets for each cohort			 */
/*		4. Output unit mismatches for improvements to units.do						 */
/*																					 */
/* Notes:  																			 */
/*	- The $doc files output in step 3 of this program get read-in back in program	 */
/*		DMCYAML_04_CurateData.do													 */
/*	- The file output in step 4 is used to enable a human curator to update values	 */
/*		in $doc\unit_harmonization to improve standardized unit representations		 */
/*	  																				 */
/* --------------------------------------------------------------------------------- */


/* ----- 1. Output "bad" phvs to a spreadsheet ----- */

/* Note: change value of cohort local macro to desired cohort before running */
clear
local entity = "MeasurementObservation"
/*local cohort = "aric"
local macroname = "`entity'_`cohort'" */


foreach cohort in aric cardia fhs jhs whi {	
use "$der\shortdata_$today.dta", clear
keep if row_good!=1
keep if bdchm_entity=="`entity'"
keep if cohort=="`cohort'"
drop phs onto_id
foreach var in varlist bad_map expr add_var_units note added_phv {
	gen `var'=""
	}
sort bdchm_label var_desc phv
save "$out\\`cohort'\fixed\fix_bdchm_mappings_$today.dta", replace
export delimited using "$out\\`cohort'\fixed\fix_bdchm_mappings_$today.csv", nolabel quote replace
}




/* ----- 2. Manually curate "bad" phvs ----- */
* Manually review the output from previous step, saving the file with manual changes to the same name, except replacing "fix" with "fixed" in the filename. *;

/* Manual step: 
A. Open the exported spreadsheet in step 1 above, "fix_bdchm_mappings_$today.csv"
B. Immediately save a copy of the file in the same folder location with the name: "fixed_bdchm_mappings_$today.csv" (note the only change is from "fix" to "fixed")
C. Row by row, manually review each phv in the spreadsheet to identify which YAML-readiness validation check was failed.
    1. Curators may need to consult online documentation from dbGAP or a cohort-maintained website to locate correct metadata
D. Make one or more of the following changes to rows in "fixed_bdchm_mappings_$today.csv" to enable that row to pass validation checks:
	1. If var_units are missing:
			1a. Look up the phv in source documentation to identify correct unit
			1b. Enter the standardized UCUM representation of the unit in the var_units column for the phv
			1c. Enter a value of "1" in the column "add_var_units"
	2. If the phv should not have been mapped to the BDCHV identified in column bdchm_varname:
			2a. Enter a value of "1" in the column "bad_map"
			2b. Note: if dbGap reports "no data was collected for this variable", the phv is considered a bad map
	3. If the phv is mapped to the correct BDCHV but its units must be converted:
			3a. Enter the conversion expression in column "expr"
	4. If the phv is mapped to the correct BDCHV but there is a complex relationship between the source variable(s) and the target BDCHV:
			4a. Enter the case statement in column "expr"
	5. If a different phv is discovered corresponding to the BDCHV and that phv is not currently present in the curation pipeline:
			5a. Create a new blank row in the spreadsheet
			5b. Enter values in columns cohort-participantidphv
E. If a GitHub issue was opened related to the phv, add the GitHub issue number to the column "note"
F. Note: sometimes a phv mapped to the correct BDCHV may require more complicated YAML code to correctly perform the conversion. In these cases, add the value "manually fixed" to the column "note"
	1. This will result in the row being output in a "bad" YAML code output. It can then be manually fixed at that stage of the pipeline.
G. Save all changes made to the file "fixed_bdchm_mappings_$today.csv"
*/




/* ----- 3. Compile all "fixed_bdchm_mappings" spreadsheets for each cohort ----- */

* -- ARIC -- *;
import delimited using "$out\aric\fixed\fixed_bdchm_mappings_2025-08-07.csv", varnames(1) case(preserve) emptylines(skip) bindquotes(strict) stringcols(_all) clear
drop if note=="manually fixed"
rename var_units var_units_fixed
rename expr expr_custom
sort phv bdchm_label
gen pair_id=phv+bdchm_label
duplicates drop
save "$temp\aric\fixed_bdchm_mappings.dta", replace

* -- CARDIA -- *;
import delimited using "$out\cardia\fixed\fixed_bdchm_mappings_2025-08-10.csv", varnames(1) case(preserve) emptylines(skip) bindquotes(strict) stringcols(_all) clear
drop if note=="manually fixed"
rename var_units var_units_fixed
rename expr expr_custom
sort phv bdchm_label
gen pair_id=phv+bdchm_label
duplicates drop
save "$temp\cardia\fixed_bdchm_mappings.dta", replace

* -- JHS -- *;
import delimited using "$out\jhs\fixed\fixed_bdchm_mappings_2025-08-18.csv", varnames(1) case(preserve) emptylines(skip) bindquotes(strict) stringcols(_all) clear
drop if substr(note,1,8)=="manually"
rename var_units var_units_fixed
rename expr expr_custom
sort phv bdchm_label
gen pair_id=phv+bdchm_label
duplicates drop
save "$temp\jhs\fixed_bdchm_mappings.dta", replace


* -- Compile -- *;
use "$temp\aric\fixed_bdchm_mappings.dta", clear
append using "$temp\cardia\fixed_bdchm_mappings.dta"
append using "$temp\jhs\fixed_bdchm_mappings.dta"
save "$temp\fixed_bdchm_mappings.dta", replace


* -- Create key of fixed mappings -- *;
use "$temp\fixed_bdchm_mappings.dta", clear
drop if add_map=="1"
keep pair_id bad_map var_units_fixed expr_custom add_map
duplicates drop
save "$doc\fixed_bdchm_mappings.dta", replace /* directory changed from temp to doc */


* -- Create key of phvs added during manual review -- *;
use "$temp\fixed_bdchm_mappings.dta", clear
keep if add_map=="1"
keep cohort bdchm_label phv pht var_desc var_units	
gen merge_bdchm_label=subinstr(bdchm_label," ","",.)
save "$doc\add_phvs.dta", replace








/* ----- 4. Output unit mismatches for improvements to units.do ----- */
/* output mismatched unit rows to manually review for conversion rules */
/*use "$der\alldata_$today.dta", clear*/
use "$der\shortdata_$today.dta", clear
keep if bdchm_entity=="MeasurementObservation" /*n=5,691*/
keep bdchm_label phv var_desc var_units bdchm_unit conversion_rule equivalent_units cohort
sort var_units bdchm_unit phv
duplicates drop /*n=5722*/
drop if var_units=="" /*n=3198*/
drop if var_units==bdchm_unit /*n=801*/
drop if conversion_rule!="" /*n=405*/
drop if equivalent_units==1 /*n=173*/
tab var_units
/* isolate cohorts we're working on */
keep if inlist(cohort,"aric","cardia","jhs") /*n=46*/
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
	1. data quality issues with var_units extracted from dbgap is sometimes the underlying root cause of this issue. 
	
*/