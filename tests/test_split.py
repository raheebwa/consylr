# SPDX-License-Identifier: MIT
"""Tests for the grouped split, per RFC-0003.

Roles are separated by scenario template, never by row. The failure this
prevents is the worst-behaved one in the project: a template appearing in both
roles *raises* measured accuracy, so it does not merely hide — it rewards. No
inspection of model output can find it. Only the partition can be checked.
"""

from consylr.split import check, partition
from consylr.templates import Template

FAMILIES = frozenset({"clean_match", "fee_at_source"})


def a_template(id: str = "t-001", family: str = "clean_match", **over: object) -> Template:
    body: dict[str, object] = {
        "id": id,
        "family": family,
        "left": {"description": "consultancy retainer", "amount": "1000.00"},
        "right": {"description": "retainer settlement", "amount": "1000.00"},
        "policy": ["P-1: retainers settle at face value"],
    }
    body.update(over)
    return Template.from_mapping(body)


def many(n: int) -> list[Template]:
    return [a_template(id=f"t-{i:03d}", policy=[f"P-{i}: clause {i}"]) for i in range(n)]


def case(template: Template, role: str, **over: object) -> dict[str, object]:
    meta: dict[str, object] = {
        "template_id": template.id,
        "template_fingerprint": template.fingerprint,
        "role": role,
        "family": template.family,
    }
    meta.update(over)
    return meta


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
    assert set(roles.values()) <= {"train", "holdout"}


def test_the_holdout_share_is_honoured_within_a_template_of_itself() -> None:
    roles = partition(many(200), holdout_share=0.25, seed=7)
    held = sum(1 for r in roles.values() if r == "holdout")
    assert 40 <= held <= 60


def test_an_aliased_template_cannot_be_split_across_roles() -> None:
    # Assignment is by structural identity, so two ids for one scenario are the
    # same draw. The leak is impossible by construction here, not merely caught.
    #
    # Checked over many seeds deliberately: at any single seed two independent
    # draws agree about seven times in ten, so one passing seed is no evidence
    # at all that the two ids were treated as one scenario.
    templates = [*many(40), a_template(id="alias-of-000", policy=["P-0: clause 0"])]
    for seed in range(30):
        roles = partition(templates, holdout_share=0.3, seed=seed)
        assert roles["alias-of-000"] == roles["t-000"], f"seed {seed}"


def test_a_reworded_template_cannot_be_split_across_roles() -> None:
    twin = a_template(
        id="reworded-000",
        policy=["P-0: clause 0"],
        left={"description": "entirely different prose", "amount": "1000.00"},
    )
    for seed in range(30):
        roles = partition([*many(40), twin], holdout_share=0.3, seed=seed)
        assert roles["reworded-000"] == roles["t-000"], f"seed {seed}"


# The comparison in `partition` is `draw < holdout_share`. Loosening it to `<=`
# is an equivalent mutation, not an untested one: the draw is a 64-bit quotient
# of a SHA-256 digest, so a draw landing exactly on the share is a 2**-64 event
# that no input can be constructed to hit. The two reachable edges are the ones
# below, and they are held.
def test_a_holdout_share_of_zero_holds_nothing_back() -> None:
    # The share is a strict lower cut: at zero, no draw may fall inside it.
    roles = partition(many(200), holdout_share=0.0, seed=5)
    assert set(roles.values()) == {"train"}


def test_a_holdout_share_of_one_holds_everything_back() -> None:
    roles = partition(many(200), holdout_share=1.0, seed=5)
    assert set(roles.values()) == {"holdout"}


# --- checking a corpus, including one this machine did not build --------------


def test_a_clean_corpus_passes() -> None:
    templates = many(10)
    roles = partition(templates, holdout_share=0.3, seed=3)
    cases = [case(t, roles[t.id]) for t in templates for _ in range(3)]
    assert check(cases, templates) == []


def test_a_template_in_two_roles_is_reported() -> None:
    templates = many(10)
    roles = partition(templates, holdout_share=0.3, seed=3)
    cases = [case(t, roles[t.id]) for t in templates]
    cases.append(case(templates[0], "holdout" if roles[templates[0].id] == "train" else "train"))
    v = next(x for x in check(cases, templates) if x.code == "template_in_two_roles")
    assert templates[0].id in v.detail


def test_one_scenario_under_two_ids_in_two_roles_is_reported() -> None:
    # The partition check passes: two distinct ids, each in one role. The model
    # is still examined on a scenario it trained on.
    original = a_template(id="t-001")
    alias = a_template(id="t-002")
    cases = [case(original, "train"), case(alias, "holdout")]
    v = next(x for x in check(cases, [original, alias]) if x.code == "scenario_in_two_roles")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_a_reworded_scenario_in_two_roles_is_reported() -> None:
    original = a_template(id="t-001")
    reworded = a_template(id="t-002", left={"description": "other prose", "amount": "1000.00"})
    cases = [case(original, "train"), case(reworded, "holdout")]
    assert "scenario_in_two_roles" in [x.code for x in check(cases, [original, reworded])]


def test_a_template_whose_content_changed_since_the_build_is_reported() -> None:
    # The third attack: the id in meta.json still resolves, but it no longer
    # names what produced the case. An audit trusting the id restates the file.
    built_from = a_template(id="t-001")
    cases = [case(built_from, "train")]
    edited = a_template(id="t-001", policy=["P-1: retainers settle net of fees"])
    v = next(x for x in check(cases, [edited]) if x.code == "template_drifted")
    assert "t-001" in v.detail


def test_a_case_naming_a_template_that_does_not_exist_is_reported() -> None:
    templates = many(3)
    ghost: dict[str, object] = {"template_id": "ghost", "role": "train"}
    cases = [case(templates[0], "train"), ghost]
    v = next(x for x in check(cases, templates) if x.code == "unresolved_template")
    assert "ghost" in v.detail


def test_a_case_with_no_recorded_fingerprint_is_reported_not_trusted() -> None:
    # RFC-0003's deep audit refuses to believe a foreign corpus's metadata. A
    # case that records no fingerprint offers nothing to disbelieve, which is
    # not the same as being correct.
    templates = many(1)
    cases = [{"template_id": templates[0].id, "role": "train"}]
    assert "no_recorded_fingerprint" in [x.code for x in check(cases, templates)]


def test_an_empty_corpus_is_a_failure_not_a_vacuous_pass() -> None:
    assert check([], many(3)) != []
