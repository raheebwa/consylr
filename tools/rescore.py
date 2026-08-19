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

The exam is re-read from disk and the record's cases are matched to it in order.
That correspondence is an assumption, so it is checked: the record carries each
case's family, and a family that disagrees with the exam's means the record was
produced against a different exam and the run is refused rather than re-scored
into a plausible number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from consylr.score import Answer, score


def rescore(exam: Path, result: Path) -> tuple[dict[str, float], dict[str, float]]:
    """The stored metrics and the ones today's scorer gives, for the same answers."""
    stored = json.loads(result.read_text(encoding="utf-8"))
    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    kept = stored.get("cases") or []
    if len(kept) != len(cases):
        raise ValueError(
            f"{result.name} holds {len(kept)} answers and {exam.name} asks {len(cases)}; "
            "these are not the same exam"
        )

    answers = []
    for case, got in zip(cases, kept, strict=True):
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        if meta["family"] != got.get("family"):
            raise ValueError(
                f"{result.name} records {got.get('family')} where {exam.name} asks "
                f"{meta['family']} at {case.name}; the record is against another exam"
            )
        answers.append(
            Answer(
                packet=json.loads((case / "packet.json").read_text(encoding="utf-8")),
                expected=json.loads((case / "expected.json").read_text(encoding="utf-8")),
                produced=got["produced"],
                family=meta["family"],
            )
        )

    report = score(answers)
    now = {
        "parse_rate": report.parse_rate,
        "schema_valid": report.schema_valid,
        "exact_match": report.exact_match,
        "correspondence_f1": report.correspondence_f1,
        "correct_abstention": report.correct_abstention,
        "false_abstention": report.false_abstention,
    }
    return {k: float(stored.get(k, 0.0)) for k in now}, now


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    exam = Path(sys.argv[1])
    width = max(len(Path(a).name) for a in sys.argv[2:])
    print(f"{'run':<{width}}  {'metric':<18} {'as scored':>10} {'canonical':>10}")
    for arg in sys.argv[2:]:
        result = Path(arg)
        was, now = rescore(exam, result)
        for metric in was:
            if abs(was[metric] - now[metric]) < 1e-9 and metric != "exact_match":
                continue
            print(f"{result.name:<{width}}  {metric:<18} {was[metric]:>9.1%} {now[metric]:>9.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
