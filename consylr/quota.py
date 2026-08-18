# SPDX-License-Identifier: MIT
"""Quota checking, per RFC-0002 and RFC-0003.

Two constraints, deliberately not one:

* **Certainty allocation** — what the model learns to do. Certainty is a
  property of a *case*, not of a family: a `fee_at_source` case with a
  supporting policy line is itself a clearly-supported case. Treating the two
  as one allocation double-counts.
* **Family coverage** — every family present in numbers sufficient to be
  measured on its own, because per-family metrics are reported and a family
  with a handful of cases produces a number with no meaning.

Both are checked before a corpus is written. A corpus that quietly missed its
quota still produces a score, and that score looks exactly like a good one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from consylr.violation import Violation

ABSTENTION_FAMILY = "cause_not_established"


@dataclass(frozen=True)
class Plan:
    """The quotas a corpus is built to.

    The abstention share is a *measured* quantity opening at 10–15%, not a
    decision. It moves only between runs, only on sealed-set measurements, and
    only against the two gauges in RFC-0002 — never to flatter a score.
    """

    families: frozenset[str]
    family_floor: int = 20
    supported_share: tuple[float, float] = (0.40, 0.50)
    abstention_share: tuple[float, float] = (0.10, 0.15)


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def check(cases: Iterable[Mapping[str, str]], plan: Plan) -> list[Violation]:
    """Every way a corpus fails its plan, naming the shortfall and its size."""
    rows = list(cases)
    if not rows:
        return [Violation("empty_corpus", "a corpus with no cases satisfies nothing")]

    total = len(rows)
    by_family = Counter(str(r.get("family")) for r in rows)
    abstention = by_family.get(ABSTENTION_FAMILY, 0)

    # The abstention family is the one place the two axes are not independent:
    # it is *defined* by the packet failing to explain the difference, so a row
    # in it cannot also be clearly supported. Left uncounted, such a row fills
    # the supported band and the abstention band at once and a corpus short of
    # its certainty allocation passes.
    contradictory = sum(
        1
        for r in rows
        if r.get("family") == ABSTENTION_FAMILY and r.get("certainty") == "supported"
    )
    supported = sum(
        1
        for r in rows
        if r.get("certainty") == "supported" and r.get("family") != ABSTENTION_FAMILY
    )

    violations: list[Violation] = []

    if contradictory:
        violations.append(
            Violation(
                "contradictory_certainty",
                f"{contradictory} of {total} cases are {ABSTENTION_FAMILY} labelled "
                "'supported'; that family's correct answer is ambiguous or unsupported, "
                "so the label is a mislabel rather than a corpus choice",
            )
        )

    lo, hi = plan.supported_share
    got = _share(supported, total)
    if got < lo:
        violations.append(
            Violation(
                "supported_share_low",
                f"clearly-supported cases are {got:.1%} of {total}; the floor is {lo:.0%}",
            )
        )
    elif got > hi:
        violations.append(
            Violation(
                "supported_share_high",
                f"clearly-supported cases are {got:.1%} of {total}; the ceiling is {hi:.0%}",
            )
        )

    lo, hi = plan.abstention_share
    got = _share(abstention, total)
    if got < lo:
        violations.append(
            Violation(
                "abstention_share_low",
                f"{ABSTENTION_FAMILY} is {got:.1%} of {total}; the floor is {lo:.0%} — "
                "below it the family is learned as a rare escape hatch rather than an answer",
            )
        )
    elif got > hi:
        violations.append(
            Violation(
                "abstention_share_high",
                f"{ABSTENTION_FAMILY} is {got:.1%} of {total}; the ceiling is {hi:.0%} — "
                "above it abstention becomes cheap and false abstention rises",
            )
        )

    for family in sorted(set(by_family) - plan.families):
        violations.append(
            Violation("unknown_family", f"{family!r} is not a family this plan names")
        )

    for family in sorted(plan.families):
        got_n = by_family.get(family, 0)
        if got_n < plan.family_floor:
            violations.append(
                Violation(
                    "family_below_floor",
                    f"{family} has {got_n} cases; the floor is {plan.family_floor}",
                )
            )

    return violations


def satisfiable(size: int, plan: Plan) -> list[Violation]:
    """Whether a corpus of `size` could meet the plan at all.

    Checked before a build rather than after: building a corpus that cannot
    satisfy its plan and failing the audit wastes the build, and refusing up
    front can name the constraint that cannot be met.
    """
    violations: list[Violation] = []

    floor_total = plan.family_floor * len(plan.families)
    if floor_total > size:
        violations.append(
            Violation(
                "family_floor_unreachable",
                f"{len(plan.families)} families at a floor of {plan.family_floor} need "
                f"{floor_total} cases; the requested size is {size}",
            )
        )

    # The abstention family is subject to both constraints at once, and they can
    # contradict: its floor is a count, its ceiling is a share. At a small size
    # the floor alone can breach the ceiling, and no corpus of that size exists.
    if ABSTENTION_FAMILY in plan.families:
        ceiling = plan.abstention_share[1]
        if _share(plan.family_floor, size) > ceiling:
            violations.append(
                Violation(
                    "abstention_ceiling_unreachable",
                    f"{ABSTENTION_FAMILY} needs at least {plan.family_floor} cases to be measurable, "
                    f"which is {_share(plan.family_floor, size):.1%} of {size} — above its "
                    f"{ceiling:.0%} ceiling. No corpus of this size satisfies both.",
                )
            )

    return violations
