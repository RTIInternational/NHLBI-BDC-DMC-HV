"""One known-issue mechanism and one WARNING ratchet for every HV-Lint rule (#885 part 4).

Every phase fails CI on ERROR. What keeps main green is not a lower severity but a written
exception: an entry in ``hv-lint/known_issues.yaml`` naming the finding, the issue that tracks
it, and its status --

* ``defect``          real; the fix is tracked in the named issue;
* ``dbgap-error``     the mapping is right and the dbGaP label (or dictionary) is wrong;
* ``false-positive``  the rule is wrong here; ``note`` says why;
* ``pending``         a curator decision is open in the named issue; nothing is decided yet.

**A finding is identified by its fingerprint, never by a count or a block's position:**
``rule | file | block | message`` where

* ``file`` is cohort-relative (``FHS-ingest/afib.yaml``), or ``<C>-ingest/`` for a finding about
  a whole cohort (a missing visit.yaml, a check that did not run);
* ``block`` is the block's CONTENT identity (:func:`block_identity`): its classes, table and the
  phvs its value slots read, so inserting or deleting another block in the file leaves it
  unchanged. Two blocks of one file with the same identity get ``#2``, ``#3`` in file order.
  ``file`` / ``cohort`` stand for a finding about a whole file / cohort;
* ``message`` is :func:`message_key`: the message with unquoted numbers (row counts, block
  numbers, shares) replaced by ``#``. Quoted text -- codes, labels -- is kept, so two reasons
  are two fingerprints. Two findings with one fingerprint get `` (#2)`` in finding order.

Fingerprints are unique per run, so an entry matches at most one finding, and a duplicate entry
is rejected when the file is read. What keeps the list honest, each an ERROR:

* **stale entry** (check ``KI``): an entry for a rule this component ran, on a file it scanned
  (or a cohort it ran in full), that matched nothing -- the defect was fixed, so the entry goes;
* **new WARNING** (``RATCHET``): a WARNING fingerprint that ``hv-lint/warning_baseline.json``
  does not list. Fixing one WARNING and adding another fails: the ratchet compares fingerprints,
  not counts;
* **fixed WARNING** (``RATCHET``): a baseline fingerprint, in scope, that no finding has.

The two commands (both refuse anything but a ``run_all.py`` run without ``--file``, so a partial
or single-component run can never rewrite rows it did not see):

* :data:`PRUNE_CMD` removes ONLY entries and baseline rows that match nothing. It never adds.
  Every stale-entry and fixed-WARNING message prints it.
* :data:`UPDATE_CMD` rewrites the WARNING baseline rows in scope from this run (adds and removes),
  so the baseline can rise as well as fall: accepting a new WARNING is a reviewed diff of
  ``warning_baseline.json``, line by line.

Entry fields: ``rule``, ``file``, ``block``, ``message`` (the fingerprint), ``issue`` (int),
``status``, ``note`` (optional). An unlisted ERROR prints the entry line to add.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

HVLINT_DIR = Path(__file__).resolve().parent
KNOWN_ISSUES_FILE = HVLINT_DIR / "known_issues.yaml"
BASELINE_FILE = HVLINT_DIR / "warning_baseline.json"
STATUSES = ("defect", "dbgap-error", "false-positive", "pending")

# run_all.py sets RUN_ALL_ENV for the phases it starts; the two rewriting modes need it.
RUN_ALL_ENV = "HVLINT_RUN_ALL"
PRUNE_ENV = "HVLINT_PRUNE"
UPDATE_ENV = "HVLINT_UPDATE_BASELINE"
PRUNE_CMD = "HVLINT_PRUNE=1 python hv-lint/run_all.py --cohort all"
UPDATE_CMD = "HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort all"

_COHORT_PATH_RE = re.compile(r"(?:^|/)([^/]+-ingest)(?:/(.*))?$")


def known_issues_path() -> Path:
    return Path(os.environ.get("HVLINT_KNOWN_ISSUES") or KNOWN_ISSUES_FILE)


def baseline_path() -> Path:
    return Path(os.environ.get("HVLINT_WARNING_BASELINE") or BASELINE_FILE)


def cohort_relative(path) -> str | None:
    """``.../FHS-ingest/afib.yaml`` -> ``FHS-ingest/afib.yaml``; ``.../MESA-ingest`` -> ``MESA-ingest/``."""
    m = _COHORT_PATH_RE.search(str(path).replace("\\", "/").rstrip("/"))
    if not m:
        return None
    return f"{m.group(1)}/{(m.group(2) or '').strip('/')}"


def cohort_of(rel: str | None) -> str | None:
    if not rel:
        return None
    return rel.split("/", 1)[0][: -len("-ingest")]


# -- fingerprints --------------------------------------------------------------------------

# A single quote opens a quoted run only after a non-word character and closes one only before
# a non-word character, so an apostrophe ("block's", 'Don't know') cannot pair with a real quote
# and leave the labels after it unquoted, which would mask their numbers.
_QUOTED_RE = re.compile(r"((?<!\w)'(?:[^']|(?<=\w)'(?=\w))*'(?!\w)|\"[^\"]*\")")
# A number glued to a word, a dot or a colon is part of a name (phv00012345, OMOP:4041720).
_NUMBER_RE = re.compile(r"(?<![\w.:])\d[\d,]*(?:\.\d+)?%?")
_PHV_RE = re.compile(r"phv\d{8}")
# Slots that say WHOSE row it is and WHEN, not WHAT the block measures: a fix to a participant
# seed (#882) or an age formula must not change the identity of the block's other findings.
_IDENTITY_SKIP = {"id", "associated_participant", "associated_visit"}


def message_key(message: str) -> str:
    """The message with unquoted numbers replaced by ``#`` and whitespace collapsed."""
    parts = _QUOTED_RE.split(str(message))
    out = [p if i % 2 else _NUMBER_RE.sub("#", p) for i, p in enumerate(parts)]
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _value_phvs(node, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and (k in _IDENTITY_SKIP or k.startswith("age_")):
                continue
            _value_phvs(v, out)
    elif isinstance(node, list):
        for v in node:
            _value_phvs(v, out)
    elif isinstance(node, str):
        out.update(_PHV_RE.findall(node))


def _short(items: list[str]) -> str:
    if len(items) <= 3:
        return ",".join(items)
    digest = hashlib.sha1("|".join(items).encode("utf-8")).hexdigest()[:6]
    return f"{items[0]},{items[1]},+{len(items) - 2}~{digest}"


def block_identity(block) -> str:
    """A block's identity from its content: ``Class@pht:phvs``.

    The phvs are those its slots read, minus ``id`` / ``associated_*`` / ``age_*``. A Visit block
    is identified by the labels its ``id`` emits instead. A block with neither is identified by
    a digest of its whole body.
    """
    cds = block.get("class_derivations") if isinstance(block, dict) else None
    if not isinstance(cds, dict) or not cds:
        body = json.dumps(block, sort_keys=True, default=str)
        return "block:" + hashlib.sha1(body.encode("utf-8")).hexdigest()[:8]
    classes = "+".join(str(c) for c in cds)
    pht = next((str(d["populated_from"]) for d in cds.values()
                if isinstance(d, dict) and d.get("populated_from")), "")
    items: list[str] = []
    if isinstance(cds.get("Visit"), dict):
        import _visit_ids  # noqa: PLC0415 - only Visit blocks need the enumerator
        slots = cds["Visit"].get("slot_derivations") or {}
        items = sorted(_visit_ids.labels(_visit_ids.slot_ids(slots.get("id")),
                                         include_fallback=True))
    if not items:
        phvs: set[str] = set()
        _value_phvs(cds, phvs)
        items = sorted(phvs)
    if not items:
        body = json.dumps(cds, sort_keys=True, default=str)
        items = ["body~" + hashlib.sha1(body.encode("utf-8")).hexdigest()[:8]]
    return f"{classes}@{pht}:{_short(items)}"


def file_identities(blocks: list) -> list[str]:
    """``block_identity`` for each block of one file, ``#2``, ``#3`` added on a collision."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for b in blocks:
        ident = block_identity(b)
        seen[ident] = seen.get(ident, 0) + 1
        out.append(ident if seen[ident] == 1 else f"{ident}#{seen[ident]}")
    return out


@dataclass(frozen=True)
class Key:
    rule: str
    file: str
    block: str
    message: str

    def text(self) -> str:
        return f"{self.file} | {self.block} | {self.message}"


class _Identities:
    """Block identities per cohort-relative file, parsed once per run."""

    def __init__(self, scanned_abs: dict[str, Path]):
        self._abs = scanned_abs
        self._cache: dict[str, list[str] | None] = {}

    def get(self, rel: str, index) -> str:
        if rel.endswith("/"):
            return "cohort"
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            return "file"
        if rel not in self._cache:
            self._cache[rel] = None
            p = self._abs.get(rel)
            if p is not None:
                try:
                    data = yaml.load(Path(p).read_text(encoding="utf-8"), Loader=_Loader)
                except (OSError, yaml.YAMLError):
                    data = None
                if data is not None:
                    self._cache[rel] = file_identities(data if isinstance(data, list) else [data])
        ids = self._cache[rel]
        if ids is None or index >= len(ids):
            return f"index:{index}"
        return ids[index]


def fingerprints(findings: list, identities: _Identities) -> dict[int, Key]:
    """``id(finding) -> Key`` for every finding under a cohort directory, unique per run."""
    raw: list[tuple[Key, object]] = []
    for f in findings:
        rel = cohort_relative(f.file)
        if rel is None:
            continue
        raw.append((Key(str(f.check), rel, identities.get(rel, f.block), message_key(f.message)),
                    f))
    raw.sort(key=lambda kf: (kf[0].rule, kf[0].file, kf[0].block, kf[0].message,
                             kf[1].block if isinstance(kf[1].block, int) else -1,
                             str(kf[1].message)))
    out: dict[int, Key] = {}
    seen: dict[Key, int] = {}
    for key, f in raw:
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = Key(key.rule, key.file, key.block, f"{key.message} (#{seen[key]})")
        out[id(f)] = key
    return out


# -- known issues ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    rule: str
    file: str
    block: str
    message: str
    issue: int
    status: str
    note: str = ""

    @property
    def key(self) -> Key:
        return Key(self.rule, self.file, self.block, self.message)

    def describe(self) -> str:
        return f"[{self.rule}] {self.file} | {self.block} | {self.message}"


def entry_line(key: Key, issue="<issue>", status="<status>", note: str = "") -> str:
    """One ``known_issues.yaml`` line. JSON strings are valid YAML double-quoted scalars."""
    s = (f"- {{rule: {json.dumps(key.rule)}, file: {key.file}, block: {json.dumps(key.block)}, "
         f"message: {json.dumps(key.message)}, issue: {issue}, status: {status}")
    if note:
        s += f", note: {json.dumps(note)}"
    return s + "}"


def load_entries(path: Path | str | None = None) -> list[Entry]:
    """Read and validate ``known_issues.yaml``. A malformed or duplicate entry raises ValueError."""
    p = Path(path) if path else known_issues_path()
    if not p.is_file():
        return []
    raw = yaml.load(p.read_text(encoding="utf-8"), Loader=_Loader) or []
    entries: list[Entry] = []
    seen: dict[Key, int] = {}
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{p.name} entry {i}: not a mapping")
        missing = [k for k in ("rule", "file", "block", "message", "issue", "status")
                   if item.get(k) in (None, "")]
        if missing:
            raise ValueError(f"{p.name} entry {i}: missing {', '.join(missing)}")
        if item["status"] not in STATUSES:
            raise ValueError(f"{p.name} entry {i}: status '{item['status']}' not in {STATUSES}")
        if not isinstance(item["issue"], int) or isinstance(item["issue"], bool) \
                or item["issue"] <= 0:
            raise ValueError(f"{p.name} entry {i}: issue must be a GitHub issue number")
        e = Entry(rule=str(item["rule"]), file=str(item["file"]), block=str(item["block"]),
                  message=str(item["message"]), issue=item["issue"], status=item["status"],
                  note=str(item.get("note") or ""))
        if e.key in seen:
            raise ValueError(f"{p.name} entries {seen[e.key]} and {i} name the same finding: "
                             f"{e.describe()}")
        seen[e.key] = i
        entries.append(e)
    return entries


def prune_entries(stale: list[Entry], path: Path | str | None = None) -> None:
    """Delete exactly the lines of ``stale`` from ``known_issues.yaml``; touch nothing else.

    A ``# <file>.yaml`` header left with no entry under it goes too.
    """
    p = Path(path) if path else known_issues_path()
    drop = {e.key for e in stale}
    kept: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            item = yaml.load(line, Loader=_Loader)
            if isinstance(item, list) and item and isinstance(item[0], dict):
                d = item[0]
                k = Key(str(d.get("rule")), str(d.get("file")), str(d.get("block")),
                        str(d.get("message")))
                if k in drop:
                    continue
        kept.append(line)
    out: list[str] = []
    for i, line in enumerate(kept):
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        if (line.startswith("# ") and line.rstrip().endswith((".yaml", "-ingest/"))
                and (nxt is None or not nxt.startswith("- "))):
            continue
        out.append(line)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


# -- WARNING baseline ------------------------------------------------------------------------

def load_baseline(path: Path | str | None = None) -> dict[str, dict[str, list[str]]]:
    """``{rule: {cohort: [fingerprint text, ...]}}``."""
    p = Path(path) if path else baseline_path()
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("warnings", {})


def _rule_order(rule: str):
    return tuple(int(x) if x.isdigit() else -1 for x in re.findall(r"\d+|[a-z]", rule))


def write_baseline(rows: dict[str, dict[str, list[str]]], path: Path | str | None = None) -> None:
    p = Path(path) if path else baseline_path()
    clean: dict[str, dict[str, list[str]]] = {}
    for r in sorted(rows, key=_rule_order):
        by_c = {c: sorted(set(v)) for c, v in sorted(rows[r].items()) if v}
        if by_c:
            clean[r] = by_c
    out = {
        "about": "Every WARNING finding, by rule and cohort, as 'file | block | message' "
                 "(hv-lint/_known_issues.py). CI fails on a fingerprint not listed here and on "
                 f"a listed one that no finding has. Drop fixed rows: {PRUNE_CMD}. "
                 f"Accept new ones (a reviewed change): {UPDATE_CMD}",
        "warnings": clean,
    }
    p.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


# -- the one entry point ---------------------------------------------------------------------

def finalize(
    findings: list,
    *,
    checks: Iterable[str],
    scanned_files: Iterable,
    make_finding: Callable[[str, int, str, str, str], object],
    partial: bool = False,
    entries: list[Entry] | None = None,
    baseline: dict[str, dict[str, list[str]]] | None = None,
    mode: str | None = None,
) -> list:
    """Apply known issues to ``findings`` in place and return the KI / RATCHET findings to add.

    ``checks`` are the rule ids this component ran and ``scanned_files`` the YAML files it read:
    an entry or baseline row is in scope when its rule is in ``checks`` and its file was scanned
    -- or, for a cohort-level one, when the run covered its cohort and was not ``partial``
    (``--file``). ``make_finding(file, block, check, severity, message)`` builds the caller's own
    Finding type. ``mode`` is ``"check"``, ``"prune"`` or ``"update"``; by default it comes from
    :data:`PRUNE_ENV` / :data:`UPDATE_ENV`.
    """
    checks = {str(c) for c in checks}
    if mode is None:
        mode = ("update" if os.environ.get(UPDATE_ENV) == "1"
                else "prune" if os.environ.get(PRUNE_ENV) == "1" else "check")
    extra: list = []
    meta = "hv-lint/known_issues.yaml"
    if mode != "check" and (partial or os.environ.get(RUN_ALL_ENV) != "1"):
        why = "a --file run" if partial else "a run not started by run_all.py"
        extra.append(make_finding(
            meta, -1, "KI", "ERROR",
            f"refusing to {mode} on {why}: it would rewrite rows for files it did not scan. "
            f"Run: {PRUNE_CMD if mode == 'prune' else UPDATE_CMD}"))
        mode = "check"

    scanned_abs: dict[str, Path] = {}
    for f in scanned_files:
        rel = cohort_relative(f)
        if rel:
            scanned_abs[rel] = Path(f)
    scanned = set(scanned_abs)
    keys = fingerprints(findings, _Identities(scanned_abs))
    cohorts = {cohort_of(r) for r in scanned}
    cohorts |= {cohort_of(k.file) for k in keys.values() if k.file.endswith("/")}

    def in_scope(rule: str, rel: str) -> bool:
        if rule not in checks:
            return False
        if rel.endswith("/"):
            return not partial and cohort_of(rel) in cohorts
        return rel in scanned

    # Known issues: exact fingerprint match.
    entries = load_entries() if entries is None else entries
    by_key = {e.key: e for e in entries}
    matched: set[Key] = set()
    for f in findings:
        k = keys.get(id(f))
        e = by_key.get(k) if k else None
        if e is None:
            continue
        matched.add(k)
        f.severity = "INFO"
        f.message = (f"{f.message} [known issue #{e.issue}, {e.status}"
                     + (f": {e.note}" if e.note else "") + "]")
    stale = [e for e in entries if e.key not in matched and in_scope(e.rule, e.file)]
    if mode == "prune" and stale:
        prune_entries(stale)
        for e in stale:
            extra.append(make_finding(meta, -1, "KI", "INFO",
                                      f"pruned stale known-issue entry {e.describe()} (#{e.issue})"))
    else:
        for e in stale:
            extra.append(make_finding(
                meta, -1, "KI", "ERROR",
                f"stale known-issue entry {e.describe()} (#{e.issue}): it matches no finding any "
                f"more, so the issue is fixed here. Remove it (and every other fixed entry or "
                f"WARNING row) with: {PRUNE_CMD}"))

    # WARNING ratchet: exact fingerprint sets per rule and cohort.
    current: dict[str, dict[str, set[str]]] = {}
    for f in findings:
        k = keys.get(id(f))
        if k is None or f.severity != "WARNING" or k.rule not in checks:
            continue
        current.setdefault(k.rule, {}).setdefault(str(cohort_of(k.file)), set()).add(k.text())
    base = load_baseline() if baseline is None else baseline

    def row_in_scope(rule: str, text: str) -> bool:
        return in_scope(rule, text.split(" | ", 1)[0])

    gone = sorted((r, c, t) for r, by_c in base.items() for c, rows in by_c.items()
                  for t in rows
                  if row_in_scope(r, t) and t not in current.get(r, {}).get(c, set()))
    new = sorted((r, c, t) for r, by_c in current.items() for c, rows in by_c.items()
                 for t in rows if t not in set(base.get(r, {}).get(c, [])))
    if mode == "update":
        rows = {r: {c: [t for t in v if not row_in_scope(r, t)] for c, v in by_c.items()}
                for r, by_c in base.items()}
        for r, by_c in current.items():
            for c, ts in by_c.items():
                rows.setdefault(r, {}).setdefault(c, []).extend(ts)
        write_baseline(rows)
    else:
        for r, c, t in new:
            extra.append(make_finding(
                "hv-lint/warning_baseline.json", -1, "RATCHET", "ERROR",
                f"new WARNING [{r}] in {c}: {t}. Fix it; or, if it is accepted, add it to the "
                f"baseline in this PR ({UPDATE_CMD}) and say why"))
        if mode == "prune" and gone:
            drop = set(gone)
            write_baseline({r: {c: [t for t in v if (r, c, t) not in drop]
                                for c, v in by_c.items()} for r, by_c in base.items()})
            for r, c, t in gone:
                extra.append(make_finding("hv-lint/warning_baseline.json", -1, "RATCHET", "INFO",
                                          f"pruned fixed WARNING [{r}] {t}"))
        else:
            for r, c, t in gone:
                extra.append(make_finding(
                    "hv-lint/warning_baseline.json", -1, "RATCHET", "ERROR",
                    f"WARNING [{r}] in {c} is fixed: {t}. Remove it from the baseline (and every "
                    f"other fixed row or entry) with: {PRUNE_CMD}"))

    unlisted = sorted((keys[id(f)] for f in findings
                       if f.severity in ("ERROR", "CRITICAL") and id(f) in keys),
                      key=lambda k: (k.file, k.block, k.rule, k.message))
    if unlisted:
        print(f"\n{len(unlisted)} ERROR finding(s) not in {meta}. Fix them; or, when one is "
              f"tracked in an issue, add its line (set issue and status):")
        for k in unlisted[:50]:
            print("  " + entry_line(k))

    dump = os.environ.get("HVLINT_DUMP_FINDINGS")
    if dump:
        with open(dump, "a", encoding="utf-8") as fh:
            for f in list(findings) + extra:
                k = keys.get(id(f))
                fh.write(json.dumps({"file": cohort_relative(f.file) or str(f.file),
                                     "block": f.block, "check": str(f.check),
                                     "severity": f.severity, "message": f.message,
                                     "key": k.text() if k else None}) + "\n")
    return extra
