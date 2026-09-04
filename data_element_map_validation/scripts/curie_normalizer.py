#!/usr/bin/env python3
"""Check whether two CURIEs are confirmed synonyms.

Two independent techniques, since no single service covers all four
vocabularies this pipeline compares (MONDO, HP, OBA, OMOP):

  same_clique() / confidence_label() — NCATS Translator SRI Node Normalizer.
    Covers MONDO, HP, UMLS, SNOMED, NCIT, etc. (disease/phenotype
    identifiers). Does NOT cover OBA (biological attributes) or OMOP CDM
    concept IDs — useful for the condition_concept (MONDO vs HP) decision,
    not for observation_type (OBA vs OMOP/LOINC).

  label_similarity() / cross_vocab_match() — fetches each CURIE's own label
    from its native vocabulary (Athena for OMOP, OLS4 for MONDO/HP/OBA) and
    compares the text directly. This is what catches the case the Normalizer
    can't: e.g. OBA:2100052 ("waist to hip ratio") and OMOP:4087501
    ("Waist/hip ratio") are the same real-world concept in two different
    terminologies, not a disagreement — without this, generate_semantic_
    review.py's auto-generated findings had no way to tell "the agent found
    a different string" apart from "the agent found a better answer", and
    would flag a confirmed cross-vocabulary match as if it needed correcting.

Endpoint (Normalizer): GET https://nodenormalization-sri.renci.org/get_normalized_nodes

Usage:
    python curie_normalizer.py MONDO:0005098 HP:0001297
    python curie_normalizer.py --labels OBA:2100052 OMOP:4087501
"""

import sys
from difflib import SequenceMatcher
from urllib.parse import quote

import requests

NORMALIZER_URL = "https://nodenormalization-sri.renci.org/get_normalized_nodes"
ATLAS_BASE_URL = "https://atlas-demo.ohdsi.org/WebAPI"
OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
_OLS4_ONTOLOGIES = {"MONDO": "mondo", "HP": "hp", "OBA": "oba"}


def same_clique(curie_a: str, curie_b: str, timeout: float = 10.0) -> bool | None:
    """Return True if curie_a and curie_b resolve to the same preferred identifier
    (i.e. the normalizer treats them as synonyms), False if they resolve to
    different preferred identifiers (distinct concepts), or None if either
    CURIE could not be normalized (unknown identifier, network error, etc.).
    """
    if not curie_a or not curie_b:
        return None
    if curie_a == curie_b:
        return True
    try:
        resp = requests.get(
            NORMALIZER_URL,
            params=[
                ("curie", curie_a),
                ("curie", curie_b),
                ("conflate", "true"),
                ("drug_chemical_conflate", "false"),
            ],
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    a_info = data.get(curie_a)
    b_info = data.get(curie_b)
    if not a_info or not b_info:
        return None
    a_pref = (a_info.get("id") or {}).get("identifier", "")
    b_pref = (b_info.get("id") or {}).get("identifier", "")
    if not a_pref or not b_pref:
        return None
    return a_pref == b_pref


def confidence_label(curie_a: str, curie_b: str) -> str:
    """Return a short curator-facing confidence tag for the (curie_a, curie_b) pair."""
    result = same_clique(curie_a, curie_b)
    if result is True:
        return "high (normalizer-confirmed synonym)"
    if result is False:
        return "needs review (normalizer resolves to a different concept)"
    return ""


def _get_omop_label(curie: str, timeout: float = 15.0) -> str | None:
    """Fetch an OMOP concept's own name from Atlas, e.g. 'OMOP:4087501' -> 'Waist/hip ratio'."""
    concept_id = curie.split(":", 1)[1] if ":" in curie else curie
    try:
        resp = requests.get(f"{ATLAS_BASE_URL}/vocabulary/concept/{concept_id}", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("CONCEPT_NAME") or None
    except Exception:
        return None


def _get_ols_label(curie: str, timeout: float = 15.0) -> str | None:
    """Fetch a MONDO/HP/OBA term's own label from OLS4 by exact obo_id match."""
    prefix, _, code = curie.partition(":")
    ontology = _OLS4_ONTOLOGIES.get(prefix.upper())
    if not ontology or not code:
        return None
    obo_id = f"{prefix.upper()}:{code}"
    try:
        resp = requests.get(
            OLS4_SEARCH_URL, params={"q": code, "ontology": ontology}, timeout=timeout,
        )
        resp.raise_for_status()
        for doc in resp.json().get("response", {}).get("docs", []):
            if doc.get("obo_id") == obo_id:
                return doc.get("label") or None
    except Exception:
        return None
    return None


def get_curie_label(curie: str) -> str | None:
    """Fetch a CURIE's own display label from its native vocabulary.

    Covers the four vocabularies this pipeline compares — MONDO/HP/OBA
    (OLS4) and OMOP (Atlas). Returns None for anything else, or on any
    lookup failure (network error, unknown ID) — callers should treat that
    as "can't determine," not "no match."
    """
    prefix = curie.split(":", 1)[0].upper()
    if prefix == "OMOP":
        return _get_omop_label(curie)
    if prefix in _OLS4_ONTOLOGIES:
        return _get_ols_label(curie)
    return None


def label_similarity(curie_a: str, curie_b: str) -> float | None:
    """Compare two CURIEs' own labels directly — catches cross-vocabulary
    synonyms (e.g. OBA "waist to hip ratio" vs OMOP "Waist/hip ratio") that
    same_clique()/confidence_label() can't see, since the Translator
    Normalizer doesn't cover OBA or OMOP. Returns None (not 0.0) when either
    label can't be fetched, so callers don't mistake "unknown" for "different."
    """
    if not curie_a or not curie_b or curie_a == curie_b:
        return 1.0 if curie_a == curie_b and curie_a else None
    label_a, label_b = get_curie_label(curie_a), get_curie_label(curie_b)
    if not label_a or not label_b:
        return None
    a, b = label_a.lower().strip(), label_b.lower().strip()
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def cross_vocab_match(curie_a: str, curie_b: str, threshold: float = 0.8) -> tuple[bool | None, str]:
    """Return (is_same_concept, note) for two CURIEs from different vocabularies,
    based on comparing their own labels rather than the CURIEs' string identity.

    is_same_concept is True/False when both labels resolved, None when at least
    one couldn't be fetched (caller should not treat None as "different" —
    it means "couldn't verify," not "confirmed distinct"). note always
    includes both labels when available, for the curator to judge directly."""
    label_a, label_b = get_curie_label(curie_a), get_curie_label(curie_b)
    if not label_a or not label_b:
        return None, ""
    score = label_similarity(curie_a, curie_b)
    if score is None:
        return None, ""
    if score >= threshold:
        return True, f"same concept across terminologies: \"{label_a}\" ≈ \"{label_b}\""
    return False, f"different concepts: \"{label_a}\" vs \"{label_b}\""


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <curie_a> <curie_b>", file=sys.stderr)
        sys.exit(1)
    print(confidence_label(sys.argv[1], sys.argv[2]))
