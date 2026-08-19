# SPDX-License-Identifier: MIT
"""Tests for the case builder, per RFC-0003.

Ground truth is known **by construction**: a case is built by applying a named
deformation to a clean pair, so the correct answer is a by-product of building it
rather than a judgement made afterwards. That is what makes the evaluation
honest, and it is the whole of the provenance story.
"""

from random import Random
from typing import Any

import pytest

from consylr.budget import Budget
from consylr.cases import (
    CAUSE_TERMS,
    DEFORMATIONS,
    Case,
    Draft,
    _clean,
    _finish,
    _serialise,
    case_seed,
)
from consylr.cases import build as _build
from consylr.prompt import render as prompt_render
from consylr.templates import Template
from tests.support import CAUSE_LINES, FAKE_BUDGET, PerCharacter, built, template_body


def build(template: Template, **over: Any) -> Case:
    """`build` with the two arguments it refuses to proceed without.

    They have no defaults in the real function, because both were once optional
    and the ordinary path therefore enforced no budget at all. That requirement
    is asserted directly by
    `test_a_case_cannot_be_built_without_saying_how_tokens_are_counted`; every
    other test here is about something else and says so by not repeating it.
    """
    over.setdefault("case_index", 0)
    over.setdefault("role", "train")
    over.setdefault("tokeniser", PerCharacter())
    over.setdefault("render", prompt_render)
    over.setdefault("budget", FAKE_BUDGET)
    return _build(template, **over)


ROOT = 20260818


def a_template(id: str = "t-001", family: str = "clean_match", **over: object) -> Template:
    body: dict[str, object] = {
        "id": id,
        "family": family,
        "left": [
            {
                "ref": "INV-1001",
                "party": "Northwind Ltd",
                "date": "2026-03-02",
                "amount": "1000.00",
            },
            {"ref": "INV-1002", "party": "Southgate Ltd", "date": "2026-03-05", "amount": "250.00"},
            {"ref": "INV-1003", "party": "Eastvale Ltd", "date": "2026-03-06", "amount": "75.00"},
        ],
        "right": [
            {
                "ref": "INV-1001",
                "party": "Northwind Ltd",
                "date": "2026-03-04",
                "amount": "1000.00",
            },
            {"ref": "INV-1002", "party": "Southgate Ltd", "date": "2026-03-07", "amount": "250.00"},
            {"ref": "INV-1003", "party": "Eastvale Ltd", "date": "2026-03-09", "amount": "75.00"},
        ],
        "policy": [{"id": "P-1", "text": "Invoices settle at face value unless a fee is stated."}],
    }
    if family in CAUSE_LINES:
        body["cause"] = "P-2"
    body.update(over)
    return Template.from_mapping(body)


# --- the seed, which everything else rests on ---------------------------------


def test_the_case_seed_is_a_function_of_the_template_and_the_index() -> None:
    assert case_seed(ROOT, "t-001", 3) == case_seed(ROOT, "t-001", 3)


def test_two_cases_from_one_template_do_not_share_a_seed() -> None:
    # Otherwise every case a template produces is the same case.
    seeds = {case_seed(ROOT, "t-001", i) for i in range(20)}
    assert len(seeds) == 20


def test_two_templates_at_one_index_do_not_share_a_seed() -> None:
    seeds = {case_seed(ROOT, f"t-{i:03d}", 0) for i in range(20)}
    assert len(seeds) == 20


def test_a_case_does_not_depend_on_how_many_were_drawn_before_it() -> None:
    # RFC-0003 refuses one shared stream: it makes case n depend on the draws
    # taken before it, so adding a family at the front silently changes every
    # case behind it and a corpus regenerated after an unrelated edit no longer
    # matches the one the published numbers came from.
    first = case_seed(ROOT, "t-002", 0)
    assert case_seed(ROOT, "t-002", 0) == first
    assert case_seed(ROOT, "t-001", 99) != first


def test_a_different_root_seed_gives_a_different_case() -> None:
    assert case_seed(ROOT, "t-001", 0) != case_seed(ROOT + 1, "t-001", 0)


# --- building ------------------------------------------------------------------


def test_the_same_inputs_build_the_same_case() -> None:
    a = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    b = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    assert a.packet == b.packet and a.expected == b.expected


def test_a_built_case_carries_its_lineage() -> None:
    template = a_template()
    case = build(template, root_seed=ROOT, case_index=4, role="holdout")
    assert case.meta["template_id"] == "t-001"
    assert case.meta["template_fingerprint"] == template.fingerprint
    assert case.meta["family"] == "clean_match"
    assert case.meta["role"] == "holdout"
    assert case.meta["seed"] == case_seed(ROOT, "t-001", 4)


def test_the_packet_declares_the_three_id_sets() -> None:
    case = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    assert set(case.packet) == {"records", "policy", "documents"}


def test_every_record_gets_a_side_prefixed_identifier() -> None:
    case = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    ids = [r["id"] for r in case.packet["records"]]
    assert [i for i in ids if i.startswith("A-")] and [i for i in ids if i.startswith("B-")]


def test_a_clean_match_expects_one_supported_match_per_pair() -> None:
    case = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    assert len(case.expected["matches"]) == 3
    assert all(m["c"] == "supported" for m in case.expected["matches"])
    assert "exceptions" not in case.expected or case.expected["exceptions"] == []


def test_a_built_case_validates_against_the_shipping_validator() -> None:
    # The builder is not trusted to be correct by construction alone. A case that
    # cannot pass the validator that ships in the product is not emitted, because
    # a corpus of cases nobody validated is a corpus graded on its own say-so.
    case = build(a_template(), root_seed=ROOT, case_index=0, role="train")
    assert case.violations == []


def test_a_family_with_no_deformation_is_refused_rather_than_approximated() -> None:
    with pytest.raises(ValueError, match="no deformation"):
        build(a_template(family="wormhole"), root_seed=ROOT, case_index=0, role="train")


def test_every_family_the_taxonomy_names_has_a_deformation() -> None:
    from consylr.schema import KINDS

    missing = (KINDS | {"clean_match", "missing_record", "decoy", "ambiguous_pair"}) - set(
        DEFORMATIONS
    )
    assert missing == set(), f"no deformation for: {sorted(missing)}"


def test_a_template_whose_sides_are_not_records_is_refused() -> None:
    with pytest.raises(ValueError, match="left"):
        build(a_template(left={"not": "a list"}), root_seed=ROOT, case_index=0, role="train")


# --- every family, put to the validator that will grade the model -------------


def a_richer_template(family: str, pairs: int = 4, amount: str = "500.00") -> Template:
    body: dict[str, object] = {
        "id": f"t-{family}",
        "family": family,
        "left": [
            {
                "ref": f"INV-{2000 + i}",
                "party": f"Party {i}",
                "date": "2026-03-02",
                "amount": amount,
            }
            for i in range(pairs)
        ],
        "right": [
            {
                "ref": f"INV-{2000 + i}",
                "party": f"Party {i}",
                "date": "2026-03-04",
                "amount": amount,
            }
            for i in range(pairs)
        ],
        "policy": [
            {"id": "P-1", "text": "Invoices settle at face value unless a deduction is stated."},
            {"id": "P-2", "text": CAUSE_LINES.get(family, "Amounts settle in full.")},
        ],
        "documents": [{"id": "D-1", "text": "Remittance advice for March 2026."}],
    }
    if family in CAUSE_LINES:
        body["cause"] = "P-2"
    return Template.from_mapping(body)


@pytest.mark.parametrize("family", sorted(DEFORMATIONS))
def test_every_family_builds_a_case_the_shipping_validator_accepts(family: str) -> None:
    # The claim "ground truth is correct by construction" is a claim about the
    # builder, and a claim needs something able to contradict it. This is that
    # something: the same validator the model's own output will face.
    case = build(a_richer_template(family), root_seed=ROOT, case_index=0, role="train")
    assert case.violations == [], [f"{v.code}: {v.detail}" for v in case.violations]


@pytest.mark.parametrize("family", sorted(DEFORMATIONS))
def test_every_family_is_reproducible(family: str) -> None:
    a = build(a_richer_template(family), root_seed=ROOT, case_index=2, role="train")
    b = build(a_richer_template(family), root_seed=ROOT, case_index=2, role="train")
    assert a.packet == b.packet and a.expected == b.expected


@pytest.mark.parametrize("family", sorted(DEFORMATIONS))
def test_every_family_declares_the_family_it_was_built_as(family: str) -> None:
    # Exactly one family per case is what makes splitting on family well-defined.
    case = build(a_richer_template(family), root_seed=ROOT, case_index=0, role="train")
    assert case.meta["family"] == family


def test_an_unmatched_record_always_reaches_residue() -> None:
    case = build(a_richer_template("missing_record"), root_seed=ROOT, case_index=0, role="train")
    assert case.expected["residue"]["l"] or case.expected["residue"]["r"]


def test_a_decoy_leaves_both_of_its_records_in_residue() -> None:
    case = build(a_richer_template("decoy"), root_seed=ROOT, case_index=0, role="train")
    rejected = next(m for m in case.expected["matches"] if m["c"] == "unsupported")
    assert set(rejected["l"]) <= set(case.expected["residue"]["l"])
    assert set(rejected["r"]) <= set(case.expected["residue"]["r"])


def test_a_duplicate_is_flagged_and_not_matched_twice() -> None:
    case = build(a_richer_template("duplicate"), root_seed=ROOT, case_index=0, role="train")
    flagged = next(e for e in case.expected["exceptions"] if e["kind"] == "duplicate")
    matched = {i for m in case.expected["matches"] for i in m["r"]}
    assert not set(flagged["on"]) & matched


def test_an_ambiguous_pair_is_one_match_naming_both_candidates() -> None:
    case = build(a_richer_template("ambiguous_pair"), root_seed=ROOT, case_index=0, role="train")
    ambiguous = [m for m in case.expected["matches"] if m["c"] == "ambiguous"]
    assert len(ambiguous) == 1 and len(ambiguous[0]["r"]) == 2


def test_an_over_budget_case_is_reported_when_a_tokeniser_is_supplied() -> None:
    from consylr.budget import Budget

    class PerCharacter:
        def encode(self, text: str) -> list[int]:
            return [0] * len(text)

    tiny = Budget(context=1000, packet_max=50, template_overhead=0, output_reserve=100).validate()
    case = build(
        a_richer_template("clean_match"),
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        budget=tiny,
    )
    assert "packet_over_budget" in [v.code for v in case.violations]
    assert case.meta["packet_tokens"] > 50


# --- the refusals, each demonstrated rather than asserted ---------------------


def test_a_case_that_fails_the_validator_is_reported_not_emitted_silently() -> None:
    # The self-validation is the only thing standing between "correct by
    # construction" and a claim about the builder that nothing can contradict.
    # A deformation that produces a wrong answer must surface as violations.
    def wrong(draft: Draft, rng: Random) -> dict[str, Any]:
        # Deforms something, so the effect proof is satisfied and the case
        # reaches the validator — which is what this test is about.
        draft.record(draft.pairs[0][1])["amount"] = "1.00"
        # A supported match that cites nothing, and residue that omits everything.
        return {
            "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": []}],
            "residue": {"l": [], "r": []},
            "do": [{"act": "accept", "on": ["A-001"]}],
        }

    DEFORMATIONS["deliberately_wrong"] = wrong
    try:
        case = build(
            a_richer_template("deliberately_wrong"), root_seed=ROOT, case_index=0, role="train"
        )
        assert "uncited_claim" in [v.code for v in case.violations]
    finally:
        del DEFORMATIONS["deliberately_wrong"]


def test_a_missing_record_always_carries_an_open_entry_as_well_as_residue() -> None:
    # Producing only one of the two is the silent-residue failure the schema
    # exists to prevent, and it validates clean on its own.
    case = build(a_richer_template("missing_record"), root_seed=ROOT, case_index=0, role="train")
    orphans = set(case.expected["residue"]["l"])
    named = {i for o in case.expected["open"] for i in o["on"]}
    assert orphans and orphans <= named


def test_cause_not_established_declines_the_cause_rather_than_naming_one() -> None:
    # Emitting a plausible cause here is a hallucination wearing caution's
    # clothing: the output looks careful and asserts something the packet does
    # not support.
    case = build(
        a_richer_template("cause_not_established"), root_seed=ROOT, case_index=0, role="train"
    )
    kinds = {e["kind"] for e in case.expected["exceptions"]}
    assert kinds == {"cause_not_established"}
    assert all(e["why"] == [] for e in case.expected["exceptions"])


def test_a_template_whose_sides_do_not_correspond_is_refused() -> None:
    body = dict(a_richer_template("clean_match").body)
    body["right"] = list(body["right"])[:2]
    with pytest.raises(ValueError, match="same clean pairs"):
        build(Template.from_mapping(body), root_seed=ROOT, case_index=0, role="train")


# --- the packet and the prompt are different strings --------------------------


def test_declaring_a_wrapper_does_not_loosen_the_packet_allowance() -> None:
    # The cap on the rendered prompt is packet_max + template_overhead. Measuring
    # the *packet* against that cap makes every declared token of wrapper an
    # extra token of packet allowance — so the more honestly a caller describes
    # its template, the weaker the gate becomes. The failure it lets through is
    # the harness left-truncating the prompt: valid JSON, healthy parse rate, and
    # the model answering about records it never saw.
    from consylr.budget import Budget

    template = a_richer_template("clean_match")
    measured = build(
        template, root_seed=ROOT, case_index=0, role="train", tokeniser=PerCharacter()
    ).meta["packet_tokens"]

    # One token over the packet allowance, and comfortably under the prompt cap.
    # Checked against the prompt cap this packet is legal, which is the mistake.
    budget = Budget(
        context=8192, packet_max=measured - 1, template_overhead=500, output_reserve=600
    ).validate()
    case = build(
        template,
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        budget=budget,
    )
    assert budget.packet_max < case.meta["packet_tokens"] < budget.prompt_max
    assert "packet_over_budget" in [v.code for v in case.violations]


def test_each_count_is_recorded_under_a_name_that_means_what_it_counted() -> None:
    # The packet count was once stored as `prompt_tokens`, which put a packet
    # count under a prompt name and let the wrapper be assumed away a second
    # time — in the metadata, where the fast audit path would later read it.
    case = build(
        a_richer_template("clean_match"),
        root_seed=ROOT,
        case_index=0,
        role="train",
        render=lambda packet: "instructions: " + _serialise(packet) + " decide.",
    )
    assert case.meta["packet_tokens"] < case.meta["prompt_tokens"]


def test_a_rendered_prompt_is_checked_against_the_prompt_cap_when_one_is_given() -> None:
    """A packet inside its allowance whose prompt is not.

    Calibrated against the packet this fixture actually produces, so the test
    isolates the prompt cap rather than tripping the packet one on the way.
    """
    from consylr.budget import Budget

    template = a_richer_template("clean_match")
    measured = build(
        template, root_seed=ROOT, case_index=0, role="train", tokeniser=PerCharacter()
    ).meta["packet_tokens"]

    # Room for the packet, and for a wrapper half the size of the real one.
    budget = Budget(
        context=4096, packet_max=measured, template_overhead=10, output_reserve=600
    ).validate()
    case = build(
        template,
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        budget=budget,
        render=lambda packet: "instructions, at some length: " + _serialise(packet) + " decide.",
    )
    assert case.meta["prompt_tokens"] > case.meta["packet_tokens"]
    codes = [v.code for v in case.violations]
    assert "prompt_over_budget" in codes and "packet_over_budget" not in codes


def test_a_template_with_no_id_is_refused_rather_than_built_under_an_empty_one() -> None:
    # It built clean and wrote meta['template_id'] == '', which the split then
    # treats as a template — one that every other id-less template is an alias of.
    body = dict(a_richer_template("clean_match").body)
    del body["id"]
    with pytest.raises(ValueError, match="id"):
        build(Template.from_mapping(body), root_seed=ROOT, case_index=0, role="train")


def test_a_record_carrying_its_own_id_is_refused() -> None:
    # Identifiers are the packet's, assigned by side and position. A record that
    # brought its own would collide across sides or point a citation at nothing,
    # and every `why` in the expected output is written against the generated id.
    # Silently overriding it was the previous behaviour; refusing says so.
    body = dict(a_richer_template("clean_match").body)
    left = [dict(r) for r in body["left"]]
    left[0]["id"] = "B-999"
    body["left"] = left
    with pytest.raises(ValueError, match="'id'"):
        build(Template.from_mapping(body), root_seed=ROOT, case_index=0, role="train")


# --- the packet must not tell the model which record was deformed -------------


def numeric_template(family: str, amount: object = 1000, pairs: int = 4) -> Template:
    """A template whose amounts are JSON numbers rather than strings.

    Nothing refuses this: the required-field check does not type-check, `_records`
    only asks that a record is a dict, and the validator never inspects an amount.
    """
    return Template.from_mapping(
        {
            "id": f"n-{family}",
            "family": family,
            "left": [
                {
                    "ref": f"INV-{i}",
                    "party": "Northwind Ltd",
                    "date": "2026-03-02",
                    "amount": amount,
                }
                for i in range(pairs)
            ],
            "right": [
                {
                    "ref": f"INV-{i}",
                    "party": "Northwind Ltd",
                    "date": "2026-03-04",
                    "amount": amount,
                }
                for i in range(pairs)
            ],
            "policy": [
                {"id": "P-1", "text": "Invoices settle at face value."},
                {"id": "P-2", "text": CAUSE_LINES.get(family, "Amounts settle in full.")},
            ],
            **({"cause": "P-2"} if family in CAUSE_LINES else {}),
        }
    )


DEFORMED_AMOUNT_FAMILIES = [
    "fee_at_source",
    "withholding",
    "partial_payment",
    "batched_vs_itemised",
    "reversal",
    "cause_not_established",
]


@pytest.mark.parametrize("family", DEFORMED_AMOUNT_FAMILIES)
def test_no_field_marks_out_the_record_the_deformation_touched(family: str) -> None:
    """The answer must not be readable from the packet's serialisation.

    A deformation wrote `str(Decimal)` back while untouched records kept the
    template's JSON type, so a deformed record was the only string-typed amount
    in the packet. A model could then score near-perfectly on exception
    identification by reading JSON types, with no reconciliation at all —
    inflating measured accuracy on exactly the capability being measured.
    """
    case = build(numeric_template(family), root_seed=ROOT, case_index=0, role="train")
    assert case.violations == []
    for field in ("ref", "party", "date", "amount"):
        shapes = {type(r[field]).__name__ for r in case.packet["records"] if field in r}
        assert len(shapes) == 1, f"{field} distinguishes records: {shapes}"


@pytest.mark.parametrize("family", sorted(DEFORMATIONS))
def test_every_amount_in_a_packet_is_written_the_same_way(family: str) -> None:
    case = build(a_richer_template(family), root_seed=ROOT, case_index=0, role="train")
    amounts = [r["amount"] for r in case.packet["records"]]
    assert all(isinstance(a, str) for a in amounts)
    assert all(a == a.strip() and a.count(".") == 1 and len(a.split(".")[1]) == 2 for a in amounts)


# --- a deformation has to prove it deformed something ------------------------


@pytest.mark.parametrize("amount", ["0.25", "0.10", "0.02"])
def test_a_small_amount_still_carries_an_observable_cut(amount: str) -> None:
    """Ground truth by construction requires the construction to have an effect.

    The 2% cut quantised to 0.00 for small amounts, so the packet was a clean
    match while the answer key asserted an exception. The ground truth was
    factually wrong, the shipping validator passed it, and a model answering
    correctly was scored wrong.
    """
    case = build(
        a_richer_template("fee_at_source", amount=amount),
        root_seed=ROOT,
        case_index=0,
        role="train",
    )
    distinct = {r["amount"] for r in case.packet["records"]}
    assert len(distinct) > 1, "nothing was deformed, yet an exception is asserted"


@pytest.mark.parametrize("amount", ["0.01", "0.00"])
def test_an_amount_that_cannot_carry_a_cut_is_refused_rather_than_asserted(amount: str) -> None:
    # The alternative is a packet that is a clean match beneath an answer key
    # asserting an exception on it: ground truth that is factually wrong, passed
    # by the validator, scoring a correct answer as wrong.
    with pytest.raises(ValueError, match="nothing to observe"):
        build(
            a_richer_template("fee_at_source", amount=amount),
            root_seed=ROOT,
            case_index=0,
            role="train",
        )


def test_money_rounds_half_up_rather_than_to_even() -> None:
    # 2% of 12.25 is 0.2450. Banker's rounding gives 0.24; money gives 0.25.
    case = build(
        a_richer_template("fee_at_source", amount="12.25", pairs=3),
        root_seed=ROOT,
        case_index=0,
        role="train",
    )
    right = [r for r in case.packet["records"] if r["id"].startswith("B-")]
    assert right[0]["amount"] == "12.00"


def test_an_unexplained_shortfall_scales_with_the_amount() -> None:
    # A hard-coded 37.50 turned a 10.00 obligation into -27.50, with no violation.
    case = build(
        a_richer_template("cause_not_established", amount="10.00"),
        root_seed=ROOT,
        case_index=0,
        role="train",
    )
    assert all(not str(r["amount"]).startswith("-") for r in case.packet["records"])


@pytest.mark.parametrize("family", sorted(DEFORMATIONS))
def test_every_asserted_exception_is_observable_in_the_packet(family: str) -> None:
    """Self-validation's missing half.

    The validator checks the answer's *form* against the packet's identifiers.
    Nothing checked the answer's *truth*: that the packet was deformed in the way
    the answer key claims. An exception naming a record byte-identical to its
    clean counterpart is an assertion about nothing.
    """
    clean = build(
        a_richer_template("clean_match"), root_seed=ROOT, case_index=0, role="train"
    ).packet
    case = build(a_richer_template(family), root_seed=ROOT, case_index=0, role="train")
    before = {r["id"]: r for r in clean["records"]}
    after = {r["id"]: r for r in case.packet["records"]}

    # Per exception, not per record: `reversal` legitimately names the original
    # posting alongside the reversing one. What cannot be legitimate is an
    # exception whose every named record is byte-identical to the clean packet.
    for exception in case.expected.get("exceptions", []):
        observable = [
            rid for rid in exception["on"] if rid not in before or before[rid] != after[rid]
        ]
        assert observable, (
            f"{family}: exception {exception['kind']!r} names only records that are "
            f"unchanged from the clean packet"
        )

    if family == "clean_match":
        assert before == after


def test_a_deformation_that_asserts_an_unobservable_exception_is_refused() -> None:
    """The rule, rather than the instances.

    Every family is fixed, but the class is not closed until the builder refuses
    a case whose answer key asserts something the packet does not show. This is
    self-validation's other half: the shipping validator checks the answer's
    form, and this checks its truth against the packet it describes.
    """

    def asserts_nothing(draft: Draft, rng: Random) -> dict[str, Any]:
        # Deforms one record and asserts the exception on a different one, so the
        # packet does change — just not anywhere the answer key points.
        draft.record(draft.pairs[1][1])["amount"] = "1.00"
        matches = _clean(draft)
        exception: dict[str, Any] = {
            "on": [draft.pairs[0][1]],
            "kind": "fee_at_source",
            "c": "supported",
            "why": [draft.warrant],
        }
        return _finish(draft, matches, [exception])

    DEFORMATIONS["asserts_nothing"] = asserts_nothing
    try:
        with pytest.raises(ValueError, match="unchanged"):
            build(a_richer_template("asserts_nothing"), root_seed=ROOT, case_index=0, role="train")
    finally:
        del DEFORMATIONS["asserts_nothing"]


def test_a_deformation_that_changes_nothing_at_all_is_refused() -> None:
    def changes_nothing(draft: Draft, rng: Random) -> dict[str, Any]:
        return _finish(draft, _clean(draft))

    DEFORMATIONS["changes_nothing"] = changes_nothing
    try:
        with pytest.raises(ValueError, match="deformed nothing"):
            build(a_richer_template("changes_nothing"), root_seed=ROOT, case_index=0, role="train")
    finally:
        del DEFORMATIONS["changes_nothing"]


# --- a gate that is opt-in is a gate that is off ------------------------------


def test_a_case_cannot_be_built_without_saying_how_tokens_are_counted() -> None:
    """The budget gate was opt-in on `tokeniser`, so the default path enforced
    nothing: a 7838-token packet against the 1200-token default cap returned no
    violations, and passing a deliberately tiny budget changed nothing because
    the argument was accepted and ignored. That was a regression — the same call
    returned `headroom_lost` before the round that "fixed" the budget.
    """
    with pytest.raises(TypeError):
        _build(a_richer_template("clean_match"), root_seed=ROOT, case_index=0, role="train")  # type: ignore[call-arg]


def test_a_large_packet_is_caught_on_the_ordinary_path() -> None:
    case = build(
        a_richer_template("clean_match", pairs=40),
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        render=_serialise,
    )
    codes = [v.code for v in case.violations]
    assert "packet_over_budget" in codes and "headroom_lost" in codes


def test_a_built_case_always_records_both_counts() -> None:
    # RFC-0003 has `meta.json` carry the rendered prompt token count, and makes
    # it what the fast audit path re-checks. Both were absent on every path the
    # code could run.
    case = build(
        a_richer_template("clean_match"),
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        render=_serialise,
    )
    assert case.meta["packet_tokens"] > 0
    assert case.meta["prompt_tokens"] > 0


def test_a_budget_whose_numbers_cannot_fit_is_refused_at_the_build() -> None:
    # `Budget.validate()` had no caller anywhere in the package, so a budget that
    # raises when validated was silently accepted.
    with pytest.raises(ValueError, match="cannot fit"):
        build(
            a_richer_template("clean_match"),
            root_seed=ROOT,
            case_index=0,
            role="train",
            tokeniser=PerCharacter(),
            render=_serialise,
            budget=Budget(context=2048, packet_max=1600, template_overhead=0, output_reserve=600),
        )


# --- the quota gate reads what the builder writes ------------------------------


@pytest.mark.parametrize(
    ("family", "certainty"),
    [
        ("clean_match", "supported"),
        ("fee_at_source", "supported"),
        ("cause_not_established", "ambiguous"),
        ("decoy", "unsupported"),
        ("ambiguous_pair", "ambiguous"),
    ],
)
def test_a_case_records_the_certainty_it_was_built_with(family: str, certainty: str) -> None:
    """`quota.check` reads `certainty` off each case, and nothing wrote it.

    So the quota gate reported `supported_share_low` at 0% on every corpus the
    builder could produce, and its contradiction check was unreachable. Each
    deformation already knows the certainty it constructed; it simply was not
    recorded.
    """
    case = build(
        a_richer_template(family),
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        render=_serialise,
    )
    assert case.meta["certainty"] == certainty


def test_a_corpus_of_built_cases_can_be_measured_by_the_quota_gate() -> None:
    from consylr.quota import Plan
    from consylr.quota import check as quota_check

    families = ["clean_match", "fee_at_source", "cause_not_established"]
    rows = [
        build(
            a_richer_template(f),
            root_seed=ROOT,
            case_index=i,
            role="train",
            tokeniser=PerCharacter(),
            render=_serialise,
        ).meta
        for f in families
        for i in range(10)
    ]
    plan = Plan(families=frozenset(families), family_floor=2)
    codes = [v.code for v in quota_check(rows, plan)]
    assert "supported_share_low" not in codes, "the gate is reading 0% again"


def test_a_clean_match_that_deformed_something_is_refused() -> None:
    # The family whose whole definition is that nothing was deformed. A packet
    # that differs from its clean self under a `clean_match` answer key is a
    # correspondence the answer does not describe, and the model is marked wrong
    # for seeing it.
    def deforms_anyway(draft: Draft, rng: Random) -> dict[str, Any]:
        draft.record(draft.pairs[0][1])["amount"] = "1.00"
        return _finish(draft, _clean(draft))

    original = DEFORMATIONS["clean_match"]
    DEFORMATIONS["clean_match"] = deforms_anyway
    try:
        with pytest.raises(ValueError, match="must deform nothing"):
            build(a_richer_template("clean_match"), root_seed=ROOT, case_index=0, role="train")
    finally:
        DEFORMATIONS["clean_match"] = original


# --- a family the packet does not distinguish is not a family ----------------


def with_policy(family: str, policy: list[dict[str, str]], **over: Any) -> Template:
    body = dict(a_richer_template(family, **over).body)
    body["policy"] = policy
    body["cause"] = policy[0]["id"]
    return Template.from_mapping(body)


FEE_POLICY = [{"id": "P-1", "text": "A settlement fee is deducted at source."}]
TAX_POLICY = [{"id": "P-1", "text": "Withholding tax is deducted before remittance."}]


def test_two_families_that_emit_the_same_packet_cannot_both_be_right() -> None:
    """`fee_at_source` and `withholding` were the same closure at the same rate.

    So one scenario emitted byte-identical packets under two contradictory answer
    keys, and the split was free to put them in different roles. RFC-0002
    distinguishes the families by the cause being *described in policy*, so a
    packet that describes neither cannot carry the distinction — and grading it
    is exactly the "cause the packet does not support" the artefact forbids.
    """
    fee = build(
        with_policy("fee_at_source", FEE_POLICY, pairs=3),
        root_seed=ROOT,
        case_index=0,
        role="train",
    )
    tax = build(
        with_policy("withholding", TAX_POLICY, pairs=3), root_seed=ROOT, case_index=0, role="train"
    )
    assert fee.packet != tax.packet, "the two families are indistinguishable in the packet"


@pytest.mark.parametrize(
    ("family", "policy"), [("fee_at_source", FEE_POLICY), ("withholding", TAX_POLICY)]
)
def test_the_exception_cites_the_line_that_names_the_cause(
    family: str, policy: list[dict[str, str]]
) -> None:
    # Every warrant-citing exception cited `policy[0]` whatever that line said.
    case = build(with_policy(family, policy, pairs=3), root_seed=ROOT, case_index=0, role="train")
    exception = next(e for e in case.expected["exceptions"] if e["kind"] == family)
    cited = {p["id"] for p in case.packet["policy"] if p["id"] in exception["why"]}
    assert cited, "the exception cites no policy line at all"
    named = " ".join(p["text"] for p in case.packet["policy"] if p["id"] in cited).lower()
    assert any(term in named for term in CAUSE_TERMS[family])


@pytest.mark.parametrize("family", sorted(CAUSE_TERMS))
def test_a_template_whose_policy_cannot_support_its_family_is_refused(family: str) -> None:
    # The check the distinction needs: "the exam grades a distinction the packet
    # carries" as a property the build enforces, not an intention.
    bland = [{"id": "P-1", "text": "Invoices settle at face value."}]
    with pytest.raises(ValueError, match=family):
        build(with_policy(family, bland, pairs=3), root_seed=ROOT, case_index=0, role="train")


def test_a_template_declaring_a_cause_line_that_does_not_exist_is_refused() -> None:
    body = dict(with_policy("fee_at_source", FEE_POLICY, pairs=3).body)
    body["cause"] = "P-9"
    with pytest.raises(ValueError, match="P-9"):
        build(Template.from_mapping(body), root_seed=ROOT, case_index=0, role="train")


def test_a_structural_family_cites_the_records_rather_than_a_policy_line() -> None:
    # `partial_payment` is observable from the records themselves — one
    # obligation settled by several transfers. Citing a policy line that says
    # nothing about it is the same defect in a quieter register.
    case = build(a_richer_template("partial_payment"), root_seed=ROOT, case_index=0, role="train")
    exception = next(e for e in case.expected["exceptions"] if e["kind"] == "partial_payment")
    assert not any(w.startswith("P-") for w in exception["why"])


def test_a_clean_pair_cites_its_own_records_not_the_deformed_pair_s_policy() -> None:
    """Evidence citation precision is a scored metric, and this was a regression.

    `Draft.warrant` began returning the cause line, and `_clean()` uses it for
    every untouched pair — so on a fee template all four matches cited "A
    settlement fee is deducted at source", including the three pairs where no fee
    was deducted. The line that actually warrants a clean match was cited
    nowhere in the case.

    It was invisible because every test written for the cause work used
    `pairs=1`, where `_clean()` returns nothing and the path never runs.
    """
    case = build(a_richer_template("fee_at_source", pairs=4), root_seed=ROOT, case_index=0)
    deformed = {i for e in case.expected["exceptions"] for i in e["on"]}
    cause = "P-2"

    for match in case.expected["matches"]:
        touched = deformed & set(match["r"])
        if not touched:
            assert cause not in match["why"], (
                f"a clean pair {match['l']}/{match['r']} cites the fee line, and no fee "
                "was deducted from it"
            )
            assert set(match["why"]) <= set(match["l"]) | set(match["r"]), (
                "a clean pair should rest on its own two records"
            )


@pytest.mark.parametrize(
    ("family", "text"),
    [
        ("fee_at_source", "Coffee and travel costs are excluded."),
        ("withholding", "Taxidermy services are out of scope."),
        ("withholding", "Any deviation from the payment syntax will be rejected."),
        ("timing_cutoff", "The vendor must disclose all fees in writing."),
    ],
)
def test_a_word_inside_another_word_does_not_declare_a_cause(family: str, text: str) -> None:
    # Bare substring matching accepted "Coffee" as a fee and "syntax" as a tax.
    with pytest.raises(ValueError, match="says nothing about it"):
        build(with_policy(family, [{"id": "P-1", "text": text}], pairs=3), root_seed=ROOT)


@pytest.mark.parametrize(
    ("family", "text"),
    [
        ("fee_at_source", "No fee is payable under this agreement."),
        ("withholding", "No tax is withheld on domestic settlements."),
    ],
)
def test_a_line_denying_the_cause_does_not_declare_it(family: str, text: str) -> None:
    # The answer key would assert a deduction the packet expressly denies.
    with pytest.raises(ValueError, match="denies"):
        build(with_policy(family, [{"id": "P-1", "text": text}], pairs=3), root_seed=ROOT)


def test_an_invisible_character_does_not_hide_a_genuine_cause() -> None:
    # The other direction, and the one that lets a valid template be sabotaged:
    # a zero-width space inside "fee" renders identically and is invisible in a
    # diff. `templates._text` exists for exactly this and was applied to every
    # identity comparison and to nothing here.
    poisoned = [{"id": "P-1", "text": "A settlement f\u200bee is deducted at source."}]
    case = build(with_policy("fee_at_source", poisoned, pairs=3), root_seed=ROOT)
    assert case.violations == []


def test_the_exception_cites_the_declared_cause_not_the_first_policy_line() -> None:
    """The falsifying test this round's headline fix did not have.

    Every citation test passed a single-line policy, so `cause` and `policy[0]`
    were always the same line — and mutating `Draft.warrant` to ignore `cause`
    entirely, reverting the fix and restoring the fee-versus-withholding
    contradiction, left the whole suite green. A fix whose revert nothing
    catches is a fix on trust.
    """
    policy = [
        {"id": "P-1", "text": "Invoices settle at face value unless stated otherwise."},
        {"id": "P-2", "text": "A settlement fee is deducted at source."},
    ]
    body = dict(a_richer_template("fee_at_source", pairs=2).body)
    body["policy"] = policy
    body["cause"] = "P-2"

    case = build(Template.from_mapping(body), root_seed=ROOT)
    exception = next(e for e in case.expected["exceptions"] if e["kind"] == "fee_at_source")
    assert exception["why"] == ["P-2"], "the exception cites the first line, not the declared cause"


# --- the packet has a size the competition specifies -------------------------


@pytest.mark.parametrize("pairs", [1, 2])
def test_a_packet_below_the_gate_one_floor_is_reported(pairs: int) -> None:
    """*[competition constraint — ADTC profiler]* 5–10 records per Gate 1 packet.

    Nothing enforced it. The first exam built from these templates had 101 of
    206 packets outside the range — 28 under and 73 over — because a template's
    pair count was chosen freely and deformations add and remove records on top
    of it. A packet outside the range tests a shape the competition does not
    specify, which is a measurement of something else.
    """
    case = build(a_richer_template("clean_match", pairs=pairs), root_seed=ROOT)
    assert "packet_too_small" in [v.code for v in case.violations]


def test_a_packet_above_the_gate_one_ceiling_is_reported() -> None:
    case = build(a_richer_template("clean_match", pairs=8), root_seed=ROOT)
    assert "packet_too_large" in [v.code for v in case.violations]


@pytest.mark.parametrize("pairs", [3, 4, 5])
def test_a_packet_inside_the_range_is_not_reported(pairs: int) -> None:
    case = build(a_richer_template("clean_match", pairs=pairs), root_seed=ROOT)
    codes = [v.code for v in case.violations]
    assert "packet_too_small" not in codes and "packet_too_large" not in codes


# --- a family that does not predict its answer, per RFC-0003 -----------------
#
# Certainty was a deterministic function of family in every corpus this project
# had built: ambiguous meant `ambiguous_pair` or `cause_not_established`,
# unsupported meant `decoy`, and the other eleven families meant supported, with
# no overlap anywhere in 12,000 cases. So "recognise the family" scored certainty
# perfectly without reading a policy line, and a tuned model learned exactly
# that — declining on nine families at a rate of 100% and on five at 0%, with
# nothing in between, and never once declining on `ambiguous_pair` despite it
# being 21% of the corpus.
#
# `withhold_cause` breaks the function. The same body emits a supported case with
# its cause line and an unsettleable one without it, so the only way to tell them
# apart is to read the policy.


def test_a_withheld_cause_declines_instead_of_naming_the_exception() -> None:
    case = built(Template.from_mapping(template_body(family="fee_at_source", withhold_cause=True)))
    kinds = {e["kind"] for e in case.expected["exceptions"]}
    assert kinds == {"cause_not_established"}
    assert all(e["c"] == "unsupported" and e["why"] == [] for e in case.expected["exceptions"])
    assert case.expected["open"], "an unsettleable difference must say what would settle it"
    assert case.meta["certainty"] != "supported"


def test_a_withheld_cause_removes_the_line_that_stated_it() -> None:
    """The packet cannot carry the distinction it is being graded on."""
    case = built(Template.from_mapping(template_body(family="fee_at_source", withhold_cause=True)))
    assert not any("fee" in str(line["text"]).lower() for line in case.packet["policy"]), (
        case.packet["policy"]
    )


def test_the_flag_is_the_only_difference_between_the_two_cases() -> None:
    """Contrastive by construction: one policy line apart, same everything else.

    A pair the model cannot tell apart except by reading the policy is the whole
    point. If withholding also moved a record, an amount or a date, the model
    could learn the difference from the ledger and never look at the policy —
    which is the shortcut being removed, rebuilt one coordinate over.
    """
    body = template_body(family="fee_at_source")
    with_cause = built(Template.from_mapping(body))
    without = built(Template.from_mapping({**body, "withhold_cause": True}))

    assert with_cause.packet["records"] == without.packet["records"]
    assert with_cause.packet["documents"] == without.packet["documents"]
    dropped = [p for p in with_cause.packet["policy"] if p not in without.packet["policy"]]
    assert len(dropped) == 1 and dropped[0]["id"] == body["cause"]


def test_a_cause_still_stated_elsewhere_is_refused() -> None:
    """Removing the declared line is not the same as removing the cause.

    A second line saying the same thing leaves the packet able to settle the case
    while the answer key says it cannot — an answer asserting less than the packet
    supports, which is the same class of defect as one asserting more.
    """
    body = template_body(family="fee_at_source")
    body["policy"] = [
        *body["policy"],
        {"id": "P-3", "text": "A settlement fee is deducted at source on every remittance."},
    ]
    with pytest.raises(ValueError, match="still states"):
        built(Template.from_mapping({**body, "withhold_cause": True}))


def test_withholding_a_cause_a_family_never_had_is_refused() -> None:
    with pytest.raises(ValueError, match="no cause to withhold"):
        built(Template.from_mapping(template_body(family="clean_match", withhold_cause=True)))


def test_a_surviving_line_that_denies_the_cause_is_still_the_cause() -> None:
    """A denial names the cause too, and the packet still settles the case.

    "The settlement fee is not waived" tells a reader the fee applies. Exempting
    denials from the absence check let a packet plainly state the cause while the
    answer key declined it — the defect the check exists to prevent, wearing the
    word `not`.
    """
    body = template_body(family="fee_at_source")
    body["policy"] = [
        *body["policy"],
        {"id": "P-3", "text": "The settlement fee is not waived for any counterparty."},
    ]
    with pytest.raises(ValueError, match="still states"):
        built(Template.from_mapping({**body, "withhold_cause": True}))


def test_twin_of_without_withholding_is_refused() -> None:
    with pytest.raises(ValueError, match="only a withheld twin"):
        built(Template.from_mapping({**template_body(family="fee_at_source"), "twin_of": "t-000"}))
