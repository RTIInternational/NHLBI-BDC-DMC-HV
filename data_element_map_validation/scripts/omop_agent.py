#!/usr/bin/env python3
"""Look up the standard OMOP concept ID for a procedure or device term via OHDSI Atlas WebAPI.

Endpoint: GET https://atlas-demo.ohdsi.org/WebAPI/vocabulary/search/{query}

Scope: Procedure and Device domains only.
  For condition/diagnosis lookups use mondo_agent.py (MONDO terms) or a
  separate OMOP condition agent.  For visit type lookups use omop_visit_agent.py.

Matching strategy (multi-pass):
  The input may be a direct clinical term ("cholecystostomy") or a longer study
  variable description ("symptomatic gallstone treatment procedure"). Both are
  handled via a three-pass search:

  Pass 1 — full description:
      Search OHDSI with the complete input string.
  Pass 2 — key-term words:
      Strip clinical stopwords (history, treatment, symptomatic, etc.) and
      search for each remaining significant word individually.
  All candidates across passes are de-duplicated then re-ranked by composite
  similarity against the ORIGINAL description:
      1.00  exact label match
      0.95  label contained within description (or vice-versa)
      else  difflib ratio * length_factor^0.4

Supported --code-system values:
  icd10pcs  → Procedure domain  (ICD-10 procedure codes → standard SNOMED concept)
  procedure → Procedure domain  (any standard procedure concept)
  cpt4      → Procedure domain  (CPT-4 codes → standard procedure concept)
  hcpcs     → Procedure domain  (HCPCS codes → standard procedure concept)
  device    → Device domain     (any standard device concept)

Usage examples:
  python omop_agent.py "appendectomy" --code-system procedure
  python omop_agent.py "cholecystostomy" --code-system icd10pcs
  python omop_agent.py "symptomatic gallstone treatment procedure" --code-system procedure
  python omop_agent.py "cardiac pacemaker" --code-system device --id-only
"""

import json
import re
import sys
import time
from difflib import SequenceMatcher
from urllib.parse import quote

import click
import requests

ATLAS_BASE_URL = "https://atlas-demo.ohdsi.org/WebAPI"

CODE_SYSTEM_DOMAIN: dict[str, str] = {
    "icd10pcs":  "Procedure",
    "procedure": "Procedure",
    "cpt4":      "Procedure",
    "hcpcs":     "Procedure",
    "device":    "Device",
    "route":     "Route",
    "race":      "Race",
    "ethnicity": "Ethnicity",
    "gender":    "Gender",
}

# Words stripped before the key-term fallback search.
# Deliberately conservative — only remove words that carry no clinical specificity.
CLINICAL_STOPWORDS: frozenset[str] = frozenset({
    # English function words
    "a", "an", "the", "and", "or", "of", "in", "at", "by", "to", "with",
    "for", "from", "is", "was", "has", "have", "had", "be", "been",
    # Study-variable framing
    "patient", "subject", "participant", "person", "individual",
    "history", "diagnosis", "diagnosed", "indication", "record",
    "presence", "absence", "prior", "previous", "current", "past",
    "whether", "status", "indicator", "measure", "variable", "element",
    "yes", "no", "binary", "boolean",
    # Generic clinical modifiers
    "symptomatic", "asymptomatic", "chronic", "acute",
    "mild", "moderate", "severe", "primary", "secondary",
    "treatment", "therapy", "intervention", "management",
    "surgery", "surgical", "operation", "operative",
    "associated", "related", "due", "resulting",
    "condition", "disease", "disorder",
    # Domain words (already filtering by domain)
    "procedure", "device",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_code_system(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower().replace("-", "").replace("_", "").replace(" ", "")


def _key_terms(description: str) -> list[str]:
    """Return significant words after stripping punctuation and clinical stopwords."""
    words = re.sub(r"[^\w\s]", " ", description.lower()).split()
    return [w for w in words if w not in CLINICAL_STOPWORDS and len(w) >= 3]


def _similarity(description: str, concept: dict) -> float:
    """Composite similarity between *description* and a concept dict."""
    q = description.lower()
    label = concept["concept_name"].lower()

    if q == label:
        return 1.0
    # Reward when the label appears verbatim inside the description or vice-versa
    if label in q or q in label:
        return 0.95

    raw = SequenceMatcher(None, q, label).ratio()
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


def _fetch_standard(query: str, domain_filter: str | None, base_url: str) -> list[dict]:
    """Search OHDSI and return standard concepts, optionally filtered by domain."""
    url = f"{base_url}/vocabulary/search/{quote(query)}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    results = []
    for doc in resp.json():
        if doc.get("STANDARD_CONCEPT") != "S":
            continue
        if domain_filter and doc.get("DOMAIN_ID") != domain_filter:
            continue
        results.append({
            "concept_id":    doc["CONCEPT_ID"],
            "concept_name":  doc.get("CONCEPT_NAME", ""),
            "concept_code":  doc.get("CONCEPT_CODE", ""),
            "vocabulary_id": doc.get("VOCABULARY_ID", ""),
            "domain_id":     doc.get("DOMAIN_ID", ""),
            "concept_class": doc.get("CONCEPT_CLASS_ID", ""),
        })
    return results


def _collect_all_candidates(
    description: str,
    domain_filter: str | None,
    base_url: str,
) -> list[dict]:
    """Run multi-pass search and return de-duplicated standard concept list."""
    seen: set[int] = set()
    candidates: list[dict] = []

    def _add(docs: list[dict]) -> None:
        for d in docs:
            cid = d["concept_id"]
            if cid not in seen:
                seen.add(cid)
                candidates.append(d)

    # Pass 1: full description
    _add(_fetch_standard(description, domain_filter, base_url))

    # Pass 2: individual key terms (skip terms already equal to full description)
    terms = _key_terms(description)
    for term in terms:
        if term == description.lower():
            continue
        _add(_fetch_standard(term, domain_filter, base_url))

    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_omop_concepts(
    description: str,
    *,
    code_system: str | None = None,
    base_url: str = ATLAS_BASE_URL,
) -> list[dict]:
    """Return standard OMOP Procedure/Device concepts for *description*, best match first.

    Args:
        description: Clinical term or study variable description to look up.
        code_system: Optional source code system hint (icd10pcs, procedure,
                     device, cpt4, hcpcs). Determines the domain filter.
        base_url: OHDSI Atlas WebAPI root URL.

    Returns:
        List of concept dicts with omop_id, concept_id, concept_name,
        concept_code, vocabulary_id, domain_id, concept_class — best match first.
    """
    cs_key = _normalise_code_system(code_system)
    domain_filter = CODE_SYSTEM_DOMAIN.get(cs_key) if cs_key else None

    candidates = _collect_all_candidates(description, domain_filter, base_url)
    candidates.sort(key=lambda c: _similarity(description, c), reverse=True)

    return [{"omop_id": f"OMOP:{c['concept_id']}", **c} for c in candidates]


def get_omop_concept_id(description: str, **kwargs) -> str | None:
    """Return the best-match OMOP concept as 'OMOP:<id>' (convenience wrapper).

    Example:
        >>> get_omop_concept_id("cholecystostomy", code_system="procedure")
        'OMOP:4178670'
    """
    omop_id, _score = get_omop_concept_id_with_score(description, **kwargs)
    return omop_id


def get_omop_concept_id_with_score(description: str, **kwargs) -> tuple[str | None, float]:
    """Like get_omop_concept_id, but also returns the top match's similarity score.

    The score is the same composite similarity used to rank candidates in
    search_omop_concepts — a text-match confidence, not a guarantee of
    ontological correctness. Callers can compare it against another
    vocabulary's score to pick a priority_curie (see generate_curie_mapreview.py's
    condition_concept handling, which weighs this against MONDO/HPO scores).
    """
    results = search_omop_concepts(description, **kwargs)
    if results:
        return results[0]["omop_id"], _similarity(description, results[0])
    return None, 0.0


def get_omop_concept_id_from_loinc(loinc_code: str, base_url: str = ATLAS_BASE_URL) -> str | None:
    """Resolve a LOINC source code to its OMOP standard concept_id, as 'OMOP:<id>'.

    Every LOINC term is itself an OMOP concept — this looks it up by exact source
    code match (VOCABULARY_ID == "LOINC", CONCEPT_CODE == code) rather than by
    text similarity, since the code is already known. Used to complete the
    LOINC -> OMOP concept_id step for observation_type / MeasurementObservation
    rows in generate_curie_mapreview.py, which previously stopped at the LOINC
    code and never resolved it to a concept_id.

    Example:
        >>> get_omop_concept_id_from_loinc("LOINC:718-7")
        'OMOP:3000963'
    """
    code = loinc_code.split(":", 1)[1] if ":" in loinc_code else loinc_code
    url = f"{base_url}/vocabulary/search/{quote(code)}"

    # atlas-demo.ohdsi.org is a shared community instance that reliably times out
    # under concurrent load (observed ~93% failure rate at 8 workers with a single
    # 30s attempt). Retry with backoff and a longer timeout before giving up.
    docs = None
    for attempt, (timeout, backoff) in enumerate([(30, 0), (45, 2), (60, 5)]):
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            docs = resp.json()
            break
        except requests.RequestException:
            continue
    if docs is None:
        return None

    match = next(
        (d for d in docs if d.get("VOCABULARY_ID") == "LOINC" and d.get("CONCEPT_CODE") == code),
        None,
    )
    return f"OMOP:{match['CONCEPT_ID']}" if match else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("description")
@click.option(
    "--code-system",
    default=None,
    help=(
        "Source code system / domain scope. "
        "Choices: icd10pcs, procedure, cpt4, hcpcs, device."
    ),
)
@click.option(
    "--base-url",
    default=ATLAS_BASE_URL,
    show_default=True,
    help="OHDSI Atlas WebAPI base URL.",
)
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only OMOP:<concept_id>. Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching standard concepts (best first).",
)
@click.option(
    "--top",
    default=1,
    show_default=True,
    help="Number of top results to return (ignored when --all is set).",
)
def main(
    description: str,
    code_system: str | None,
    base_url: str,
    id_only: bool,
    show_all: bool,
    top: int,
) -> None:
    """Find the standard OMOP Procedure or Device concept for a clinical DESCRIPTION.

    DESCRIPTION may be a direct clinical term (\"cholecystostomy\") or a longer
    study variable description (\"symptomatic gallstone treatment procedure\").

    \b
    Examples:
        python omop_agent.py "appendectomy" --code-system procedure
        python omop_agent.py "cholecystostomy" --code-system icd10pcs
        python omop_agent.py "symptomatic gallstone treatment procedure" --code-system procedure
        python omop_agent.py "cardiac pacemaker" --code-system device --id-only
        python omop_agent.py "laparoscopic gallbladder removal" --code-system procedure --top 3
    """
    cs_key = _normalise_code_system(code_system)
    if code_system and cs_key not in CODE_SYSTEM_DOMAIN:
        click.echo(
            f"Unknown code system '{code_system}'. "
            f"Choose from: {', '.join(CODE_SYSTEM_DOMAIN)}.",
            err=True,
        )
        sys.exit(1)

    try:
        results = search_omop_concepts(description, code_system=code_system, base_url=base_url)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from Atlas WebAPI: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo(f"Could not connect to {base_url}. Check your network.", err=True)
        sys.exit(1)

    if not results:
        domain_hint = CODE_SYSTEM_DOMAIN.get(cs_key or "") or "Procedure/Device"
        click.echo(
            f"No standard OMOP concepts found for '{description}' in {domain_hint}.",
            err=True,
        )
        sys.exit(1)

    if id_only:
        click.echo(results[0]["omop_id"])
        return

    output = results if show_all else results[:top]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
