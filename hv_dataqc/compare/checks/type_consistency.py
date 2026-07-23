"""Variable type consistency: C11.

Checks that source and harmonized agree on variable type (continuous vs
categorical), using the source-driven expected type (dbGaP > YAML intent >
observed heuristic). An expected categorical type with numeric-only or
sentinel-only observed values is downgraded to INFO rather than WARN,
since that pattern usually means the source metadata declares it
categorical but the values are numerically coded.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult
from hv_dataqc.compare.crosswalk import (
    _codes_are_numeric_or_sentinel,
    _distribution_count_map,
)


def check_c11_type_consistency(
    src_var: dict,
    harmonized_var: dict,
    var_name: str,
    expected_type: str | None = None,
    type_basis: str | None = None,
) -> CheckResult:
    """C11: Variable type consistency between source and harmonized.

    Flags when the harmonized observed type disagrees with the source-driven
    expected type.  The harmonized extractor does not decide which comparison
    family applies; it is validated against dbGaP/source/YAML intent.
    """
    src_type = expected_type or src_var.get("type")
    harmonized_type = harmonized_var.get("type")
    detail_base = {
        "expected_type": src_type,
        "harmonized_type": harmonized_type,
    }
    if type_basis:
        detail_base["type_basis"] = type_basis

    if not src_type or not harmonized_type:
        return CheckResult("C11", var_name, "SKIP", "Type information missing", detail_base)
    if src_type == harmonized_type:
        basis_msg = f" ({type_basis})" if type_basis else ""
        return CheckResult("C11", var_name, "PASS", f"Type consistent: {src_type}{basis_msg}", detail_base)

    if src_type == "categorical" and harmonized_type == "continuous":
        observed_codes = set(_distribution_count_map(src_var))
        if _codes_are_numeric_or_sentinel(observed_codes):
            detail = {**detail_base, "observed_codes_numeric_or_sentinel": True}
            return CheckResult(
                "C11", var_name, "INFO",
                "Source is encoded/categorical but observed values are numeric; treating as numeric-coded source metadata, not a harmonization type error",
                detail,
            )

    return CheckResult(
        "C11", var_name, "WARN",
        f"Type mismatch: expected={src_type}, harmonized={harmonized_type}",
        detail_base,
    )
