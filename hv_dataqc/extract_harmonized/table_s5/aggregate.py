"""Pool per-cohort, per-observation_type summaries into per-bdc_label rows.

Each cohort's harmonized JSON has one entry per ``observation_type`` CURIE.
The same conceptual variable may appear under different CURIEs across
cohorts (OMOP in one, OBA in another).  This module collapses all entries
sharing the same ``bdc_label`` into a single pooled row covering every
cohort that contributed.

## Pooling math

For n / nulls_missing / participants: **exact** sum across contributors.
Cohorts have disjoint participant sets, so summing distinct participant
counts is correct.

For mean: **exact** n-weighted average across contributors that provide
both ``n_valid`` and ``mean``.

For min, max: **exact** min-of-mins, max-of-maxes.

For sd: **exact** parallel-samples pooled SD when every contributor
with ``n_valid > 0`` supplies both ``mean`` and ``sd``.  Returns
``None`` if any contributor is missing one of the two — pooling only
the contributors that have ``sd`` would silently exclude others under
the same label.  Formula:

    SD_pool = sqrt(
        (sum_i (n_i - 1) * SD_i^2 + sum_i n_i * (mean_i - mean_pool)^2)
        / (N - 1)
    )

For median: **n-weighted average of contributor medians.**  The
original ``sb_for_bdc`` script computed the median of the concatenated
cross-cohort rows; neither is the "true" cross-cohort median in any
deeper statistical sense (cohorts use different assays / units /
populations), and both are point estimates of central tendency.  The
n-weighted approach lets the post-processor run from aggregate JSON
without re-entering the enclave.

For categorical / non-continuous variables: returns the categorical
shape (counts only).  Mean / median / sd / min / max are all ``None``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PooledRow:
    """One pooled row: stats across every contributor with the same bdc_label."""

    bdc_label: str
    n: int
    nulls_missing: int
    participants: int
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    sd: float | None
    contributing_codes: tuple[str, ...]
    contributing_cohorts: tuple[str, ...]
    n_contributors: int


def _opt_float(value) -> float | None:
    """Coerce to float if numeric and finite; otherwise None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _weighted_mean(values: list[tuple[int, float]]) -> float | None:
    """Return sum(n * x) / sum(n) for the provided ``(n, x)`` pairs."""
    total_n = sum(n for n, _ in values)
    if total_n <= 0:
        return None
    return sum(n * x for n, x in values) / total_n


def _pooled_sd(contribs: list[tuple[int, float, float]]) -> float | None:
    """Parallel-samples pooled SD across ``(n, mean, sd)`` contributors.

    Returns ``None`` if any contributor is missing one of n/mean/sd or the
    total pooled count is < 2 (no variance defined).
    """
    if not contribs or any(n <= 0 for n, _, _ in contribs):
        return None
    total_n = sum(n for n, _, _ in contribs)
    if total_n < 2:
        return None
    pooled_mean = sum(n * m for n, m, _ in contribs) / total_n
    within = sum((n - 1) * (sd ** 2) for n, _, sd in contribs)
    between = sum(n * (m - pooled_mean) ** 2 for n, m, _ in contribs)
    variance = (within + between) / (total_n - 1)
    if variance < 0:
        return None
    return math.sqrt(variance)


def pool_entries(
    entries: list[dict],
    *,
    bdc_label: str,
) -> PooledRow:
    """Collapse one or more harmonized-JSON variable entries into a PooledRow.

    Args:
        entries: List of dicts, each with one cohort's per-``observation_type``
            summary.  Each entry should carry ``n_valid``, ``n_total``,
            ``n_missing`` and (for continuous) ``mean``, ``sd``, ``median``,
            ``min``, ``max``.  Categorical or unknown-type entries are
            tolerated; their stats are treated as missing.
        bdc_label: The label these entries pool into (recorded on the result).

    Returns:
        PooledRow with exact n / nulls / mean / sd / min / max and approximate
        median (n-weighted average of contributor medians).
    """
    if not entries:
        return PooledRow(
            bdc_label=bdc_label, n=0, nulls_missing=0, participants=0,
            mean=None, median=None, minimum=None, maximum=None, sd=None,
            contributing_codes=(), contributing_cohorts=(), n_contributors=0,
        )

    n_total = sum(int(e.get("n_valid", 0) or 0) for e in entries)
    nulls = sum(int(e.get("n_missing", 0) or 0) for e in entries)
    # 'participants' isn't always present; fall back to n_valid when missing.
    participants = sum(
        int(e.get("participants", e.get("n_valid", 0)) or 0)
        for e in entries
    )

    # n-weighted mean over contributors that have both n_valid > 0 and mean.
    mean_contribs: list[tuple[int, float]] = []
    median_contribs: list[tuple[int, float]] = []
    sd_contribs: list[tuple[int, float, float]] = []
    # SD pooling is strict: if ANY contributing cohort with n_valid > 0 is
    # missing mean or sd, we can't form an honest parallel-samples SD, so the
    # final sd is None.  Tracking this here avoids silently pooling a
    # subset of cohorts under the same label.
    sd_strictly_pooled = True
    mins: list[float] = []
    maxs: list[float] = []
    for e in entries:
        n = int(e.get("n_valid", 0) or 0)
        if n <= 0:
            continue
        m = _opt_float(e.get("mean"))
        if m is not None:
            mean_contribs.append((n, m))
        med = _opt_float(e.get("median"))
        if med is not None:
            median_contribs.append((n, med))
        sd = _opt_float(e.get("sd"))
        if m is not None and sd is not None:
            sd_contribs.append((n, m, sd))
        else:
            sd_strictly_pooled = False
        lo = _opt_float(e.get("min"))
        if lo is not None:
            mins.append(lo)
        hi = _opt_float(e.get("max"))
        if hi is not None:
            maxs.append(hi)

    codes = tuple(
        sorted({str(e.get("observation_type", "")) for e in entries if e.get("observation_type")})
    )
    cohorts = tuple(
        sorted({str(e["_cohort"]) for e in entries if e.get("_cohort")})
    )

    return PooledRow(
        bdc_label=bdc_label,
        n=n_total,
        nulls_missing=nulls,
        participants=participants,
        mean=_weighted_mean(mean_contribs),
        median=_weighted_mean(median_contribs),
        minimum=min(mins) if mins else None,
        maximum=max(maxs) if maxs else None,
        sd=_pooled_sd(sd_contribs) if sd_strictly_pooled else None,
        contributing_codes=codes,
        contributing_cohorts=cohorts,
        n_contributors=len(entries),
    )


def group_by_bdc_label(
    cohort_jsons: dict[str, dict],
) -> dict[str, list[dict]]:
    """Group every variable across cohorts by its ``bdc_label``.

    Args:
        cohort_jsons: Mapping of cohort name -> loaded harmonized JSON dict.

    Returns:
        Mapping of ``bdc_label`` -> list of variable entries (each with a
        synthetic ``_cohort`` field added for provenance).  Entries with no
        ``bdc_label`` are dropped — they're not in any S5 row anyway.
    """
    grouped: dict[str, list[dict]] = {}
    for cohort, doc in cohort_jsons.items():
        for var_key, var in (doc.get("variables") or {}).items():
            if not isinstance(var, dict):
                continue
            label = var.get("bdc_label")
            if not label:
                continue
            # Shallow copy so we don't mutate the input dict; tag with cohort.
            tagged = dict(var)
            tagged["_cohort"] = cohort
            tagged.setdefault("_variable_key", var_key)
            grouped.setdefault(label, []).append(tagged)
    return grouped


def pool_all(cohort_jsons: dict[str, dict]) -> dict[str, PooledRow]:
    """One-shot: group all cohorts' variables and pool each bdc_label.

    Returns ``{bdc_label: PooledRow}`` for every label that appears in any
    cohort's harmonized output.
    """
    grouped = group_by_bdc_label(cohort_jsons)
    return {
        label: pool_entries(entries, bdc_label=label)
        for label, entries in grouped.items()
    }
