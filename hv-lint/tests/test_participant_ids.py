"""Rule 5.11, the participant-ID seed (new in #885 part 3), pinned on known cases (fixtures
copied from main 731984f5) and on synthetic dbGaP detail indexes: the study's participant ID is
derived from the cache, and every identity seed must read it from the block's own table.

The other #885 part 3 rules (2.12, 2.7, 3.10, 3.16, 1.13) are in test_slot_value_rules.py.

Run: python -m pytest hv-lint/tests/test_participant_ids.py
"""

import gzip
import json
import sys
from pathlib import Path

import yaml

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-5"):
    sys.path.insert(0, str(HVLINT / sub) if sub else str(HVLINT))

import validate_visit_structure as vvs  # noqa: E402

FIX = HVLINT / "tests" / "fixtures" / "known_cases"
CACHE = HVLINT / "dbgap-cache"


def case(name: str) -> dict:
    return yaml.safe_load((FIX / f"{name}.yaml").read_text(encoding="utf-8"))


def _write(tmp_path: Path, name: str, blocks: list) -> Path:
    path = tmp_path / "priority_variables_transform" / "FHS-ingest" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(blocks), encoding="utf-8")
    return path


_fhs_detail = None


def fhs_detail() -> dict:
    global _fhs_detail
    if _fhs_detail is None:
        with gzip.open(CACHE / "phs000007.v35_detail.json.gz", "rt", encoding="utf-8") as fh:
            _fhs_detail = json.load(fh)
    return _fhs_detail


# -- 5.11 ----------------------------------------------------------------------------------------

def _511(tmp_path, block):
    path = _write(tmp_path, "x.yaml", [block])
    return vvs.check_5_11_participant_seed([path], tmp_path, fhs_detail())


def test_511_idtype_seed_is_flagged(tmp_path):
    f = _511(tmp_path, case("fhs_afib_b0"))
    assert [(x.check, x.severity) for x in f] == [("5.11", "ERROR")]
    assert "idtype" in f[0].message and "not a participant ID" in f[0].message


def test_511_other_tables_shareid_is_flagged(tmp_path):
    f = _511(tmp_path, case("fhs_bdy_hgt_b42"))
    assert len(f) == 1 and "another table" in f[0].message


def test_511_correct_shareid_block_is_quiet(tmp_path):
    """FHS albumin_bld b0: shareid seeds in its own table, a dotted age reference."""
    assert _511(tmp_path, case("fhs_albumin_bld_b0")) == []


def test_511_visit_seed_must_equal_participant_seed(tmp_path):
    b = case("fhs_albumin_bld_b0")
    (cls,) = b["class_derivations"].values()
    part = cls["slot_derivations"]["associated_participant"]
    seed = part["expr"].split("{")[1].split("}")[0]
    part["expr"] = part["expr"].replace(seed, "phv00001363")
    f = _511(tmp_path, b)
    # One finding per reason: phv00001363 is not a participant ID, and the seeds differ.
    assert len(f) == 2 and all(x.check == "5.11" for x in f)
    assert sum("differs from participant seed" in x.message for x in f) == 1


# 5.11 against an unseen study: the participant ID comes from the cache, not from a name list.

def _novel_detail(*, tables: int = 4, id_name: str = "PARTID") -> dict:
    """A study whose every table carries ``id_name``; pht000001 also holds a cohort code, and
    pht000099 (a dbGaP Subject table) keys by ``SUBJ_KEY`` and holds an id-sounding code."""
    d: dict = {}
    n = 0
    for t in range(1, tables + 1):
        pht = f"pht{t:06d}"
        for name, desc in ((id_name, "Participant identifier"), (f"VAR{t}", "a measurement")):
            n += 1
            d[f"phv{n:08d}"] = {"name": name, "pht": pht, "description": desc}
    d["phv00000901"] = {"name": "STUDYCODE", "pht": "pht000001", "description": "cohort code"}
    d["phv00000902"] = {"name": "SUBJ_KEY", "pht": "pht000099", "description": "Subject ID"}
    d["phv00000903"] = {"name": "ARM_TYPE", "pht": "pht000099",
                        "description": "Study arm identifier"}
    return d


def _seed_block(pht: str, seed: str) -> dict:
    return {"class_derivations": {"MeasurementObservation": {
        "populated_from": pht,
        "slot_derivations": {
            "associated_participant": {
                "expr": f'uuid5("https://w3id.org/bdchm/Participant", str({{{seed}}}) + ":NEW")'},
            "associated_visit": {
                "expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{seed}}}) + ":NEW V1")'},
        }}}}


def _511_novel(tmp_path, block, detail):
    path = _write(tmp_path, "x.yaml", [block])
    return vvs.check_5_11_participant_seed([path], tmp_path, detail)


def test_511_novel_study_id_name_is_derived_from_the_cache():
    ids = vvs.participant_ids(_novel_detail())
    assert ids.name == "partid" and ids.fallback is None
    assert "partid" not in vvs.FALLBACK_PARTICIPANT_ID_NAMES   # not the list doing the work


def test_511_novel_study_id_seed_is_accepted(tmp_path):
    """PARTID is in no fixed list: before the metadata derivation this block was a false ERROR."""
    assert _511_novel(tmp_path, _seed_block("pht000002", "phv00000003"), _novel_detail()) == []


def test_511_novel_study_cohort_code_seed_still_errors(tmp_path):
    f = _511_novel(tmp_path, _seed_block("pht000001", "phv00000901"), _novel_detail())
    assert [(x.check, x.severity) for x in f] == [("5.11", "ERROR")]
    assert "STUDYCODE" in f[0].message and "not a participant ID" in f[0].message


def test_511_table_without_the_study_id_accepts_its_own_subject_id(tmp_path):
    """A Subject / GENEVA-style table has no PARTID; its own subject identifier keys it."""
    assert _511_novel(tmp_path, _seed_block("pht000099", "phv00000902"), _novel_detail()) == []


def test_511_table_without_the_study_id_rejects_a_code_that_reads_as_an_identifier(tmp_path):
    """FHS idtype reads "cohort identifier": an id-sounding code in such a table is still not a
    participant."""
    f = _511_novel(tmp_path, _seed_block("pht000099", "phv00000903"), _novel_detail())
    assert len(f) == 1 and "ARM_TYPE" in f[0].message and f[0].severity == "ERROR"


def test_511_fhs_idtype_is_rejected_even_in_a_table_without_shareid():
    ids = vvs.participant_ids(fhs_detail())
    assert ids.name == "shareid"
    assert not ids.accepts("idtype", "pht999999", "Framingham Heart Study cohort identifier")


def test_511_fallback_is_used_and_reported_when_the_cache_names_no_id(tmp_path):
    """Two tables that share no name: the metadata does not answer. The fixed list decides, and
    a WARNING says so -- a fallback is not a metadata-verified pass."""
    detail = {"phv00000001": {"name": "SUBJECT_ID", "pht": "pht000001", "description": ""},
              "phv00000002": {"name": "PARTID", "pht": "pht000002", "description": ""}}
    ids = vvs.participant_ids(detail)
    assert ids.name is None and ids.fallback
    ok = _511_novel(tmp_path, _seed_block("pht000001", "phv00000001"), detail)
    assert [(x.check, x.severity) for x in ok] == [("5.11", "WARNING")]
    assert "fixed fallback list" in ok[0].message
    bad = _511_novel(tmp_path, _seed_block("pht000002", "phv00000002"), detail)
    assert sorted(x.severity for x in bad) == ["ERROR", "WARNING"]


def test_511_every_current_cohort_derives_its_id_from_metadata():
    """The measurement the 5.11 reference entry records: no current cohort needs the fallback."""
    import _cohorts
    want = {"ARIC": "subject_id", "CARDIA": "individual_id", "CHS": "individual_id",
            "COPDGene": "subject_id", "FHS": "shareid", "HCHS": "subject_id",
            "JHS": "subject_id", "LTRC": "subject_id", "MESA": "sidno",
            "SPIROMICS": "subject_id", "WHI": "subjid"}
    got = {}
    for cohort in want:
        key = _cohorts.cache_key_for(cohort, str(CACHE))
        got[cohort] = vvs.participant_ids(
            _cohorts.load_cache_artifact(CACHE, key, "_detail")).name  # type: ignore[arg-type]
    assert got == want


def _nested(nested_pht):
    """A MeasurementObservationSet on pht000012 whose nested observation is seeded from
    pht000011's shareid (phv00001363)."""
    seed = 'uuid5("https://w3id.org/bdchm/Participant", str({phv00001363}) + ":FHS")'
    inner = {"slot_derivations": {"associated_participant": {"expr": seed}}}
    if nested_pht:
        inner["populated_from"] = nested_pht
    return {"class_derivations": {"MeasurementObservationSet": {
        "populated_from": "pht000012", "slot_derivations": {
            "associated_participant": {"expr": seed.replace("phv00001363", "phv00001559")},
            "observations": {"class_derivations": [{"MeasurementObservation": inner}]}}}}}


def test_511_nested_class_reads_its_own_table_as_35_does(tmp_path):
    """Review round 1 B 9d: a nested populated_from makes that table reachable for the seed."""
    assert _511(tmp_path, _nested("pht000011")) == []
    f = _511(tmp_path / "b", _nested(None))
    assert len(f) == 1 and "another table than pht000012" in f[0].message
