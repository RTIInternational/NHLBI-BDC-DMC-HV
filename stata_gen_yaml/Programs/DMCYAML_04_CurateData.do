/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_03_CleanData													*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/11/12															*/
/* Date Last Updated: 2025/11/13													*/
/* Description:	This program performs single cell/row value overrides enabled by 	*/
/*	   manual curation reviews. It also outputs unit mismatches between source data	*/
/*	   and BDCHV definitions.														*/
/*		1. Exclude rows/variables													*/
/*		2. Correct BDCHM variable mappings											*/
/*		3. Correct units															*/
/*		4. Merge in key file of manually corrected data								*/
/*		5. Save curated data														*/
/*																					*/
/* Notes:  																			*/
/*	- This program code may be edited by curators to log other cell or row specific	*/
/*		value overrides. 															*/
/*	- Curators may use the unit mismatches output in step 6 to improve the unit key	*/
/*	   "$doc\unit_harmonization.xlsx"												*/
/*	  																				*/
/* -------------------------------------------------------------------------------- */


use "$temp\alldata_clean.dta", clear



/* ----- 1. Exclude rows/variables ----- */
* dbGap says "no data was collected for this variable" *;
drop if inlist(phv,"phv00507051","phv00507200")

* Misc other problems *;
drop if phv=="phv00206893" & bdchm_label=="mean arterial pressure" /*var in dbgap appears to actually be a measure of % coronary stenosis */
drop if phv=="phv00156409" /*the same dataset has another variable that maps directly to alcohol servings/week, so mapping this var to the target BDCHV is unnecessary duplication */





/* ----- 2. Correct BDCHM variable mappings ----- */
/* Note: bad BDCHM mappings occurred during a manual process run by curators, and should ideally be fixed in the source data files read in at the top of program 1. They are handled for this processing pipeline by code below*/

	* BUN *;
	replace bdchm_label="bun" if bdchm_label=="bun creatinine ratio" & inlist(phv,"phv00175987","phv00203866")
	
	* Fasting lipids *;
	replace bdchm_label="" if bdchm_label=="fasting lipids" & inlist(phv,"phv00253225","phv00083303","phv00084980","phv00087524")
	
	* Height *;
	replace bdchm_label="" if bdchm_label=="height" & phv=="phv00206817"
	
	* Lactate *;
	replace bdchm_label="lactate in blood" if inlist(phv,"phv00166732","phv00172259","phv00255391","phv00521044","phv00521118")
	
	* White blood cells *;
	replace bdchm_label="" if inlist(phv,"phv00507187")
	
	* Neutrophils percent *;
	replace bdchm_label="lymphocytes percent" if phv=="phv00127622"
	replace bdchm_label="neutrophils percent" if inlist(phv,"phv00112694","phv00112697")
	replace bdchm_label="" if inlist(phv,"phv00112695")
		

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






/* ----- 4. Merge in key files of manually corrected data ----- */
* Note: the two files $doc\add_phvs & $doc\fixed_bdchm_mappings are output by DMCYAML_06_QC  *;
sort phv bdchm_label
gen pair_id=phv+bdchm_label
merge m:1 pair_id using "$doc\fixed_bdchm_mappings.dta" 
drop if _merge==2 /* n=3. these are 3 med adher maps */
replace var_units=var_units_fixed if var_units_fixed!=""
replace bdchm_label="" if bad_map=="1"
drop _merge var_units_fixed bad_map

* Add new phvs I manually added to "fixed" files *;
append using "$doc\add_phvs.dta"








/* ----- 5. Save curated data ----- */

* Suppress output of files that Anne has done manually - see GitHub issues *;
/* ARIC */ replace bdchm_label="" if cohort=="aric" & inlist(bdchm_label,"troponin all types","carotid imt","carotid stenosis left","carotid stenosis right")
replace bdchm_label="" if cohort=="jhs" & inlist(bdchm_label,"carotid imt") /* GitHub issue 239 */

order cohort bdchm_label phv phs pht var_name var_desc var_units var_type enum* example* 
sort merge_bdchm_label phv enum_code
duplicates drop 
drop if bdchm_label==""
drop if phv==""
save "$temp\alldata_curate.dta", replace /*n=42005*/

