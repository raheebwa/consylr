# SPDX-License-Identifier: MIT
"""Tests for the case builder, per RFC-0003.

Ground truth is known **by construction**: a case is built by applying a named
deformation to a clean pair, so the correct answer is a by-product of building it
rather than a judgement made afterwards. That is what makes the evaluation
honest, and it is the whole of the provenance story.
"""

import pytest

from consylr.cases import DEFORMATIONS, _serialise, build, case_seed
from consylr.templates import Template

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
        ],
        "right": [
            {
                "ref": "INV-1001",
                "party": "Northwind Ltd",
                "date": "2026-03-04",
                "amount": "1000.00",
            },
            {"ref": "INV-1002", "party": "Southgate Ltd", "date": "2026-03-07", "amount": "250.00"},
        ],
        "policy": [{"id": "P-1", "text": "Invoices settle at face value unless a fee is stated."}],
    }
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
    assert len(case.expected["matches"]) == 2
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


def a_richer_template(family: str, pairs: int = 4) -> Template:
    body: dict[str, object] = {
        "id": f"t-{family}",
        "family": family,
        "left": [
            {
                "ref": f"INV-{2000 + i}",
                "party": f"Party {i}",
                "date": "2026-03-02",
                "amount": "500.00",
            }
            for i in range(pairs)
        ],
        "right": [
            {
                "ref": f"INV-{2000 + i}",
                "party": f"Party {i}",
                "date": "2026-03-04",
                "amount": "500.00",
            }
            for i in range(pairs)
        ],
        "policy": [
            {"id": "P-1", "text": "Invoices settle at face value unless a deduction is stated."},
            {"id": "P-2", "text": "Settlement fees are deducted at source."},
        ],
        "documents": [{"id": "D-1", "text": "Remittance advice for March 2026."}],
    }
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

    tiny = Budget(context=1000, packet_max=50, output_reserve=100).validate()
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
    def wrong(draft: object, rng: object) -> dict[str, object]:
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


class PerCharacter:
    def encode(self, text: str) -> list[int]:
        return [0] * len(text)


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


def test_the_packet_count_is_recorded_under_a_name_that_means_the_packet() -> None:
    case = build(
        a_richer_template("clean_match"),
        root_seed=ROOT,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
    )
    assert "packet_tokens" in case.meta
    assert "prompt_tokens" not in case.meta, "nothing here has rendered a prompt"


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


def test_a_record_carrying_its_own_id_does_not_override_the_generated_one() -> None:
    # Identifiers are the packet's, assigned by side and position. A record that
    # brought its own would collide across sides or point a citation at nothing,
    # and every `why` in the expected output is written against the generated id.
    body = dict(a_richer_template("clean_match").body)
    left = [dict(r) for r in body["left"]]
    left[0]["id"] = "B-999"
    body["left"] = left
    case = build(Template.from_mapping(body), root_seed=ROOT, case_index=0, role="train")
    ids = [r["id"] for r in case.packet["records"]]
    assert "B-999" not in ids
    assert len(ids) == len(set(ids))
    assert case.violations == []
