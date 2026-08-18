# SPDX-License-Identifier: MIT
"""What makes two templates the same scenario, per RFC-0003.

Identity was computed over the template *body* while a case is built from a
strict subset of it, so content the builder never reads split one scenario
across both roles — with byte-identical packets and byte-identical answer keys,
and every gate clean. Listing more field names fixed the instances twice and the
class neither time.

The model here is different in kind. The builder refuses record keys it does not
know, so nothing unclassified can reach a packet; and identity is a digest over a
*normalised projection of what the builder actually reads*. Identity over the
artefact the model sees, rather than over the source text that produced it.

Every test below is a leak or a false merge the previous model admitted.
"""

from typing import Any

import pytest

from consylr.cases import Case, build
from consylr.cases import _serialise as serialise
from consylr.identity import PROBE_ID, PROBE_SEED, scenario
from consylr.identity import check as identity_check
from consylr.split import partition
from consylr.templates import Template, check
from tests.support import FAKE_BUDGET, FAMILIES, PerCharacter, built, template_body


def other(**over: Any) -> Template:
    return Template.from_mapping(template_body(id="t-002", **over))


def a_real(id: str, **over: Any) -> Template:
    return Template.from_mapping(template_body(id=id, **over))


BASE = Template.from_mapping(template_body(id="t-001"))


def same_scenario(a: Template, b: Template, seeds: int = 60) -> None:
    """One scenario, and therefore never on opposite sides of the split."""
    assert scenario(a) == scenario(b)
    for seed in range(seeds):
        roles = partition([a, b], holdout_share=0.5, seed=seed)
        assert roles[a.id] == roles[b.id], f"split at seed {seed}"


# --- content the builder never reads must not make a second scenario ---------


def test_a_body_key_the_builder_never_reads_is_refused() -> None:
    # `load()` refuses a NOTES.md beside the templates, which pushes exactly this
    # note inside the JSON — where it used to split one scenario in 58 of the
    # first 100 seeds, with byte-identical packets on both sides.
    with pytest.raises(ValueError, match="comment"):
        built(other(comment="copied from t-000"))


def test_a_body_key_the_builder_never_reads_is_reported() -> None:
    v = next(x for x in check([other(comment="note")], FAMILIES) if x.code == "unknown_field")
    assert "comment" in v.detail


@pytest.mark.parametrize("key", ["note", "comment", "counterparty", "payee", "label", "reason"])
def test_a_record_key_the_builder_does_not_know_is_refused(key: str) -> None:
    # Verified live for seven of seven plausible names: two templates differing
    # only in the wording of such a field built clean, produced identical
    # expected outputs, and landed in opposite roles. A five-name denylist over a
    # shape that accepts arbitrary keys can only ever chase the names someone
    # thought of.
    left = [{**r, key: "some prose"} for r in template_body()["left"]]
    with pytest.raises(ValueError, match=key):
        built(other(left=left))


# --- the same scenario written differently ------------------------------------


@pytest.mark.parametrize("amount", ["1000.0", "1000.000", 1000, 1000.0])
def test_the_way_an_amount_is_written_is_not_a_scenario(amount: object) -> None:
    # `_money` collapses every one of these to the same Decimal wherever the
    # builder reasons, so a difference the model cannot see was splitting the
    # split.
    same_scenario(BASE, other(amount=amount))


@pytest.mark.parametrize("ref", ["INV-2000\u200b", " INV-2000 ", "INV-2000\t", "INV-2000 "])
def test_invisible_characters_in_a_reference_are_not_a_scenario(ref: str) -> None:
    # A zero-width space is unreviewable in a diff and in a rendered packet, so a
    # corpus could be poisoned with no visible edit.
    records = [{**r, "ref": ref} for r in template_body(pairs=1)["left"]]
    a = Template.from_mapping(template_body(id="t-001", pairs=1, left=records))
    plain = [{**r, "ref": "INV-2000"} for r in template_body(pairs=1)["left"]]
    b = Template.from_mapping(template_body(id="t-002", pairs=1, left=plain))
    same_scenario(a, b)


def test_unicode_normal_form_is_not_a_scenario() -> None:
    # macOS normalises filenames and pasted text to NFD; Linux and Windows use
    # NFC. The same reference typed on two machines was two scenarios.
    nfc = [{**r, "ref": "INV-CAFÉ"} for r in template_body(pairs=1)["left"]]
    nfd = [{**r, "ref": "INV-CAFÉ"} for r in template_body(pairs=1)["left"]]
    a = Template.from_mapping(template_body(id="t-001", pairs=1, left=nfc))
    b = Template.from_mapping(template_body(id="t-002", pairs=1, left=nfd))
    same_scenario(a, b)


def test_reordering_both_sides_is_a_different_scenario_and_this_is_a_known_gap() -> None:
    """Honest about a residual risk rather than quiet about it.

    Reversing both record lists by one permutation preserves every clean pair,
    but identifiers are assigned by position — so A-001 holds different content
    and the packet genuinely differs. Under identity taken over what the model
    sees, that is two scenarios, and the two can land in opposite roles.

    A model trained on one has effectively seen the other, with the labels
    moved. The mechanical backstops do not catch it either: they refuse
    *identical* packets carrying contradictory answers, and these packets are
    not identical.

    The exposure is bounded — it needs a template committed twice with its
    records permuted, which is an authoring mistake rather than something the
    generator produces — and closing it properly means comparing packets as
    multisets of records rather than as sequences. Recorded here so the next
    reader finds a decision rather than an oversight.
    """
    body = template_body(id="t-002")
    body["left"] = list(reversed(body["left"]))
    body["right"] = list(reversed(body["right"]))
    assert scenario(BASE) != scenario(Template.from_mapping(body))


@pytest.mark.parametrize(
    ("field", "value"),
    [("party", "Northwind Limited"), ("policy_text", "Face value settles invoices.")],
)
def test_reworded_prose_is_a_different_scenario(field: str, value: str) -> None:
    """Deliberate, and the reversal of an earlier decision.

    Identity dropped the counterparty and the policy prose so that two templates
    a paraphrase apart would collide. It cost false merges: "Invoices settle at
    face value" and "A 40% commission is deducted from every remittance" became
    one scenario, reported as differing "only in what never reaches a packet",
    which a diff of those packets disproves.

    RFC-0003 keeps paraphrase off by default and never paraphrases the sealed
    set, so the invariance defended against a transformation this project does
    not apply. If it is ever switched on, a paraphrased corpus is a preserved
    derived artefact with its provenance recorded — not two independently
    authored templates that have to be recognised as one.
    """
    assert scenario(BASE) != scenario(other(**{field: value}))


# --- and the mirror: a real difference must stay a difference ----------------


def test_a_changed_amount_is_a_different_scenario() -> None:
    assert scenario(BASE) != scenario(other(amount="900.00"))


def test_a_changed_record_count_is_a_different_scenario() -> None:
    assert scenario(BASE) != scenario(other(pairs=2))


def test_a_changed_reference_is_a_different_scenario() -> None:
    records = [{**r, "ref": "PO-9"} for r in template_body()["left"]]
    assert scenario(BASE) != scenario(other(left=records))


def test_a_changed_policy_identifier_is_a_different_scenario() -> None:
    renumbered = [{**p, "id": "P-9"} for p in template_body()["policy"]]
    assert scenario(BASE) != scenario(other(policy=renumbered))


def test_a_different_family_is_a_different_scenario() -> None:
    assert scenario(BASE) != scenario(other(family="fee_at_source"))


def test_prose_that_is_not_prose_is_refused_rather_than_erased() -> None:
    # `_without_surface` deleted the whole value under a surface key, so a nested
    # object holding rates and caps was erased from the identity and two
    # genuinely different scenarios were reported as one — the report asserting
    # "a paraphrase cannot change a number", which was untrue there.
    nested = [{"id": "P-1", "text": {"rule": "deduct", "rate": "0.02"}}]
    with pytest.raises(ValueError, match="text"):
        built(other(policy=nested))


def test_a_changed_date_is_a_different_scenario() -> None:
    # A date either side of a cut-off is a whole perturbation family, so a date
    # dropped from the projection would merge `timing_cutoff` into its clean twin.
    records = [{**r, "date": "2026-09-09"} for r in template_body()["left"]]
    assert scenario(BASE) != scenario(other(left=records))


def test_a_changed_document_is_a_different_scenario() -> None:
    # The documents a packet carries are evidence the answer may cite.
    assert scenario(BASE) != scenario(other(documents=[{"id": "D-9", "text": "x"}]))


def test_a_citation_key_the_builder_does_not_know_is_refused() -> None:
    with pytest.raises(ValueError, match="footnote"):
        built(other(policy=[{"id": "P-1", "text": "prose", "footnote": "hidden"}]))


# --- identity is what build() emits, not what the template says --------------


def missing_record_pair() -> tuple[Template, Template]:
    """Two templates whose right-hand records differ and whose packets do not.

    `missing_record` deletes a right-hand record, so everything about it is
    invisible in the packet and in the answer — and was load-bearing in a
    fingerprint taken over the template.
    """
    body = template_body(family="missing_record", pairs=1)
    alpha = Template.from_mapping({**body, "id": "t-alpha"})
    other_right = [
        {"ref": "ZZZZ-9999", "party": "Totally Other Co", "date": "1999-01-01", "amount": "42.00"}
    ]
    beta = Template.from_mapping({**body, "id": "t-beta", "right": other_right})
    return alpha, beta


def probe_case(template: Template) -> Case:
    """What the identity probe sees: the template built under the reserved id.

    The id is normalised because `case_seed` mixes it in, so two copies of one
    scenario under different ids would otherwise draw differently and emit
    different cases — which is the aliasing identity has to catch, not report.
    """
    return build(
        Template.from_mapping({**template.body, "id": PROBE_ID}),
        root_seed=PROBE_SEED,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        render=serialise,
        budget=FAKE_BUDGET,
    )


def test_two_templates_that_emit_the_same_case_are_one_scenario() -> None:
    alpha, beta = missing_record_pair()
    assert alpha.body["right"] != beta.body["right"]
    assert probe_case(alpha).packet == probe_case(beta).packet
    assert probe_case(alpha).expected == probe_case(beta).expected
    same_scenario(alpha, beta)


def test_content_a_deformation_overwrites_is_not_a_scenario() -> None:
    # `timing_cutoff` overwrites the date with a constant, so the date it
    # overwrote cannot be seen in the packet and must not decide the split.
    body = template_body(family="timing_cutoff", pairs=2)
    a = Template.from_mapping({**body, "id": "t-001"})
    moved = [{**r, "date": "1998-07-04"} for r in body["right"]]
    b = Template.from_mapping({**body, "id": "t-002", "right": moved})
    if probe_case(a).packet == probe_case(b).packet:
        same_scenario(a, b)


def test_two_templates_that_emit_different_cases_are_different_scenarios() -> None:
    a = Template.from_mapping(template_body(id="t-001"))
    b = Template.from_mapping(template_body(id="t-002", amount="900.00"))
    assert probe_case(a).packet != probe_case(b).packet
    assert scenario(a) != scenario(b)


def test_the_scenario_is_the_same_whatever_the_corpus_seed_is() -> None:
    # Identity has to be stable across corpora. If it moved with the root seed,
    # the same template would change identity between builds and every leak
    # check would be relative to the corpus that happened to be built.
    a = Template.from_mapping(template_body(id="t-001"))
    first = scenario(a)
    built(a, root_seed=999_999)
    assert scenario(a) == first


def test_the_scenario_probes_more_than_one_case() -> None:
    # Two different templates coinciding at one probe index is unlikely; at
    # three it is negligible. The failure mode of a single probe is a silent
    # merge of distinct scenarios, which is the property being exterminated —
    # so this is collision insurance, not ceremony.
    from consylr.identity import PROBE_INDICES

    assert len(PROBE_INDICES) >= 3


# --- auditing a set of templates for scenarios held more than once -----------


def test_one_file_under_two_ids_is_reported() -> None:
    v = next(
        x
        for x in identity_check([a_real("t-001"), a_real("t-002")])
        if x.code == "duplicate_scenario"
    )
    assert "t-001" in v.detail and "t-002" in v.detail
    assert "one file under two ids" in v.detail


def test_two_files_that_emit_one_case_are_reported_as_what_they_are() -> None:
    # Not an alias — the files genuinely differ. What they differ about never
    # reaches a packet, which is the more interesting half of the report.
    alpha, beta = missing_record_pair()
    v = next(x for x in identity_check([alpha, beta]) if x.code == "duplicate_scenario")
    assert "never reaches a packet" in v.detail


def test_a_pair_a_rewording_apart_is_not_reported_as_one_scenario() -> None:
    # Their packets differ, so a model trained on one has not seen the other.
    templates = [a_real("t-001"), a_real("t-002", party="Northwind Limited")]
    assert identity_check(templates) == []


def test_distinct_scenarios_are_not_reported() -> None:
    templates = [a_real("t-001"), a_real("t-002", amount="900.00")]
    assert identity_check(templates) == []


def test_a_template_that_cannot_be_built_is_reported_not_crashed_through() -> None:
    # An unbuildable template has no scenario. Inventing one would let it take a
    # role in a partition it can never contribute a case to, and raising here
    # would stop an audit that is meant to count every problem at the first one.
    unbuildable = Template.from_mapping(
        template_body(id="t-bad", family="fee_at_source", amount="0.01")
    )
    v = next(x for x in identity_check([unbuildable]) if x.code == "unbuildable_template")
    assert "t-bad" in v.detail


# --- the backstop: one packet may not carry two answers ----------------------


def dual_vocabulary_pair() -> tuple[Template, Template]:
    """Two families whose packets are identical and whose answers are not.

    One policy line satisfies both vocabularies — "fee" reads as a fee at source,
    "tax" as a withholding — so the word-list check passes for each family while
    the packet distinguishes neither. That is why the word list cannot be the
    gate: it can always be satisfied by prose that means something else.
    """
    line = [{"id": "P-1", "text": "A withholding tax fee is deducted before remittance."}]
    body = template_body(pairs=1)
    fee = Template.from_mapping(
        {**body, "id": "t-fee", "family": "fee_at_source", "policy": line, "cause": "P-1"}
    )
    tax = Template.from_mapping(
        {**body, "id": "t-tax", "family": "withholding", "policy": line, "cause": "P-1"}
    )
    return fee, tax


def test_one_packet_carrying_two_answers_is_refused() -> None:
    """Contradictory ground truth, caught mechanically rather than by vocabulary.

    A word list can always be satisfied by prose that means something else, so
    it cannot be the gate. This can: two cases whose packets are identical and
    whose answer keys differ are, between them, teaching the model that one
    input has two correct outputs — and grading it on a distinction the packet
    does not carry. It needs no opinion about what the policy line says.
    """
    fee, tax = dual_vocabulary_pair()
    assert probe_case(fee).packet == probe_case(tax).packet
    assert probe_case(fee).expected != probe_case(tax).expected
    v = next(x for x in identity_check([fee, tax]) if x.code == "contradictory_ground_truth")
    assert "t-fee" in v.detail and "t-tax" in v.detail


def test_two_templates_agreeing_on_one_packet_are_not_contradictory() -> None:
    # The same packet with the same answer is an alias, reported as a duplicate
    # scenario rather than as a contradiction.
    codes = [x.code for x in identity_check([a_real("t-001"), a_real("t-002")])]
    assert "contradictory_ground_truth" not in codes
    assert "duplicate_scenario" in codes


def test_an_alias_collides_even_when_the_deformation_draws_on_the_seed() -> None:
    """The falsifying test for the probe's id substitution.

    `case_seed` mixes the template id in, so two copies of one scenario under
    different ids draw differently unless the probe normalises the id. Every
    other alias test used `clean_match` — the one family whose deformation never
    touches the generator — so removing the substitution left the suite green
    while re-opening the aliasing the probe exists to close.
    """
    from consylr import identity

    # The cache is keyed on the content digest, which already excludes the id —
    # so with it warm the second template never probes and the property looks
    # true whether or not the probe holds it. Cleared between, this asks the
    # probe directly.
    a = Template.from_mapping(template_body(id="t-001", family="fee_at_source", pairs=4))
    b = Template.from_mapping(template_body(id="t-002", family="fee_at_source", pairs=4))

    identity._SEEN.clear()
    first = scenario(a)
    identity._SEEN.clear()
    second = scenario(b)
    assert first == second, "the probe let the template id reach the draw"

    identity._SEEN.clear()
    assert "duplicate_scenario" in [x.code for x in identity_check([a, b])]
