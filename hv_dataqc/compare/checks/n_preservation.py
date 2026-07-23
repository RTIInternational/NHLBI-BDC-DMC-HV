"""N-preservation checks: C1 (participant denominator) and C2 (valid N).

C1 compares harmonized participants to the source participant universe that is
eligible for harmonization.  When available, that universe is the exact union
of participants in YAML-mapped source PHTs.  The all-source union remains in
the result detail as context because source extracts often include roster or
administrative tables that are not clinical harmonization anchors.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult, fmt_n as _n


def check_c1_n_preservation(
    source: dict, harmonized: dict, fail_pct: float = 1.0,
    mapped_phts: set | None = None,
) -> list[CheckResult]:
    """C1: Participant count comparison against the mapped source universe."""
    all_source_n = source.get("total_participants", 0)
    harmonized_n = harmonized.get("total_participants", 0)

    if all_source_n == 0:
        return [CheckResult("C1", "_total", "SKIP", "No source participant count")]
    if harmonized_n == 0:
        return [CheckResult("C1", "_total", "FAIL", "No harmonized participants found")]

    denominators = source.get("participant_denominators") or {}
    expected_n = denominators.get("mapped_source_union_n")
    denominator_basis = "mapped_source_union" if expected_n else "all_source_union"
    if not expected_n:
        expected_n = all_source_n

    detail_base: dict = {
        "source_n": expected_n,
        "harmonized_n": harmonized_n,
        "denominator_basis": denominator_basis,
        "all_source_union_n": all_source_n,
    }
    for key in (
        "max_source_pht", "max_source_pht_n",
        "mapped_source_phts", "mapped_source_union_n",
        "mapped_source_max_pht", "mapped_source_max_pht_n",
    ):
        if key in denominators:
            detail_base[key] = denominators[key]

    pht_note_parts: list[str] = []
    mapped_max_fallback: CheckResult | None = None
    participants_by_pht: dict[str, int] = source.get("participants_by_pht", {})
    if participants_by_pht:
        max_pht_n = max(participants_by_pht.values())
        max_pht_key = max(participants_by_pht, key=participants_by_pht.get)
        detail_base.update({
            "max_single_pht": max_pht_key,
            "max_single_pht_n": max_pht_n,
        })
        pht_note_parts.append(f"all-PHT union={_n(all_source_n)}")
        pht_note_parts.append(f"max single-PHT: {max_pht_key}={_n(max_pht_n)}")
        if denominator_basis == "mapped_source_union":
            pht_note_parts.append(f"mapped-PHT union={_n(expected_n)}")
        if mapped_phts:
            mapped_counts = {
                pht: n for pht, n in participants_by_pht.items()
                if pht in mapped_phts
            }
            if mapped_counts:
                mapped_max_n = max(mapped_counts.values())
                mapped_max_key = max(mapped_counts, key=mapped_counts.get)
                if "mapped_source_max_pht" not in detail_base:
                    detail_base.update({
                        "mapped_pht_max": mapped_max_key,
                        "mapped_pht_max_n": mapped_max_n,
                    })
                pht_note_parts.append(f"mapped-PHT max: {mapped_max_key}={_n(mapped_max_n)}")
                if denominator_basis != "mapped_source_union" and harmonized_n == mapped_max_n:
                    detail = {
                        **detail_base,
                        "source_n": mapped_max_n,
                        "denominator_basis": "mapped_source_max_fallback",
                    }
                    mapped_max_fallback = CheckResult(
                        "C1", "_total", "WARN",
                        "Participant count matches mapped-PHT max, but exact mapped-PHT union is unavailable: "
                        f"{_n(harmonized_n)} [{'; '.join(pht_note_parts)}]",
                        detail,
                    )
    pht_note = f" [{'; '.join(pht_note_parts)}]" if pht_note_parts else ""

    if harmonized_n == expected_n:
        if denominator_basis == "mapped_source_union" and all_source_n != expected_n:
            msg = (
                "Participant count matches mapped source universe: "
                f"{_n(expected_n)}; all-source union is {_n(all_source_n)}"
            )
        else:
            msg = f"Participant count matches: {_n(expected_n)}"
        return [CheckResult("C1", "_total", "PASS",
                             f"{msg}{pht_note}",
                             detail_base)]

    if mapped_max_fallback:
        return [mapped_max_fallback]

    if harmonized_n < expected_n:
        loss_pct = round((expected_n - harmonized_n) / expected_n * 100, 1)
        status = "FAIL" if loss_pct > fail_pct else "WARN"
        detail = {**detail_base, "loss_pct": loss_pct}
        return [CheckResult("C1", "_total", status,
                             f"Participant loss from {denominator_basis}: {_n(expected_n)} -> {_n(harmonized_n)}"
                             f" ({loss_pct}%){pht_note}",
                             detail)]

    return [CheckResult("C1", "_total", "WARN",
                         f"Harmonized has MORE participants than {denominator_basis}:"
                         f" {_n(expected_n)} -> {_n(harmonized_n)}{pht_note}",
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
