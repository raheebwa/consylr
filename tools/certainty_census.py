# SPDX-License-Identifier: MIT
"""What certainty a model emits, by family — the instrument that found the defect.

    python -m tools.certainty_census <exam dir> <result.json> [<result.json> ...]

Aggregate abstention rates hid it. Counting how often a tuned model declined, by
family, gave **nine families at exactly 100% and five at exactly 0%, with nothing
in between** — a model reading family identity rather than evidence, which no
average over those two groups could show. The overall numbers looked like a
threshold sitting in the wrong place; the per-family split showed there was no
threshold at all.

So this reports the distribution rather than a mean, and it reports
**strictly-between** as a figure of its own. A family that is neither always nor
never is a family whose answer moved with something other than its own identity,
which is the entire claim the decoupling makes. It is the finding, not a rounding
of the rate, and burying it inside a percentage is how it stayed invisible.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from consylr.cases import _certainty
from consylr.score import _abstains


@dataclass
class Tally:
    asked: int = 0
    unparsed: int = 0
    declined: int = 0
    labels: Counter[str] = field(default_factory=Counter)

    @property
    def scored(self) -> int:
        return self.asked - self.unparsed

    @property
    def decline_rate(self) -> float:
        return self.declined / self.scored if self.scored else 0.0

    @property
    def shares(self) -> dict[str, float]:
        total = sum(self.labels.values())
        return {k: v / total for k, v in self.labels.items()} if total else {}


@dataclass
class Census:
    per_family: dict[str, Tally] = field(default_factory=dict)

    @property
    def graded(self) -> int:
        """Families whose decline rate is strictly between never and always."""
        return sum(1 for t in self.per_family.values() if 0.0 < t.decline_rate < 1.0)


def census(answers: list[tuple[str, str]]) -> Census:
    """The distribution of what was emitted, per family."""
    out = Census()
    for family, produced in answers:
        tally = out.per_family.setdefault(family, Tally())
        tally.asked += 1
        try:
            body = json.loads(produced)
        except (json.JSONDecodeError, TypeError):
            tally.unparsed += 1
            continue
        if not isinstance(body, dict):
            tally.unparsed += 1
            continue
        tally.declined += _abstains(body)
        # The case's own certainty, by the same rule the corpus records — the
        # weakest correspondence the answer asserts. Counting every label
        # separately would report a two-match answer twice and make the shares
        # incomparable with the corpus census they are read against.
        tally.labels[_certainty(body)] += 1
    return out


def _answers(exam: Path, result: Path) -> list[tuple[str, str]]:
    stored = json.loads(result.read_text(encoding="utf-8"))
    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    kept = stored.get("cases") or []
    if len(kept) != len(cases):
        raise ValueError(
            f"{result.name} holds {len(kept)} answers and {exam.name} asks {len(cases)}"
        )
    out = []
    for case, got in zip(cases, kept, strict=True):
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        if meta["family"] != got.get("family"):
            raise ValueError(f"{result.name} is a record against another exam")
        out.append((str(meta["family"]), str(got["produced"])))
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    exam = Path(sys.argv[1])
    for arg in sys.argv[2:]:
        result = Path(arg)
        c = census(_answers(exam, result))
        print(f"\n=== {result.name} ===")
        print(
            f"{'family':24s} {'declines':>9} {'supported':>10} {'ambiguous':>10} {'unsupp':>8} {'n':>5}"
        )
        for f, t in sorted(c.per_family.items()):
            s: dict[str, Any] = t.shares
            print(
                f"{f:24s} {t.decline_rate:9.0%} {s.get('supported', 0):10.0%} "
                f"{s.get('ambiguous', 0):10.0%} {s.get('unsupported', 0):8.0%} {t.asked:5d}"
            )
        always = sum(1 for t in c.per_family.values() if t.decline_rate == 1.0)
        never = sum(1 for t in c.per_family.values() if t.decline_rate == 0.0)
        print(f"\nall-or-nothing: {always} families always decline, {never} never")
        print(f"GRADED (strictly between): {c.graded} — the families whose answer moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
