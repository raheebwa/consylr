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

    Fifty-three bits, not sixty-four: a 64-bit quotient is rounded to the nearest
    float64 and the largest of them rounds to exactly 1.0, which would put a
    template outside the interval this docstring claims and make a
    `holdout_share` of 1.0 not quite total.
    """
    digest = hashlib.sha256(f"{seed}:{structural_fingerprint}".encode()).digest()
    return (int.from_bytes(digest[:8], "big") >> 11) / (1 << 53)


def _validated_share(holdout_share: float) -> float:
    """Refuse a share that is not one.

    A percent written where a fraction was meant silently produced a corpus with
    no training cases at all, and a NaN silently produced one with no holdout —
    both of which the audit then passed, because a corpus holding one role has no
    boundary for anything to cross. RFC-0003 has the generator fail loudly on a
    constraint it cannot meet; quietly satisfying a nonsensical one is worse.
    """
    if not 0.0 <= holdout_share <= 1.0:  # false for NaN, which is the point
        raise ValueError(f"holdout_share must be a fraction in [0, 1], got {holdout_share!r}")
    return holdout_share


def partition(templates: Iterable[Template], *, holdout_share: float, seed: int) -> dict[str, str]:
    """Which role each template's cases belong to, keyed by template id.

    Two templates that are the same scenario take the same draw, so an alias or
    a rewording cannot straddle the boundary however the ids are spelled.
    """
    _validated_share(holdout_share)
    items = list(templates)

    # Keyed on the id, so two templates declaring one id would collapse to
    # whichever was read last — two templates in, one role out, with the winner
    # decided by directory order. The corpus then fails its audit as
    # `template_drifted`, pointing a reader at a content edit nobody made.
    seen: set[str] = set()
    for t in items:
        if t.id in seen:
            raise ValueError(f"{t.id!r} is declared by more than one template")
        seen.add(t.id)

    return {
        t.id: HOLDOUT if _draw(seed, t.structural_fingerprint) < holdout_share else TRAIN
        for t in items
    }


def check(
    cases: Iterable[Mapping[str, Any]],
    templates: Iterable[Template],
    *,
    expected: Mapping[str, str] | None = None,
) -> list[Violation]:
    """Every way a corpus's partition fails, including one built elsewhere.

    `expected` is the partition the corpus claims to have been built to. Given
    it, the check stops asking only whether the roles are self-consistent and
    starts asking whether they are the ones the seed and share actually produce —
    which is the difference between passing a corpus and passing its exact
    inverse.
    """
    rows = list(cases)
    known = {t.id: t for t in templates}

    if not rows:
        return [Violation("empty_corpus", "a corpus with no cases has no partition to check")]

    violations: list[Violation] = []

    roles_by_id: dict[str, set[str]] = {}
    seen_roles: set[str] = set()
    for row in rows:
        template_id = str(row.get("template_id", ""))
        role = row.get("role")
        if role not in (TRAIN, HOLDOUT):
            # Every unrecognised spelling once certified clean, because both leak
            # checks key off a template holding more than one role — so a corpus
            # with one uniform value made them structurally unreachable.
            violations.append(
                Violation(
                    "unknown_role",
                    f"{role!r} is not a role; every case belongs to {TRAIN!r} or {HOLDOUT!r}",
                    template_id or None,
                )
            )
            continue
        seen_roles.add(role)
        roles_by_id.setdefault(template_id, set()).add(role)

    for absent in sorted({TRAIN, HOLDOUT} - seen_roles):
        violations.append(
            Violation(
                "role_missing",
                f"no case is in {absent!r}; a corpus holding one role has no boundary for "
                "anything to cross, so every leak check below is vacuous on it",
            )
        )

    if expected is not None:
        for template_id in sorted(roles_by_id):
            want = expected.get(template_id)
            if want is not None and roles_by_id[template_id] != {want}:
                violations.append(
                    Violation(
                        "role_not_as_partitioned",
                        f"{template_id!r} is recorded as "
                        f"{', '.join(sorted(roles_by_id[template_id]))} but the partition it "
                        f"claims puts it in {want!r}",
                        template_id,
                    )
                )

    for template_id in sorted(set(known) - set(roles_by_id)):
        violations.append(
            Violation(
                "template_unused",
                f"{template_id!r} was loaded but produced no case; a corpus covering one "
                "template of many is not a corpus this partition describes",
                template_id,
            )
        )

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
        ids = sorted(
            i for i in roles_by_id if i in known and known[i].structural_fingerprint == structure
        )
        # `len(ids) > 1` is the whole difference between "one scenario reached
        # both roles" and "one template's own rows did". Without it every
        # ordinary template_in_two_roles cascaded into this higher-severity
        # code, and an auditor counting leaks counted mistakes that were none.
        if len(by_structure[structure]) > 1 and len(ids) > 1:
            violations.append(
                Violation(
                    "scenario_in_two_roles",
                    f"{', '.join(repr(i) for i in ids)} are one scenario and their cases are "
                    f"split across {', '.join(sorted(by_structure[structure]))}; the model is "
                    "examined on what it was trained on and the score rises",
                )
            )

    return violations
