

foreach x in `1' {
replace `x' = lower(`x')
replace `x' = subinstr(`x'," ","",.)

replace `x'="%" if inlist(`x',"%ofnormal","percent","percentoftotalleukocytes")
replace `x'="1/2cup" if inlist(`x',"1/2cupor2-4sticks","1/2cupvegetables,or1cupofsoup","1/2fruitor1/2cup","1earor1/2cup","1fruit,1/2cupor5dried","1fruitor1/2cup")
replace `x'="10^3/mm3" if inlist(`x',"103/mm3","th/cmm","x1000/mm3")
replace `x'="10^3/ul" if inlist(`x',"10^3cells/ul","103/mm3","thou/ul(thousandspermicroliter)","thousands/ul","thousandspermicroliter","x10^3/ul","x10e3/ul")
replace `x'="10^6/mm3" if inlist(`x',"106/mm3","m/cmm")
replace `x'="10^6/ul" if inlist(`x',"count,x10e12","millions/ul","x10e6/ul")
replace `x'="10^9/l" if inlist(`x',"count,x10e9")
replace `x'="3-4oz" if inlist(`x',"3-4oz.")
replace `x'="agatstonunit" if inlist(`x',"Agatston unit")
replace `x'="bpm" if inlist(`x',"beats","beats/min","beats/minute","beatspermin","beatsperminute")
replace `x'="cells/ul" if inlist(`x',"kcell/ul")
replace `x'="cm" if inlist(`x',"centimeters")
replace `x'="cs" if inlist(`x',"hundredsofsecond","hundredthsofasec.","hundredthsofasecond","hundredthsofsecond")
replace `x'="days" if inlist(`x',"dayssinceexam1","numberofdayssinceexam1")
replace `x'="dg/dl" if inlist(`x',"decigrams/100ml")
replace `x'="dl" if inlist(`x',"deciliter")
replace `x'="events/hr" if inlist(`x',"#/hr","events/hour")
replace `x'="fl" if inlist(`x',"femtoliter")
replace `x'="ft" if inlist(`x',"feet")
replace `x'="g" if inlist(`x',"gm")
replace `x'="g/day" if inlist(`x',"g/24hr","g/d")
replace `x'="g/dl" if inlist(`x',"gm/dl")
replace `x'="hr" if inlist(`x',"hour","hours")
replace `x'="hu" if inlist(`x',"hounsfieldunits(hu)")
replace `x'="in" if inlist(`x',"inches","inches,tonextlower1/4inch","inchestonextlower1/4inch","tonextlower1/4inch")
replace `x'="iu" if inlist(`x',"i.u.")
replace `x'="iu/l" if inlist(`x',"u/l")
replace `x'="kcell/ul" if inlist(`x',"kcell/mcl")
replace `x'="l" if inlist(`x',"liters","litres")
replace `x'="lbs" if inlist(`x',"lb","pounds","pounds,tonearestpound")
replace `x'="meq/l" if inlist(`x',"meq/liter")
replace `x'="meq/l(x100)" if inlist(`x',"meq/liter(x100)")
replace `x'="mg/day" if inlist(`x',"mg/24hours","mg/24hr","mg/d")
replace `x'="mg/dl" if inlist(`x',"mg/100ml","mgper100ml","mgperdl")
replace `x'="mg/g" if inlist(`x',"mg/gcr")
replace `x'="min" if inlist(`x',"minutes")
replace `x'="miu/l" if inlist(`x',"mul")
replace `x'="miu/ml" if inlist(`x',"mu/ml")
replace `x'="ml/day" if inlist(`x',"ml/alcohol/day")
replace `x'="ml/min/1.73m2" if inlist(`x',"ml/min/1.73m^2","ml/minper1.73m2")
replace `x'="mm3(10^3/ul)" if inlist(`x',"mm3(1,000,000/microliter)","mm3(1,000,000permicroliter)")
replace `x'="mmhg" if inlist(`x',"hgmm","mm/hg","tonearest2mm/hg","tonearest2mmhg")
replace `x'="mmol/dl" if inlist(`x',"mmoles/dl")
replace `x'="mmol/l" if inlist(`x',"mmolperl")
replace `x'="month" if inlist(`x',"months")
replace `x'="ms" if inlist(`x',"millisec","milliseconds","msec")
replace `x'="ng/ml" if inlist(`x',"plasmang/ml")
replace `x'="none" if inlist(`x',"codes","n/a","numberofkids","numberofsiblings")
replace `x'="num/day" if inlist(`x',"cigarette/day","cigarettes/day","cigarettesperday")
replace `x'="num/ml" if inlist(`x',"platelets/ml")
replace `x'="num/ul" if inlist(`x',"number/microl")
replace `x'="oz" if inlist(`x',"1oz","1oz.or1/2cup")
replace `x'="s" if inlist(`x',"seconds")
replace `x'="score" if inlist(`x',"scale")
replace `x'="servings" if inlist(`x',"1serving")
replace `x'="servings/week" if inlist(`x',"drinks/week","servingsperweek")
replace `x'="tbs" if inlist(`x',"1tbs")
replace `x'="ug/l" if inlist(`x',"mcg/l")
replace `x'="uiu/ml" if inlist(`x',"microu/ml","uu/ml")
replace `x'="um3" if inlist(`x',"microm3","um3(micrometerscubed)")
replace `x'="uv" if inlist(`x',"microvolts")
replace `x'="x10^3/ul" if inlist(`x',"x10e3/ul")
replace `x'="years" if inlist(`x',"numberofyearssinceexam1","year","yearsold")






replace `x'="" if inlist(`x',"none")
}



/* add this codeline if need be

replace `x'="" if inlist(`x',"none")