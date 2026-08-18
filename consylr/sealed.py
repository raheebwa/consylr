# SPDX-License-Identifier: MIT
"""Sealing the evaluation set, per RFC-0003 and issue #15.

Sealed means sealed. No packet here is ever seen by a training run, and the seed
that produced it is recorded on every case — so the set can be rebuilt, and so
nobody re-draws it into training by reaching for a seed they believed was
unused.

**There is no role parameter, and that is the safety property.** RFC-0003 asks
`seal` to reject a training configuration *structurally* rather than by
convention, because a single command taking `--role` can be pointed at the wrong
one by a typo and the resulting corpus looks entirely correct. A `Sealed`
configuration cannot describe a training run: the role it writes is not
something a caller can supply.

The split is grouped by template *within* each family, never across them. Both
roles have to cover all fourteen families — per-family metrics are reported, so
a family missing from the exam is a metric that cannot be computed, and a family
missing from training is one the model never learns.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from consylr import corpus, prompt
from consylr.budget import Tokeniser
from consylr.cases import Case, build
from consylr.identity import scenario
from consylr.split import HOLDOUT
from consylr.templates import Template


@dataclass(frozen=True)
class Sealed:
    """What the exam is built from. It cannot describe anything else."""

    seed: int

    #: Two of the five templates per family, which puts roughly two hundred
    #: packets in the exam while leaving three fifths of every family for
    #: training. Both numbers are here rather than at a call site because the
    #: sealed set is frozen: changing them makes a different exam.
    per_family: int = 2
    cases_per_template: int = 7


def _rank(seed: int, template: Template) -> str:
    """A template's position within its family, from the seed and its scenario.

    Keyed on the scenario rather than the id, so two ids for one scenario sort
    together and cannot be separated into different roles by the choice below.
    """
    return hashlib.sha256(f"{seed}:{scenario(template)}".encode()).hexdigest()


def sealed_templates(templates: Iterable[Template], config: Sealed) -> list[Template]:
    """The templates the exam is drawn from, chosen per family.

    Deterministic and order-independent: a corpus rebuilt after a file is
    renamed is the same corpus.
    """
    by_family: dict[str, list[Template]] = {}
    for t in templates:
        by_family.setdefault(t.family, []).append(t)

    chosen: list[Template] = []
    for family in sorted(by_family):
        ordered = sorted(by_family[family], key=lambda t: _rank(config.seed, t))
        chosen.extend(ordered[: config.per_family])
    return chosen


def seal(
    templates: Iterable[Template],
    config: Sealed,
    out: Path,
    *,
    tokeniser: Tokeniser,
) -> Sequence[Path]:
    """Build the exam and write it, or write nothing.

    The audit is `corpus.write`'s, which compares every packet that would reach
    disk: identical packet under different answers, or in two roles, and no
    corpus at all if either holds.
    """
    cases: list[Case] = []
    for template in sealed_templates(templates, config):
        for index in range(config.cases_per_template):
            case = build(
                template,
                root_seed=config.seed,
                case_index=index,
                role=HOLDOUT,
                tokeniser=tokeniser,
                render=prompt.render,
                budget=prompt.BUDGET,
            )
            # Recorded per case rather than in a manifest beside them: a case
            # that travels alone still says which exam it belongs to and which
            # seed would rebuild it.
            case.meta["sealed_seed"] = config.seed
            cases.append(case)

    return corpus.write(out, cases)
