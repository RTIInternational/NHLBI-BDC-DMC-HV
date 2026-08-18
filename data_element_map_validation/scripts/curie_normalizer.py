#!/usr/bin/env python3
"""Check whether two CURIEs are confirmed synonyms via the NCATS Translator
SRI Node Normalizer.

Endpoint: GET https://nodenormalization-sri.renci.org/get_normalized_nodes

Scope: this only helps within the identifier space the normalizer covers
(MONDO, HP, UMLS, SNOMED, NCIT, etc. — disease/phenotype identifiers). It
does NOT cover OBA (biological attributes) or OMOP CDM concept IDs, so it
is only useful for the condition_concept (MONDO vs HP) decision, not for
observation_type (OBA vs OMOP/LOINC).

Usage:
    python curie_normalizer.py MONDO:0005098 HP:0001297
"""

import sys

import requests

NORMALIZER_URL = "https://nodenormalization-sri.renci.org/get_normalized_nodes"


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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <curie_a> <curie_b>", file=sys.stderr)
        sys.exit(1)
    print(confidence_label(sys.argv[1], sys.argv[2]))
