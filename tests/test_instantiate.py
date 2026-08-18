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

from consylr.identity import scenario
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


def test_no_pool_can_reach_a_packet() -> None:
    """The property the builder's internal resolution exists to guarantee.

    This began as a refusal — the builder raising on a pattern handed to it
    unresolved — and the refusal was the wrong shape. `shape_violations` reads a
    record's keys and never the types of its values, so a pool on 'party' built
    with **zero violations** and rendered `['Northwind Ltd', 'Southgate Ltd']`
    into the prompt as a counterparty name. Refusing that at the door would have
    left every caller responsible for remembering; resolving inside the builder
    means no caller can forget, and the guarantee is structural.
    """
    parties = ["Northwind Ltd", "Southgate Ltd"]
    case = built(a_pattern(party=parties))

    reached = {r["party"] for r in case.packet["records"]}
    assert case.violations == []
    assert reached <= set(parties), "a value the pattern never declared reached the packet"
    assert all(isinstance(p, str) for p in reached), "a pool reached the packet"


def test_a_pool_with_nothing_to_draw_from_is_refused() -> None:
    """A malformed pool is an authoring defect, and it raises rather than reports.

    An empty pool has no value to select, and a silent fallback would put a
    value in the packet that the template never declared — which is the inferred
    ground truth this whole design exists to avoid.
    """
    with pytest.raises(ValueError, match="empty pool"):
        built(a_pattern(party=[]))


def test_a_well_formed_pool_is_not_a_shape_violation() -> None:
    """A pattern is a legitimate artefact, so the audit must not reject one.

    The first version of this guard rejected every container and would have
    failed `templates-train/` wholesale.
    """
    assert shape_violations(a_pattern()) == []


def test_a_pattern_takes_part_in_the_split_like_any_other_template() -> None:
    """A pattern with no scenario cannot be partitioned, so it cannot be used.

    `identity.scenario()` probes a template by building it under a constant seed
    and a constant id. A pattern reaching that probe unresolved has no scenario
    at all — which does not degrade the split, it removes the template from it
    entirely. Instantiating inside the builder is what makes the probe see a
    canonical draw instead of a pool.
    """
    assert len(scenario(a_pattern())) == 64


def test_the_probe_reads_the_pattern_not_the_corpus_draw() -> None:
    """Identity normalises the variation, which is what lets a pattern vary.

    Two templates declaring the same pools are the same scenario however many
    different cases each goes on to produce; two declaring different pools are
    not. Without this the split key dissolves — every instantiated case would be
    its own scenario.
    """
    same = scenario(a_pattern()) == scenario(a_pattern(id="t-999"))
    different = scenario(a_pattern()) != scenario(a_pattern(policy_text="A different rule."))

    assert same, "one pattern under two ids is one scenario"
    assert different, "two different patterns are two scenarios"


def test_a_case_records_the_pattern_it_came_from_and_what_it_became() -> None:
    """Both identities, because they answer different questions.

    The pattern's digest is the authored artefact drift detection watches; the
    instantiated body is what this case actually was. Recording only the second
    makes "which pattern produced this case" an archaeology.
    """
    pattern = a_pattern()
    case = built(pattern, case_index=4)

    assert case.meta["template_fingerprint"] == pattern.fingerprint
    assert case.meta["case_fingerprint"] != pattern.fingerprint
