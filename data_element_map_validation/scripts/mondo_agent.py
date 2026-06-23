#!/usr/bin/env python3
"""Look up the best-matching MONDO term for a condition description via the EBI OLS4 API.

Endpoint: GET https://www.ebi.ac.uk/ols4/api/search?ontology=mondo&q={query}

Matching strategy (single pass + client-side re-ranking):
  OLS4's own exact=true does substring matching, not true exact matching, so
  all ranking is done client-side after fetching up to 100 candidates:
    - Exact label match      → 1.00
    - Exact synonym match    → 0.95
    - Otherwise              → difflib ratio * length_factor^0.4
  where length_factor = len(query) / max(len(query), len(label))
  This penalises overly specific labels (e.g. "renal hypertension" over
  "essential hypertension" for the query "hypertension").

Note: MONDO has no concept labelled simply "hypertension"; the closest general
clinical term is MONDO:0001134 (essential hypertension). For highly ambiguous
short queries, passing a fuller variable description (e.g. "history of
hypertension") will improve accuracy.

Usage examples:
    python mondo_agent.py "type 2 diabetes"
    python mondo_agent.py "hypertension" --id-only
    python mondo_agent.py "myocardial infarction" --all
"""

import json
import re
import sys
from difflib import SequenceMatcher
from urllib.parse import quote

import click
import requests

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# Survey-language phrases that precede or follow a clinical term.
# Pattern: "<ClinicalTerm>: <SurveyPhrase>" or "<SurveyPhrase> <ClinicalTerm>"
_SURVEY_PHRASES_RE = re.compile(
    r":\s*(have you ever had|have you ever been|at about what age did|"
    r"do you currently|do you have|did you have|has a doctor ever told you|"
    r"at what age did|when did|how long have you had|please indicate).*",
    re.IGNORECASE,
)
# Strip trailing parenthetical clarifiers  e.g. "(in legs or lungs)", "(MI)"
_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]{4,}\)\s*$")


def _extract_clinical_term(description: str) -> str:
    """Return the core clinical term from a survey-style variable description.

    Examples:
        "Emphysema: Have you ever had emphysema"  -> "Emphysema"
        "Asthma: At about what age did asthma start" -> "Asthma"
        "Heart attack (MI)"                          -> "Heart attack (MI)"
        "Blood clots (in legs or lungs)"             -> "Blood clots"
    """
    # Remove survey phrases that follow a colon
    cleaned = _SURVEY_PHRASES_RE.sub("", description).strip().rstrip(":")
    # Remove long parenthetical suffixes (keep short ones like "(MI)")
    cleaned = _PAREN_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned if cleaned else description


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_mondo_id(doc: dict) -> str | None:
    """Return the MONDO:XXXXXXX string from a doc, or None if not a MONDO term."""
    obo_id = doc.get("obo_id", "")
    if obo_id.startswith("MONDO:"):
        return obo_id
    short_form = doc.get("short_form", "")
    if short_form.startswith("MONDO_"):
        return short_form.replace("MONDO_", "MONDO:", 1)
    return None


def _similarity(query: str, concept: dict) -> float:
    """Composite similarity score between *query* and a concept dict.

    Priority:
      1.00  exact label match
      0.95  exact synonym match
      else  difflib ratio normalised by label length (penalises over-specific labels)
    """
    q = query.lower()
    label = concept["label"].lower()
    synonyms = [s.lower() for s in concept["exact_synonyms"]]

    if q == label:
        return 1.0
    if q in synonyms:
        return 0.95

    candidates = [label] + synonyms
    raw = max(SequenceMatcher(None, q, c).ratio() for c in candidates if c)
    # Normalise: penalise labels that are much longer than the query
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


def _fetch_docs(query: str, *, rows: int) -> list[dict]:
    """Call OLS4 and return raw docs for MONDO concepts only."""
    url = f"{OLS4_SEARCH_URL}?ontology=mondo&q={quote(query)}&rows={rows}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("docs", [])


def _docs_to_concepts(docs: list[dict]) -> list[dict]:
    """Convert raw API docs to cleaned concept dicts, dropping non-MONDO entries."""
    concepts = []
    for doc in docs:
        mondo_id = _extract_mondo_id(doc)
        if mondo_id is None:
            continue
        concepts.append(
            {
                "mondo_id": mondo_id,
                "label": doc.get("label", ""),
                "description": (doc.get("description") or [""])[0],
                "exact_synonyms": doc.get("exact_synonyms", []),
            }
        )
    return concepts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_mondo_terms(
    description: str,
    *,
    rows: int = 100,
) -> list[dict]:
    """Return MONDO concepts for *description*, best match first.

    Single search pass — fetches up to *rows* candidates from OLS4, then
    re-ranks client-side by composite similarity score:

      1.00  exact label match (case-insensitive)
      0.95  exact synonym match (case-insensitive)
      else  difflib ratio * length_factor^0.4  (penalises over-specific labels)

    Note: OLS4's own ``exact=true`` parameter does substring matching, not true
    exact matching, so exact-match detection is performed client-side here.

    Args:
        description: Free-text condition label from a study file.
        rows: Max candidates to fetch from OLS4.

    Returns:
        List of concept dicts (mondo_id, label, description, exact_synonyms),
        best match first.
    """
    concepts = _docs_to_concepts(_fetch_docs(description, rows=rows))
    concepts.sort(key=lambda c: _similarity(description, c), reverse=True)
    return concepts


def get_mondo_id(description: str, **kwargs) -> str | None:
    """Return only the top MONDO ID string, with multi-pass query cleaning.

    Pass 1: search with full description as-is.
    Pass 2: if no results, search with the extracted clinical term
            (strips survey-style preamble like "Have you ever had…").

    Example:
        >>> get_mondo_id("type 2 diabetes")
        'MONDO:0005148'
        >>> get_mondo_id("Emphysema: Have you ever had emphysema")
        'MONDO:0004849'
    """
    results = search_mondo_terms(description, **kwargs)
    if results:
        return results[0]["mondo_id"]

    # Pass 2: strip survey language and retry
    cleaned = _extract_clinical_term(description)
    if cleaned.lower() != description.lower():
        results2 = search_mondo_terms(cleaned, **kwargs)
        if results2:
            return results2[0]["mondo_id"]

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("description")
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the top MONDO ID (e.g. MONDO:0005148). Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching MONDO terms (scored, best first) instead of just the top result.",
)
@click.option(
    "--rows",
    default=100,
    show_default=True,
    help="Max candidates to fetch from the API in the fuzzy search pass.",
)
def main(description: str, id_only: bool, show_all: bool, rows: int) -> None:
    """Find the best-matching MONDO term for a condition DESCRIPTION.

    DESCRIPTION is the free-text condition label from your study file,
    e.g. \"type 2 diabetes mellitus\" or \"history of hypertension\".

    \b
    Examples:
        python mondo_agent.py "type 2 diabetes"
        python mondo_agent.py "type 2 diabetes" --id-only
        python mondo_agent.py "hypertension" --id-only
        python mondo_agent.py "myocardial infarction" --all
    """
    try:
        results = search_mondo_terms(description, rows=rows)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from OLS4 API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to https://www.ebi.ac.uk. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No MONDO terms found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["mondo_id"])
        return

    output = results if show_all else results[:1]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
