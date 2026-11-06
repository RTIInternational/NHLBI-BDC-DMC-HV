"""Tests for the S4 extract-freshness check (extract_source.extract_coverage)."""

from __future__ import annotations

import unittest

from hv_dataqc.extract_source.extract_coverage import stale_reason


def _doc(**meta) -> dict:
    return {"metadata": meta}


class StaleReasonTests(unittest.TestCase):
    def test_scoped_extract_covering_specs_is_current(self) -> None:
        doc = _doc(scoped_to_phvs=["phv1", "phv2", "phv3"], phv_list=None)
        self.assertIsNone(stale_reason(doc, {"phv1", "phv2"}))

    def test_spec_phv_outside_scope_is_stale(self) -> None:
        doc = _doc(scoped_to_phvs=["phv1"], phv_list=None)
        reason = stale_reason(doc, {"phv1", "phv2"})
        self.assertIsNotNone(reason)
        self.assertIn("phv2", reason or "")

    def test_full_extract_is_current(self) -> None:
        self.assertIsNone(stale_reason(_doc(scoped_to_phvs=None, phv_list=None), {"phv9"}))

    def test_extract_without_tracking_is_stale(self) -> None:
        self.assertIsNotNone(stale_reason(_doc(), set()))

    def test_phv_list_extract_is_stale(self) -> None:
        doc = _doc(scoped_to_phvs=None, phv_list=["phv1"])
        self.assertIsNotNone(stale_reason(doc, {"phv1"}))


if __name__ == "__main__":
    unittest.main()
