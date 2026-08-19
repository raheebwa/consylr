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
        clean_match__supported=62,
        fee_at_source__supported=8,
        cause_not_established__unsupported=12,
        fee_at_source__ambiguous=18,
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
    assert "10.0%" in v.detail and "65" in v.detail


# --- satisfiability is checked before a corpus is written, not after ----------


def test_a_plan_that_cannot_be_met_at_a_size_is_refused_up_front() -> None:
    # Twelve families at a floor of ten cannot fit in a hundred cases while also
    # leaving 65-75% clearly supported. Building it and failing the audit wastes
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


# --- the two axes are separate, and a row cannot satisfy both -----------------


def test_an_abstention_case_labelled_supported_is_a_contradiction() -> None:
    # RFC-0002: cause_not_established is the family where the packet does *not*
    # explain the difference, so its correct answer is ambiguous/unsupported. A
    # row in that family labelled `supported` is not a corpus choice, it is a
    # mislabel, and counting it in both bands is the exact double-count this
    # module's docstring says it exists to prevent.
    corpus = cases(
        clean_match__supported=25,
        cause_not_established__supported=15,
        fee_at_source__ambiguous=60,
    )
    codes = [v.code for v in check(corpus, PLAN)]
    assert "contradictory_certainty" in codes


def test_double_counting_cannot_rescue_a_corpus_short_of_the_supported_floor() -> None:
    # The same 15 rows filling both the supported floor and the abstention
    # ceiling at once. Relabelled to their RFC-correct certainty the identical
    # corpus is 15 points short, so a pass here green-lights a bad corpus.
    corpus = cases(
        clean_match__supported=25,
        cause_not_established__supported=15,
        fee_at_source__ambiguous=60,
    )
    codes = [v.code for v in check(corpus, PLAN)]
    assert "supported_share_low" in codes


def test_abstention_is_counted_by_family_not_by_certainty() -> None:
    # `decoy`'s correct answer is an `unsupported` match (RFC-0002), so a corpus
    # can hold plenty of `unsupported` rows that are not abstention at all.
    # Folding the two axes into one would read this corpus as 52% abstention.
    plan = Plan(families=PLAN.families | {"decoy"}, family_floor=2)
    corpus = cases(
        clean_match__supported=70,
        decoy__unsupported=15,
        cause_not_established__unsupported=12,
        fee_at_source__ambiguous=3,
    )
    assert check(corpus, plan) == []


# --- the boundaries themselves, because a band is only its two edges ---------
#
# Every threshold below was mutable without a test noticing. A share check that
# is off by one row is the difference between a corpus at its floor and one just
# under it, and that is precisely the corpus the plan exists to reject.


def test_the_supported_floor_is_inclusive() -> None:
    corpus = cases(
        clean_match__supported=65,
        fee_at_source__ambiguous=23,
        cause_not_established__unsupported=12,
    )
    assert check(corpus, PLAN) == []


def test_one_case_below_the_supported_floor_fails() -> None:
    corpus = cases(
        clean_match__supported=64,
        fee_at_source__ambiguous=24,
        cause_not_established__unsupported=12,
    )
    assert "supported_share_low" in [v.code for v in check(corpus, PLAN)]


def test_the_supported_ceiling_is_inclusive() -> None:
    corpus = cases(
        clean_match__supported=75,
        fee_at_source__ambiguous=13,
        cause_not_established__unsupported=12,
    )
    assert check(corpus, PLAN) == []


def test_one_case_above_the_supported_ceiling_fails_and_names_the_ceiling() -> None:
    corpus = cases(
        clean_match__supported=76,
        fee_at_source__ambiguous=12,
        cause_not_established__unsupported=12,
    )
    v = next(x for x in check(corpus, PLAN) if x.code == "supported_share_high")
    assert "76.0%" in v.detail and "75%" in v.detail


def test_the_abstention_floor_is_inclusive() -> None:
    corpus = cases(
        clean_match__supported=70,
        fee_at_source__ambiguous=20,
        cause_not_established__unsupported=10,
    )
    assert check(corpus, PLAN) == []


def test_one_case_below_the_abstention_floor_fails_and_names_the_family() -> None:
    corpus = cases(
        clean_match__supported=45, fee_at_source__ambiguous=46, cause_not_established__unsupported=9
    )
    v = next(x for x in check(corpus, PLAN) if x.code == "abstention_share_low")
    assert ABSTENTION_FAMILY in v.detail and "9.0%" in v.detail and "10%" in v.detail


def test_the_abstention_ceiling_is_inclusive() -> None:
    corpus = cases(
        clean_match__supported=70,
        fee_at_source__ambiguous=15,
        cause_not_established__unsupported=15,
    )
    assert check(corpus, PLAN) == []


def test_one_case_above_the_abstention_ceiling_fails_and_names_the_family() -> None:
    corpus = cases(
        clean_match__supported=45,
        fee_at_source__ambiguous=39,
        cause_not_established__unsupported=16,
    )
    v = next(x for x in check(corpus, PLAN) if x.code == "abstention_share_high")
    assert ABSTENTION_FAMILY in v.detail and "16.0%" in v.detail and "15%" in v.detail


def test_a_family_exactly_at_a_binding_floor_passes() -> None:
    # Every other fixture runs the floor at 2 against families six times that, so
    # the coverage constraint was never tested anywhere near where it binds.
    plan = Plan(families=PLAN.families, family_floor=12)
    corpus = cases(
        clean_match__supported=70,
        fee_at_source__ambiguous=18,
        cause_not_established__unsupported=12,
    )
    assert check(corpus, plan) == []


def test_a_family_one_case_below_a_binding_floor_fails() -> None:
    plan = Plan(families=PLAN.families, family_floor=13)
    corpus = cases(
        clean_match__supported=45,
        fee_at_source__ambiguous=43,
        cause_not_established__unsupported=12,
    )
    v = next(x for x in check(corpus, plan) if x.code == "family_below_floor")
    assert ABSTENTION_FAMILY in v.detail and "12" in v.detail and "13" in v.detail


def test_every_unknown_family_is_reported_not_just_the_first() -> None:
    corpus = cases(
        clean_match__supported=44,
        fee_at_source__ambiguous=42,
        cause_not_established__unsupported=12,
        vibes__supported=1,
        chaos__supported=1,
    )
    named = [v.detail for v in check(corpus, PLAN) if v.code == "unknown_family"]
    assert len(named) == 2
    assert any("chaos" in d for d in named) and any("vibes" in d for d in named)


def test_a_floor_total_exactly_equal_to_the_size_is_reachable() -> None:
    plan = Plan(families=frozenset(f"f{i}" for i in range(5)), family_floor=20)
    assert satisfiable(size=100, plan=plan) == []


def test_a_floor_total_one_over_the_size_is_not() -> None:
    plan = Plan(families=frozenset(f"f{i}" for i in range(5)), family_floor=20)
    v = next(x for x in satisfiable(size=99, plan=plan) if x.code == "family_floor_unreachable")
    assert "100" in v.detail and "99" in v.detail


def test_the_unreachable_abstention_ceiling_names_both_numbers() -> None:
    plan = Plan(families=frozenset({"clean_match", ABSTENTION_FAMILY}), family_floor=20)
    v = next(
        x for x in satisfiable(size=100, plan=plan) if x.code == "abstention_ceiling_unreachable"
    )
    assert "20" in v.detail and "20.0%" in v.detail and "15%" in v.detail


def test_the_empty_corpus_and_contradiction_reports_say_what_is_wrong() -> None:
    assert "no cases" in check([], PLAN)[0].detail
    corpus = cases(
        clean_match__supported=25, cause_not_established__supported=15, fee_at_source__ambiguous=60
    )
    v = next(x for x in check(corpus, PLAN) if x.code == "contradictory_certainty")
    assert "15" in v.detail and ABSTENTION_FAMILY in v.detail


def test_the_default_supported_band_is_the_one_rfc_0002_states() -> None:
    """The plan's default IS the specification, so it is pinned to the document.

    A band that lives only as a default drifts by being convenient. This one moved
    once already — from a training-signal-density argument to a deployment-prior
    argument — and the move is only defensible because it was written down with
    its reasoning and its tuning-log line first. Changing the number here without
    changing RFC-0002 is the silent retuning rule 3 names.
    """
    assert Plan(families=frozenset({"clean_match"})).supported_share == (0.65, 0.75)
