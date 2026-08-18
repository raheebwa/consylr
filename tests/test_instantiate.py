# SPDX-License-Identifier: MIT
"""Tests for per-case instantiation, per RFC-0003 and issue #20.

A template yields as many distinct cases as its deformation can distinguish —
three for most families, one for the three whose deformation ignores the case
index. That is why `train-v1` holds 903 cases against RFC-0003's 8,000-15,000,
and why padding to the number was refused: padding means duplicates, and the
corpus writer refuses those.

Instantiation closes the gap by making the *values* vary per case rather than
the deformation alone. A pattern template declares a pool where a fixed template
declares a value, and the case's seed selects within it.

**The pool is declared in the template body, and the seed only selects within
it.** `identity.scenario()` probes every template under one constant id
(`PROBE_ID`), so values derived from the seed alone would be identical across
every pattern template and collapse them all into one scenario. Reading the pool
from the body is what keeps two scenarios distinct: the body is what the probe
hashes, so templates differ exactly when their patterns differ.
"""

from __future__ import annotations

from typing import Any

import pytest

from consylr.instantiate import instantiate
from consylr.templates import Template, shape_violations
from tests.support import built, template_body

#: Amounts spread widely enough that a draw is visible. Two templates sharing a
#: pool are the same scenario, which is why the pool is content rather than
#: configuration.
AMOUNTS = ["480.00", "1250.00", "17400.00", "925.50", "6300.00", "88.75"]


def a_pattern(**over: Any) -> Template:
    """A template whose left/right amounts are a pool rather than one value."""
    body = template_body(**over)
    for side in ("left", "right"):
        for record in body[side]:
            record["amount"] = list(AMOUNTS)
    return Template.from_mapping(body)


def test_a_pool_resolves_to_one_of_its_own_candidates() -> None:
    """The draw selects within the declared pool and invents nothing.

    A value from outside the pool would be a value the template never declared,
    which puts the ground truth back to being inferred rather than constructed.
    """
    resolved = instantiate(a_pattern(), root_seed=7, case_index=0)

    drawn = {r["amount"] for side in ("left", "right") for r in resolved.body[side]}
    assert drawn, "the instantiated template carried no records"
    assert drawn <= set(AMOUNTS)
    assert all(isinstance(a, str) for a in drawn), "a pool must resolve to a literal"


@pytest.mark.parametrize("side", ["left", "right"])
def test_two_case_indices_draw_different_values(side: str) -> None:
    """The whole point of #20: one template, many genuinely distinct cases.

    Without this, a template yields what its deformation can distinguish and the
    corpus stops at 903.
    """
    pattern = a_pattern()
    first = instantiate(pattern, root_seed=7, case_index=0)
    second = instantiate(pattern, root_seed=7, case_index=1)

    assert [r["amount"] for r in first.body[side]] != [r["amount"] for r in second.body[side]]


def test_the_same_case_instantiates_identically_every_time() -> None:
    """Reproducibility is the provenance story; a corpus is regenerated, not kept."""
    a = instantiate(a_pattern(), root_seed=7, case_index=3)
    b = instantiate(a_pattern(), root_seed=7, case_index=3)

    assert a.body == b.body


def test_a_literal_field_is_left_exactly_as_it_was() -> None:
    """A template may fix what it does not want varied, and fixing must mean fixed."""
    resolved = instantiate(a_pattern(), root_seed=7, case_index=0)
    original = a_pattern().body["left"]

    assert all(r["ref"] == o["ref"] for r, o in zip(resolved.body["left"], original, strict=True))


def test_an_instantiated_pattern_is_something_the_generator_can_actually_build() -> None:
    """The rule this repository already holds its fixtures to.

    Instantiation that produced a template the product refuses would be a
    mechanism for reaching a corpus size, not for reaching one that validates.
    """
    resolved = instantiate(a_pattern(), root_seed=7, case_index=0)

    assert built(resolved).violations == []


def test_both_sides_of_a_clean_pair_draw_the_same_value() -> None:
    """The correspondence has to survive the draw.

    Drawing per side would give the left invoice and the right settlement two
    different amounts, and every clean pair in the corpus would stop
    corresponding — with the answer key still saying it does.
    """
    resolved = instantiate(a_pattern(), root_seed=7, case_index=2)

    left = [r["amount"] for r in resolved.body["left"]]
    right = [r["amount"] for r in resolved.body["right"]]
    assert left == right


def test_the_builder_refuses_a_pattern_it_was_handed_uninstantiated() -> None:
    """A pool must never reach the packet, and the guard needs a caller.

    An amount was already caught, but only by `money.canonical` refusing a list
    it could not read — and only for `amount`. The fields no canonicaliser
    touches were not caught at all: a pool on `party` built **clean**, and the
    literal text `['Northwind Ltd', 'Southgate Ltd']` was rendered into the
    prompt as a counterparty name, in a case the corpus writer would have
    accepted. This is that hole, closed where the audit and the builder share one
    definition of what a template is.
    """
    with pytest.raises(ValueError, match="not instantiated"):
        built(a_pattern(party=["Northwind Ltd", "Southgate Ltd"]))


def test_the_audit_reports_the_pool_the_builder_raises_on() -> None:
    """One definition, read by both. An audit blind to what the builder refuses
    would pass a template set that cannot produce a single case."""
    faults = shape_violations(a_pattern(party=["Northwind Ltd", "Southgate Ltd"]))

    assert [v.code for v in faults] == ["bad_type"] * len(faults)
    assert faults, "the closed-world check did not see an un-instantiated pool"
