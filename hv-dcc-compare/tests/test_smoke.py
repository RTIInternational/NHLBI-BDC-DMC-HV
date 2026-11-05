"""Smoke tests for hv-dcc-compare.

These tests use only synthetic data and verify packaging, CLI startup, and the
aggregate-only safety contract. They must not require participant-level data.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Building TSV fixtures from explicit separators keeps the escapes
# readable inline and avoids doubling them inside nested literals.
TAB = '\t'
NL = '\n'


class HvDccCompareSmokeTests(unittest.TestCase):
    def run_script(self, relative_path: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / relative_path), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_config_imports(self) -> None:
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            self.assertIn("ARIC", config.COHORTS)
            self.assertIn("demographics", config.DATASETS)
            self.assertGreaterEqual(len(config.BDC_MEASUREMENT_MAP), 1)
            self.assertEqual(config.normalize_cohort_name("HCHS"), "HCHS_SOL")
        finally:
            sys.path[:] = original_sys_path

    def test_cli_help_starts(self) -> None:
        scripts = [
            "extract-topmed/extract_topmed_summaries.py",
            "extract-harmonized/extract_harmonized_summaries.py",
            "compare/compare.py",
            "compare/match_quality_table.py",
            "compare/validate_completeness.py",
            "compare/batch_scorecard.py",
            "compare/core_variable_coverage_table.py",
        ]
        for script in scripts:
            with self.subTest(script=script):
                result = self.run_script(script, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())

    def test_topmed_extract_outputs_aggregate_json_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "demographics.tsv"
            out_dir = tmp_path / "out"
            input_path.write_text(
                "SUBJECT_ID\tunique_subject_key\ttopmed_study\tdcc_harmonization_id\tvariable\tvalue\n"
                "TEST_ID_001\tKEY001\tARIC\tH1\tannotated_sex_1\tFemale\n"
                "TEST_ID_002\tKEY002\tARIC\tH1\tannotated_sex_1\tMale\n"
                "TEST_ID_001\tKEY001\tARIC\tH1\trace_us_1\tWhite\n",
                encoding="utf-8",
            )

            result = self.run_script(
                "extract-topmed/extract_topmed_summaries.py",
                "--demographics-file",
                str(input_path),
                "--output-dir",
                str(out_dir),
                "--cohorts",
                "ARIC",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            combined_output = result.stdout + result.stderr
            self.assertNotIn("TEST_ID_001", combined_output)
            self.assertNotIn("KEY001", combined_output)

            json_path = out_dir / "topmed_aric_summary.json"
            data = json.loads(json_path.read_text(encoding="utf-8"))
            serialized = json.dumps(data)
            self.assertNotIn("TEST_ID_001", serialized)
            self.assertNotIn("KEY001", serialized)
            self.assertEqual(data["total_participants"], 2)
            self.assertIn("annotated_sex_1", data["variables"])

    def test_translate_bdc_json_remaps_concept_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "bdc.json"
            out_path = Path(tmp) / "translated.json"
            in_path.write_text(
                json.dumps(
                    {
                        "metadata": {"cohort": "ARIC"},
                        "variables": {
                            "OBA:VT0001253": {
                                "type": "continuous",
                                "n_valid": 1,
                                "bdc_label": "Height",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_script(
                "compare/translate_bdc_json.py",
                str(in_path),
                str(out_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("height_baseline_1", data["variables"])
            self.assertNotIn("OBA:VT0001253", data["variables"])

    def test_continuous_stats_suppressed_below_small_cell_floor(self) -> None:
        """Below the floor, every distributional statistic describes one person."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-topmed"))
            import extract_topmed_summaries as ex  # type: ignore  # noqa: PLC0415
            import pandas as pd  # noqa: PLC0415

            below = ex.continuous_stats(pd.Series([170.0, 171.0, 172.0]))
            self.assertTrue(below["suppressed"])
            self.assertEqual(below["n_valid"], 3)
            for key in ("mean", "sd", "median", "q1", "q3", "p1", "p99"):
                self.assertIsNone(below[key], f"{key} leaked below the floor")

            at_floor = ex.continuous_stats(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
            self.assertNotIn("suppressed", at_floor)
            self.assertIsNotNone(at_floor["mean"])

            # min/max name a single participant's value and must not be emitted.
            self.assertNotIn("min", at_floor)
            self.assertNotIn("max", at_floor)
            self.assertIn("p1", at_floor)
            self.assertIn("p99", at_floor)
        finally:
            sys.path[:] = original_sys_path

    def test_unmapped_diagnostic_respects_small_cell_floor(self) -> None:
        """Unmapped raw values are named only at or above the disclosure floor."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-topmed"))
            import extract_topmed_summaries as ex  # type: ignore  # noqa: PLC0415
            import pandas as pd  # noqa: PLC0415

            series = pd.Series(
                ["White"] * 10
                + ["LEGACY_CODE_ABOVE_FLOOR"] * 6
                + ["RARE_CODE_BELOW_FLOOR"] * 2
            )
            stats = ex.categorical_stats(series, {"White": "White"})
            diag = stats["unmapped_diagnostics"]

            self.assertEqual(diag["n_unmapped"], 8)
            self.assertEqual(diag["n_distinct_raw_values"], 2)
            self.assertIn("LEGACY_CODE_ABOVE_FLOOR", diag["raw_values_at_or_above_floor"])
            self.assertNotIn("RARE_CODE_BELOW_FLOOR", diag["raw_values_at_or_above_floor"])
            self.assertEqual(diag["n_distinct_below_floor"], 1)

            # The withheld value must not reach the JSON by any other route.
            self.assertNotIn("RARE_CODE_BELOW_FLOOR", json.dumps(stats))
        finally:
            sys.path[:] = original_sys_path

    def test_value_map_lookup_is_whitespace_insensitive_on_both_sides(self) -> None:
        """Both extractors must normalize identically, or the same source value
        maps on one side and lands in UNMAPPED on the other."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-topmed"))
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            import extract_topmed_summaries as topmed  # type: ignore  # noqa: PLC0415
            import extract_harmonized_summaries as bdc  # type: ignore  # noqa: PLC0415
            import pandas as pd  # noqa: PLC0415

            # Six values: above the small-cell floor, so "Female" survives as
            # its own distribution key rather than being pooled.
            series = pd.Series(
                ["female", "female  ", "  female", "female", " female ", "female"]
            )
            value_map = {"female": "Female"}
            for name, mod in (("topmed", topmed), ("bdc", bdc)):
                dist = mod.categorical_stats(series, value_map)["distribution"]
                with self.subTest(extractor=name):
                    self.assertEqual(dist.get("Female", {}).get("n"), 6)
                    self.assertNotIn("UNMAPPED", dist)
        finally:
            sys.path[:] = original_sys_path

    def _build_layout(self, root: Path, layout: str) -> None:
        """Write a minimal dm-bip tree in the current or legacy layout."""
        if layout == "current":
            md = (root / "DMC_ARIC_20260831_202820" / "consent_groups"
                  / "nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1"
                  / "nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1_BDCHM"
                  / "mapped-data")
        else:
            md = (root / "DMC_aric-phs000280-v8-r1-c1_ARIC_Processed_20260322_141514"
                  / "aric-phs000280-v8-r1-c1_BDCHM" / "mapped-data")
        md.mkdir(parents=True, exist_ok=True)
        (md / "Demography.tsv").write_text(
            "associated_participant\tsex\n" + "".join(
                f"P{i:04d}\tOMOP:8532\n" for i in range(10)
            ),
            encoding="utf-8",
        )

    def test_discovers_both_dm_bip_layouts(self) -> None:
        """dm-bip changed its output layout on 2026-08-31; both must work."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            for layout in ("current", "legacy"):
                with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self._build_layout(root, layout)

                    self.assertEqual(config.discover_cohorts(root)
                                     if hasattr(config, "discover_cohorts")
                                     else ["ARIC"], ["ARIC"])
                    dirs = config.find_mapped_data_dirs(root, "ARIC")
                    self.assertEqual(len(dirs), 1, f"{layout}: {dirs}")
                    self.assertTrue(dirs[0].endswith("mapped-data"))

                    # --base-dir one level too high still resolves.
                    dirs_up = config.find_mapped_data_dirs(root.parent, "ARIC")
                    self.assertTrue(any("mapped-data" in d for d in dirs_up))
        finally:
            sys.path[:] = original_sys_path

    def test_base_dir_accepts_the_run_directory_itself(self) -> None:
        """Pointing --base-dir at .../DMC_ARIC_<date>_<time> must find the
        consent_groups/ beneath it, not report "no output found"."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "project-files" / "20260831_FinalAlignmentTest"
                run = root / "DMC_ARIC_20260831_202820"
                for cg in ("nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1",
                           "nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c2"):
                    md = run / "consent_groups" / cg / f"{cg}_BDCHM" / "mapped-data"
                    md.mkdir(parents=True)
                    (md / "Demography.tsv").write_text(
                        "associated_participant\tsex\nP0001\tOMOP:8532\n",
                        encoding="utf-8",
                    )

                # Every level down to the run directory resolves, and each
                # finds both consent groups.
                for label, base in (("run dir", run),
                                    ("run set", root),
                                    ("above run set", root.parent)):
                    with self.subTest(level=label):
                        dirs = config.find_mapped_data_dirs(base, "ARIC")
                        self.assertEqual(len(dirs), 2, f"{label}: {dirs}")
                        self.assertTrue(all(d.endswith("mapped-data") for d in dirs))

                # A run dir belonging to another cohort must not be claimed.
                self.assertEqual(config.find_mapped_data_dirs(run, "CHS"), [])

                # A path that does not exist is not a run directory, even though
                # its name matches the pattern.
                missing = Path(tmp) / "nope" / "DMC_ARIC_20260831_202820"
                self.assertEqual(config.find_dmc_run_dirs(missing), [])
        finally:
            sys.path[:] = original_sys_path

    def test_run_dir_name_resolves_to_canonical_cohort_key(self) -> None:
        """Folder spellings must land on the exact COHORTS key."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            cases = {
                "DMC_ARIC_20260831_202820": "ARIC",
                "DMC_COPDGene_20260831_203118": "COPDGene",
                "DMC_copdgene_20260831_203118": "COPDGene",
                "DMC_HCHS_20260831_203257": "HCHS_SOL",
                "DMC_aric_phs000280_v8_r1_c1_ARIC_Processed_20260101": "ARIC",
                "not_a_run_dir": None,
            }
            for name, expected in cases.items():
                with self.subTest(dir=name):
                    self.assertEqual(config.cohort_from_dmc_dir_name(name), expected)
                    if expected:
                        self.assertIn(expected, config.COHORTS)
        finally:
            sys.path[:] = original_sys_path

    def test_cohort_lookup_is_case_insensitive(self) -> None:
        """COHORTS says "COPDGene", BASELINE_VISIT_CONFIG says "COPDGENE".

        Whichever spelling arrives, both lookups must resolve -- a miss on the
        visit config silently skips every measurement for the cohort.
        """
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            for spelling in ("COPDGene", "COPDGENE", "copdgene"):
                with self.subTest(spelling=spelling):
                    self.assertTrue(
                        config.cohort_lookup(config.COHORTS, spelling),
                        "cohort metadata lookup missed",
                    )
                    self.assertTrue(
                        config.cohort_lookup(config.BASELINE_VISIT_CONFIG, spelling),
                        "baseline visit lookup missed",
                    )

            # Every cohort must have a resolvable baseline visit config.
            for cohort in config.COHORTS:
                with self.subTest(cohort=cohort):
                    self.assertTrue(
                        config.cohort_lookup(config.BASELINE_VISIT_CONFIG, cohort),
                        f"{cohort} has no baseline visit config",
                    )
        finally:
            sys.path[:] = original_sys_path

    def test_dbgap_version_parsed_from_every_consent_group_naming_style(self) -> None:
        """Consent-group dirs use hyphens, underscores, or neither before the
        version; provenance must survive all three."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415

            cases = {
                "nih-nhlbi-topmed-parent-aric-phs000280-v8-r1-c1": ("phs000280", "v8"),
                "parent-CHS_HMB-MDS_-phs000287-v7-p1-c1": ("phs000287", "v7"),
                "copdgene_phs000179_v7_r1_c1": ("phs000179", "v7"),
                "parent-MESA_HMB_-phs000209-v13-p3-c1": ("phs000209", "v13"),
                "nih-nhlbi-topmed-parent-fhs-phs000007-v35-r1-c1": ("phs000007", "v35"),
            }
            for segment, expected in cases.items():
                with self.subTest(consent_group=segment):
                    path = f"/base/run/consent_groups/{segment}/{segment}_BDCHM/mapped-data"
                    self.assertEqual(ex.parse_dbgap_version_from_dirs([path]), expected)
        finally:
            sys.path[:] = original_sys_path

    def test_data_dictionary_labels_unmapped_concepts(self) -> None:
        """Unmapped concepts must print as labels, not bare CURIEs."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                csv_path = Path(tmp) / "BDC-HM-Test-DataDictionary-20260831.csv"
                csv_path.write_text(
                    "output_table,output_column,code_in_data,label,definition,"
                    "vocabulary,code_form" + NL +
                    "Condition,condition_concept,MONDO:0005002,chronic obstructive "
                    "pulmonary disease,,MONDO,ontology code (CURIE)" + NL +
                    "MeasurementObservation,observation_type,OMOP:4282779,"
                    "Cigarette smoking tobacco,,OMOP,ontology code (CURIE)" + NL,
                    encoding="utf-8",
                )
                d = config.load_data_dictionary(str(csv_path), verbose=False)

                self.assertEqual(
                    config.label_for_code("MONDO:0005002", dictionary=d),
                    "chronic obstructive pulmonary disease",
                )
                # Qualified lookup wins, bare code still resolves.
                self.assertEqual(
                    config.label_for_code("OMOP:4282779", "MeasurementObservation",
                                          "observation_type", dictionary=d),
                    "Cigarette smoking tobacco",
                )
                # The code stays visible so a report is traceable.
                self.assertEqual(
                    config.display_label("MONDO:0005002", dictionary=d),
                    "chronic obstructive pulmonary disease [MONDO:0005002]",
                )
                # Unknown codes degrade to the bare code, never to an error.
                self.assertEqual(config.display_label("MONDO:9999999", dictionary=d),
                                 "MONDO:9999999")
                self.assertIsNone(config.label_for_code("", dictionary=d))

            # No dictionary at all is a supported state, not a failure.
            self.assertEqual(config.load_data_dictionary(str(Path(tmp) / "gone.csv"),
                                                         verbose=False), {})
            self.assertEqual(config.display_label("MONDO:0005002", dictionary={}),
                             "MONDO:0005002")
        finally:
            sys.path[:] = original_sys_path

    def test_smoking_found_in_measurement_observation_file(self) -> None:
        """COPDGene emits smoking as a MeasurementObservation, not an
        Observation. Looking in only one file reported BDC as missing both
        smoking core variables for 10,371 participants who had it."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                md = (Path(tmp) / "DMC_COPDGene_20260831_203118" / "consent_groups"
                      / "copdgene_phs000179_v7_r1_c1"
                      / "copdgene_phs000179_v7_r1_c1_BDCHM" / "mapped-data")
                md.mkdir(parents=True)
                header = ("associated_participant" + TAB + "observation_type" + TAB
                          + "value_enum" + TAB + "associated_visit" + NL)
                rows = []
                for i in range(30):
                    code = "OMOP:40766945" if i < 15 else "OMOP:45883537"
                    rows.append(f"P{i:04d}" + TAB + "OMOP:4282779" + TAB + code
                                + TAB + "v1" + NL)
                (md / "MeasurementObservation.tsv").write_text(
                    header + "".join(rows), encoding="utf-8")
                (md / "Visit.tsv").write_text(
                    "id" + TAB + "name" + NL + "v1" + TAB + "COPDGene P1" + NL,
                    encoding="utf-8")

                stats: dict = {}
                ex.process_observations(
                    [str(md)], "COPDGene", set(), 30, stats,
                    visit_mapping=ex.load_visit_mapping([str(md)]),
                )

                # Both smoking core variables must now be derived.
                self.assertIn("current_smoker_baseline_1", stats)
                self.assertIn("ever_smoker_baseline_1", stats)
                self.assertEqual(
                    stats["current_smoker_baseline_1"]["distribution"]
                    ["Current Smoker"]["n"], 15)
                self.assertEqual(
                    stats["ever_smoker_baseline_1"]["distribution"]
                    ["Never Smoked"]["n"], 15)
        finally:
            sys.path[:] = original_sys_path

    def test_baseline_absence_is_not_reported_as_config_failure(self) -> None:
        """A variable collected only at a later exam is a fact about the study,
        not a broken visit config. The 2026-09-10 run raised 66 CRITICAL banners
        this way, every one of them false."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415
            import io  # noqa: PLC0415
            import contextlib  # noqa: PLC0415

            def run(visit_rows: str):
                with tempfile.TemporaryDirectory() as tmp:
                    md = Path(tmp) / "md"
                    md.mkdir()
                    meas = ["associated_participant" + TAB + "observation_type" + TAB
                            + "value_quantity__value_decimal" + TAB
                            + "value_quantity__unit" + TAB + "associated_visit"]
                    for i in range(20):
                        meas.append(f"P{i:04d}" + TAB + "OBA:VT0001253" + TAB
                                    + "170.0" + TAB + "cm" + TAB + "v1")
                        meas.append(f"P{i:04d}" + TAB + "OBA:VT0000223" + TAB
                                    + "0.5" + TAB + "10*9/L" + TAB + "v5")
                    (md / "MeasurementObservation.tsv").write_text(
                        NL.join(meas) + NL, encoding="utf-8")
                    (md / "Visit.tsv").write_text(visit_rows, encoding="utf-8")
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        ex.process_measurements(
                            [str(md)], "ARIC", set(), 20, {},
                            visit_mapping=ex.load_visit_mapping([str(md)]),
                        )
                    return buf.getvalue()

            # Config works; one variable is exam-5 only -> informational only.
            good = run("id" + TAB + "name" + NL + "v1" + TAB + "ARIC EXAM 1" + NL
                       + "v5" + TAB + "ARIC EXAM 5" + NL)
            self.assertNotIn("CRITICAL", good)
            self.assertIn("NOTE:", good)
            self.assertIn("ARIC EXAM 5", good)  # says where the data is

            # Nothing resolves -> the real configuration failure still alarms.
            bad = run("id" + TAB + "name" + NL + "v1" + TAB + "BOGUS A" + NL
                      + "v5" + TAB + "BOGUS B" + NL)
            self.assertIn("CRITICAL", bad)
            self.assertIn("configuration failure", bad)
        finally:
            sys.path[:] = original_sys_path

    def test_tar_extraction_rejects_prefix_sibling_escape(self) -> None:
        """Containment must use is_relative_to, not a string prefix.

        A prefix comparison accepts a sibling directory whose name merely begins
        with the destination's ("/x/foo" vs "/x/foobar"), letting a member land
        outside the intended directory. Flagged by Copilot on PR #572.
        """
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-topmed"))
            sys.path.insert(0, str(ROOT))
            import tarfile  # noqa: PLC0415
            import io  # noqa: PLC0415
            import extract_topmed_summaries as ex  # type: ignore  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tgz = root / "bundle.tar.gz"

                def write_archive(member_name: str) -> None:
                    payload = b"pwned"
                    with tarfile.open(tgz, "w:gz") as tf:
                        info = tarfile.TarInfo(member_name)
                        info.size = len(payload)
                        tf.addfile(info, io.BytesIO(payload))

                extract_root = root / "extract"
                # dest becomes <extract_root>/bundle; escape into a sibling
                # directory sharing that prefix.
                write_archive("../bundle_evil/payload.txt")
                with self.assertRaises(ValueError):
                    ex.extract_eav_from_tgz(tgz, extract_root)
                self.assertFalse((extract_root / "bundle_evil").exists(),
                                 "member escaped the destination directory")

                # Plain parent-directory traversal stays blocked too.
                write_archive("../../escape.txt")
                with self.assertRaises(ValueError):
                    ex.extract_eav_from_tgz(tgz, extract_root)

                # An absolute member path is rejected.
                write_archive("/abs/escape.txt")
                with self.assertRaises(ValueError):
                    ex.extract_eav_from_tgz(tgz, extract_root)
        finally:
            sys.path[:] = original_sys_path

    def test_dictionary_prefers_definition_over_echoed_curie_label(self) -> None:
        """26 OBA rows label a CURIE with the CURIE re-cased; the real name is
        in definition. Permissible value names must keep their labels."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                csv_path = Path(tmp) / "BDC-HM-X-DataDictionary-20260831.csv"
                csv_path.write_text(
                    "output_table,output_column,code_in_data,label,definition,"
                    "vocabulary,code_form" + NL +
                    "MeasurementObservation,observation_type,OBA:VT0001253,"
                    "Oba:vt0001253,Height | the vertical measurement,OBA,x" + NL +
                    "Condition,condition_status,ABSENT,Absent,"
                    "was absent at observation time,BDC-HM,x" + NL +
                    "Condition,condition_concept,MONDO:0005002,"
                    "chronic obstructive pulmonary disease,a lung disease,MONDO,x" + NL,
                    encoding="utf-8",
                )
                d = config.load_data_dictionary(str(csv_path), verbose=False)
                # Echoed CURIE label -> first clause of the definition.
                self.assertEqual(config.label_for_code("OBA:VT0001253", dictionary=d),
                                 "Height")
                # Permissible value name that merely re-cases -> keep the label.
                self.assertEqual(config.label_for_code("ABSENT", dictionary=d), "Absent")
                # A real label is never overridden by its definition.
                self.assertEqual(config.label_for_code("MONDO:0005002", dictionary=d),
                                 "chronic obstructive pulmonary disease")
        finally:
            sys.path[:] = original_sys_path

    def test_reads_integer_and_concept_value_columns(self) -> None:
        """dm-bip spreads values across four columns and cohorts differ in which
        they use. Reading only value_decimal/value_enum turned real data into a
        presence count -- 15,061 ARIC household-income values became "present".
        value_string must still be refused: free text is disclosive.
        """
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415
            import pandas as pd  # noqa: PLC0415

            def frame(col: str, values: list) -> pd.DataFrame:
                return pd.DataFrame({col: values})

            # value_decimal -- unchanged behaviour
            s, src, kind = ex.select_value_series(
                frame("value_quantity__value_decimal", [1.5, 2.5, 3.5]))
            self.assertEqual(kind, "numeric")
            self.assertEqual(list(s), [1.5, 2.5, 3.5])

            # value_integer only -- previously fell through to presence-only
            s, src, kind = ex.select_value_series(
                frame("value_quantity__value_integer", [1, 2, 3]))
            self.assertEqual(kind, "numeric")
            self.assertEqual(src, "value_quantity__value_integer")
            self.assertEqual(list(s), [1, 2, 3])

            # value_concept only -- coded, not numeric
            s, src, kind = ex.select_value_series(
                frame("value_quantity__value_concept", ["OMOP:8527", "OMOP:8516"]))
            self.assertEqual(kind, "coded")
            self.assertEqual(src, "value_quantity__value_concept")

            # value_enum wins over value_concept when both are coded
            s, src, kind = ex.select_value_series(pd.DataFrame({
                "value_enum": ["A", "B"],
                "value_quantity__value_concept": ["OMOP:1", "OMOP:2"]}))
            self.assertEqual(src, "value_enum")

            # numeric wins over coded: a variable populating both is a quantity
            s, src, kind = ex.select_value_series(pd.DataFrame({
                "value_quantity__value_integer": [4, 5],
                "value_enum": ["A", "B"]}))
            self.assertEqual(kind, "numeric")

            # value_string is NEVER read -- must fall through to nothing
            s, src, kind = ex.select_value_series(
                frame("value_string", ["free text a", "free text b"]))
            self.assertEqual(kind, "")
            self.assertEqual(src, "")
            self.assertEqual(len(s), 0)

            # decimal and integer coalesce per row rather than one winning
            values, used, n_raw = ex.coalesce_numeric_values(pd.DataFrame({
                "value_quantity__value_decimal": [1.5, None, None],
                "value_quantity__value_integer": [None, 7, 8]}))
            self.assertEqual(list(values.dropna()), [1.5, 7.0, 8.0])
            self.assertEqual(len(used), 2)
            self.assertEqual(n_raw, 3)

            # The parse floor: a column that is mostly non-numeric is a coded
            # variable, not a quantity. Without this, one numeric-looking entry
            # among coded answers turns every other row into a missing value.
            s, src, kind = ex.select_value_series(
                frame("value_quantity__value_decimal", ["refused"] * 9 + ["7"]))
            self.assertEqual(kind, "coded", "10% numeric must not read as a quantity")
            s, src, kind = ex.select_value_series(
                frame("value_quantity__value_decimal", ["refused"] * 5 + list("12345")))
            self.assertEqual(kind, "numeric", "50% numeric is at the floor")

            # A populated enum outranks a mostly-text decimal column.
            s, src, kind = ex.select_value_series(pd.DataFrame({
                "value_quantity__value_decimal": ["refused"] * 9 + ["7"],
                "value_enum": ["A"] * 10}))
            self.assertEqual(src, "value_enum")

            # the policy tuples must not grow to include free text
            self.assertNotIn("value_string", ex.NUMERIC_VALUE_COLUMNS)
            self.assertNotIn("value_string", ex.CODED_VALUE_COLUMNS)
        finally:
            sys.path[:] = original_sys_path

    def test_unit_comparison_ignores_notation_but_not_real_differences(self) -> None:
        """dm-bip writes UCUM and config writes conventional notation, so a
        literal comparison flagged 48 variables on the 2026-09-10 run with all
        but one being notation. A check that cries wolf gets ignored."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415

            same = [("mmHg", "mm[Hg]"), ("10^3/uL", "10*3/uL"), ("hours", "h"),
                    ("pg", "pg/{cell}"), ("mg/dL", "mg/dl"), ("10^6/uL", "10*6/uL")]
            for a, b in same:
                with self.subTest(same=(a, b)):
                    self.assertEqual(ex.normalize_unit(a), ex.normalize_unit(b))

            differ = [("cm", "in"), ("kg", "lb"), ("mg/dL", "g/dL"),
                      ("mm3", '#reported_units: "Hounsfield units (HU)')]
            for a, b in differ:
                with self.subTest(differ=(a, b)):
                    self.assertNotEqual(ex.normalize_unit(a), ex.normalize_unit(b))

            self.assertEqual(ex.normalize_unit(""), "")
            self.assertEqual(ex.normalize_unit(None), "")
        finally:
            sys.path[:] = original_sys_path

    def test_numeric_values_in_a_coded_column_are_quantities(self) -> None:
        """ARIC writes dietary servings into value_concept; they came out as
        categories ['0.0','0.5','1.0',...] instead of a mean. Real CURIEs must
        still be treated as codes."""
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT / "extract-harmonized"))
            sys.path.insert(0, str(ROOT))
            import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415
            import pandas as pd  # noqa: PLC0415

            numbers = pd.DataFrame({"value_quantity__value_concept":
                                    ["0.0", "0.5", "1.0", "3.0", "5.5", "7.0"]})
            series, src, kind = ex.select_value_series(numbers)
            self.assertEqual(kind, "numeric")
            self.assertEqual(src, "value_quantity__value_concept")
            self.assertAlmostEqual(float(series.mean()), 2.8333, places=3)

            curies = pd.DataFrame({"value_quantity__value_concept":
                                   ["OMOP:8527", "OMOP:8516", "OMOP:8527"]})
            series, src, kind = ex.select_value_series(curies)
            self.assertEqual(kind, "coded")
        finally:
            sys.path[:] = original_sys_path


    def _scorecard_module(self):
        """Import compare/batch_scorecard.py by path.

        It is a standalone script rather than an installed module, and it puts
        the toolkit root on sys.path itself so `config` resolves.
        """
        import importlib.util  # noqa: PLC0415

        # Running it as a script puts compare/ on sys.path automatically, which
        # is how it finds its sibling match_quality_table; an importlib load
        # does not, so add it here.
        for extra in (str(ROOT), str(ROOT / "compare")):
            if extra not in sys.path:
                sys.path.insert(0, extra)
        spec = importlib.util.spec_from_file_location(
            "batch_scorecard_under_test", ROOT / "compare" / "batch_scorecard.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_ungraded_variables_reach_the_rollup(self) -> None:
        """A variable that cannot be tiered must not vanish between `Match` and
        the grade columns.

        Raised on PR #572: with two of three variables ungraded, the summary
        read `Match: 3`, grades summing to 1, and GOOD at 100% -- a real mean
        gap nowhere in the table a reader triages from. Replacing the old
        default-SD-to-1 with "?" fixed a wrong grade but moved the problem:
        the variable disappeared instead of being mislabelled.
        """
        bs = self._scorecard_module()

        def cont(mean, sd, n=100):
            if mean is None:
                # What continuous_stats emits below the small-cell floor.
                return {"type": "continuous", "unit": "cm", "n_total": n, "n_valid": 3,
                        "n_missing": n - 3, "pct_missing": 0.0, "mean": None, "sd": None,
                        "n_implausible": 0, "suppressed": True}
            return {"type": "continuous", "unit": "cm", "n_total": n, "n_valid": n,
                    "n_missing": 0, "pct_missing": 0.0, "mean": mean, "sd": sd,
                    "n_implausible": 0}

        with tempfile.TemporaryDirectory() as tmp:
            tdir, bdir = Path(tmp) / "t", Path(tmp) / "b"
            tdir.mkdir(), bdir.mkdir()
            # Two suppressed on the reference side; one of those has a 25cm gap.
            (tdir / "topmed_aric_summary.json").write_text(json.dumps({
                "metadata": {"cohort": "ARIC"}, "total_participants": 100,
                "variables": {"height_baseline_1": cont(170, 9),
                              "weight_baseline_1": cont(None, None),
                              "bmi_baseline_1": cont(None, None)}}), encoding="utf-8")
            (bdir / "bdc_aric_summary_20260101_000000.json").write_text(json.dumps({
                "metadata": {"cohort": "ARIC"}, "total_participants": 100,
                "variables": {"height_baseline_1": cont(170.2, 9),
                              "weight_baseline_1": cont(195, 14),
                              "bmi_baseline_1": cont(27, 4)}}), encoding="utf-8")

            result = bs.run_cohort_scorecard(
                tdir / "topmed_aric_summary.json",
                bdir / "bdc_aric_summary_20260101_000000.json")

            self.assertEqual(result["matched_vars"], 3)
            self.assertEqual(result["n_ungraded"], 2, "ungraded variables were not counted")
            self.assertEqual(result["total_graded"], 1)
            # The counts must account for every matched variable.
            self.assertEqual(sum(result["grades"].values()) + result["n_ungraded"],
                             result["matched_vars"])

            summary = bs.format_cross_cohort_summary([result], "20260101_000000")
            header = next(ln for ln in summary.splitlines() if ln.strip().startswith("Cohort"))
            row = next(ln for ln in summary.splitlines() if ln.strip().startswith("ARIC"))
            total = next(ln for ln in summary.splitlines() if ln.strip().startswith("TOTAL"))

            self.assertIn("?", header, "summary table has no '?' column")
            # The '?' count must land under the '?' header, and the TOTAL row
            # must line up with it -- the totals row was a column short.
            q_col = header.index("?")
            for label, line in (("cohort row", row), ("TOTAL row", total)):
                with self.subTest(line=label):
                    self.assertEqual(line[q_col - 3:q_col + 2].strip(), "2",
                                     f"'?' count not aligned under its header in the {label}")

            card = bs.format_cohort_scorecard(result)
            self.assertIn("?=2", card)
            self.assertIn("1 of 3 matched", card)
            self.assertIn("of graded", card, "A+B rate is not qualified as graded-only")
            # Type comes from the recorded var_type: the "missing mean" branch
            # carries no t_mean, so these used to print as `cat`.
            for line in card.splitlines():
                if line.strip().startswith(("weight_baseline_1", "bmi_baseline_1")):
                    with self.subTest(row=line.split()[0]):
                        self.assertIn("cont", line)
                        self.assertIn("?", line)

    def test_no_known_participant_level_debug_prints(self) -> None:
        source_files = [
            ROOT / "extract-harmonized" / "extract_harmonized_summaries.py",
            ROOT / "extract-topmed" / "extract_topmed_summaries.py",
            ROOT / "compare" / "validate_completeness.py",
        ]
        forbidden_fragments = [
            "Sample IDs:",
            "Sample procedure IDs:",
            "Sample demography IDs:",
            "Raw samples:",
            "Check sample output above",
        ]
        for path in source_files:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                with self.subTest(path=path.name, fragment=fragment):
                    self.assertNotIn(fragment, text)


def _tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [TAB.join(header)] + [TAB.join(r) for r in rows]
    path.write_text(NL.join(lines) + NL, encoding="utf-8")


class ExtractorAccuracyTests(unittest.TestCase):
    """Each test drives the real process_* function on a synthetic mapped-data
    directory and asserts on the graded statistic, not on a helper."""

    def setUp(self) -> None:
        self._sys_path = sys.path.copy()
        sys.path.insert(0, str(ROOT / "extract-harmonized"))
        sys.path.insert(0, str(ROOT))
        import extract_harmonized_summaries as ex  # type: ignore  # noqa: PLC0415
        self.ex = ex
        self._tmp = tempfile.TemporaryDirectory()
        self.md = Path(self._tmp.name) / "md"
        self.md.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        sys.path[:] = self._sys_path

    def _visits(self, labels: dict[str, str]) -> dict[str, str]:
        _tsv(self.md / "Visit.tsv", ["id", "name"], [[k, v] for k, v in labels.items()])
        return self.ex.load_visit_mapping([str(self.md)])

    def _quiet(self, fn, *args, **kwargs):
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            result = fn(*args, **kwargs)
        return result, buf.getvalue()

    def test_unknown_condition_status_is_missing_not_no(self) -> None:
        vm = self._visits({"v1": "ARIC EXAM 1"})
        rows = ([[f"P{i}", "MONDO:0005068", "PRESENT", "v1"] for i in range(10)]
                + [[f"P{i}", "MONDO:0005068", "ABSENT", "v1"] for i in range(10, 30)]
                # blank = skip-pattern follow-up not asked: still a respondent
                + [[f"P{i}", "MONDO:0005068", "", "v1"] for i in range(30, 40)]
                + [[f"P{i}", "MONDO:0005068", "UNKNOWN", "v1"] for i in range(40, 60)])
        _tsv(self.md / "Condition.tsv",
             ["associated_participant", "condition_concept", "condition_status",
              "associated_visit"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_conditions, [str(self.md)], "ARIC", set(), 100,
                    stats, visit_mapping=vm)
        dist = stats["mi_prior_1"]["distribution"]
        self.assertEqual(dist["Prior History"]["n"], 10)
        self.assertEqual(dist["No Prior History"]["n"], 30)  # not 50
        self.assertEqual(stats["mi_prior_1"]["n_missing"], 60)

    def test_prior_history_never_falls_back_to_other_visits(self) -> None:
        vm = self._visits({"v1": "ARIC EXAM 1", "h": "ARIC Hospital Form"})
        # PAD answered only on a post-baseline hospital form; MI at baseline.
        rows = ([[f"P{i}", "MONDO:0005294", "PRESENT", "h"] for i in range(20)]
                + [[f"P{i}", "MONDO:0005068", "ABSENT", "v1"] for i in range(30)])
        _tsv(self.md / "Condition.tsv",
             ["associated_participant", "condition_concept", "condition_status",
              "associated_visit"], rows)
        stats: dict = {}
        _, out = self._quiet(self.ex.process_conditions, [str(self.md)], "ARIC",
                             set(), 100, stats, visit_mapping=vm)
        self.assertEqual(stats["pad_prior_1"]["n_valid"], 0)  # gap, not prevalence
        self.assertIn("not_comparable", stats["pad_prior_1"])
        self.assertIn("mi_prior_1", stats)
        self.assertIn("NOT COMPARABLE", out)

        # No condition row at any baseline visit: nothing is graded.
        stats = {}
        rows = [[f"P{i}", "MONDO:0005068", "PRESENT", "h"] for i in range(20)]
        _tsv(self.md / "Condition.tsv",
             ["associated_participant", "condition_concept", "condition_status",
              "associated_visit"], rows)
        self._quiet(self.ex.process_conditions, [str(self.md)], "ARIC", set(), 100,
                    stats, visit_mapping=vm)
        self.assertEqual(stats["mi_prior_1"]["n_valid"], 0)

    def _drugs(self, rows: list[list[str]], cohort: str = "HCHS_SOL",
               visit: str = "HCHS EXAM") -> dict:
        vm = self._visits({"v1": visit})
        _tsv(self.md / "DrugExposure.tsv",
             ["associated_participant", "drug_concept", "exposure_status",
              "associated_visit"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_drugs, [str(self.md)], cohort, set(), 100,
                    {f"P{i}" for i in range(100)}, stats, visit_mapping=vm)
        return stats

    def test_antihypertensive_uses_study_indicator_over_drug_classes(self) -> None:
        rows = ([[f"P{i}", "ATC:C02", "PRESENT", "v1"] for i in range(10)]
                + [[f"P{i}", "ATC:C02", "ABSENT", "v1"] for i in range(10, 95)]
                + [[f"P{i}", "ATC:C02", "UNKNOWN", "v1"] for i in range(95, 100)]
                # beta blocker taken by people who said "no" to BP medication
                + [[f"P{i}", "ATC:C07A", "PRESENT", "v1"] for i in range(10, 20)])
        s = self._drugs(rows)["antihypertensive_meds_1"]
        self.assertEqual(s["distribution"]["Yes"]["n"], 10)
        self.assertEqual(s["distribution"]["No"]["n"], 85)
        self.assertEqual(s["n_missing"], 5)

    def test_medication_list_source_keeps_attendee_denominator(self) -> None:
        # CARDIA-style list: only the few participants who listed a BP drug
        # have a row, so absence means "not taking", not missing.
        rows = ([[f"P{i}", "ATC:C02", "PRESENT", "v1"] for i in range(6)]
                + [[f"P{i}", "ATC:C02", "ABSENT", "v1"] for i in range(6, 8)])
        s = self._drugs(rows)["antihypertensive_meds_1"]
        self.assertEqual(s["distribution"]["Yes"]["n"], 6)
        self.assertEqual(s["distribution"]["No"]["n"], 94)

    def test_lipid_meds_match_subclasses_and_mean_current_use(self) -> None:
        rows = ([[f"P{i}", "ATC:C10AA", "PRESENT", "v1"] for i in range(8)]
                + [[f"P{i}", "ATC:C10AB", "PRESENT", "v1"] for i in range(8, 12)]
                + [[f"P{i}", "ATC:C10A", "HISTORICAL", "v1"] for i in range(12, 20)]
                + [[f"P{i}", "ATC:C10A", "ABSENT", "v1"] for i in range(20, 90)])
        s = self._drugs(rows)["lipid_lowering_medication_1"]
        self.assertEqual(s["distribution"]["Yes"]["n"], 12)
        self.assertEqual(s["distribution"]["No"]["n"], 78)

    def test_ethnicity_unknown_is_missing(self) -> None:
        rows = ([[f"P{i}", "OMOP:38003563"] for i in range(10)]
                + [[f"P{i}", "OMOP:38003564"] for i in range(10, 30)]
                + [[f"P{i}", "OMOP:8552"] for i in range(30, 50)])
        _tsv(self.md / "Demography.tsv", ["associated_participant", "ethnicity"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_demography, [str(self.md)], "FHS", stats)
        dist = stats["hispanic_or_latino_1"]["distribution"]
        self.assertNotIn("UNMAPPED", dist)
        self.assertEqual(stats["hispanic_or_latino_1"]["n_missing"], 20)

    def test_stenosis_band_labels_graded_as_worst_side(self) -> None:
        vm = self._visits({"v1": "MESA CLASSIC EXAM 1"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_concept", "associated_visit"]
        rows = []
        for i in range(20):
            rows.append([f"P{i}", "OMOP:43020498", "0", "v1"])          # left
            rows.append([f"P{i}", "OMOP:43021859", "25-49" if i < 6 else "1-24", "v1"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "MESA", set(), 20,
                    stats, visit_mapping=vm)
        dist = stats["carotid_stenosis_1"]["distribution"]
        self.assertEqual(dist["2"]["n"], 6)
        self.assertEqual(dist["1"]["n"], 14)

    def test_visit_override_takes_first_listed_exam_with_a_value(self) -> None:
        vm = self._visits({"e9": "FHS OFFSPRING EXAM 9", "e1": "FHS OFFSPRING EXAM 1",
                           "o4": "FHS ORIGINAL EXAM 4"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "associated_visit"]
        rows = []
        for i in range(10):
            # Exam 1 row first in file order; Exam 9 must still win.
            rows.append([f"P{i}", "OBA:VT0000217", "5.0", "e1"])
            rows.append([f"P{i}", "OBA:VT0000217", "7.0" if i < 6 else "", "e9"])
            rows.append([f"P{i}", "OBA:VT0000217", "99.0", "o4"])  # not a DCC exam
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "FHS", set(), 10,
                    stats, visit_mapping=vm)
        s = stats["wbc_ncnc_bld_1"]
        self.assertEqual(s["n_valid"], 10)
        # 6 at Exam 9 (7.0) and 4 falling back to Exam 1 (5.0); Original excluded.
        self.assertAlmostEqual(s["mean"], (6 * 7.0 + 4 * 5.0) / 10, places=4)

    def test_stenosis_override_keeps_both_sides(self) -> None:
        vm = self._visits({"e6": "FHS OFFSPRING EXAM 6"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_concept", "associated_visit"]
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OMOP:43020498", "1-24", "e6"])
            rows.append([f"P{i}", "OMOP:43021859", "50-74", "e6"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "FHS", set(), 10,
                    stats, visit_mapping=vm)
        self.assertEqual(stats["carotid_stenosis_1"]["distribution"]["3"]["n"], 10)

    def test_most_nonmissing_first_reproduces_the_greedy_visit_rule(self) -> None:
        vm = self._visits({"e3": "ARIC EXAM 3", "e4": "ARIC EXAM 4", "e5": "ARIC EXAM 5"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "associated_visit"]
        rows = []
        # Exam 5 has the most participants (P0-P7), so it wins everyone it has
        # even though Exam 3 is listed first; P8/P9 then fall to Exam 3.
        for i in range(8):
            rows.append([f"P{i}", "OBA:2045301", "30.0", "e5"])
        for i in range(4, 10):
            rows.append([f"P{i}", "OBA:2045301", "20.0", "e3"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "ARIC", set(), 10,
                    stats, visit_mapping=vm)
        s = stats["mch_entmass_rbc_1"]
        self.assertEqual(s["n_valid"], 10)
        self.assertAlmostEqual(s["mean"], (8 * 30.0 + 2 * 20.0) / 10, places=4)
        self.assertTrue(s["visit_label"].startswith("ARIC EXAM 5 > ARIC EXAM 3"))

    def test_drug_visit_override_excludes_unlisted_subcohorts(self) -> None:
        vm = self._visits({"o4": "FHS ORIGINAL EXAM 4", "f1": "FHS OFFSPRING EXAM 1"})
        rows = ([[f"P{i}", "ATC:C10A", "PRESENT", "o4"] for i in range(30)]
                + [[f"P{i}", "ATC:C10A", "PRESENT", "f1"] for i in range(30, 35)]
                + [[f"P{i}", "ATC:C10A", "ABSENT", "f1"] for i in range(35, 50)])
        _tsv(self.md / "DrugExposure.tsv",
             ["associated_participant", "drug_concept", "exposure_status",
              "associated_visit"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_drugs, [str(self.md)], "FHS", set(), 50,
                    {f"P{i}" for i in range(50)}, stats, visit_mapping=vm)
        s = stats["lipid_lowering_medication_1"]
        self.assertEqual(s["distribution"]["Yes"]["n"], 5)
        self.assertEqual(s["distribution"]["No"]["n"], 15)

    def test_override_keeps_one_whole_row_across_value_columns(self) -> None:
        vm = self._visits({"e9": "FHS OFFSPRING EXAM 9", "e1": "FHS OFFSPRING EXAM 1"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "value_quantity__value_integer",
                  "associated_visit"]
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OBA:VT0000217", "5.0", "", "e1"])
            rows.append([f"P{i}", "OBA:VT0000217", "", "7", "e9"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "FHS", set(), 10,
                    stats, visit_mapping=vm)
        self.assertAlmostEqual(stats["wbc_ncnc_bld_1"]["mean"], 7.0, places=4)

    def test_subcohort_without_indicator_is_a_gap_not_a_drug_class(self) -> None:
        vm = self._visits({"g": "FHS GENERATION 3 EXAM 1", "f": "FHS OFFSPRING EXAM 1"})
        rows = ([[f"P{i}", "ATC:C02", "PRESENT", "g"] for i in range(20)]
                + [[f"P{i}", "ATC:C02", "ABSENT", "g"] for i in range(20, 70)]
                # Offspring has only a diuretic flag: not the indicator.
                + [[f"P{i}", "ATC:C03", "PRESENT", "f"] for i in range(70, 85)]
                + [[f"P{i}", "ATC:C03", "ABSENT", "f"] for i in range(85, 100)])
        _tsv(self.md / "DrugExposure.tsv",
             ["associated_participant", "drug_concept", "exposure_status",
              "associated_visit"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_drugs, [str(self.md)], "FHS", set(), 100,
                    {f"P{i}" for i in range(100)}, stats, visit_mapping=vm)
        s = stats["antihypertensive_meds_1"]
        self.assertEqual(s["distribution"]["Yes"]["n"], 20)
        self.assertEqual(s["distribution"]["No"]["n"], 50)
        self.assertEqual(s["n_missing"], 30)

    def test_unknown_ethnicity_row_does_not_hide_a_real_answer(self) -> None:
        rows = ([[f"P{i}", "OMOP:8552"] for i in range(10)]
                + [[f"P{i}", "OMOP:38003563"] for i in range(10)]
                + [[f"P{i}", "Unknown"] for i in range(10, 15)])
        _tsv(self.md / "Demography.tsv", ["associated_participant", "ethnicity"], rows)
        stats: dict = {}
        self._quiet(self.ex.process_demography, [str(self.md)], "FHS", stats)
        dist = stats["hispanic_or_latino_1"]["distribution"]
        self.assertEqual(dist["Hispanic or Latino"]["n"], 10)
        self.assertNotIn("UNMAPPED", dist)

    def test_blank_drug_status_is_missing_not_no(self) -> None:
        rows = ([[f"P{i}", "ATC:C10AA", "PRESENT", "v1"] for i in range(10)]
                + [[f"P{i}", "ATC:C10AA", "ABSENT", "v1"] for i in range(10, 80)]
                + [[f"P{i}", "ATC:C10AA", "", "v1"] for i in range(80, 90)])
        s = self._drugs(rows)["lipid_lowering_medication_1"]
        self.assertEqual(s["distribution"]["No"]["n"], 70)  # not 80
        self.assertEqual(s["n_missing"], 20)

    def test_heavily_skipped_question_stays_a_question(self) -> None:
        # 60 of 100 blank: still a question (explicit negatives exist), so the
        # denominator is who answered, not all attendees.
        rows = ([[f"P{i}", "ATC:C10AA", "PRESENT", "v1"] for i in range(10)]
                + [[f"P{i}", "ATC:C10AA", "ABSENT", "v1"] for i in range(10, 40)]
                + [[f"P{i}", "ATC:C10AA", "", "v1"] for i in range(40, 100)])
        s = self._drugs(rows)["lipid_lowering_medication_1"]
        self.assertEqual(s["distribution"]["No"]["n"], 30)
        self.assertEqual(s["n_missing"], 60)

    def test_same_visit_tie_under_override_is_reported(self) -> None:
        vm = self._visits({"y15": "CARDIA YEAR 15"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "associated_visit"]
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OMOP:4208414", "2.0", "y15"])   # one assay
            rows.append([f"P{i}", "OMOP:4208414", "3.3", "y15"])   # another assay
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        _, out = self._quiet(self.ex.process_measurements, [str(self.md)], "CARDIA",
                             set(), 10, {}, visit_mapping=vm)
        self.assertIn("10 participant(s) had CONFLICTING values", out)

        # Different values at DIFFERENT listed visits are resolved by priority,
        # not a conflict.
        vm = self._visits({"e9": "FHS OFFSPRING EXAM 9", "e2": "FHS OFFSPRING EXAM 2"})
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OBA:VT0000217", "6.0", "e9"])
            rows.append([f"P{i}", "OBA:VT0000217", "7.0", "e2"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        _, out = self._quiet(self.ex.process_measurements, [str(self.md)], "FHS",
                             set(), 10, {}, visit_mapping=vm)
        self.assertNotIn("CONFLICTING", out)

    def test_fhs_ldl_reads_the_calculated_value(self) -> None:
        vm = self._visits({"f1": "FHS OFFSPRING EXAM 1"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "method_type", "associated_visit"]
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OBA:VT0001815", "125.0", "fasted for minimum 12 hrs", "f1"])
            rows.append([f"P{i}", "OBA:VT0001815", "120.0",
                         "fasted for minimum 12 hrs - calculated value", "f1"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "FHS", set(), 10,
                    stats, visit_mapping=vm)
        self.assertAlmostEqual(stats["ldl_1"]["mean"], 120.0, places=4)

    def test_preferred_method_override_selects_the_reference_source(self) -> None:
        vm = self._visits({"v1": "JHS Exam 1"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "method_type", "associated_visit"]
        rows = []
        for i in range(10):
            rows.append([f"P{i}", "OBA:VT0000184", "40.0", "Analysis derived", "v1"])
            rows.append([f"P{i}", "OBA:VT0000184", "50.0", "Fasting lab assay", "v1"])
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        self._quiet(self.ex.process_measurements, [str(self.md)], "JHS", set(), 10,
                    stats, visit_mapping=vm)
        self.assertAlmostEqual(stats["hdl_1"]["mean"], 50.0, places=4)
        self.assertEqual(stats["hdl_1"]["bdc_method"], "Fasting lab assay")

    def test_unmatched_preferred_method_is_not_reported_as_applied(self) -> None:
        vm = self._visits({"v1": "CHS BASELINE BOTH"})
        header = ["associated_participant", "observation_type",
                  "value_quantity__value_decimal", "method_type", "associated_visit"]
        rows = [[f"P{i}", "OBA:VT0001259", "70.0", "anthropometry", "v1"] for i in range(10)]
        _tsv(self.md / "MeasurementObservation.tsv", header, rows)
        stats: dict = {}
        _, out = self._quiet(self.ex.process_measurements, [str(self.md)], "CHS",
                             set(), 10, stats, visit_mapping=vm)
        self.assertNotIn("bdc_method", stats["weight_baseline_1"])
        self.assertIn("matched no rows", out)


if __name__ == "__main__":
    unittest.main()
