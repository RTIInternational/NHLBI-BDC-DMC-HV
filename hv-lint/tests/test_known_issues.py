"""The enforcement model (#885 part 4): fingerprints, known issues, stale entries, the WARNING
ratchet, and the prune / update modes.

Run: python -m pytest hv-lint/tests/test_known_issues.py
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
import _known_issues as K  # noqa: E402

TREE = HVLINT.parent / "priority_variables_transform"


@dataclass
class F:
    file: str
    block: int
    check: str
    severity: str
    message: str


def _block(value_phv: str, pht: str = "pht000012", seed: str = "phv00001558") -> dict:
    return {"class_derivations": {"Condition": {"populated_from": pht, "slot_derivations": {
        "associated_participant": {"expr": f'uuid5("P", str({{{seed}}}) + ":FHS")'},
        "condition_status": {"populated_from": value_phv,
                             "value_mappings": {"0": "ABSENT", "1": "PRESENT"}}}}}}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Two spec files, and empty known-issue / baseline files, all in tmp."""
    d = tmp_path / "priority_variables_transform" / "FHS-ingest"
    d.mkdir(parents=True)
    afib = d / "afib.yaml"
    afib.write_text(yaml.safe_dump([_block("phv00000001"), _block("phv00000002"),
                                    _block("phv00000003")]), encoding="utf-8")
    other = d / "other.yaml"
    other.write_text(yaml.safe_dump([_block("phv00000009")]), encoding="utf-8")
    ki, bl = tmp_path / "ki.yaml", tmp_path / "bl.json"
    ki.write_text("", encoding="utf-8")
    monkeypatch.setenv("HVLINT_KNOWN_ISSUES", str(ki))
    monkeypatch.setenv("HVLINT_WARNING_BASELINE", str(bl))
    for v in ("HVLINT_PRUNE", "HVLINT_UPDATE_BASELINE", "HVLINT_RUN_ALL"):
        monkeypatch.delenv(v, raising=False)
    return {"afib": afib, "other": other, "ki": ki, "bl": bl}


def _run(findings, t, checks=("5.11",), scanned=None, **kw):
    scanned = [t["afib"], t["other"]] if scanned is None else scanned
    return K.finalize(findings, checks=checks, scanned_files=scanned, make_finding=F, **kw)


def _key(f: F) -> K.Key:
    ids = K.file_identities(yaml.safe_load(Path(f.file).read_text(encoding="utf-8")))
    return K.Key(f.check, K.cohort_relative(f.file), ids[f.block], K.message_key(f.message))


def _list(t, *findings, issue=882, status="defect") -> None:
    t["ki"].write_text("".join(K.entry_line(_key(f), issue, status) + "\n" for f in findings),
                       encoding="utf-8")


def _baseline(*findings) -> None:
    rows: dict = {}
    for f in findings:
        k = _key(f)
        rows.setdefault(f.check, {}).setdefault(K.cohort_of(k.file), []).append(k.text())
    K.write_baseline(rows)


def _at(path, block, check="5.11", sev="ERROR", msg="seed {phv00001558} is not a participant ID"):
    return F(str(path), block, check, sev, msg)


# -- fingerprints -------------------------------------------------------------------------

def test_message_key_keeps_quoted_codes_and_names_and_drops_counts():
    k = K.message_key("drops observed value '5' (\"Present\"), 412 of 3,608 rows (11%) in "
                      "block 14; phv00012345 OMOP:4041720 pht001116")
    assert k == ("drops observed value '5' (\"Present\"), # of # rows (#) in block #; "
                 "phv00012345 OMOP:4041720 pht001116")
    assert K.message_key("value '0'") != K.message_key("value '1'")


def test_block_identity_is_content_not_position():
    a, b, c = _block("phv00000001"), _block("phv00000002"), _block("phv00000003")
    before = K.file_identities([a, b, c])
    after = K.file_identities([_block("phv00000099"), a, b, c])
    assert after[1:] == before, "inserting a block must not change the others' identity"
    assert before[0] == "Condition@pht000012:phv00000001"


def test_block_identity_ignores_participant_seed_and_age():
    a = _block("phv00000001", seed="phv00001558")
    b = _block("phv00000001", seed="phv00001559")
    b["class_derivations"]["Condition"]["slot_derivations"]["age_at_diagnosis"] = {
        "expr": "{phv00000777} * 365"}
    assert K.block_identity(a) == K.block_identity(b)


def test_identical_blocks_get_an_ordinal():
    a = _block("phv00000001")
    assert K.file_identities([a, a]) == ["Condition@pht000012:phv00000001",
                                         "Condition@pht000012:phv00000001#2"]


def test_cohort_level_paths():
    assert K.cohort_relative("priority_variables_transform/MESA-ingest") == "MESA-ingest/"
    assert K.cohort_relative("priority_variables_transform/MESA-ingest/") == "MESA-ingest/"
    assert K.cohort_of("MESA-ingest/") == "MESA"


# -- known issues -------------------------------------------------------------------------

def test_matched_finding_is_info_with_its_issue(tree):
    f = _at(tree["afib"], 0)
    _list(tree, f)
    assert _run([f], tree) == []
    assert f.severity == "INFO" and "#882" in f.message


def test_removing_the_entry_leaves_exactly_that_finding_at_error(tree):
    f, g = _at(tree["afib"], 0), _at(tree["afib"], 1)
    _list(tree, g)
    assert _run([f, g], tree) == []
    assert [(x.block, x.severity) for x in (f, g)] == [(0, "ERROR"), (1, "INFO")]


def test_an_entry_survives_a_block_inserted_above_it(tree):
    _list(tree, _at(tree["afib"], 2))
    blocks = yaml.safe_load(tree["afib"].read_text(encoding="utf-8"))
    tree["afib"].write_text(yaml.safe_dump([_block("phv00000099")] + blocks), encoding="utf-8")
    moved = _at(tree["afib"], 3)
    assert _run([moved], tree) == [] and moved.severity == "INFO"


def test_a_second_reason_in_a_listed_block_is_its_own_finding(tree):
    f = _at(tree["afib"], 0)
    _list(tree, f)
    g = _at(tree["afib"], 0, msg="seed {phv00009999} is in another table")
    assert _run([f, g], tree) == []
    assert (f.severity, g.severity) == ("INFO", "ERROR")


def test_two_findings_with_one_fingerprint_need_two_entries(tree):
    f, g = _at(tree["afib"], 0, msg="no arm"), _at(tree["afib"], 0, msg="no arm")
    _list(tree, f)
    assert _run([f, g], tree) == []
    assert sorted((f.severity, g.severity)) == ["ERROR", "INFO"]


def test_stale_entry_fails_and_names_the_prune_command(tree):
    _list(tree, _at(tree["afib"], 0))
    extra = _run([], tree)
    assert [(x.check, x.severity) for x in extra] == [("KI", "ERROR")]
    assert "stale" in extra[0].message and K.PRUNE_CMD in extra[0].message


def test_entry_out_of_scope_is_not_stale(tree):
    _list(tree, _at(tree["afib"], 0))
    assert _run([], tree, scanned=[tree["other"]]) == []        # file not scanned (--file)
    assert _run([], tree, checks=("3.5",)) == []                # rule not run


def test_cohort_level_entry_is_out_of_scope_in_a_partial_run(tree):
    f = F("priority_variables_transform/FHS-ingest", -1, "5.8", "ERROR", "did not run")
    tree["ki"].write_text(K.entry_line(K.Key("5.8", "FHS-ingest/", "cohort", "did not run"),
                                       872, "defect") + "\n", encoding="utf-8")
    assert _run([f], tree, checks=("5.8",)) == [] and f.severity == "INFO"
    assert _run([], tree, checks=("5.8",), partial=True) == []
    assert [x.check for x in _run([], tree, checks=("5.8",))] == ["KI"]


def test_duplicate_entry_is_rejected(tree):
    f = _at(tree["afib"], 0)
    _list(tree, f, f)
    with pytest.raises(ValueError, match="same finding"):
        K.load_entries()


def test_entry_without_issue_or_with_unknown_status_is_rejected(tmp_path):
    p = tmp_path / "ki.yaml"
    head = '- {rule: "5.11", file: FHS-ingest/a.yaml, block: "x", message: "m", '
    p.write_text(head + "status: defect}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="issue"):
        K.load_entries(p)
    p.write_text(head + "issue: 1, status: maybe}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        K.load_entries(p)
    p.write_text(head + "issue: 1, status: pending}\n", encoding="utf-8")
    assert K.load_entries(p)[0].status == "pending"


def test_cohort_level_finding_is_fingerprinted(tree):
    f = F("priority_variables_transform/MESA-ingest/", -1, "5.0", "WARNING", "No visit.yaml")
    extra = _run([f], tree, checks=("5.0",))
    assert [x.check for x in extra] == ["RATCHET"] and "MESA-ingest/ | cohort" in extra[0].message


# -- WARNING ratchet ---------------------------------------------------------------------

def test_ratchet_compares_fingerprints_so_a_swap_fails(tree):
    w0 = _at(tree["afib"], 0, "5.2", "WARNING", "label 'FHS OFFSPRING EXAM 6-7' has no Visit")
    _baseline(w0)
    assert _run([w0], tree, checks=("5.2",)) == []
    w1 = _at(tree["afib"], 1, "5.2", "WARNING", "label 'FHS OFSPRING EXAM 1' has no Visit")
    extra = _run([w1], tree, checks=("5.2",))          # one fixed, one added: the count is equal
    assert sorted(x.message.split(":")[0] for x in extra) == [
        "WARNING [5.2] in FHS is fixed", "new WARNING [5.2] in FHS"]
    assert all(x.severity == "ERROR" for x in extra)


def test_fixed_warning_fails_and_names_the_prune_command(tree):
    _baseline(_at(tree["afib"], 0, "5.2", "WARNING", "x"))
    extra = _run([], tree, checks=("5.2",))
    assert [x.check for x in extra] == ["RATCHET"] and K.PRUNE_CMD in extra[0].message


def test_baseline_rows_of_unscanned_files_are_out_of_scope(tree):
    _baseline(_at(tree["other"], 0, "5.2", "WARNING", "x"))
    assert _run([], tree, checks=("5.2",), scanned=[tree["afib"]]) == []


# -- prune and update ---------------------------------------------------------------------

def test_prune_removes_only_stale_entries_and_rows_and_never_adds(tree, monkeypatch):
    keep, gone = _at(tree["afib"], 0), _at(tree["afib"], 1)
    header = "# head\n\n# FHS-ingest/afib.yaml\n"
    tree["ki"].write_text(header + K.entry_line(_key(keep), 882, "defect") + "\n"
                          + K.entry_line(_key(gone), 882, "defect") + "\n", encoding="utf-8")
    keep_key = _key(keep)
    w_keep = _at(tree["afib"], 2, "5.11", "WARNING", "keep")
    _baseline(w_keep, _at(tree["other"], 0, "5.11", "WARNING", "gone"))
    monkeypatch.setenv("HVLINT_RUN_ALL", "1")
    new = _at(tree["afib"], 2, msg="a new unlisted error")
    new_w = _at(tree["afib"], 1, "5.11", "WARNING", "a new warning")
    extra = _run([keep, w_keep, new, new_w], tree, mode="prune")
    assert keep.severity == "INFO" and new.severity == "ERROR"
    assert len([x for x in extra if "pruned" in x.message and x.severity == "INFO"]) == 2
    assert [x.check for x in extra if x.severity == "ERROR"] == ["RATCHET"]   # new_w: not added
    assert [e.key for e in K.load_entries()] == [keep_key]
    assert tree["ki"].read_text(encoding="utf-8").startswith(header)
    rows = K.load_baseline()["5.11"]["FHS"]
    assert len(rows) == 1 and rows[0].endswith("| keep")


@pytest.mark.parametrize("mode,run_all,partial", [
    ("prune", False, False), ("update", False, False),
    ("prune", True, True), ("update", True, True)])
def test_prune_and_update_refuse_a_partial_or_single_component_run(tree, monkeypatch, mode,
                                                                   run_all, partial):
    _list(tree, _at(tree["afib"], 0))
    before = tree["ki"].read_text(encoding="utf-8")
    if run_all:
        monkeypatch.setenv("HVLINT_RUN_ALL", "1")
    extra = _run([], tree, mode=mode, partial=partial)
    assert any("refusing" in x.message and x.severity == "ERROR" for x in extra)
    assert tree["ki"].read_text(encoding="utf-8") == before
    assert not tree["bl"].exists()


def test_update_rewrites_only_rows_in_scope(tree, monkeypatch):
    _baseline(_at(tree["other"], 0, "5.2", "WARNING", "other"),
              _at(tree["afib"], 0, "5.2", "WARNING", "old"))
    monkeypatch.setenv("HVLINT_RUN_ALL", "1")
    assert _run([_at(tree["afib"], 1, "5.2", "WARNING", "now")], tree, checks=("5.2",),
                scanned=[tree["afib"]], mode="update") == []
    rows = K.load_baseline()["5.2"]["FHS"]
    assert sorted(r.rsplit(" | ", 1)[1] for r in rows) == ["now", "other"]


# -- the committed files -------------------------------------------------------------------

@pytest.fixture
def committed(monkeypatch):
    monkeypatch.delenv("HVLINT_KNOWN_ISSUES", raising=False)
    monkeypatch.delenv("HVLINT_WARNING_BASELINE", raising=False)


def test_every_entry_names_an_issue_and_a_status(committed):
    entries = K.load_entries()
    assert entries, "hv-lint/known_issues.yaml is empty or missing"
    for e in entries:
        assert e.status in K.STATUSES, e
        assert re.fullmatch(r"\d\.\d+b?", e.rule), e
        assert re.fullmatch(r"[A-Za-z]+-ingest/([\w.-]+\.yaml)?", e.file), e


def test_every_entry_points_at_a_file_that_exists(committed):
    if not TREE.is_dir():
        pytest.skip("no spec tree")
    missing = sorted({e.file for e in K.load_entries() if not (TREE / e.file).exists()})
    assert missing == []


def test_committed_baseline_is_fingerprints(committed):
    base = K.load_baseline()
    assert base, "hv-lint/warning_baseline.json is empty or missing"
    for rule, by_cohort in base.items():
        for cohort, rows in by_cohort.items():
            assert rows == sorted(set(rows)), (rule, cohort)
            for r in rows:
                assert r.count(" | ") >= 2 and K.cohort_of(r.split(" | ")[0]) == cohort, r


def test_committed_entries_and_rows_are_written_in_normal_form(committed):
    """A hand-written entry whose message is not message_key() form can never match."""
    def normal(msg: str) -> bool:
        base = re.sub(r" \(#\d+\)$", "", msg)      # the ordinal of a repeated fingerprint
        return base == K.message_key(base)

    for e in K.load_entries():
        assert normal(e.message), e.describe()
    for rule, by_cohort in K.load_baseline().items():
        for rows in by_cohort.values():
            for r in rows:
                assert normal(r.split(" | ", 2)[2]), r


def test_a_test_sees_neither_the_committed_files_nor_a_mode():
    """Review round 2 B F3: tests/conftest.py isolates every test, so `HVLINT_PRUNE=1
    HVLINT_RUN_ALL=1 pytest` cannot rewrite the committed files and no test passes on their
    content without asking for it (the `committed` fixture above)."""
    assert K.known_issues_path() != K.KNOWN_ISSUES_FILE
    assert K.baseline_path() != K.BASELINE_FILE
    assert K.load_entries() == [] and K.load_baseline() == {}
    for name in (K.PRUNE_ENV, K.UPDATE_ENV, K.RUN_ALL_ENV):
        assert name not in os.environ
