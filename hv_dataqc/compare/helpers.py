"""Pure utility helpers shared across all compare sub-modules.

These functions have no dependencies on other compare sub-modules; they only
use the standard library and ``hv_dataqc_common``.  They are the primary
helpers that check modules (cross_variable.py, type_consistency.py, …) import
from ``crosswalk.py`` — moved here so each module has a single, focused
concern.
"""

from __future__ import annotations

import re
from typing import Any

from hv_dataqc.compare._common import AmbiguousColumnError
from hv_dataqc.hv_dataqc_common import canonical_phv_id, normalize_category_key

# Public alias so callers that import _canonical_phv_id from crosswalk still work.
_canonical_phv_id = canonical_phv_id


# ---------------------------------------------------------------------------
# Source-extract lookup helpers
# ---------------------------------------------------------------------------

def _build_variables_by_name(
    variables_by_pht: dict[str, dict],
) -> dict[str, dict[str, dict]]:
    """Index the source extract by column name then PHT.

    Returns ``{col_name: {pht: summary}}``. This is the canonical view used
    when the crosswalk needs to look up a source column's stats by its bare
    name and disambiguate across PHTs (multi-PHT longitudinal cohorts).

    Distinct from ``variables_by_pht`` (the extractor's emission), which is
    keyed PHT-first. Both views share the same underlying summary objects.
    """
    by_name: dict[str, dict[str, dict]] = {}
    for pht, pht_vars in variables_by_pht.items():
        for col, summary in pht_vars.items():
            by_name.setdefault(col, {})[pht] = summary
    return by_name


def _pick_single_pht_summary(
    variables_by_name: dict[str, dict[str, dict]],
    col: str,
) -> dict | None:
    """Pick a single PHT's summary for a column when caller can't disambiguate.

    - Returns the summary when the column appears in exactly one PHT.
    - Returns None when the column is absent.
    - Raises AmbiguousColumnError when the column appears in 2+ PHTs.

    This helper exists because some YAML/cache edge cases (e.g., a PHV not
    present in the dbGaP cache, or a YAML referencing a column under a PHT
    different from where the extractor recorded it) leave the crosswalk
    without an authoritative PHT for a source column. The caller is expected
    to catch AmbiguousColumnError and surface it as a per-variable FAIL so
    operators can fix the YAML/cache (or, eventually, opt into multi-PHT
    aggregation for columns that legitimately pool).
    """
    pht_map = variables_by_name.get(col)
    if not pht_map:
        return None
    if len(pht_map) > 1:
        raise AmbiguousColumnError(col, pht_map)
    return next(iter(pht_map.values()))


# ---------------------------------------------------------------------------
# Code normalization helpers
# ---------------------------------------------------------------------------

def _normalize_code(c: Any) -> str:
    """Normalise a coded value for cross-source matching.

    Distribution keys from the source extractor often arrive as float-typed
    strings (e.g. ``'1.0'``) because pandas read the column as numeric, while
    YAML value_mappings keys are typically integer strings (``'1'``).  This
    function trims trailing ``.0`` from integer-valued floats and strips
    surrounding whitespace so the two representations compare equal.
    """
    s = str(c).strip()
    # Drop trailing .0 for integer-valued floats: '1.0' -> '1', '12.0' -> '12'
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        return s[:-2]
    return s


_NULL_SENTINEL_CODES: set[str] = {
    "",
    ".",
    "*",
    "**",
    "***",
    "****",
    "*****",
    "******",
    "*******",
    "********",
    "*********",
    "NA",
    "N/A",
    "NULL",
    "NONE",
    "MISSING",
}


def _is_null_sentinel_code(code: Any) -> bool:
    """Return True for common dbGaP/SAS/suppression sentinels, not semantic categories."""
    normalized = normalize_category_key(_normalize_code(code)).upper()
    if normalized in _NULL_SENTINEL_CODES:
        return True
    return bool(re.fullmatch(r"\*{2,}", normalized))


def _codes_are_numeric_or_sentinel(codes: set[str]) -> bool:
    """Whether all observed categorical keys are parseable numeric values or null sentinels."""
    meaningful = [code for code in codes if not _is_null_sentinel_code(code)]
    if not meaningful:
        return False
    for code in meaningful:
        try:
            float(str(code))
        except (TypeError, ValueError):
            return False
    return True


# ---------------------------------------------------------------------------
# Distribution aggregation helpers
# ---------------------------------------------------------------------------

def _distribution_count_map(summary: dict | None) -> dict[str, int]:
    """Return normalized category -> count for a categorical summary."""
    dist = (summary or {}).get("distribution") or (summary or {}).get("values") or {}
    if not isinstance(dist, dict):
        return {}
    counts: dict[str, int] = {}
    for raw_code, info in dist.items():
        key = normalize_category_key(_normalize_code(raw_code))
        if isinstance(info, dict):
            count = int(info.get("n", info.get("count", 0)) or 0)
        else:
            try:
                count = int(info)
            except (TypeError, ValueError):
                count = 0
        counts[key] = counts.get(key, 0) + count
    return counts
