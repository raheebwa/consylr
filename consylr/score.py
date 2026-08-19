# SPDX-License-Identifier: MIT
"""Scoring a model's answers against the exam, per RFC-0001's metric table.

Most of this is arithmetic. Two parts are not, and both are places where a
plausible implementation measures the wrong thing.

**Abstention has two directions and only one of them looks like a failure.**
Correct abstention on unsupported cases is the capability the product is sold
on; false abstention on clearly-supported cases is what it costs. A model that
refuses everything scores perfectly on the first and is useless, so the two are
reported side by side and never combined.

**`missing_record` abstains through its `open` entry, not its certainty.** Its
matches are supported — the clean pairs really do correspond — and the refusal
is the orphan in residue with an entry saying what would settle it. A refusal
rate computed from certainty alone misses that family entirely, which is the
measurement-design point recorded on #16 while the corpus was being built.

An unparseable answer is counted and not scored. Scoring it as zero on every
metric would mix two different failures — the model that cannot produce JSON and
the model that produces the wrong answer — and the remedies are not the same.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from consylr import schema
from consylr.canonical import ordered

#: The families whose correct answer is a refusal, per RFC-0002. Named here
#: because the scorer must know which direction of abstention a case tests.
ABSTAINING = frozenset({"cause_not_established", "missing_record", "decoy", "ambiguous_pair"})


@dataclass(frozen=True)
class Answer:
    """One exam question, the key, and what the model said."""

    packet: Mapping[str, Any]
    expected: Mapping[str, Any]
    produced: str
    family: str


@dataclass
class Tally:
    """Counts for a slice of the exam, kept as counts until asked for a rate."""

    asked: int = 0
    parsed: int = 0
    valid: int = 0
    exact: int = 0
    matched: float = 0.0
    predicted: float = 0.0
    truth: float = 0.0
    cited: int = 0
    resolved: int = 0
    abstain_asked: int = 0
    abstain_right: int = 0
    confident_asked: int = 0
    abstain_wrong: int = 0

    def _rate(self, part: float, whole: float) -> float:
        return part / whole if whole else 0.0

    @property
    def parse_rate(self) -> float:
        return self._rate(self.parsed, self.asked)

    @property
    def schema_valid(self) -> float:
        return self._rate(self.valid, self.asked)

    @property
    def exact_match(self) -> float:
        return self._rate(self.exact, self.asked)

    @property
    def correspondence_f1(self) -> float:
        precision = self._rate(self.matched, self.predicted)
        recall = self._rate(self.matched, self.truth)
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    @property
    def citation_resolution(self) -> float:
        return self._rate(self.resolved, self.cited)

    @property
    def correct_abstention(self) -> float:
        return self._rate(self.abstain_right, self.abstain_asked)

    @property
    def false_abstention(self) -> float:
        return self._rate(self.abstain_wrong, self.confident_asked)


@dataclass
class Report(Tally):
    per_family: dict[str, Tally] = field(default_factory=dict)


def _correspondences(output: Mapping[str, Any]) -> set[tuple[frozenset[str], frozenset[str]]]:
    """The claims an answer makes, as comparable things.

    Only supported and ambiguous matches: an `unsupported` match asserts no
    correspondence, so counting it as one would credit a model for the pairs it
    explicitly rejected.
    """
    out = set()
    for match in output.get("matches", []) or []:
        if not isinstance(match, dict) or match.get("c") not in ("supported", "ambiguous"):
            continue
        left = frozenset(str(i) for i in match.get("l", []) or [])
        right = frozenset(str(i) for i in match.get("r", []) or [])
        out.add((left, right))
    return out


def _abstains(output: Mapping[str, Any]) -> bool:
    """Whether an answer declines to settle something.

    Read from three places, because the families decline in three ways: a
    certainty below `supported`, an `open` entry saying what is missing, or a
    disposition that asks rather than accepts. `missing_record` uses only the
    second, which is why certainty alone is not enough.
    """
    for match in output.get("matches", []) or []:
        if isinstance(match, dict) and match.get("c") in ("ambiguous", "unsupported"):
            return True
    if output.get("open"):
        return True
    return any(
        isinstance(d, dict) and d.get("act") in ("request", "escalate", "hold")
        for d in output.get("do", []) or []
    )


def _tally(answer: Answer, into: Sequence[Tally]) -> None:
    for tally in into:
        tally.asked += 1

    try:
        produced = json.loads(answer.produced)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(produced, dict):
        return

    # Compared through a canonical list order, because the gold's own order is
    # arbitrary — see `consylr.canonical`. Without it a correct answer scores
    # zero for listing its matches in a different sequence, which on rung 6000
    # cost 46 of 204 and reported `decoy` at 0% with all fourteen right.
    #
    # Inside the same guard as the parse, because `ordered` recurses over raw
    # model output. A deep enough answer would raise past the caller and end the
    # run, discarding every raw answer `record` exists to keep — a whole
    # evaluation lost to one bad case, which is the opposite of the module's
    # rule that an unparseable answer is counted and not scored.
    try:
        same = ordered(produced) == ordered(answer.expected)
    except RecursionError:
        return
    for tally in into:
        tally.parsed += 1
        if not schema.validate(produced, answer.packet):
            tally.valid += 1
        if same:
            tally.exact += 1

    claimed = _correspondences(produced)
    truth = _correspondences(answer.expected)
    for tally in into:
        tally.matched += len(claimed & truth)
        tally.predicted += len(claimed)
        tally.truth += len(truth)

    records = {str(r.get("id")) for r in answer.packet.get("records", []) or []}
    policy = {str(p.get("id")) for p in answer.packet.get("policy", []) or []}
    documents = {str(d.get("id")) for d in answer.packet.get("documents", []) or []}
    known = records | policy | documents
    citations = [
        str(i)
        for section in ("matches", "exceptions", "open")
        for entry in (produced.get(section, []) or [])
        if isinstance(entry, dict)
        for i in (entry.get("why", []) or [])
    ]
    for tally in into:
        tally.cited += len(citations)
        tally.resolved += sum(1 for c in citations if c.split(":")[0] in known)

    abstained = _abstains(produced)
    if answer.family in ABSTAINING:
        for tally in into:
            tally.abstain_asked += 1
            tally.abstain_right += int(abstained)
    else:
        for tally in into:
            tally.confident_asked += 1
            tally.abstain_wrong += int(abstained)


def score(answers: Iterable[Answer]) -> Report:
    """Every metric RFC-0001 names, overall and per family."""
    report = Report()
    for answer in answers:
        family = report.per_family.setdefault(answer.family, Tally())
        _tally(answer, (report, family))
    return report


def record(
    answers: Sequence[Answer],
    report: Report,
    *,
    exam: str,
    model: str,
    mode: str,
    **extra: Any,
) -> dict[str, Any]:
    """One run, in the form it is kept in — metrics and what was actually said.

    **The raw output is retained on every case, not only on failures.** RFC-0001
    left that open; the first scaffolded reference run closed it. It reported a
    correspondence F1 of exactly 0.500 on nine of fourteen families, the
    arithmetic behind it was sound, and the only way to tell an honest result
    from an artefact was to read what the model emitted — which the run had
    scored and thrown away.

    Failure-only retention would not have helped. Those answers parsed. An
    implausible number on a well-formed answer is precisely the case it misses,
    and it is the case worth investigating, because a malformed answer already
    announces itself.
    """
    return {
        "exam": exam,
        "model": model,
        "mode": mode,
        "packets": len(answers),
        "parse_rate": report.parse_rate,
        "schema_valid": report.schema_valid,
        "exact_match": report.exact_match,
        "correspondence_f1": report.correspondence_f1,
        "citation_resolution": report.citation_resolution,
        "correct_abstention": report.correct_abstention,
        "false_abstention": report.false_abstention,
        "per_family": {
            f: {"exact": t.exact_match, "f1": t.correspondence_f1, "n": t.asked}
            for f, t in report.per_family.items()
        },
        "cases": [{"family": a.family, "produced": a.produced} for a in answers],
        **extra,
    }


def positional(packet: Mapping[str, Any]) -> str:
    """What a model that reads nothing would answer: pair record n with record n.

    **This is a control, and every reported correspondence F1 belongs beside it.**
    The generator emits records in correspondence order on both sides, so pairing
    by list position and claiming every pair supported is a winning policy that
    consults no amount, no reference, no date and no policy line. On sealed-v4 it
    scores **0.839** correspondence F1. A tuned model at 0.904 is therefore 0.065
    above reading nothing — not 0.904 above it, which is how the raw figure reads
    to anyone who has not seen this number.

    It is built from the packet's identifiers alone. The moment it consults
    `expected` it stops being a control and becomes a cheat, so it does not take
    the answer key as an argument at all.

    Records left unpaired by a length mismatch are declared residue rather than
    matched, because a control that claimed them would score better than reading
    nothing can and would understate the real gain.
    """
    ids = [str(r.get("id", "")) for r in packet.get("records", [])]
    left = [i for i in ids if i.startswith("A-")]
    right = [i for i in ids if i.startswith("B-")]
    paired = min(len(left), len(right))
    return json.dumps(
        {
            "matches": [
                {"l": [a], "r": [b], "c": "supported", "why": [a, b]}
                for a, b in zip(left[:paired], right[:paired], strict=True)
            ],
            "exceptions": [],
            "open": [],
            "residue": {"l": left[paired:], "r": right[paired:]},
            "do": [{"act": "accept", "on": left[:paired] + right[:paired]}],
        }
    )
