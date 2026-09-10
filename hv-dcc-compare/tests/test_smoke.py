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
            import io, contextlib  # noqa: PLC0415

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
            import tarfile, io  # noqa: PLC0415
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


if __name__ == "__main__":
    unittest.main()
