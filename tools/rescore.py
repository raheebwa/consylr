# SPDX-License-Identifier: MIT
"""Re-score a stored run record against the exam, without re-running the model.

A run record keeps every raw answer, not only the failures — which is what makes
this possible. When the scorer changes, the question "what would this run have
scored" is answerable from disk in seconds instead of by spending the GPU hours
again, and the old file is left exactly as it was.

It exists because the scorer did change: exact match used to compare answers in
list order, and the gold's own order is arbitrary. The corrected figure and the
figure that was reported are both real, and both belong in the record — so this
prints them side by side rather than replacing one with the other.

    python -m tools.rescore <exam dir> <result.json> [<result.json> ...]

**It refuses rather than guesses, in two directions.** A record carries the
digest of the exam it was scored against, so re-scoring it against a different
one is caught by the check `evaluate.py` already makes before it will score
anything — matching family sequences would otherwise let a confident table be
computed against packets the model never saw. And a metric the record does not
carry has no baseline, so there is nothing to compare; defaulting it to zero
would report a run predating the metric as a hundred-point gain and credit it to
whatever change is under review.

Runs that cannot be re-scored are expected input, not an accident: this
project's own base and scaffolded evaluations predate answer retention and hold
none. So one refusal does not end a batch — it prints, the rest are examined,
and the exit status says something was refused.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from consylr.corpus import content_digest
from consylr.score import Answer, positional, score

#: Every metric a record carries, and the reason the null control travels with
#: correspondence F1 wherever it is printed: a model that reads nothing scores
#: 0.839 on this exam by pairing record *n* with record *n*, so the raw figure
#: reads as far better than it is to anyone who has not seen the control. A
#: control kept in a script nobody runs is a control nobody sees.
METRICS = (
    "parse_rate",
    "schema_valid",
    "exact_match",
    "correspondence_f1",
    "correct_abstention",
    "false_abstention",
)


def rescore(exam: Path, result: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The stored metrics and the ones today's scorer gives, for the same answers."""
    stored = json.loads(result.read_text(encoding="utf-8"))
    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    kept = stored.get("cases") or []
    if len(kept) != len(cases):
        raise ValueError(
            f"{result.name} holds {len(kept)} answers and {exam.name} asks {len(cases)}; "
            "these are not the same exam"
        )

    recorded = str(stored.get("exam_digest", ""))
    digest = content_digest(exam)
    if recorded != digest:
        raise ValueError(
            f"{result.name} was scored against exam digest {recorded[:12] or 'none'}, "
            f"not the {digest[:12]} on disk; re-scoring it would compute a number "
            "against packets the model was never shown"
        )

    missing = [m for m in METRICS if stored.get(m) is None]
    if missing:
        raise ValueError(
            f"{result.name} carries no {', '.join(missing)}; there is no baseline to "
            "compare against, and a zero would report the absence as a regression"
        )

    answers, nulls = [], []
    for case, got in zip(cases, kept, strict=True):
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        if meta["family"] != got.get("family"):
            raise ValueError(
                f"{result.name} records {got.get('family')} where {exam.name} asks "
                f"{meta['family']} at {case.name}; the record is against another exam"
            )
        packet = json.loads((case / "packet.json").read_text(encoding="utf-8"))
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        answers.append(
            Answer(
                packet=packet, expected=expected, produced=got["produced"], family=meta["family"]
            )
        )
        nulls.append(
            Answer(
                packet=packet,
                expected=expected,
                produced=positional(packet),
                family=meta["family"],
            )
        )

    report = score(answers)
    now: dict[str, Any] = {m: float(getattr(report, m)) for m in METRICS}
    now["null_correspondence_f1"] = score(nulls).correspondence_f1
    now["per_family"] = {f: t.exact_match for f, t in report.per_family.items()}
    was: dict[str, Any] = {m: float(stored[m]) for m in METRICS}
    was["per_family"] = {
        f: float(v.get("exact", 0.0)) for f, v in (stored.get("per_family") or {}).items()
    }
    return was, now


def _report(name: str, was: dict[str, Any], now: dict[str, Any], width: int) -> None:
    for metric in METRICS:
        if metric == "correspondence_f1":
            # Not a percentage. Printed with its control, per RFC-0001.
            print(
                f"{name:<{width}}  {metric:<20} {was[metric]:>9.3f} {now[metric]:>9.3f}"
                f"   (null {now['null_correspondence_f1']:.3f})"
            )
        elif metric == "exact_match" or abs(was[metric] - now[metric]) >= 1e-9:
            print(f"{name:<{width}}  {metric:<20} {was[metric]:>9.1%} {now[metric]:>9.1%}")
    before, after = was["per_family"], now["per_family"]
    for family in sorted(after):
        if family in before and abs(before[family] - after[family]) >= 1e-9:
            print(f"{name:<{width}}    {family:<18} {before[family]:>9.1%} {after[family]:>9.1%}")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(__doc__)
        return 2
    exam = Path(args[0])
    width = max(len(Path(a).name) for a in args[1:])
    print(f"{'run':<{width}}  {'metric':<20} {'as scored':>9} {'canonical':>9}")
    refused = 0
    for arg in args[1:]:
        result = Path(arg)
        try:
            was, now = rescore(exam, result)
        except (ValueError, OSError, json.JSONDecodeError) as refusal:
            print(f"REFUSED: {refusal}")
            refused += 1
            continue
        _report(result.name, was, now, width)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
