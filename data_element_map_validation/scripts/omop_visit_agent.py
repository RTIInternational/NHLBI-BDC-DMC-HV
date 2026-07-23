#!/usr/bin/env python3
"""Map a clinical visit description to a standard OMOP Visit concept via OHDSI Atlas WebAPI.

Endpoint: GET https://atlas-demo.ohdsi.org/WebAPI/vocabulary/search/visit

Strategy:
  All standard Visit concepts are pre-loaded from OHDSI at startup (~50 concepts).
  Matching is done entirely client-side in three tiers:
    1.00  exact label match (case-insensitive)
    0.95  curated synonym / alias hit
    else  difflib ratio * length_factor^0.4  (length-normalised)

  Curated synonyms cover common clinical study variable phrasings that would
  not match the canonical OMOP label alone (e.g. "nursing home" → Non-hospital
  institution Visit, "clinic" → Outpatient Visit).

Usage examples:
  python omop_visit_agent.py "outpatient visit"
  python omop_visit_agent.py "non-hospital long term care facility"
  python omop_visit_agent.py "nursing home stay" --id-only
  python omop_visit_agent.py "emergency department" --all
"""

import json
import re
import sys
from difflib import SequenceMatcher
from urllib.parse import quote

import click
import requests

ATLAS_BASE_URL = "https://atlas-demo.ohdsi.org/WebAPI"

# ---------------------------------------------------------------------------
# Curated synonym map  concept_id → frozenset of lower-case aliases
# Covers common study-variable phrasings that differ from the OMOP label.
# ---------------------------------------------------------------------------
VISIT_SYNONYMS: dict[int, frozenset[str]] = {
    # Outpatient Visit
    9202: frozenset({
        "outpatient", "clinic", "opd", "ambulatory care", "day visit",
        "clinic visit", "outpatient clinic", "ambulatory visit",
    }),
    # Inpatient Visit
    9201: frozenset({
        "inpatient", "admission", "hospitalization", "hospital stay",
        "admitted", "ip visit", "hospital visit", "inpatient admission",
    }),
    # Emergency Room Visit
    9203: frozenset({
        "emergency", "er", "ed", "emergency department", "emergency room",
        "a&e", "urgent care", "emergency visit",
    }),
    # Emergency Room and Inpatient Visit
    262: frozenset({
        "observation", "ed admission", "er admission",
        "emergency inpatient", "emergency room and inpatient",
        "erip", "er-ip", "er to inpatient", "ed to inpatient",
        "emergency to inpatient", "er inpatient", "ed inpatient",
        "emergency room to inpatient", "emergency department to inpatient",
    }),
    # Office Visit
    581477: frozenset({
        "office", "physician office", "provider office", "doctor office",
        "office visit", "provider visit", "outpatient office",
    }),
    # Home Visit
    581476: frozenset({
        "home visit", "house call", "home care visit",
    }),
    # Non-hospital institution Visit  ← covers long-term / non-hospital facilities
    42898160: frozenset({
        "long term care", "long-term care", "ltc", "nursing home",
        "skilled nursing", "snf", "skilled nursing facility",
        "non-hospital", "non hospital", "extended care",
        "long term facility", "long-term facility",
        "ltcf", "residential care", "convalescent home",
        "rehabilitation facility", "rehab facility", "subacute",
        "sub-acute", "custodial care",
    }),
    # Ambulatory Rehabilitation Visit
    581479: frozenset({
        "rehab", "rehabilitation", "ambulatory rehab",
        "physical therapy", "pt visit", "occupational therapy", "ot visit",
        "outpatient rehab", "outpatient rehabilitation",
    }),
    # Home Health Agency
    38004519: frozenset({
        "home health", "home health agency", "home health visit",
    }),
    # Adult Care Home
    38004307: frozenset({
        "adult care home", "adult home", "assisted living",
        "adult care facility",
    }),
    # In Home Supportive Care Agency
    38004206: frozenset({
        "home supportive care", "in-home support", "in home support",
        "supportive care at home",
    }),
    # Long Term Care Pharmacy
    38004344: frozenset({
        "long term care pharmacy", "ltc pharmacy", "nursing home pharmacy",
    }),
    # Ambulance Visit
    581478: frozenset({
        "ambulance", "ems", "emergency medical services",
        "emergency transport", "paramedic visit",
    }),
    # Laboratory Visit
    32036: frozenset({
        "laboratory", "lab", "clinical lab", "blood draw", "lab visit",
    }),
    # Outpatient Laboratory Visit
    32253: frozenset({
        "outpatient lab", "outpatient laboratory", "outpatient lab visit",
    }),
    # Pharmacy visit
    581458: frozenset({
        "pharmacy", "pharmacy visit", "drug pickup", "medication dispensing",
    }),
    # Case Management Visit
    38004193: frozenset({
        "case management", "care coordination", "care management visit",
        "case management visit",
    }),
    # Home Infusion Agency
    38004196: frozenset({
        "home infusion", "infusion at home", "home iv therapy",
    }),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_visit_concepts(base_url: str) -> list[dict]:
    """Fetch all standard Visit domain concepts from OHDSI and return as list of dicts."""
    seen: set[int] = set()
    concepts: list[dict] = []

    for query in ("visit", "ambulance", "pharmacy", "laboratory", "home", "office", "shelter"):
        url = f"{base_url}/vocabulary/search/{quote(query)}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        for doc in resp.json():
            if doc.get("STANDARD_CONCEPT") != "S":
                continue
            if doc.get("DOMAIN_ID") != "Visit":
                continue
            cid = doc["CONCEPT_ID"]
            if cid in seen:
                continue
            seen.add(cid)
            concepts.append({
                "concept_id":    cid,
                "concept_name":  doc.get("CONCEPT_NAME", ""),
                "concept_code":  doc.get("CONCEPT_CODE", ""),
                "vocabulary_id": doc.get("VOCABULARY_ID", ""),
            })

    return concepts


def _word_in(phrase: str, text: str) -> bool:
    """Return True if *phrase* appears in *text* at a word boundary."""
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def _similarity(description: str, concept: dict) -> float:
    """Three-tier similarity: exact label → curated synonym → length-normalised difflib."""
    q = description.lower().strip()
    label = concept["concept_name"].lower()
    cid = concept["concept_id"]

    if q == label:
        return 1.0

    # Curated synonym check: query contains or equals any alias
    aliases = VISIT_SYNONYMS.get(cid, frozenset())
    if q in aliases:
        return 0.95
    # Accept if any alias appears in the query at a word boundary
    # (avoids short tokens like "er" matching inside "term" or "care")
    if any(_word_in(alias, q) for alias in aliases):
        return 0.90

    raw = SequenceMatcher(None, q, label).ratio()
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_visit_concept(
    description: str,
    *,
    base_url: str = ATLAS_BASE_URL,
) -> list[dict]:
    """Return standard OMOP Visit concepts matching *description*, best match first.

    Args:
        description: Clinical visit description or study variable label.
        base_url: OHDSI Atlas WebAPI root URL.

    Returns:
        List of concept dicts (concept_id, concept_name, concept_code,
        vocabulary_id, omop_id, score) sorted by similarity score descending.
    """
    all_concepts = _load_visit_concepts(base_url)
    scored = []
    for c in all_concepts:
        score = _similarity(description, c)
        scored.append({**c, "omop_id": f"OMOP:{c['concept_id']}", "score": round(score, 4)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def get_visit_concept_id(description: str, **kwargs) -> str | None:
    """Return the best-match OMOP Visit concept as 'OMOP:<id>' (convenience wrapper).

    Example:
        >>> get_visit_concept_id("nursing home stay")
        'OMOP:42898160'
    """
    results = match_visit_concept(description, **kwargs)
    return results[0]["omop_id"] if results else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("description")
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
    help="Return all Visit concepts ranked by score (not just the top match).",
)
@click.option(
    "--top",
    default=1,
    show_default=True,
    help="Number of top results to return (ignored when --all is set).",
)
def main(description: str, base_url: str, id_only: bool, show_all: bool, top: int) -> None:
    """Map a visit DESCRIPTION to a standard OMOP Visit concept.

    DESCRIPTION is a free-text visit type label from your study file,
    e.g. \"outpatient visit\", \"non-hospital long term care facility\",
    or \"nursing home stay\".

    \b
    Examples:
        python omop_visit_agent.py "outpatient visit"
        python omop_visit_agent.py "non-hospital long term care facility" --id-only
        python omop_visit_agent.py "nursing home" --id-only
        python omop_visit_agent.py "emergency department visit" --top 3
    """
    try:
        results = match_visit_concept(description, base_url=base_url)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from Atlas WebAPI: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo(f"Could not connect to {base_url}. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No Visit concepts found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["omop_id"])
        return

    output = results if show_all else results[:top]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
