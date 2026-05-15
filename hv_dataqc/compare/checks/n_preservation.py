"""N-preservation checks: C1 (total participant count) and C2 (per-variable valid N).

C1 compares total participant counts between source and harmonized at the
study level. C2 compares per-variable n_valid (non-missing row counts),
optionally using an `expected_n` provided by crosswalk for value-mapping
routed concept slots.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult, fmt_n as _n


def check_c1_n_preservation(
    source: dict, harmonized: dict, fail_pct: float = 1.0,
    mapped_phts: set | None = None,
) -> list[CheckResult]:
    """C1: Total participant count comparison.

    If the source summary includes ``participants_by_pht`` and ``mapped_phts``
    is provided (PHTs actually referenced by YAML), the message shows both:
      - max across mapped PHTs (the YAML-scoped universe ceiling)
      - all-PHT union (total_participants, the pass/fail denominator)

    If ``mapped_phts`` is not provided, falls back to showing the global max
    single PHT for diagnostics.  The pass/fail denominator always remains
    ``total_participants``.
    """
    src_n = source.get("total_participants", 0)
    harmonized_n = harmonized.get("total_participants", 0)

    if src_n == 0:
        return [CheckResult("C1", "_total", "SKIP", "No source participant count")]
    if harmonized_n == 0:
        return [CheckResult("C1", "_total", "FAIL", "No harmonized participants found")]

    detail_base: dict = {"source_n": src_n, "harmonized_n": harmonized_n}
    pht_note = ""
    participants_by_pht: dict[str, int] = source.get("participants_by_pht", {})
    if participants_by_pht:
        max_pht_n = max(participants_by_pht.values())
        max_pht_key = max(participants_by_pht, key=participants_by_pht.get)
        detail_base.update({
            "max_single_pht": max_pht_key,
            "max_single_pht_n": max_pht_n,
        })
        if mapped_phts:
            mapped_counts = {
                pht: n for pht, n in participants_by_pht.items()
                if pht in mapped_phts
            }
            if mapped_counts:
                mapped_max_n = max(mapped_counts.values())
                mapped_max_key = max(mapped_counts, key=mapped_counts.get)
                pht_note = (
                    f" [mapped-PHT max: {mapped_max_key}={mapped_max_n};"
                    f" all-PHT union={src_n}]"
                )
                detail_base.update({
                    "mapped_pht_max": mapped_max_key,
                    "mapped_pht_max_n": mapped_max_n,
                })
            else:
                pht_note = f" [cross-PHT union={src_n}]"
        else:
            pht_note = (
                f" [max single-PHT: {max_pht_key}={max_pht_n};"
                f" cross-PHT union={src_n}]"
            )

    if harmonized_n == src_n:
        return [CheckResult("C1", "_total", "PASS",
                             f"Participant count matches: {_n(src_n)}{pht_note}",
                             detail_base)]

    if harmonized_n < src_n:
        loss_pct = round((src_n - harmonized_n) / src_n * 100, 1)
        status = "FAIL" if loss_pct > fail_pct else "WARN"
        detail = {**detail_base, "loss_pct": loss_pct}
        return [CheckResult("C1", "_total", status,
                             f"Participant loss: {_n(src_n)} -> {_n(harmonized_n)}"
                             f" ({loss_pct}%){pht_note}",
                             detail)]

    return [CheckResult("C1", "_total", "WARN",
                         f"Harmonized has MORE participants than source:"
                         f" {_n(src_n)} -> {_n(harmonized_n)}{pht_note}",
                         detail_base)]


def check_c2_n_loss(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_pct: float = 0.5, warn_pct: float = 2.0,
    gain_warn_pct: float | None = None, gain_fail_pct: float | None = None,
    expected_n: int | None = None,
) -> CheckResult:
    """C2: Per-variable valid-N comparison.

    When *expected_n* is provided (typically by ``_expected_harmonized_n``
    for value_mappings-routed concept slots), it is used as the denominator
    in place of the raw source ``n_valid``.  This makes the check correctly
    handle one-source-to-many-concepts routing where the full source row
    count is not the right comparison target for a single harmonized concept.
    """
    src_n_raw = src_var.get("n_valid", 0)
    src_n = expected_n if expected_n is not None else src_n_raw
    harmonized_n = harmonized_var.get("n_valid", 0)
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []

    detail_base = {
        "source_n": src_n,
        "harmonized_n": harmonized_n,
    }
    if confidence:
        detail_base["comparison_confidence"] = confidence
    if limitations:
        detail_base["comparison_limitations"] = limitations
    if expected_n is not None:
        detail_base["source_n_raw"] = src_n_raw
        detail_base["expected_n_for_concept"] = expected_n

    if confidence == "unsupported":
        return CheckResult(
            "C2", var_name, "SKIP",
            "Expected N requires row-level joint counts; aggregate comparison not attempted",
            detail_base,
        )
    if src_n == 0:
        return CheckResult("C2", var_name, "SKIP", "No valid source values", detail_base)
    if harmonized_n == src_n:
        return CheckResult("C2", var_name, "PASS", f"N preserved: {_n(src_n)}", detail_base)

    loss_pct = round((src_n - harmonized_n) / src_n * 100, 1) if src_n > 0 else 0
    detail_base["loss_pct"] = loss_pct
    if abs(loss_pct) <= pass_pct:
        return CheckResult("C2", var_name, "PASS",
                           f"N within {pass_pct}%: {_n(src_n)} -> {_n(harmonized_n)}",
                           detail_base)
    if confidence == "partial":
        return CheckResult(
            "C2", var_name, "WARN",
            f"Partial expected N differs from harmonized: {_n(src_n)} -> {_n(harmonized_n)} ({abs(loss_pct)}%); row-level data needed for exact verdict",
            detail_base,
        )
    if 0 < loss_pct <= warn_pct:
        return CheckResult("C2", var_name, "WARN",
                           f"Moderate N loss: {_n(src_n)} -> {_n(harmonized_n)} ({loss_pct}%)",
                           detail_base)
    if loss_pct > warn_pct:
        return CheckResult("C2", var_name, "FAIL",
                           f"Significant N loss: {_n(src_n)} -> {_n(harmonized_n)} ({loss_pct}%)",
                           detail_base)
    gain_pct = round(-loss_pct, 1)
    gain_warn = warn_pct if gain_warn_pct is None else gain_warn_pct
    gain_fail = gain_warn if gain_fail_pct is None else gain_fail_pct
    detail_base["gain_pct"] = gain_pct
    status = "FAIL" if gain_pct > gain_fail else "WARN"
    severity = "Large" if status == "FAIL" else "Moderate"
    return CheckResult("C2", var_name, status,
                       f"{severity} N gain: {_n(src_n)} -> {_n(harmonized_n)} ({gain_pct}%)",
                       detail_base)
