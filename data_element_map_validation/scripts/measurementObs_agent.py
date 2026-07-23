#!/usr/bin/env python3
"""Map a lab result / vital sign / quantitative measurement description to a LOINC code.

Uses NLM LOINC clinical tables API (public, no credentials required):
  GET https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search?terms=<query>&df=...

Note: fhir.loinc.org requires a free LOINC account; use NLM API instead.

Ranking:
  1.00  exact Long Common Name match (case-insensitive)
  0.95  exact Component or Short Name match
  0.90  component substring match at word boundary
  0.87  query is a word-boundary substring of the component
  else  difflib ratio * length_factor^0.4

Preferred (bonus applied, not exclusive):
  - SCALE_TYP = Qn  (quantitative, +0.02)
  - TIME_ASPCT = Pt (point in time, +0.01)
  - Specimen hint match (+0.03) or mismatch (-0.05)

Output format:  LOINC:<code>   e.g.  LOINC:718-7

Usage examples:
  python measurementObs_agent.py "hemoglobin"
  python measurementObs_agent.py "basophils" --specimen blood --top 3
  python measurementObs_agent.py "FEV1 post-bronchodilator"
  python measurementObs_agent.py "heart rate bpm" --id-only
  python measurementObs_agent.py "systolic blood pressure" --top 5
"""

import json
import re
import sys
from difflib import SequenceMatcher
from urllib.parse import urlencode

import click
import requests

NLM_LOINC_URL = "https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search"

# ---------------------------------------------------------------------------
# Curated synonym map: loinc_code → (canonical long name, frozenset of aliases)
# Covers abbreviations and study-variable phrasings that NLM search misses.
# ---------------------------------------------------------------------------
LOINC_SYNONYMS: dict[str, tuple[str, frozenset]] = {
    # CBC
    "718-7":   ("Hemoglobin [Mass/volume] in Blood",
                frozenset({"hemoglobin", "hgb", "hb", "hgb (g/dl)", "hemoglobin g/dl", "hgb (g/dL)"})),
    "4544-3":  ("Hematocrit [Volume Fraction] of Blood by Automated count",
                frozenset({"hematocrit", "hct", "hct (%)", "haematocrit", "hematocrit pct"})),
    "785-6":   ("MCH [Entitic mass] by Automated count",
                frozenset({"mch", "mch (pg)", "mean corpuscular hemoglobin", "mch pg"})),
    "787-2":   ("MCV [Entitic volume] by Automated count",
                frozenset({"mcv", "mcv (fl)", "mean corpuscular volume", "mcv fl"})),
    "786-4":   ("MCHC [Entitic Mass/volume] in Red Blood Cells by Automated count",
                frozenset({"mchc", "mchc (g/dl)", "mean corpuscular hemoglobin concentration", "mchc g/dl"})),
    "789-8":   ("Erythrocytes [#/volume] in Blood by Automated count",
                frozenset({"rbc", "red blood cell count", "red blood cells", "erythrocytes", "rbc count"})),
    "6690-2":  ("Leukocytes [#/volume] in Blood by Automated count",
                frozenset({"wbc", "white blood cell count", "white blood cells", "leukocytes", "wbc count"})),
    "26444-0": ("Basophils [#/volume] in Blood",
                frozenset({"basophils", "basophil", "basophil count", "baso", "basophl"})),
    "26449-9": ("Eosinophils [#/volume] in Blood",
                frozenset({"eosinophils", "eosinophil", "eosinophil count", "eos", "eosinphl"})),
    "26474-7": ("Lymphocytes [#/volume] in Blood",
                frozenset({"lymphocytes", "lymphocyte", "lymphocyte count", "lymph", "lymphcyt"})),
    "26484-6": ("Monocytes [#/volume] in Blood",
                frozenset({"monocytes", "monocyte", "monocyte count", "mono", "monocyt"})),
    "26499-4": ("Neutrophils [#/volume] in Blood",
                frozenset({"neutrophils", "neutrophil", "neutrophil count", "neut", "neutrophl"})),
    "777-3":   ("Platelets [#/volume] in Blood",
                frozenset({"platelets", "plt", "platelet count", "thrombocytes"})),
    # Vitals
    "8867-4":  ("Heart rate",
                frozenset({"heart rate", "hr", "heart rate bpm", "pulse rate", "pulse"})),
    "8480-6":  ("Systolic blood pressure",
                frozenset({"systolic blood pressure", "sbp", "sysbp", "sys bp",
                           "systolic bp", "blood pressure systolic"})),
    "8462-4":  ("Diastolic blood pressure",
                frozenset({"diastolic blood pressure", "dbp", "diabp", "dias bp",
                           "diastolic bp", "blood pressure diastolic"})),
    "59408-5": ("Oxygen saturation in Arterial blood by Pulse oximetry",
                frozenset({"spo2", "sao2", "oxygen saturation", "o2 sat", "o2sat",
                           "resting sao2", "resting sao2 %", "resting spo2",
                           "pulse oximetry", "pulse ox"})),
    "8302-2":  ("Body height",
                frozenset({"height", "body height", "height cm", "stature", "ht",
                           "height_cm"})),
    "29463-7": ("Body weight",
                frozenset({"weight", "body weight", "weight kg", "wt", "body wt",
                           "weight_kg"})),
    "39156-5": ("Body mass index (BMI) [Ratio]",
                frozenset({"bmi", "body mass index", "body mass index (bmi)"})),
    "8280-0":  ("Waist Circumference at umbilicus by Tape measure",
                frozenset({"waist circumference", "waist circ", "waist circumference cm",
                           "waist_cm", "waist circumference, cm"})),
    # Spirometry
    "20150-9": ("FEV1",
                frozenset({"fev1", "fev1 pre", "fev1 pre-bronchodilator",
                           "forced expiratory volume 1", "fev1_pre"})),
    "20155-8": ("FEV1 --post bronchodilation",
                frozenset({"fev1 post", "fev1 post-bronchodilator", "fev1 postbronchodilator",
                           "fev1_post", "fev1 after bronchodilator"})),
    "20157-4": ("FEV1/FVC",
                frozenset({"fev1/fvc", "fev1 fvc ratio", "fev1/fvc ratio",
                           "fev1 fvc", "fev1_fvc"})),
    "19875-1": ("FEV1/FVC --post bronchodilation",
                frozenset({"fev1/fvc post", "fev1/fvc post-bronchodilator",
                           "fev1_fvc_post"})),
    "19874-4": ("FEV1/FVC --pre bronchodilation",
                frozenset({"fev1/fvc pre", "fev1/fvc pre-bronchodilator",
                           "fev1_fvc_pre"})),
    "19870-2": ("FVC --post bronchodilation",
                frozenset({"fvc post", "fvc post-bronchodilator", "fvc_post",
                           "fvc after bronchodilator"})),
    "19868-6": ("FVC --pre bronchodilation",
                frozenset({"fvc pre", "fvc pre-bronchodilator", "fvc_pre",
                           "fvc before bronchodilator"})),
    "20152-5": ("FVC",
                frozenset({"fvc", "forced vital capacity"})),
    # Percents predicted
    "20151-7": ("FEV1/Predicted --post bronchodilation",
                frozenset({"fev1 % pred post", "fev1 percent predicted post",
                           "fev1pp post", "fev1 % pred post-bronchodilator",
                           "fev1pp_post"})),
    "20149-3": ("FEV1/Predicted",
                frozenset({"fev1 % pred", "fev1 percent predicted",
                           "fev1pp", "predicted fev1 pct"})),
}

# Reverse index: alias → loinc_code (built at module load)
_ALIAS_TO_LOINC: dict[str, str] = {}
for _code, (_name, _aliases) in LOINC_SYNONYMS.items():
    _ALIAS_TO_LOINC[_name.lower()] = _code
    for _alias in _aliases:
        _ALIAS_TO_LOINC[_alias.lower()] = _code


def _curated_match(query: str) -> dict | None:
    """Return a curated LOINC entry if the query matches an alias, else None."""
    q = query.lower().strip()
    # Exact alias match
    code = _ALIAS_TO_LOINC.get(q)
    # Cleaned alias match (strip units and punctuation)
    if code is None:
        q_clean = _UNIT_PAREN_RE.sub(" ", q)
        q_clean = _PUNCTUATION_RE.sub(" ", q_clean).strip()
        code = _ALIAS_TO_LOINC.get(q_clean)
    # Partial: check if any alias is contained in the query at word boundary
    if code is None:
        for alias, lcode in _ALIAS_TO_LOINC.items():
            if len(alias) >= 3 and _word_in(alias, q):
                code = lcode
                break
    if code is None:
        return None
    canonical, _ = LOINC_SYNONYMS[code]
    system, scale = _parse_long_name(canonical)
    return {
        "loinc_id":         f"LOINC:{code}",
        "long_common_name": canonical,
        "component":        canonical.split("[")[0].strip().split("--")[0].strip(),
        "system":           system,
        "scale_typ":        scale,
        "method_typ":       "",
        "shortname":        "",
        "class_":           "",
        "score":            1.0,
    }


# Words to remove before sending a query to the NLM API
_SEARCH_STOPWORDS = frozenset({
    "a", "an", "the", "at", "in", "of", "or", "by", "and",
    "resting", "predicted", "pred", "post", "pre",
    "measure", "1st", "2nd", "first", "second",
    "cm", "mm", "kg", "lb", "bpm", "pg", "fl", "fl",
})

# Remove parenthetical units: (K/uL), (g/dL), (%), etc.
_UNIT_PAREN_RE = re.compile(r"\([^)]*\)")
_PUNCTUATION_RE = re.compile(r"[%,;:/\\]")

_DF_FIELDS = [
    "LOINC_NUM",
    "LONG_COMMON_NAME",
    "COMPONENT",
    "SYSTEM",
    "SCALE_TYP",
    "TIME_ASPCT",
    "METHOD_TYP",
    "SHORTNAME",
    "CLASS",
]

# Specimen abbreviation map used in LOINC SYSTEM field
_SPECIMEN_MAP: dict[str, list[str]] = {
    "blood":   ["Bld", "BldC", "BldMV", "BldA", "BldV"],
    "serum":   ["Ser", "Ser/Plas", "Plas", "Plas/Bld/Ser"],
    "urine":   ["Urine", "Ur"],
    "sputum":  ["Sput"],
    "breath":  ["Exhaled gas", "Exhaled"],
    "plasma":  ["Plas", "Ser/Plas"],
    "csf":     ["CSF"],
}


def _clean_query(description: str) -> str:
    """Strip units, punctuation, and noise words for NLM API search."""
    q = _UNIT_PAREN_RE.sub(" ", description)   # remove (K/uL), (pg), etc.
    q = _PUNCTUATION_RE.sub(" ", q)             # remove % , : / \ ;
    tokens = [t for t in q.split() if t.lower() not in _SEARCH_STOPWORDS and len(t) > 1]
    return " ".join(tokens)


def _search_loinc(query: str, max_results: int = 40) -> list[dict]:
    """Fetch LOINC candidates from NLM search API.

    NLM API response format:
      [total_count, [loinc_num_list], null, [[row_values_per_df_field], ...]]
    The df parameter fields are the field names for rows in index 3.
    """
    params = {
        "terms": query,
        "df": ",".join(_DF_FIELDS),
        "maxList": max_results,
    }
    url = f"{NLM_LOINC_URL}?{urlencode(params)}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # index 0: total, index 1: loinc codes (not field names), index 3: rows
    if len(data) < 4 or not data[3]:
        return []
    return [dict(zip(_DF_FIELDS, row)) for row in data[3]]


_SYSTEM_RE = re.compile(r"\bin\s+([A-Za-z][\w/. ()-]+?)(?:\s+by\s+|\s*$)", re.IGNORECASE)
_PROP_RE = re.compile(r"\[([^\]]+)\]")
_QN_PROPS = frozenset({
    "mass/volume", "moles/volume", "#/volume", "number/volume",
    "ratio", "mass/time", "volume/time", "arbitrary units/volume",
    "pure mass fraction", "% of hemoglobin", "% of total",
})


def _parse_long_name(long_name: str) -> tuple[str, str]:
    """Extract (system, scale_type) from a LOINC LONG_COMMON_NAME.

    Examples:
      'Hemoglobin [Mass/volume] in Blood'  → ('Blood', 'Qn')
      'Basophils [#/volume] in Blood'      → ('Blood', 'Qn')
      'Smoking status'                     → ('', '')
    """
    system = ""
    scale = ""
    m = _SYSTEM_RE.search(long_name)
    if m:
        system = m.group(1).strip()
    props = [p.lower() for p in _PROP_RE.findall(long_name)]
    if any(p in _QN_PROPS for p in props):
        scale = "Qn"
    return system, scale


def _word_in(phrase: str, text: str) -> bool:
    """Return True if phrase appears at a word boundary in text."""
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def _specimen_matches(system: str, hint: str) -> bool | None:
    """Return True/False/None if specimen system matches/mismatches/unknown."""
    if not hint or not system:
        return None
    hint_l = hint.lower()
    sys_l = system.lower()
    expected_systems = _SPECIMEN_MAP.get(hint_l, [hint_l])
    for s in expected_systems:
        if s.lower() in sys_l or sys_l in s.lower():
            return True
    return False


def _similarity(query: str, entry: dict, specimen_hint: str = "") -> float:
    """Three-tier + fuzzy similarity score for a LOINC entry vs query."""
    q = query.lower().strip()
    long_name = (entry.get("LONG_COMMON_NAME") or "").lower()
    component = (entry.get("COMPONENT") or "").lower()
    short_name = (entry.get("SHORTNAME") or "").lower()

    # Parse system and scale from long name (NLM API does not populate those fields)
    system, scale = _parse_long_name(long_name)

    # Penalise deprecated codes heavily
    if long_name.startswith("deprecated"):
        return 0.0

    # Tier 1: exact long common name
    if q == long_name:
        score = 1.0
    # Tier 2: exact component or short name
    elif q == component or q == short_name:
        score = 0.95
    # Tier 3: component at word boundary in query, or query in component
    elif component and _word_in(component, q):
        score = 0.90
    elif component and _word_in(q, component):
        score = 0.87
    else:
        # Tier 4: fuzzy against long common name and component
        r_long = SequenceMatcher(None, q, long_name).ratio()
        r_comp = SequenceMatcher(None, q, component).ratio()
        raw = max(r_long, r_comp)
        len_factor = len(q) / max(len(q), len(long_name)) if long_name else 0.5
        score = raw * (len_factor ** 0.4)

    # Quantitative bonus (preferred for lab/vital measurements)
    if scale == "Qn":
        score = min(score + 0.02, 1.0)

    # Specimen hint bonus / penalty — compare against parsed system
    match = _specimen_matches(system, specimen_hint)
    if match is True:
        score = min(score + 0.03, 1.0)
    elif match is False:
        score = max(score - 0.05, 0.0)

    return round(score, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_loinc(
    description: str,
    *,
    specimen: str = "",
    max_results: int = 40,
) -> list[dict]:
    """Return LOINC concepts matching description, best match first.

    Args:
        description: Lab test / vital sign description from your study file.
        specimen: Optional specimen type hint (e.g. 'blood', 'serum', 'urine').
        max_results: Number of candidates to fetch from NLM API.

    Returns:
        List of dicts: loinc_id, long_common_name, component, system,
        scale_typ, time_aspct, method_typ, shortname, class_, score.
    """
    # Curated lookup: instant match for well-known abbreviations/aliases
    curated = _curated_match(description)
    if curated:
        return [curated]

    # Build search queries: cleaned description (with specimen) + first key token fallback
    base_query = _clean_query(description)
    tokens = base_query.split()
    first_token = tokens[0] if tokens else base_query

    # Include specimen in search when provided (e.g. "basophils blood")
    search_with_spec = f"{base_query} {specimen}".strip() if specimen else base_query
    search_token_spec = f"{first_token} {specimen}".strip() if specimen else first_token

    # Multi-pass: specifed query, token+specimen, bare token — dedup codes
    passes = list(dict.fromkeys([search_with_spec, search_token_spec, first_token]))
    seen_codes: set[str] = set()
    all_candidates: list[dict] = []
    for q in passes:
        if not q:
            continue
        for entry in _search_loinc(q, max_results=max_results):
            code = entry.get("LOINC_NUM", "")
            if code and code not in seen_codes:
                seen_codes.add(code)
                all_candidates.append(entry)

    scored = []
    for entry in all_candidates:
        score = _similarity(description, entry, specimen_hint=specimen)
        long_name = entry.get("LONG_COMMON_NAME", "")
        system, scale = _parse_long_name(long_name)
        scored.append({
            "loinc_id":         f"LOINC:{entry.get('LOINC_NUM', '')}",
            "long_common_name": long_name,
            "component":        entry.get("COMPONENT", ""),
            "system":           system,
            "scale_typ":        scale,
            "method_typ":       entry.get("METHOD_TYP", ""),
            "shortname":        entry.get("SHORTNAME", ""),
            "class_":           entry.get("CLASS", ""),
            "score":            score,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def get_loinc_id(description: str, **kwargs) -> str | None:
    """Return the best-match LOINC code as 'LOINC:<code>' or None.

    Example:
        >>> get_loinc_id("hemoglobin")
        'LOINC:718-7'
    """
    results = match_loinc(description, **kwargs)
    return results[0]["loinc_id"] if results else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("description")
@click.option(
    "--specimen",
    default="",
    show_default=True,
    help="Specimen type hint: blood, serum, urine, plasma, sputum, breath.",
)
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only LOINC:<code>. Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all ranked results (not just top N).",
)
@click.option(
    "--top",
    default=1,
    show_default=True,
    help="Number of top results to return (ignored when --all is set).",
)
@click.option(
    "--max-results",
    default=40,
    show_default=True,
    help="Number of candidates to fetch from NLM API.",
)
def main(
    description: str,
    specimen: str,
    id_only: bool,
    show_all: bool,
    top: int,
    max_results: int,
) -> None:
    """Map a lab/vital DESCRIPTION to a LOINC code via NLM LOINC search.

    DESCRIPTION is a free-text measurement label from your study file,
    e.g. "hemoglobin", "FEV1 post-bronchodilator", "systolic blood pressure".

    \b
    Examples:
        python measurementObs_agent.py "hemoglobin"
        python measurementObs_agent.py "basophils" --specimen blood --top 3
        python measurementObs_agent.py "heart rate bpm" --id-only
        python measurementObs_agent.py "FEV1 % pred post-bronchodilator" --top 5
        python measurementObs_agent.py "hematocrit" --specimen blood --all
    """
    try:
        results = match_loinc(description, specimen=specimen, max_results=max_results)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from NLM LOINC API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to NLM LOINC API. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No LOINC concepts found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["loinc_id"])
        return

    output = results if show_all else results[:top]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
