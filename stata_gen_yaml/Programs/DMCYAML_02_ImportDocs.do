/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_02_ImportDocs													*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/06/20															*/
/* Date Last Updated: 2025/07/18													*/
/* Description:	This program imports key documentation used to enrich data files.	*/
/*		0. Read in data																*/
/*		1. Unit documentation														*/
/* 		2. BDCHM priority variables													*/
/*		3. dbGAP datasets: phts, participants, visits								*/
/*																					*/
/* Notes:  																			*/
/*		- unit_standardization.xlsx is a manually curated crosswalk of unit values	*/
/*		  and their standardized equivalent representations.						*/
/*		- BDCHM priority variables & dbGAP datasets are both from "BDCHM Variable	*/
/*		  Mapping" at https://docs.google.com/spreadsheets/d/1hxbZxSx				*/
/*		  R88HnBXjcgdeJD1AOj-pzlxMrnx5n_YLkEF0/edit?gid=2039879463#gid=2039879463	*/
/* -------------------------------------------------------------------------------- */


/* ----- 0. Read in data ----- */
foreach tab in "BDCHM Harmonized Variables V1" "contextual variables V2" {
import excel using "$doc\BDCHM Variable Mapping.xlsx", sheet("`tab'") firstrow case(lower) allstring clear
	foreach x of varlist * {
		replace `x'=subinstr(`x', "`=char(10)'", "`=char(32)'", .) /* replace linebreaks inside cells with a space */
		replace `x'=strtrim(`x')
		replace `x'=stritrim(`x')
		replace `x'=ustrtrim(`x')
		} 
missings dropvars, force
local tab2 = subinstr("`tab'"," ","",.)
save "$temp\\`tab2'.dta", replace
}



/* ----- 1. Unit documentation ----- */
* Write code to standardize values of bdchm_unit based on unit_harmonization crosswalk *;
foreach tab in unit_key conversions equivalencies ucum {
import excel using "$doc\unit_harmonization.xlsx", sheet("`tab'") firstrow allstring clear
save "$temp\\`tab'.dta", replace
}

/* should we replace the units for 1/2 and 1/4cup to be cup units, then do the operand? */

* Unit key *;
use "$temp\\unit_key.dta", clear
drop note
drop if standard_value==""
sort standard_value
drop if source_value==standard_value
gen item=`"`=char(34)'"'+source_value+`"`=char(34)'"'+","
gen rep_value=`"`=char(34)'"'+standard_value+`"`=char(34)'"'
keep rep_value item
duplicates drop
sort rep_value
by rep_value: gen count=_n
summ count
local numitems = "item`r(max)'"
reshape wide item, i(rep_value) j(count)
egen items=concat(item1-`numitems')
replace items=substr(items, 1, strlen(items) - 1)

gen code="replace `=char(96)'x`=char(39)'="+rep_value+" if inlist(`=char(96)'x`=char(39)',"+items+")"

keep code
export delimited "$prog\units.txt", delimiter(tab) novarnames /*datafmt quote*/ noquote replace 
/* Manual step:  paste output into units.do as codelines*/


* Unit conversion key *;
use "$temp\\conversions.dta", clear
gen unit_merge_key=this_unit+"_"+that_unit
sort unit_merge_key
save "$doc\conversions.dta", replace


* Unit equivalencies key *;
use "$temp\\equivalencies.dta", clear	
keep if equivalency_always=="1"
gen unit_merge_key=this_unit+"_"+that_unit
sort unit_merge_key
keep unit_merge_key
gen equivalent_units=1
save "$doc\equivalencies.dta", replace







/* ----- 2. BDCHM priority variables ----- */
use "$temp\\BDCHMHarmonizedVariablesV1.dta", clear
keep bdchmelementattribute variablelabel variablemachinereadablename standardizeddatatype standardizedunit omopstandardconceptid obacurie
drop if bdchmelementattribute==""

* Rename vars *;
split bdchmelementattribute, p(".")
rename bdchmelementattribute1 bdchm_entity
drop bdchmelementattribute2-bdchmelementattribute3
order bdchm_entity
label var bdchm_entity "BDCHM Entity, from key"

rename variablelabel bdchm_varlabel
label var bdchm_varlabel "BDCHM Variable Label, from key"

rename variablemachinereadablename bdchm_varname
label var bdchm_varname "BDCHM Variable Name, from key"
	
rename standardizeddatatype bdchm_vartype
label var bdchm_vartype "BDCHM Variable Type, from key"

* Units *;
rename standardizedunit bdchm_unit
do "$prog\\units.do" bdchm_unit

* Ontologies *;
replace obacurie="" if inlist(obacurie,"Same as platelet quantity?","REQUESTED")
replace omopstandardconceptid="434489" if omopstandardconceptid=="434489 or 4306655"
replace omopstandardconceptid="" if inlist(omopstandardconceptid,"need to curate through a concept set")
gen omopid="OMOP:"+omopstandardconceptid if omopstandardconceptid!=""
rename obacurie obaid
	gen onto_id=obaid
	replace onto_id=omopid if obaid==""
	replace onto_id=omopid if inlist(bdchm_varname,"carotid_imt")
tab onto_id, miss

* Prep for merging *;
gen merge_bdchm_label=lower(bdchm_varlabel) 	
replace merge_bdchm_label=subinstr(merge_bdchm_label," ","",.)
sort merge_bdchm_label
save "$doc\bdchm_key.dta", replace



/* ----- 3. dbGAP datasets: phts, participants, visits ----- */
use "$temp\contextualvariablesv2.dta", clear
rename datatablepht pht
replace associatedvisit=upper(associatedvisit)
drop datatablename notes
drop if pht==""
duplicates drop
sort pht
save "$doc\pht_visit.dta", replace



