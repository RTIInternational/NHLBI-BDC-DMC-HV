#!/usr/bin/env python3
"""HV-Lint Phase 3: status-slot value_mappings semantic checks (Rules 3.17, 3.18).

A status slot (condition_status, exposure_status, procedure_status, or any
other ``*_status`` slot) maps source codes to PRESENT / HISTORICAL / ABSENT.
These checks read what each mapped code means in dbGaP and flag mappings
that say the opposite.

Requires:
  - Extended PHV detail index (``<cohort>_detail.json.gz``): code labels,
    descriptions, table membership
  - Value-count index (``<cohort>_stats.json.gz``, build_phv_stats_index.py):
    var_report n and per-code counts. Optional: without it 3.17b does not run
    and 3.18 falls back to its label-only signal.

Checks:
    3.17  Status polarity
          a) a code whose dbGaP label clearly means no / never / none /
             not taking maps to PRESENT or HISTORICAL, or a clearly
             affirmative label ("yes", "yes, now", "taking") maps to ABSENT
          b) an unlabelled flag observed only as 1/2 is mapped with 0/1 keys:
             '0' -> ABSENT never fires and '1' (the "No" of a 1=No/2=Yes flag)
             is emitted PRESENT
    3.18  Conditional follow-up mapped to ABSENT -- '0' / "No" -> ABSENT on a
          question asked only of people who reported the condition
          ("hospitalized for MI?" asked after "new MI? yes"), so "No" means
          "had it, not hospitalized", not "does not have it"

Usage:
    python hv-lint/phase-3/check_status_semantic.py --cache-dir hv-lint/dbgap-cache
    python hv-lint/phase-3/check_status_semantic.py --cache-dir hv-lint/dbgap-cache --cohort CHS
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
import _cohorts  # noqa: E402
import _known_issues  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_value_semantic as _cvs  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}
PHV_RE = re.compile(r"phv\d{8}")

POSITIVE_STATUS = {"PRESENT", "HISTORICAL"}
NEGATIVE_STATUS = {"ABSENT"}

# --- Label classification (3.17a, 3.18) ------------------------------------
#
# Deliberately conservative: a label is classified only when its meaning is
# not in doubt. Anything hedged, partial or missing-like returns None.

# Hedged, missing-like or partial labels. Checked first: "not sure" and
# "no answer" start like a negative but are not one; "yes, doubtful" and
# "yes, not now" start like an affirmative but are not one.
_AMBIGUOUS_LABEL_RE = re.compile(
    r"don'?t know|do not know|not sure|unsure|uncertain|doubtful|questionable|"
    r"possibl|probabl|maybe|borderline|suspect|unknown|refus|missing|"
    r"not applicable|\bn/?a\b|not asked|not done|not ascertained|not recorded|"
    r"not assessed|not available|not collected|not obtained|not answered|"
    r"not coded|not interviewed|not examined|not measured|not reported|"
    r"not determined|not verified|not confirmed|"
    r"\bno (?:answer|response|data|info|information|record|form|visit|exam|"
    r"interview|value|reading|result|test|measurement|sample|contact)\b|"
    r"\bbut\b|\bnot now\b|\bunless\b",
    re.IGNORECASE,
)

_NEGATIVE_LABEL_RE = re.compile(
    r"^(?:no|none|never|negative|absent|denie[sd]|not"
    r"|(?:did|does|do|has|have|had|was|is|were) not"
    r"|didn'?t|doesn'?t|don'?t|hasn'?t|haven'?t|wasn'?t|isn'?t)\b",
    re.IGNORECASE,
)

_MIXED_NEGATIVE_RE = re.compile(
    r"\byes\b|\bnow\b|\bcurrently\b|\bat present\b|\bat this time\b|"
    r"\bformerly\b|\bformer\b|\bpreviously\b|\bpast\b|\bused to\b|\bany more\b|"
    r"\banymore\b|\bno longer\b|\bnot since\b",
    re.IGNORECASE,
)

_AFFIRMATIVE_LABEL_RE = re.compile(
    r"^(?:yes(?:\W+(?:now|currently|current|definite|definitely|confirmed|"
    r"taking|present))?|(?:currently )?taking|present|positive)\W*$",
    re.IGNORECASE,
)


def _strip_code_prefix(label: str, code: str) -> str:
    """Drop a leading "<code> =" / "<code>:" echo such as "1 = Yes"."""
    return re.sub(rf"^\s*{re.escape(code)}\s*[=:)]\s*", "", label).strip()


def classify_label(label: str, code: str = "") -> str | None:
    """Return "negative", "affirmative" or None (not clear enough to judge)."""
    text = _strip_code_prefix(label or "", code) if code else (label or "").strip()
    text = re.sub(r"\s+", " ", text)
    if not text or _AMBIGUOUS_LABEL_RE.search(text):
        return None
    if _NEGATIVE_LABEL_RE.match(text):
        # "No/Yes", "never ... yes": both polarities in one label -> no call.
        # "Not present now, formerly definite": a time-limited negative is a
        # history answer, which HISTORICAL may correctly carry.
        if _MIXED_NEGATIVE_RE.search(text):
            return None
        return "negative"
    if _AFFIRMATIVE_LABEL_RE.match(text):
        return "affirmative"
    return None


def negative_answer(code: str, codes: dict | None) -> bool:
    """A "No" answer: ``code``'s label in the variable's ``codes`` is negative, or the variable has
    no code labels at all and the code is 'N' or '0'.

    A variable dbGaP publishes without code labels (ARIC IFIA06A, observed N / Y / U) still
    answers "No" with 'N'. An unlabelled code of a LABELLED variable means nothing yet: its
    meaning is a curator question (CARDIA A12CB* observed '0', #873 Q19), not a "No".
    """
    label = (codes or {}).get(code)
    if label:
        return classify_label(label, code) == "negative"
    if codes:
        return False
    return str(code).strip().upper() in {"N", "0"}


# --- Follow-up detection (3.18) --------------------------------------------

# Phrases that mark a question asked about an event the participant already
# reported (signal b).
FOLLOWUP_PHRASE_RE = re.compile(
    r"hospitali[sz]ed|hospital for|treated in|seen by|how old|"
    r"under medical care|emergency room",
    re.IGNORECASE,
)

# Condition vocabulary for sibling matching. Two variables are siblings
# only when their descriptions name the same condition from this list, so
# "HOSPITALIZED FOR MI" matches "NEW MYOCARDIAL INFARCTION" while form
# boilerplate ("[Derived Variable Dataset, visit 4]") and relatives
# ("natural mother") never make a match. A condition missing here means no
# sibling and no finding: the list errs toward silence.
CONDITION_PATTERNS: dict[str, re.Pattern] = {
    key: re.compile(rx, re.IGNORECASE) for key, rx in {
        "myocardial infarction": r"myocardial|heart attack|\bmi\b",
        "angina": r"angina",
        "stroke": r"stroke|\bstk\b|cerebrovascular|\bcva\b",
        "tia": r"\btia\b|transient ischemic",
        "heart failure": r"heart failure|\bchf\b|\bhf\b",
        "copd": r"\bcopd\b|chronic obstructive",
        "emphysema": r"emphysema",
        "bronchitis": r"bronchitis",
        "asthma": r"asthma",
        "diabetes": r"diabet",
        "hypertension": r"(?<!pulmonary )hypertension|high blood pressure|\bhbp\b|\bhtn\b",
        "atrial fibrillation": r"atrial fibrillation|\bafib\b",
        "peripheral artery disease": r"claudication|peripheral arter|peripheral vascular|\bpad\b",
        "venous thromboembolism": r"thrombosis|\bdvt\b|blood clot|embol",
        "left ventricular hypertrophy": r"ventricular hypertrophy|\blvh\b",
        "coronary heart disease": r"coronary heart|coronary artery disease|\bchd\b|\bcad\b",
        "cancer": r"cancer|malignan",
        "kidney disease": r"kidney|renal",
    }.items()
}


# A sibling about a relative ("Family history of stroke") or about the form
# itself ("Diabetes Questionnaire form present") is not a screening question
# for the participant's condition.
_FAMILY_RE = re.compile(
    r"family|mother|father|parent|sibling|brother|sister|relative|offspring",
    re.IGNORECASE,
)
_ADMIN_RE = re.compile(
    r"\b(?:form|questionnaire)\b.*\b(?:present|completed|administered|available|done)\b",
    re.IGNORECASE,
)
# "Exam 27", "visit 4", "year 10": a sibling from another exam of a
# multi-exam table is the same question asked at another time.
_EXAM_NUMBER_RE = re.compile(r"\b(?:exam|visit|year|yr|cycle)\s*(\d+)", re.IGNORECASE)


def _exam_numbers(description: str) -> set[str]:
    return set(_EXAM_NUMBER_RE.findall(description or ""))


@lru_cache(maxsize=None)
def condition_terms(description: str) -> frozenset[str]:
    """Return the conditions a description names (keys of CONDITION_PATTERNS).

    Bracketed text is dropped first: it names the source form or dataset.
    """
    text = re.sub(r"\[[^\]]*\]", " ", description or "")
    return frozenset(key for key, rx in CONDITION_PATTERNS.items() if rx.search(text))


def _shared_condition(a: set[str], b: set[str]) -> set[str]:
    return a & b


# Signal (a): the follow-up's n lies between these multiples of the
# sibling's "yes" count. The upper bound allows for a few people answering
# the follow-up after a "don't know" on the screening question; the lower
# bound stops a small-n variable matching any sibling with a large "yes"
# count. (CHS MIHOSP59 n=38 vs NEWMI59 yes=38; HSSTK22 n=216 vs STK22
# yes=229.)
FOLLOWUP_N_RATIO_MAX = 1.1
FOLLOWUP_N_RATIO_MIN = 0.5
# The screening question must split the table: a sibling answered "yes" by
# more than half its respondents cannot separate a follow-up from a question
# asked of everyone (ARIC derived "PAD41" n=6061 matched an aspirin-code
# variable with yes=6210 before this bound).
SIBLING_MAX_YES_SHARE = 0.5
# Below this many "yes" answers a ratio match is noise (FHS fy591 n=1 vs a
# sibling with yes=2 matched before this floor).
FOLLOWUP_MIN_COUNT = 5
# Signal (c), a gate question that names no condition ("FOLLOW A SPECIAL
# DIET", "HOSPITALIZED IN PAST FOUR WEEKS") opening a branch of per-condition
# items ("FOR DIABETES", "HOSPITALIZED FOR HEART ATTACK"). With no shared
# condition to pair them, the count alone decides, so its band is narrower
# than signal (a)'s: CHS DIABF38 n=792 vs DIETF38 yes=921 (0.86), DIABO38
# 116 vs OFFDIT38 137 (0.85), DIABF58 124 vs DIETF58 127, ARIC IFIA06A 355
# vs IFIA05 360. The measurement behind the bound is in #885.
GATE_N_RATIO_MIN = 0.8
# A branch item names the reason for the gate's "yes": "FOR DIABETES" (a
# special diet's reason), "HOSPITALIZED FOR HEART ATTACK". A question that
# merely follows a gate ("did your mother ever have a stroke?" after "is
# your mother's history known?") is not one: its "No" is a real ABSENT.
GATE_ITEM_RE = re.compile(r"(?:^|\.\s+)for\b", re.IGNORECASE)

# A confirmation or adjudication follow-up ("CONFIRMED: ATRIAL
# FIBRILLATION", "ASTHMA CONFIRMED BY MD") re-decides the condition, so its
# "No" may legitimately be ABSENT.
_CONFIRMATION_RE = re.compile(r"confirm|verif|adjudicat|validat", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DetailIndex:
    """The shared detail index's records plus a table -> PHVs lookup for siblings.

    ``records`` values are check_value_semantic.PhvDetail (or any object with
    name / pht / description / codes).
    """
    records: dict = field(default_factory=dict)
    by_pht: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: dict) -> "DetailIndex":
        idx = cls(records=dict(records))
        for phv, rec in idx.records.items():
            idx.by_pht.setdefault(rec.pht, []).append(phv)
        return idx


@dataclass
class PhvStats:
    n: int
    counts: dict[str, int]


@dataclass
class FollowUp:
    """Evidence that a variable is a conditional follow-up question."""
    sibling_phv: str
    sibling_name: str
    sibling_yes: int | None
    n: int | None
    count_signal: bool
    phrase_signal: bool
    gate: bool = False

    def evidence(self) -> str:
        parts = []
        if self.gate:
            parts.append(
                f"n={self.n} vs gate question {self.sibling_name} ({self.sibling_phv}) "
                f"yes={self.sibling_yes}"
            )
        elif self.count_signal:
            parts.append(
                f"n={self.n} vs {self.sibling_name} ({self.sibling_phv}) "
                f"yes={self.sibling_yes}"
            )
        else:
            parts.append(f"sibling {self.sibling_name} ({self.sibling_phv})")
        if self.phrase_signal:
            parts.append("follow-up wording in label")
        return "; ".join(parts)


@dataclass
class Finding:
    file: str
    block: int
    check: str
    severity: str
    message: str

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        return f"  {sev}  block {self.block:>3}  [{self.check}] {self.message}"

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error", "HIGH": "warning",
            "WARNING": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        file_esc = (self.file.replace("%", "%25").replace("\r", "%0D")
                    .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))
        msg_esc = self.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return f"::{level} file={file_esc}::HV-Lint [{self.check}] {msg_esc} (block {self.block})"


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------


def load_detail_index(cache_dir: Path, cache_key: str) -> DetailIndex:
    """Load the extended detail index through the shared Phase 3 loader."""
    return DetailIndex.from_records(_cvs.load_detail_index(cache_dir, cache_key).records)


def cohort_cache_pairs(cohort: str, cache_dir: Path) -> list[tuple[str, str]]:
    """``[(cohort_name, cache_key)]`` from the resolver every phase uses."""
    return _cohorts.cohorts_to_load(cohort, cache_dir, find_transform_dir())


def load_stats_index(cache_dir: Path, cache_key: str) -> dict[str, PhvStats] | None:
    """Load the value-count index (build_phv_stats_index.py), or None when it is absent.

    The one reader of ``<cache_key>_stats.json.gz``: the same release-keyed stem as the
    detail index (``phs000287.v7_stats.json.gz`` beside ``phs000287.v7_detail.json.gz``).
    Only coded variables (an entry with ``c``) are returned: a variable missing from it has no
    coded values in its var_report. ``load_nonnull_counts`` reads every variable's n.
    """
    raw = _read_stats(cache_dir, cache_key)
    if raw is None:
        return None
    return {
        phv: PhvStats(n=int(rec.get("n", 0)), counts=dict(rec["c"] or {}))
        for phv, rec in raw.items() if "c" in rec
    }


def load_nonnull_counts(cache_dir: Path, cache_key: str) -> dict[str, int] | None:
    """``{phv: non-null n}`` for every variable the release's var_reports describe.

    None when the index is absent, or when it holds coded variables only (built before n was
    kept for every variable): every release has uncoded variables (at least its subject id),
    so such an index cannot tell an empty variable from an unreported one. A variable missing
    from the result has no var_report; its n is unknown, not 0.
    """
    raw = _read_stats(cache_dir, cache_key)
    if raw is None or all("c" in rec for rec in raw.values()):
        return None
    return {phv: int(rec.get("n", 0)) for phv, rec in raw.items()}


def _read_stats(cache_dir: Path, cache_key: str) -> dict | None:
    gz_path = Path(cache_dir) / f"{cache_key}_stats.json.gz"
    if not gz_path.exists():
        return None
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def find_yaml_files(base_dir: Path, cohort: str) -> list[Path]:
    files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.endswith(".swp")
    )
    if cohort.lower() != "all":
        pattern = f"{cohort}-ingest".lower()
        files = [f for f in files if any(part.lower() == pattern for part in f.parts)]
    return files


def detect_cohort(file_path: Path) -> str:
    for part in file_path.parts:
        if part.endswith("-ingest"):
            return part.replace("-ingest", "")
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def iter_status_mappings(block: dict):
    """Yield (class_name, slot_name, phv, value_mappings) for each status slot.

    A status slot is any slot named ``*_status`` that reads one PHV through
    ``populated_from`` and maps its codes with ``value_mappings``.
    """
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return
    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        slots = cls_def.get("slot_derivations")
        if not isinstance(slots, dict):
            continue
        for slot_name, slot_def in slots.items():
            if not slot_name.endswith("_status") or not isinstance(slot_def, dict):
                continue
            vm = slot_def.get("value_mappings")
            pf = slot_def.get("populated_from")
            if not isinstance(vm, dict) or not vm:
                continue
            if not isinstance(pf, str) or not PHV_RE.fullmatch(pf):
                continue
            yield cls_name, slot_name, pf, {str(k): v for k, v in vm.items()}


def _yes_count(detail, stats: PhvStats) -> int:
    """Count of a screening variable's affirmative answers.

    Every coded answer that is neither negative nor missing-like counts, so
    "TOLD DURING PAST YEAR" and "YES, EMERGENCY ROOM" are both "yes".
    """
    total = 0
    for code, count in stats.counts.items():
        label = (detail.codes or {}).get(code, "")
        if not label:
            continue
        if _AMBIGUOUS_LABEL_RE.search(label) or _NEGATIVE_LABEL_RE.match(label.strip()):
            continue
        total += count
    return total


def detect_followup(
    phv: str, detail_idx: DetailIndex, stats: dict[str, PhvStats] | None,
) -> FollowUp | None:
    """Return follow-up evidence for ``phv``, or None.

    A sibling is a coded yes/no variable that comes earlier in the same
    table (lower phv), names the same condition (CONDITION_PATTERNS) and is
    not itself worded as a follow-up. The variable is a follow-up when

      (a) its var_report n is within [FOLLOWUP_N_RATIO_MIN,
          FOLLOWUP_N_RATIO_MAX] x a sibling's "yes" count, and that sibling
          is answered "yes" by at most SIBLING_MAX_YES_SHARE of its
          respondents (count signal), or
      (b) its description has follow-up wording and a sibling exists, and
          the cohort has no value-count index, or
      (c) it is worded as an item of a branch ("FOR DIABETES", follow-up
          wording) and the gate that opens the branch -- the nearest earlier
          coded variable asked of more people, naming no condition ("follow a
          special diet?", "hospitalized in the past four weeks?") -- has a
          "yes" count within [GATE_N_RATIO_MIN, FOLLOWUP_N_RATIO_MAX] of its
          n (_detect_gate). Used only when (a) finds no sibling.

    When the cohort has counts they decide: follow-up wording on a question
    asked of everyone ("since your last exam, were you hospitalized for
    heart failure?") is not a conditional follow-up, and its "No" is a
    statement about the interval, not a skipped branch. A variable missing
    from a loaded count index has no coded values in its var_report.
    """
    detail = detail_idx.records.get(phv)
    if detail is None:
        return None
    terms = condition_terms(detail.description)
    if not terms:
        return None
    phrase = bool(FOLLOWUP_PHRASE_RE.search(detail.description))
    own = stats.get(phv) if stats else None

    best: FollowUp | None = None
    for sib_phv in detail_idx.by_pht.get(detail.pht, []):
        # The screening question precedes its follow-up in the table.
        if sib_phv >= phv:
            continue
        sib = detail_idx.records[sib_phv]
        if not sib.codes or FOLLOWUP_PHRASE_RE.search(sib.description):
            continue
        if _ADMIN_RE.search(sib.description):
            continue
        if _FAMILY_RE.search(sib.description) and not _FAMILY_RE.search(detail.description):
            continue
        own_exams, sib_exams = _exam_numbers(detail.description), _exam_numbers(sib.description)
        if own_exams and sib_exams and not (own_exams & sib_exams):
            continue
        if not _shared_condition(terms, condition_terms(sib.description)):
            continue
        if not any(classify_label(lbl, c) == "affirmative" for c, lbl in sib.codes.items()):
            continue

        count_signal = False
        sib_yes = None
        sib_stats = stats.get(sib_phv) if stats else None
        if own is not None and sib_stats is not None and sib_stats.n > 0:
            sib_yes = _yes_count(sib, sib_stats)
            if (sib_yes >= FOLLOWUP_MIN_COUNT and own.n > 0
                    and sib_yes <= SIBLING_MAX_YES_SHARE * sib_stats.n
                    and FOLLOWUP_N_RATIO_MIN * sib_yes
                    <= own.n <= FOLLOWUP_N_RATIO_MAX * sib_yes):
                count_signal = True

        if not (count_signal or (phrase and stats is None)):
            continue
        cand = FollowUp(
            sibling_phv=sib_phv, sibling_name=sib.name, sibling_yes=sib_yes,
            n=own.n if own else None, count_signal=count_signal,
            phrase_signal=phrase,
        )
        if best is None or (cand.count_signal and not best.count_signal):
            best = cand
    # A same-condition sibling outranks a gate, so a variable both match keeps the evidence (and
    # the known-issue fingerprint) it had before gates were recognised.
    if (best is None or not best.count_signal) and own is not None:
        gate = _detect_gate(phv, detail, own, detail_idx, stats, phrase)
        if gate is not None:
            return gate
    return best


def _detect_gate(phv: str, detail, own: PhvStats, detail_idx: DetailIndex,
                 stats: dict[str, PhvStats], phrase: bool) -> FollowUp | None:
    """Signal (c): the nearest earlier coded variable that opens the branch ``phv`` sits in.

    ``phv`` must read as an item of a branch (GATE_ITEM_RE, or follow-up wording). Walking back
    from it, every coded variable passed must be asked of about as few people (n at most
    FOLLOWUP_N_RATIO_MAX x ``phv``'s n); the first one that is not is the candidate gate.
    It must name no condition, carry an affirmative code, be answered "yes" by at most
    SIBLING_MAX_YES_SHARE of its respondents and at least FOLLOWUP_MIN_COUNT times, and its
    "yes" count must be within [GATE_N_RATIO_MIN, FOLLOWUP_N_RATIO_MAX] of ``phv``'s n. A
    coincidental count far up the table (CHS DIABF38 n=792 vs HAPPEN05 yes=988) is never
    reached, because the walk stops at the first variable asked of more people.
    """
    if not (phrase or GATE_ITEM_RE.search(detail.description)):
        return None
    earlier = sorted((p for p in detail_idx.by_pht.get(detail.pht, []) if p < phv),
                     reverse=True)
    for sib_phv in earlier:
        sib_stats = stats.get(sib_phv)
        if sib_stats is None or sib_stats.n <= 0:
            continue
        if sib_stats.n <= FOLLOWUP_N_RATIO_MAX * own.n:
            continue  # another item of the same branch, asked of about as many people
        sib = detail_idx.records[sib_phv]
        if not sib.codes or condition_terms(sib.description) or _ADMIN_RE.search(sib.description):
            return None
        if not any(classify_label(lbl, c) == "affirmative" for c, lbl in sib.codes.items()):
            return None
        sib_yes = _yes_count(sib, sib_stats)
        if not (sib_yes >= FOLLOWUP_MIN_COUNT
                and sib_yes <= SIBLING_MAX_YES_SHARE * sib_stats.n
                and GATE_N_RATIO_MIN * sib_yes <= own.n <= FOLLOWUP_N_RATIO_MAX * sib_yes):
            return None
        return FollowUp(
            sibling_phv=sib_phv, sibling_name=sib.name, sibling_yes=sib_yes, n=own.n,
            count_signal=True, phrase_signal=phrase, gate=True,
        )
    return None


# ---------------------------------------------------------------------------
# Check 3.17: status polarity
# ---------------------------------------------------------------------------


def _observed_codes(st: PhvStats) -> set[str]:
    return {c for c, n in st.counts.items() if n > 0}


def check_status_polarity(
    block: dict, block_idx: int, rel_path: str,
    detail_idx: DetailIndex, stats: dict[str, PhvStats] | None,
) -> list[Finding]:
    findings: list[Finding] = []
    for cls_name, slot_name, phv, vm in iter_status_mappings(block):
        detail = detail_idx.records.get(phv)
        if detail is None:
            continue
        codes = detail.codes or {}
        where = f"{cls_name}.{slot_name} {phv} ({detail.name})"

        # 3.17a: label says the opposite of the target.
        followup: FollowUp | None = None
        followup_checked = False
        for code, target in vm.items():
            if not isinstance(target, str) or code not in codes:
                continue
            label = codes[code]
            polarity = classify_label(label, code)
            if polarity == "negative" and target in POSITIVE_STATUS:
                # On a conditional follow-up, "No" answers the follow-up
                # ("not hospitalized"), not the condition; the person had it.
                if not followup_checked:
                    followup = detect_followup(phv, detail_idx, stats)
                    followup_checked = True
                if followup is not None:
                    continue
                findings.append(Finding(
                    rel_path, block_idx, "3.17", "ERROR",
                    f"Status polarity: {where} code '{code}' (\"{label}\") -> "
                    f"{target}; a negative answer must not emit {target}",
                ))
            elif polarity == "affirmative" and target in NEGATIVE_STATUS:
                findings.append(Finding(
                    rel_path, block_idx, "3.17", "ERROR",
                    f"Status polarity: {where} code '{code}' (\"{label}\") -> "
                    f"{target}; an affirmative answer must not emit ABSENT",
                ))

        # 3.17b: unlabelled 1/2 flag read with 0/1 keys.
        if codes or not stats or phv not in stats:
            continue
        observed = _observed_codes(stats[phv])
        if ({"1", "2"} <= observed and "0" not in observed
                and vm.get("0") in NEGATIVE_STATUS
                and vm.get("1") in POSITIVE_STATUS):
            findings.append(Finding(
                rel_path, block_idx, "3.17", "ERROR",
                f"Status polarity: {where} has no code labels and is observed "
                f"only as {', '.join(sorted(observed))} (var_report), but is "
                f"mapped '0' -> {vm['0']}, '1' -> {vm['1']}: '0' never occurs, "
                f"so the lower code of a 1/2 flag (1 = No) is emitted "
                f"{vm['1']}",
            ))
    return findings


# ---------------------------------------------------------------------------
# Check 3.18: conditional follow-up mapped to ABSENT
# ---------------------------------------------------------------------------


def check_followup_absent(
    block: dict, block_idx: int, rel_path: str,
    detail_idx: DetailIndex, stats: dict[str, PhvStats] | None,
) -> list[Finding]:
    findings: list[Finding] = []
    for cls_name, slot_name, phv, vm in iter_status_mappings(block):
        # Only condition status: a drug or procedure follow-up ("taking meds
        # for diabetes?", "type of procedure: angioplasty?") asks about the
        # exposure itself, so its "No" is a true ABSENT for that exposure.
        if slot_name != "condition_status":
            continue
        detail = detail_idx.records.get(phv)
        if detail is None:
            continue
        codes = detail.codes or {}
        absent_codes = [
            c for c, t in vm.items()
            if t in NEGATIVE_STATUS
            and (c == "0" or negative_answer(c, codes))
        ]
        if not absent_codes:
            continue
        if _CONFIRMATION_RE.search(detail.description):
            continue
        fu = detect_followup(phv, detail_idx, stats)
        if fu is None:
            continue
        # A gate match is a count match on the item that opens the branch, which the item's own
        # wording ("FOR DIABETES") confirms: as strong as count + phrase.
        severity = ("ERROR" if fu.gate or (fu.count_signal and fu.phrase_signal)
                    else "WARNING")
        code_list = ", ".join(
            f"'{c}'" + (f" (\"{codes[c]}\")" if c in codes else "")
            for c in absent_codes
        )
        findings.append(Finding(
            rel_path, block_idx, "3.18", severity,
            f"Follow-up question mapped to ABSENT: {cls_name}.{slot_name} "
            f"{phv} ({detail.name}, \"{detail.description}\") maps {code_list} "
            f"-> ABSENT, but it is asked only of people who reported the "
            f"condition [{fu.evidence()}]; its \"No\" answers the follow-up, "
            f"not whether the person has the condition",
        ))
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Checks 3.17-3.18: status-slot value_mappings semantics"
    )
    p.add_argument(
        "--cache-dir", required=True,
        help="Directory containing *_detail.json.gz and *_stats.json.gz indexes"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort or 'all' (default: all)"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity for non-zero exit (default: error)"
    )
    p.add_argument(
        "--expect-study", default=None,
        help="OVERRIDE the release the cohort declares (phs000287 or phs000287.v7) for one "
             "named --cohort. The release check always runs; without this flag the expectation "
             "comes from the cohort's _manifest-<cohort>.yaml."
    )
    args = p.parse_args()
    _cohorts.reject_expect_study_for_all(p, args)
    return args


def main() -> int:
    args = parse_args()
    # The file scan matches `<cohort>-ingest`, so an alias or a padded `all` must name the
    # DIRECTORY here, as `cohorts_to_load` already names the cache; otherwise the run loads the
    # cache and scans no file.
    args.cohort = _cohorts.canonical_cohort(args.cohort, find_transform_dir())
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    cache_dir = Path(args.cache_dir)

    if not cache_dir.is_dir():
        print(f"ERROR: Cache directory not found: {cache_dir}", file=sys.stderr)
        return 1

    indexes: dict[str, DetailIndex] = {}
    stats_by_cohort: dict[str, dict[str, PhvStats] | None] = {}
    missing_index: list[str] = []
    for cohort_name, cache_key in cohort_cache_pairs(args.cohort, cache_dir):
        try:
            indexes[cohort_name] = load_detail_index(cache_dir, cache_key)
        except FileNotFoundError:
            # A cohort with no detail index would have every file skipped; a new cohort with no
            # known-issue entries would then pass unchecked, so this fails like a missing stats
            # index does.
            print(f"ERROR: no {cache_key}_detail.json.gz for {cohort_name} in {cache_dir}: "
                  f"3.17 / 3.18 DID NOT RUN for it.", file=sys.stderr)
            missing_index.append(cohort_name)
            continue
        # The release this component reads is checked here too, so run alone it cannot pass on a
        # superseded cache that only a sibling component would have caught.
        release_error = _cohorts.release_check_error(cohort_name, cache_dir, cache_key,
                                                     args.expect_study)
        if release_error:
            print(release_error, file=sys.stderr)
            return 1
        stats_by_cohort[cohort_name] = load_stats_index(cache_dir, cache_key)
        st = stats_by_cohort[cohort_name]
        if st is None:
            # Without counts 3.17b cannot run and 3.18 loses its count signal; a weakened rule
            # that passes is a skipped check, so this fails rather than warns.
            print(f"ERROR: no {cache_key}_stats.json.gz for {cohort_name} in {cache_dir}: "
                  f"3.17b and the 3.18 count signal cannot run. Build it with "
                  f"hv-lint/build_phv_stats_index.py --cohort {cache_key}.", file=sys.stderr)
            missing_index.append(cohort_name)
            continue
        print(f"  Loaded {cohort_name}: {len(indexes[cohort_name].records):,} PHVs, "
              f"{len(st):,} with var_report counts")

    if missing_index:
        return 1

    if not indexes:
        print("ERROR: No detail indexes found.", file=sys.stderr)
        return 1

    base_dir = find_transform_dir()
    hv_root = base_dir.parent
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        # A named cohort with nothing to scan was not checked; only `all` over an empty tree
        # has nothing to fail.
        return 1 if args.cohort.lower() != "all" else 0

    print(f"Found {len(yaml_files)} YAML files to validate")

    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0

    for file_path in yaml_files:
        rel_path = file_path.relative_to(hv_root).as_posix()
        cohort = detect_cohort(file_path)
        if cohort not in indexes:
            continue
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if data is None:
            continue

        blocks = data if isinstance(data, list) else [data]
        files_checked += 1
        for idx, block in enumerate(blocks):
            blocks_checked += 1
            if not isinstance(block, dict):
                continue
            all_findings.extend(check_status_polarity(
                block, idx, rel_path, indexes[cohort], stats_by_cohort[cohort]))
            all_findings.extend(check_followup_absent(
                block, idx, rel_path, indexes[cohort], stats_by_cohort[cohort]))

    # Report
    # Known issues, stale entries and the WARNING ratchet (hv-lint/_known_issues.py).
    all_findings.extend(_known_issues.finalize(
        all_findings, checks={"3.17", "3.18"}, scanned_files=yaml_files, make_finding=Finding))

    fail_rank = SEVERITY_RANK[args.fail_on.upper()]
    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"\n{'='*70}")
    print("HV-Lint Checks 3.17-3.18: Status-Slot value_mappings Semantics")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")
    parts = [f"{counts[s]} {s}" for s in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO")
             if counts.get(s, 0) > 0]
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print("Findings:       None -- all status mappings consistent")

    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath], key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    blocking = [f for f in all_findings if SEVERITY_RANK.get(f.severity, 0) >= fail_rank]
    if blocking:
        print(f"\nFAILED: {len(blocking)} findings at or above '{args.fail_on}'")
        return 1
    if all_findings:
        print(f"\nPASSED (with {len(all_findings)} advisory findings below fail threshold)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
