#!/usr/bin/env python3
"""Look up the best-matching OBA term for a measurement/observation description via EBI OLS4.

Endpoint: GET https://www.ebi.ac.uk/ols4/api/search?ontology=oba&q={query}

OBA (Ontology of Biological Attributes) encodes *what* was measured — the biological
attribute or phenotype trait. Use for observation_type slots.

For disease entities use mondo_agent; for phenotypic abnormalities use hpo_agent.

Usage examples:
    python oba_agent.py "lymphocyte count"
    python oba_agent.py "body mass index" --id-only
    python oba_agent.py "blood pressure" --all
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


def _extract_measurement_term(description: str) -> str:
    """Return the core measurement term from a survey-style variable description."""
    cleaned = _SURVEY_PHRASES_RE.sub("", description).strip().rstrip(":")
    cleaned = _PAREN_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned if cleaned else description


def _extract_oba_id(doc: dict) -> str | None:
    """Return the OBA:XXXXXXX string from a doc, or None if not an OBA term."""
    obo_id = doc.get("obo_id", "")
    if obo_id.startswith("OBA:"):
        return obo_id
    short_form = doc.get("short_form", "")
    if short_form.startswith("OBA_"):
        return "OBA:" + short_form[4:]
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
    """Call OLS4 and return raw docs for OBA concepts only."""
    url = f"{OLS4_SEARCH_URL}?ontology=oba&q={quote(query)}&rows={rows}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("docs", [])


def _docs_to_concepts(docs: list[dict]) -> list[dict]:
    """Convert raw API docs to cleaned concept dicts, dropping non-OBA entries."""
    concepts = []
    for doc in docs:
        oba_id = _extract_oba_id(doc)
        if oba_id is None:
            continue
        concepts.append({
            "oba_id": oba_id,
            "label": doc.get("label", ""),
            "description": (doc.get("description") or [""])[0],
            "exact_synonyms": doc.get("exact_synonyms", []),
        })
    return concepts


def search_oba_terms(description: str, *, rows: int = 100) -> list[dict]:
    """Return OBA concepts for *description*, best match first.

    Args:
        description: Free-text measurement/observation label from a study file.
        rows: Max candidates to fetch from OLS4.

    Returns:
        List of concept dicts (oba_id, label, description, exact_synonyms),
        best match first.
    """
    concepts = _docs_to_concepts(_fetch_docs(description, rows=rows))
    concepts.sort(key=lambda c: _similarity(description, c), reverse=True)
    return concepts


def get_oba_id(description: str, **kwargs) -> str | None:
    """Return only the top OBA ID string, with multi-pass query cleaning.

    Pass 1: search with full description as-is.
    Pass 2: if no results, search with the extracted measurement term
            (strips survey-style preamble like "Have you ever had…").

    Example:
        >>> get_oba_id("lymphocyte count")
        'OBA:VT0000717'
        >>> get_oba_id("body mass index")
        'OBA:0001547'
    """
    results = search_oba_terms(description, **kwargs)
    if results:
        return results[0]["oba_id"]

    cleaned = _extract_measurement_term(description)
    if cleaned.lower() != description.lower():
        results2 = search_oba_terms(cleaned, **kwargs)
        if results2:
            return results2[0]["oba_id"]

    return None


@click.command()
@click.argument("description")
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the top OBA ID (e.g. OBA:VT0000717). Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching OBA terms (scored, best first) instead of just the top result.",
)
@click.option(
    "--rows",
    default=100,
    show_default=True,
    help="Max candidates to fetch from the API.",
)
def main(description: str, id_only: bool, show_all: bool, rows: int) -> None:
    """Find the best-matching OBA term for a measurement/observation DESCRIPTION.

    \b
    Examples:
        python oba_agent.py "lymphocyte count"
        python oba_agent.py "body mass index" --id-only
        python oba_agent.py "blood pressure" --all
    """
    try:
        results = search_oba_terms(description, rows=rows)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from OLS4 API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to https://www.ebi.ac.uk. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No OBA terms found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["oba_id"])
        return

    output = results if show_all else results[:1]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
