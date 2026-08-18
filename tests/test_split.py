# SPDX-License-Identifier: MIT
"""Tests for the grouped split, per RFC-0003.

Roles are separated by scenario template, never by row. The failure this
prevents is the worst-behaved one in the project: a template appearing in both
roles *raises* measured accuracy, so it does not merely hide — it rewards. No
inspection of model output can find it. Only the partition can be checked, and
the partition is only as strong as the identity underneath it.

Every fixture is in the shape `cases.build()` consumes, for the reason given in
`tests/support.py`.
"""

from typing import Any

import pytest

from consylr.identity import check as identity_check
from consylr.identity import scenario
from consylr.split import HOLDOUT, TRAIN, _draw, check, partition
from consylr.templates import Template
from tests.support import a_template, template_body


def many(n: int) -> list[Template]:
    """`n` templates that are genuinely different scenarios."""
    return [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(n)]


def case(template: Template, role: str, **over: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "template_id": template.id,
        "template_fingerprint": template.fingerprint,
        "role": role,
        "family": template.family,
    }
    meta.update(over)
    return meta


def corpus(templates: list[Template], roles: dict[str, str], each: int = 2) -> list[dict[str, Any]]:
    return [case(t, roles[t.id]) for t in templates for _ in range(each)]


# --- partitioning -------------------------------------------------------------


def test_the_same_seed_gives_the_same_partition() -> None:
    templates = many(50)
    assert partition(templates, holdout_share=0.2, seed=7) == partition(
        templates, holdout_share=0.2, seed=7
    )


def test_a_different_seed_gives_a_different_partition() -> None:
    templates = many(50)
    assert partition(templates, holdout_share=0.2, seed=7) != partition(
        templates, holdout_share=0.2, seed=8
    )


def test_the_partition_does_not_depend_on_the_order_templates_are_read() -> None:
    # Otherwise renaming a data file re-partitions the corpus, and the numbers
    # published against the old partition no longer describe the new one.
    templates = many(50)
    assert partition(templates, holdout_share=0.2, seed=7) == partition(
        list(reversed(templates)), holdout_share=0.2, seed=7
    )


def test_every_template_lands_in_exactly_one_role() -> None:
    roles = partition(many(50), holdout_share=0.2, seed=7)
    assert len(roles) == 50
    assert set(roles.values()) <= {TRAIN, HOLDOUT}


def test_the_holdout_share_is_honoured_within_a_template_of_itself() -> None:
    roles = partition(many(200), holdout_share=0.25, seed=7)
    held = sum(1 for r in roles.values() if r == HOLDOUT)
    assert 40 <= held <= 60


def test_an_aliased_template_cannot_be_split_across_roles() -> None:
    # Assignment is by structural identity, so two ids for one scenario are the
    # same draw. The leak is impossible by construction here, not merely caught.
    #
    # Checked over many seeds deliberately: at any single seed two independent
    # draws agree about seven times in ten, so one passing seed is no evidence
    # at all that the two ids were treated as one scenario.
    templates = [*many(40), a_template(id="alias-of-000", amount="100.00")]
    for seed in range(30):
        roles = partition(templates, holdout_share=0.3, seed=seed)
        assert roles["alias-of-000"] == roles["t-000"], f"seed {seed}"


def test_a_scenario_committed_twice_cannot_be_split_across_roles() -> None:
    """Aliasing, which is the case identity has to close by construction.

    A rewording is deliberately *not* this case: RFC-0003 keeps paraphrase off
    and never paraphrases the sealed set, so two templates a rewording apart
    emit different packets and are different scenarios. Making them collide cost
    false merges of packets that differed materially.

    Checked over many seeds: at any single seed two independent draws agree about
    seven times in ten, so one passing seed is no evidence at all.
    """
    original, alias = a_template(id="t-001"), a_template(id="t-002")
    for seed in range(40):
        roles = partition([original, alias], holdout_share=0.5, seed=seed)
        assert roles["t-001"] == roles["t-002"], f"leaked at seed {seed}"


def test_a_share_equal_to_a_template_s_own_draw_leaves_it_in_train() -> None:
    # The cut is `draw < share`, and the boundary is reachable after all: the
    # share is a parameter, so it can be set to a draw that was computed. An
    # earlier comment here called this an equivalent mutation on the grounds that
    # no digest could be made to land on a given share — which had it backwards.
    t = a_template(id="t-001")
    share = _draw(7, scenario(t))
    assert partition([t], holdout_share=share, seed=7) == {"t-001": TRAIN}


def test_a_holdout_share_of_zero_holds_nothing_back() -> None:
    assert set(partition(many(200), holdout_share=0.0, seed=5).values()) == {TRAIN}


def test_a_holdout_share_of_one_holds_everything_back() -> None:
    assert set(partition(many(200), holdout_share=1.0, seed=5).values()) == {HOLDOUT}


def test_every_draw_is_a_multiple_of_two_to_the_minus_fifty_three() -> None:
    """Which is what keeps every draw inside [0, 1).

    A 64-bit quotient is rounded to the nearest float64, and the largest of them
    rounds to exactly 1.0 — so `holdout_share=1.0` would not be total and a draw
    would sit outside the interval `_draw` documents. Sampling cannot find that:
    it is a 2**-53 event. The property that rules it out is checkable directly —
    a 53-bit numerator over 2**53 is exactly representable and strictly below 1.
    """
    draws = [_draw(s, scenario(t)) for s in range(20) for t in many(20)]
    assert all(0.0 <= d < 1.0 for d in draws)
    assert all((d * (1 << 53)).is_integer() for d in draws)


@pytest.mark.parametrize("share", [-1.0, 2.0, 25.0, float("nan"), float("inf")])
def test_a_share_that_is_not_a_share_is_refused(share: float) -> None:
    # A percent-for-fraction slip silently produced a corpus with no training
    # cases at all, and NaN silently produced one with no holdout. RFC-0003 has
    # the generator fail loudly on a constraint it cannot meet; satisfying a
    # nonsensical one quietly is worse than either.
    with pytest.raises(ValueError, match="holdout_share"):
        partition(many(5), holdout_share=share, seed=1)


def test_two_templates_sharing_an_id_are_refused_rather_than_collapsed() -> None:
    # A dict comprehension keyed on the id silently keeps the last one, so two
    # templates go in and one role comes out — and which one wins depends on the
    # order the directory was read in.
    with pytest.raises(ValueError, match="t-001"):
        partition(
            [a_template(id="t-001"), a_template(id="t-001", amount="9.00")],
            holdout_share=0.3,
            seed=1,
        )


# --- checking a corpus, including one this machine did not build --------------


def test_a_clean_corpus_passes() -> None:
    templates = many(10)
    assert (
        check(corpus(templates, partition(templates, holdout_share=0.3, seed=3)), templates) == []
    )


def test_a_template_in_two_roles_is_reported() -> None:
    templates = many(10)
    roles = partition(templates, holdout_share=0.3, seed=3)
    cases = corpus(templates, roles, each=1)
    cases.append(case(templates[0], HOLDOUT if roles[templates[0].id] == TRAIN else TRAIN))
    v = next(x for x in check(cases, templates) if x.code == "template_in_two_roles")
    assert templates[0].id in v.detail


def test_one_template_straddling_the_boundary_is_one_finding_not_two() -> None:
    # `scenario_in_two_roles` means the model was examined on what it trained on.
    # Raising it for every row-level mistake as well makes an auditor counting
    # that code count leaks that did not happen — and the schema's own rule is
    # that one defect produces one violation, because cascades inflate a number
    # a quota audit then reads.
    templates = many(10)
    roles = partition(templates, holdout_share=0.3, seed=3)
    cases = corpus(templates, roles, each=1)
    cases.append(case(templates[0], HOLDOUT if roles[templates[0].id] == TRAIN else TRAIN))
    codes = [x.code for x in check(cases, templates)]
    assert codes.count("template_in_two_roles") == 1
    assert "scenario_in_two_roles" not in codes


def test_one_scenario_under_two_ids_in_two_roles_is_reported() -> None:
    # The partition check passes: two distinct ids, each in one role. The model
    # is still examined on a scenario it trained on.
    original, alias = a_template(id="t-001"), a_template(id="t-002")
    cases = [case(original, TRAIN), case(alias, HOLDOUT)]
    v = next(x for x in check(cases, [original, alias]) if x.code == "scenario_in_two_roles")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_a_scenario_under_two_ids_in_two_roles_is_reported_on_audit() -> None:
    original, alias = a_template(id="t-001"), a_template(id="t-002")
    cases = [case(original, TRAIN), case(alias, HOLDOUT)]
    assert "scenario_in_two_roles" in [x.code for x in check(cases, [original, alias])]


def test_a_template_whose_content_changed_since_the_build_is_reported() -> None:
    # The id in meta.json still resolves, but it no longer names what produced
    # the case. An audit trusting the id restates the file.
    cases = [case(a_template(id="t-001"), TRAIN)]
    edited = a_template(id="t-001", amount="4242.00")
    v = next(x for x in check(cases, [edited]) if x.code == "template_drifted")
    assert "t-001" in v.detail


def test_a_case_naming_a_template_that_does_not_exist_is_reported() -> None:
    templates = many(3)
    ghost: dict[str, Any] = {"template_id": "ghost", "role": TRAIN}
    v = next(
        x
        for x in check([case(templates[0], TRAIN), ghost], templates)
        if x.code == "unresolved_template"
    )
    assert "ghost" in v.detail


def test_a_case_with_no_recorded_fingerprint_is_reported_not_trusted() -> None:
    # RFC-0003's deep audit refuses to believe a foreign corpus's metadata. A
    # case that records no fingerprint offers nothing to disbelieve, which is
    # not the same as being correct.
    templates = many(1)
    cases: list[dict[str, Any]] = [{"template_id": templates[0].id, "role": TRAIN}]
    assert "no_recorded_fingerprint" in [x.code for x in check(cases, templates)]


def test_an_empty_corpus_is_a_failure_not_a_vacuous_pass() -> None:
    assert check([], many(3)) != []


# --- a role has to be a role, and a corpus has to have both -------------------


@pytest.mark.parametrize("role", ["", "banana", "eval", "TRAIN", " train ", 42, None])
def test_a_role_that_is_not_a_role_is_reported(role: object) -> None:
    # Every one of these once certified clean. Both leak checks key off a
    # template holding more than one role, so a corpus with a single uniform
    # value made them structurally unreachable — a gate that cannot fail.
    templates = many(4)
    cases = [case(t, TRAIN) for t in templates]
    cases[0]["role"] = role
    assert "unknown_role" in [x.code for x in check(cases, templates)]


def test_a_corpus_with_no_role_key_at_all_is_reported() -> None:
    templates = many(4)
    cases = [{"template_id": t.id, "template_fingerprint": t.fingerprint} for t in templates]
    assert "unknown_role" in [x.code for x in check(cases, templates)]


@pytest.mark.parametrize("role", [TRAIN, HOLDOUT])
def test_a_corpus_holding_only_one_role_is_reported(role: str) -> None:
    templates = many(6)
    assert "role_missing" in [x.code for x in check([case(t, role) for t in templates], templates)]


def test_a_corpus_whose_roles_are_inverted_is_reported_when_the_partition_is_given() -> None:
    # The strongest form of the check: not merely that the roles are consistent,
    # but that they are the ones the seed and share actually produce.
    templates = many(20)
    roles = partition(templates, holdout_share=0.3, seed=7)
    flipped = {t: (HOLDOUT if r == TRAIN else TRAIN) for t, r in roles.items()}
    cases = corpus(templates, flipped, each=1)
    assert "role_not_as_partitioned" in [x.code for x in check(cases, templates, expected=roles)]


def test_a_corpus_matching_the_partition_it_claims_passes() -> None:
    templates = many(20)
    roles = partition(templates, holdout_share=0.3, seed=7)
    assert check(corpus(templates, roles, each=1), templates, expected=roles) == []


def test_a_loaded_template_that_produced_no_cases_is_reported() -> None:
    # Five hundred templates and cases for one of them was a clean audit.
    templates = many(8)
    roles = partition(templates, holdout_share=0.3, seed=3)
    assert "template_unused" in [
        x.code for x in check(corpus(templates[:2], roles, each=1), templates)
    ]


def test_a_template_that_cannot_be_built_is_reported_not_raised_through() -> None:
    """`partition` and `check` called `scenario()` unguarded.

    So one template that `templates.check` certifies clean — a cause-bearing
    family with no `cause` key, which is the shape every such template had
    before that check existed — aborted the whole audit with an uncaught
    ValueError, where its sibling `identity.check` reports it as one violation
    among many. An audit that must count every problem died at the first one.
    """
    legacy = Template.from_mapping(
        {
            **template_body(id="t-legacy", family="fee_at_source"),
            "cause": "P-2",
            "policy": [{"id": "P-2", "text": "Invoices settle at face value."}],
        }
    )
    good = a_template(id="t-good")

    roles = partition([good, legacy], holdout_share=0.3, seed=1)
    assert legacy.id not in roles, "an unbuildable template has no scenario to place"
    assert good.id in roles

    # `identity.check` owns whether a template emits a case at all; what matters
    # here is that neither of these raises through an audit meant to count.
    codes = [v.code for v in check([case(good, roles[good.id])], [good, legacy])]
    assert codes, "the audit ran and reported"
    assert "unbuildable_template" in [v.code for v in identity_check([legacy])]
