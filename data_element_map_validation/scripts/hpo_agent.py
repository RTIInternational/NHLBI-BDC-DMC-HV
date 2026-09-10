#!/usr/bin/env python3
"""Look up the best-matching HPO term for a phenotype description via the EBI OLS4 API.

Endpoint: GET https://www.ebi.ac.uk/ols4/api/search?ontology=hp&q={query}

Matching strategy mirrors mondo_agent: single pass + client-side re-ranking:
  - Exact label match      → 1.00
  - Exact synonym match    → 0.95
  - Otherwise              → difflib ratio * length_factor^0.4

Use for phenotypic abnormalities, clinical signs, and symptoms. For disease
entities (COPD, diabetes, asthma), prefer mondo_agent.

Usage examples:
    python hpo_agent.py "angina pectoris"
    python hpo_agent.py "hypertension" --id-only
    python hpo_agent.py "sleep apnea" --all
"""

import json
import re
import sys
from difflib import SequenceMatcher
from urllib.parse import quote

import click
import requests

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

_SURVEY_PHRASES_RE = re.compile(
    r":\s*(have you ever had|have you ever been|at about what age did|"
    r"do you currently|do you have|did you have|has a doctor ever told you|"
    r"at what age did|when did|how long have you had|please indicate).*",
    re.IGNORECASE,
)
_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]{4,}\)\s*$")


def _extract_clinical_term(description: str) -> str:
    """Return the core clinical term from a survey-style variable description."""
    cleaned = _SURVEY_PHRASES_RE.sub("", description).strip().rstrip(":")
    cleaned = _PAREN_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned if cleaned else description


def _extract_hp_id(doc: dict) -> str | None:
    """Return the HP:XXXXXXX string from a doc, or None if not an HPO term."""
    obo_id = doc.get("obo_id", "")
    if obo_id.startswith("HP:"):
        return obo_id
    short_form = doc.get("short_form", "")
    if short_form.startswith("HP_"):
        return short_form.replace("HP_", "HP:", 1)
    return None


def _similarity(query: str, concept: dict) -> float:
    """Composite similarity score between *query* and a concept dict."""
    q = query.lower()
    label = concept["label"].lower()
    synonyms = [s.lower() for s in concept["exact_synonyms"]]

    if q == label:
        return 1.0
    if q in synonyms:
        return 0.95

    candidates = [label] + synonyms
    raw = max(SequenceMatcher(None, q, c).ratio() for c in candidates if c)
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


def _fetch_docs(query: str, *, rows: int) -> list[dict]:
    """Call OLS4 and return raw docs for HPO concepts only."""
    url = f"{OLS4_SEARCH_URL}?ontology=hp&q={quote(query)}&rows={rows}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("docs", [])


def _docs_to_concepts(docs: list[dict]) -> list[dict]:
    """Convert raw API docs to cleaned concept dicts, dropping non-HPO entries."""
    concepts = []
    for doc in docs:
        hp_id = _extract_hp_id(doc)
        if hp_id is None:
            continue
        concepts.append(
            {
                "hp_id": hp_id,
                "label": doc.get("label", ""),
                "description": (doc.get("description") or [""])[0],
                "exact_synonyms": doc.get("exact_synonyms", []),
            }
        )
    return concepts


def search_hpo_terms(description: str, *, rows: int = 100) -> list[dict]:
    """Return HPO concepts for *description*, best match first.

    Fetches up to *rows* candidates from OLS4, then re-ranks client-side by
    composite similarity score.

    Args:
        description: Free-text phenotype label from a study file.
        rows: Max candidates to fetch from OLS4.

    Returns:
        List of concept dicts (hp_id, label, description, exact_synonyms),
        best match first.
    """
    concepts = _docs_to_concepts(_fetch_docs(description, rows=rows))
    concepts.sort(key=lambda c: _similarity(description, c), reverse=True)
    return concepts


def get_hpo_id(description: str, **kwargs) -> str | None:
    """Return only the top HP ID string, with multi-pass query cleaning.

    Pass 1: search with full description as-is.
    Pass 2: if no results, search with the extracted clinical term
            (strips survey-style preamble like "Have you ever had…").

    Example:
        >>> get_hpo_id("angina pectoris")
        'HP:0001681'
        >>> get_hpo_id("hypertension")
        'HP:0000822'
    """
    hp_id, _score = get_hpo_id_with_score(description, **kwargs)
    return hp_id


def get_hpo_id_with_score(description: str, **kwargs) -> tuple[str | None, float]:
    """Like get_hpo_id, but also returns the top match's similarity score.

    The score is the same composite label/synonym similarity used to rank
    candidates in search_hpo_terms — a text-match confidence, not a
    guarantee of ontological correctness. Callers can bucket it into
    curator-facing confidence tiers or compare it against another vocabulary's
    score to pick a priority_curie (see generate_curie_mapreview.py).
    """
    results = search_hpo_terms(description, **kwargs)
    if results:
        return results[0]["hp_id"], _similarity(description, results[0])

    cleaned = _extract_clinical_term(description)
    if cleaned.lower() != description.lower():
        results2 = search_hpo_terms(cleaned, **kwargs)
        if results2:
            return results2[0]["hp_id"], _similarity(cleaned, results2[0])

    return None, 0.0


@click.command()
@click.argument("description")
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the top HP ID (e.g. HP:0001681). Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching HPO terms (scored, best first) instead of just the top result.",
)
@click.option(
    "--rows",
    default=100,
    show_default=True,
    help="Max candidates to fetch from the API.",
)
def main(description: str, id_only: bool, show_all: bool, rows: int) -> None:
    """Find the best-matching HPO term for a phenotype DESCRIPTION.

    \b
    Examples:
        python hpo_agent.py "angina pectoris"
        python hpo_agent.py "hypertension" --id-only
        python hpo_agent.py "sleep apnea" --all
    """
    try:
        results = search_hpo_terms(description, rows=rows)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from OLS4 API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to https://www.ebi.ac.uk. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No HPO terms found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["hp_id"])
        return

    output = results if show_all else results[:1]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
