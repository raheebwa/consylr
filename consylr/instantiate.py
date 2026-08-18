# SPDX-License-Identifier: MIT
"""Per-case instantiation of a pattern template, per RFC-0003 and issue #20.

A fixed template yields as many distinct cases as its deformation can
distinguish — three for most families, exactly one for the three whose
deformation ignores the case index. That is the whole reason `train-v1` stopped
at 903 cases against RFC-0003's 8,000-15,000, and why it was annotated rather
than padded: padding means duplicates, and the corpus writer refuses them.

A **pattern template** declares a pool where a fixed template declares a value,
and the case's seed selects within it. The scenario is the pattern; the case is
one draw from it.

Two properties hold this up, and neither is a matter of care.

**The pool is declared in the template body.** `identity.scenario()` probes every
template under one constant id, so a value derived from the seed alone would be
identical across every pattern template and collapse them into a single
scenario. Reading the pool from the body is what keeps scenarios distinct: the
body is what the probe hashes, so two templates differ exactly when their
patterns do.

**The draw is keyed by the pool itself, not by the side it sits on.** Two records
declaring the same pool at the same position resolve to the same value, which is
how a clean correspondence survives instantiation — the left invoice and the
right settlement still carry one amount. Where a template wants the two sides to
differ, as a raised date differs from a settled one, it declares two pools and
gets two draws. The alternative, drawing per side, silently breaks every clean
pair; the alternative of drawing once per position breaks every family whose
construction depends on the two sides differing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from consylr.cases import case_seed
from consylr.templates import RECORD_FIELDS, Template

#: The sides whose records carry drawable fields. Policy and document text are
#: prose, and RFC-0003 keeps prose out of identity — a pool of policy wordings
#: would vary what the model reads without varying the scenario.
SIDES = ("left", "right")


def _selection(seed: int, position: int, field: str, pool: Sequence[str]) -> str:
    """One value from a pool, determined by the case, the position and the pool.

    The pool is part of the key rather than only its source. That is what makes
    two records sharing a pool resolve alike, and it is the reason this is a
    digest over the candidates instead of an index into them: keying on the
    pool's *contents* means a template that reorders its candidates without
    changing them keeps every case it already produced.
    """
    material = f"{seed}:{position}:{field}:" + "\x1f".join(pool)
    drawn = int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")
    return pool[drawn % len(pool)]


def is_pattern(template: Template) -> bool:
    """Whether any record field is a pool rather than a value."""
    return any(
        isinstance(record.get(field), list)
        for side in SIDES
        for record in _side(template.body, side)
        for field in RECORD_FIELDS
    )


def _side(body: Mapping[str, Any], side: str) -> list[Mapping[str, Any]]:
    records = body.get(side)
    return list(records) if isinstance(records, list) else []


def instantiate(template: Template, *, root_seed: int, case_index: int) -> Template:
    """The template this case is built from, with every pool resolved.

    A template carrying no pool is returned unchanged rather than rebuilt, so a
    fixed template instantiates to itself and the two kinds can share one path.
    """
    if not is_pattern(template):
        return template

    body = deepcopy(dict(template.body))
    seed = case_seed(root_seed, template.id, case_index)

    for side in SIDES:
        records = body.get(side)
        if not isinstance(records, list):
            continue
        for position, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            for field in sorted(RECORD_FIELDS):
                pool = record.get(field)
                if not isinstance(pool, list):
                    continue
                if not pool:
                    raise ValueError(
                        f"{template.id} declares an empty pool for {field!r}; "
                        "a pool with no candidates cannot be drawn from"
                    )
                if not all(isinstance(candidate, str) for candidate in pool):
                    raise ValueError(
                        f"{template.id} declares a non-string candidate for {field!r}; "
                        "a drawn value reaches the packet and must be text"
                    )
                record[field] = _selection(seed, position, field, pool)

    return Template.from_mapping(body)
