# SPDX-License-Identifier: MIT
"""The twin-probe's pair-level metric.

    python -m tools.probe_report <probe corpus dir> <eval result.json>

**A diagnostic probe, not an exam.** It shares its mechanism with the training
corpus — the same `withhold_cause` twins — so what it measures is whether the
behaviour generalises to new instances of a construction the model has seen. Not
a general capability, and not a substitute for the sealed set. That caveat is
printed with the numbers, because a figure this quotable travels without its
context otherwise.

**The metric is the flip.** Each pair is two packets whose records, amounts, dates
and documents are byte-identical and whose policy differs by one line. A flip is
both halves right: settled answered, withheld declined for an unestablished
cause. Aggregate scores move for many reasons; a model that changes its answer
when one policy line is withheld from an otherwise identical packet is reading
evidence, and nothing else explains it.

**The two ways of failing are counted apart**, for the same reason abstention has
two directions in RFC-0001. A model that declines everything gets every withheld
half right and is useless. A model that asserts everything gets every settled half
right and is the model we already have — certainty read off the family rather than
the policy. A single combined score hides both.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from consylr.score import _abstains


@dataclass(frozen=True)
class Pair:
    """One minimal pair, and what the model said about each half."""

    family: str
    settled: str
    withheld: str


@dataclass
class Tally:
    asked: int = 0
    flips: int = 0
    unparsed: int = 0
    asserted_on_withheld: int = 0
    declined_on_settled: int = 0

    @property
    def flip_rate(self) -> float:
        return self.flips / self.asked if self.asked else 0.0


@dataclass
class Report(Tally):
    per_family: dict[str, Tally] = field(default_factory=dict)


def _parsed(text: str) -> dict[str, Any] | None:
    try:
        out = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return out if isinstance(out, dict) else None


def _declines_unestablished(out: dict[str, Any]) -> bool:
    return any(
        isinstance(e, dict) and e.get("kind") == "cause_not_established"
        for e in out.get("exceptions", []) or []
    )


def report(pairs: list[Pair]) -> Report:
    """Flip rate and both failure directions, overall and per family."""
    out = Report()
    for p in pairs:
        family = out.per_family.setdefault(p.family, Tally())
        for t in (out, family):
            t.asked += 1

        settled, withheld = _parsed(p.settled), _parsed(p.withheld)
        if settled is None or withheld is None:
            # Counted and not scored, per RFC-0001: a half that never parsed did
            # not decline and did not assert, and scoring it as either would mix
            # two failures whose remedies differ.
            for t in (out, family):
                t.unparsed += 1
            continue

        answered = not _abstains(settled)
        declined = _declines_unestablished(withheld)
        for t in (out, family):
            if answered and declined:
                t.flips += 1
            if not declined:
                t.asserted_on_withheld += 1
            if not answered:
                t.declined_on_settled += 1
    return out


def pairs_from(corpus: Path, result: Path) -> list[Pair]:
    """Match each stored answer to its case, then each withheld case to its twin."""
    stored = json.loads(result.read_text(encoding="utf-8"))
    cases = sorted(p for p in corpus.iterdir() if (p / "packet.json").exists())
    kept = stored.get("cases") or []
    if len(kept) != len(cases):
        raise ValueError(
            f"{result.name} holds {len(kept)} answers and {corpus.name} asks {len(cases)}"
        )

    said: dict[str, str] = {}
    family: dict[str, str] = {}
    for case, got in zip(cases, kept, strict=True):
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        said[case.name] = got["produced"]
        family[case.name] = meta["family"]

    out = []
    for name in sorted(said):
        if "-probe-" not in name:
            continue
        head, _, rest = name.partition("-probe-")
        n, index = rest.split("-")
        twin = f"{head}-{500 + int(n):03d}-{index}"
        if twin not in said:
            raise ValueError(f"{name} has no settled twin in {corpus.name}")
        out.append(Pair(family=family[name], settled=said[twin], withheld=said[name]))
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    corpus, result = Path(sys.argv[1]), Path(sys.argv[2])
    r = report(pairs_from(corpus, result))

    print(f"=== twin probe: {corpus.name} / {result.name} ===")
    print("DIAGNOSTIC PROBE, NOT AN EXAM — shares the twin mechanism with training, so it")
    print("measures generalisation of the behaviour to new instances, not general capability.")
    print(f"pairs                 {r.asked}")
    print(f"flip rate             {r.flip_rate:.1%}   ({r.flips} both halves right)")
    print(f"asserted on withheld  {r.asserted_on_withheld}  (read the family, not the policy)")
    print(f"declined on settled   {r.declined_on_settled}  (declines regardless)")
    print(f"unparsed halves       {r.unparsed}")
    print("\nper family (flip / asserts-on-withheld / declines-on-settled / n):")
    for f, t in sorted(r.per_family.items()):
        print(
            f"  {f:24s} {t.flip_rate:6.1%}  {t.asserted_on_withheld:4d}  "
            f"{t.declined_on_settled:4d}  {t.asked:4d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
