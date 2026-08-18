# SPDX-License-Identifier: MIT
"""The grouped split, per RFC-0003.

Roles are separated by scenario template, never by row. A template may produce
many cases; every case from one template lands in exactly one role.

This is the check whose failure is worst behaved in the whole project. A
template appearing in both roles does not merely go unnoticed — it **raises**
measured accuracy, because the model is examined on a scenario it was trained
on. Nothing downstream reports an error, and no inspection of model output can
find it. The partition itself is the only thing that can be checked.

So identity is taken from template *content*, and the declared id is a label
over it. Three constructions defeat a check that trusts the id, and each is
handled here rather than assumed away:

* **Aliasing** — one scenario committed twice under two ids. Assignment draws on
  the structural fingerprint, so both copies take the same draw and the leak is
  impossible by construction rather than merely detected.
* **A rewording** — two templates one paraphrase apart. RFC-0003 permits
  paraphrase to touch free-text surface fields only, so an identity over
  everything it may not touch is invariant under it.
* **Drift between build and audit** — the recorded id still resolves but no
  longer names what produced the case. The audit re-derives the fingerprint from
  the template on disk instead of believing the one in the corpus.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from consylr.templates import Template
from consylr.violation import Violation

TRAIN = "train"
HOLDOUT = "holdout"


def _draw(seed: int, structural_fingerprint: str) -> float:
    """A template's position in [0, 1), from the seed and its structural identity.

    Derived per template rather than from one shared stream: a shared stream
    makes each draw depend on how many were taken before it, so adding a
    template at the front re-partitions everything behind it and a corpus
    regenerated after an unrelated edit no longer matches the published one.
    """
    digest = hashlib.sha256(f"{seed}:{structural_fingerprint}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / (1 << 64)


def partition(templates: Iterable[Template], *, holdout_share: float, seed: int) -> dict[str, str]:
    """Which role each template's cases belong to, keyed by template id.

    Two templates that are the same scenario take the same draw, so an alias or
    a rewording cannot straddle the boundary however the ids are spelled.
    """
    return {
        t.id: HOLDOUT if _draw(seed, t.structural_fingerprint) < holdout_share else TRAIN
        for t in templates
    }


def check(cases: Iterable[Mapping[str, Any]], templates: Iterable[Template]) -> list[Violation]:
    """Every way a corpus's partition fails, including one built elsewhere."""
    rows = list(cases)
    known = {t.id: t for t in templates}

    if not rows:
        return [Violation("empty_corpus", "a corpus with no cases has no partition to check")]

    violations: list[Violation] = []

    roles_by_id: dict[str, set[str]] = {}
    for row in rows:
        template_id = str(row.get("template_id", ""))
        roles_by_id.setdefault(template_id, set()).add(str(row.get("role", "")))

    for template_id in sorted(i for i in roles_by_id if i not in known):
        violations.append(
            Violation(
                "unresolved_template",
                f"{template_id!r} is named by a case but is not a template that was loaded",
            )
        )

    for template_id in sorted(i for i, r in roles_by_id.items() if len(r) > 1 and i in known):
        named = ", ".join(sorted(roles_by_id[template_id]))
        violations.append(
            Violation(
                "template_in_two_roles",
                f"{template_id!r} has cases in {named}; every case from one template belongs "
                "to exactly one role",
                template_id,
            )
        )

    # Re-derived from the template on disk, never read from the corpus: the
    # corpus whose metadata cannot be believed is exactly the foreign one this
    # has to be able to fail.
    for template_id in sorted(i for i in roles_by_id if i in known):
        recorded = {
            str(r.get("template_fingerprint", ""))
            for r in rows
            if str(r.get("template_id", "")) == template_id
        }
        if "" in recorded:
            violations.append(
                Violation(
                    "no_recorded_fingerprint",
                    f"cases of {template_id!r} record no template fingerprint, so nothing in "
                    "them can be checked against the template that is on disk",
                    template_id,
                )
            )
        actual = known[template_id].fingerprint
        for drifted in sorted(f for f in recorded if f and f != actual):
            violations.append(
                Violation(
                    "template_drifted",
                    f"cases of {template_id!r} were built from {drifted[:12]} but the template "
                    f"on disk is {actual[:12]}; the id still resolves and no longer names what "
                    "produced them",
                    template_id,
                )
            )

    by_structure: dict[str, set[str]] = {}
    for template_id, roles in roles_by_id.items():
        template = known.get(template_id)
        if template is not None:
            by_structure.setdefault(template.structural_fingerprint, set()).update(roles)

    for structure in sorted(by_structure):
        if len(by_structure[structure]) > 1:
            ids = sorted(
                i
                for i in roles_by_id
                if i in known and known[i].structural_fingerprint == structure
            )
            violations.append(
                Violation(
                    "scenario_in_two_roles",
                    f"{', '.join(repr(i) for i in ids)} are one scenario and their cases are "
                    f"split across {', '.join(sorted(by_structure[structure]))}; the model is "
                    "examined on what it was trained on and the score rises",
                )
            )

    return violations
