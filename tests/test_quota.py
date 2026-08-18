# SPDX-License-Identifier: MIT
"""Tests for the quota checker defined by RFC-0002 and RFC-0003.

Two constraints, not one. Certainty is a property of a case rather than of a
family — a fee case with a supporting policy line *is* a clearly-supported case
— so conflating the certainty allocation with family coverage double-counts.
"""

from consylr.quota import ABSTENTION_FAMILY, Plan, check, satisfiable


def cases(**counts: int) -> list[dict[str, str]]:
    """Cases as (family, certainty) pairs, spelled `family__certainty=n`."""
    out: list[dict[str, str]] = []
    for key, n in counts.items():
        family, certainty = key.split("__")
        out.extend({"family": family, "certainty": certainty} for _ in range(n))
    return out


PLAN = Plan(
    families=frozenset({"clean_match", "fee_at_source", "cause_not_established"}), family_floor=2
)


def test_a_corpus_meeting_both_constraints_passes() -> None:
    corpus = cases(
        clean_match__supported=40,
        fee_at_source__supported=8,
        cause_not_established__unsupported=12,
        fee_at_source__ambiguous=40,
    )
    assert check(corpus, PLAN) == []


def test_too_few_clearly_supported_cases_is_reported() -> None:
    # The planted failure for the certainty allocation.
    corpus = cases(
        clean_match__supported=10,
        fee_at_source__ambiguous=78,
        cause_not_established__unsupported=12,
    )
    codes = [v.code for v in check(corpus, PLAN)]
    assert "supported_share_low" in codes


def test_too_many_clearly_supported_cases_is_also_reported() -> None:
    corpus = cases(
        clean_match__supported=88, fee_at_source__ambiguous=2, cause_not_established__unsupported=10
    )
    assert "supported_share_high" in [v.code for v in check(corpus, PLAN)]


def test_an_abstention_family_below_its_share_is_reported() -> None:
    corpus = cases(
        clean_match__supported=45, fee_at_source__ambiguous=52, cause_not_established__unsupported=3
    )
    assert "abstention_share_low" in [v.code for v in check(corpus, PLAN)]


def test_an_abstention_family_above_its_share_is_reported() -> None:
    # Cheap abstention is how a model learns to refuse everything and score well.
    corpus = cases(
        clean_match__supported=45,
        fee_at_source__ambiguous=25,
        cause_not_established__unsupported=30,
    )
    assert "abstention_share_high" in [v.code for v in check(corpus, PLAN)]


def test_a_family_below_its_floor_is_reported_by_name() -> None:
    # The planted failure for family coverage.
    corpus = cases(
        clean_match__supported=45,
        fee_at_source__ambiguous=44,
        cause_not_established__unsupported=11,
    )
    plan = Plan(families=PLAN.families | {"reversal"}, family_floor=2)
    v = [x for x in check(corpus, plan) if x.code == "family_below_floor"]
    assert v and "reversal" in v[0].detail


def test_a_family_the_plan_does_not_name_is_reported() -> None:
    corpus = cases(
        clean_match__supported=45,
        fee_at_source__ambiguous=43,
        cause_not_established__unsupported=12,
        vibes__supported=1,
    )
    assert "unknown_family" in [v.code for v in check(corpus, PLAN)]


def test_the_report_names_the_shortfall_and_its_size() -> None:
    corpus = cases(
        clean_match__supported=10,
        fee_at_source__ambiguous=78,
        cause_not_established__unsupported=12,
    )
    v = next(x for x in check(corpus, PLAN) if x.code == "supported_share_low")
    assert "10.0%" in v.detail and "40" in v.detail


# --- satisfiability is checked before a corpus is written, not after ----------


def test_a_plan_that_cannot_be_met_at_a_size_is_refused_up_front() -> None:
    # Twelve families at a floor of ten cannot fit in a hundred cases while also
    # leaving 40-50% clearly supported. Building it and failing the audit wastes
    # the build; refusing names the constraint that cannot be met.
    plan = Plan(families=frozenset(f"f{i}" for i in range(12)), family_floor=10)
    problems = satisfiable(size=100, plan=plan)
    assert problems and "family_floor" in problems[0].code


def test_a_plan_that_fits_is_accepted() -> None:
    assert satisfiable(size=1000, plan=PLAN) == []


def test_an_empty_corpus_is_a_failure_not_a_vacuous_pass() -> None:
    assert check([], PLAN) != []


def test_the_two_abstention_constraints_can_contradict_at_a_small_size() -> None:
    # Its floor is a count and its ceiling is a share, so a small corpus can make
    # them mutually unsatisfiable. Naming that is more useful than failing later.
    plan = Plan(families=frozenset({"clean_match", ABSTENTION_FAMILY}), family_floor=20)
    codes = [v.code for v in satisfiable(size=100, plan=plan)]
    assert "abstention_ceiling_unreachable" in codes
