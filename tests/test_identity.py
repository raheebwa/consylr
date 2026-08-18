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

from consylr.split import partition
from consylr.templates import Template, check
from tests.support import FAMILIES, built, template_body


def other(**over: Any) -> Template:
    return Template.from_mapping(template_body(id="t-002", **over))


BASE = Template.from_mapping(template_body(id="t-001"))


def same_scenario(a: Template, b: Template, seeds: int = 60) -> None:
    """Identical projection, and therefore never on opposite sides of the split."""
    assert a.structural_fingerprint == b.structural_fingerprint
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


def test_the_order_records_are_listed_in_is_not_a_scenario() -> None:
    # Reversing both sides by the same permutation preserves every clean pair.
    # `sort_keys` sorts keys and never arrays, so this split the two.
    body = template_body(id="t-002")
    body["left"] = list(reversed(body["left"]))
    body["right"] = list(reversed(body["right"]))
    same_scenario(BASE, Template.from_mapping(body))


def test_a_reworded_counterparty_is_not_a_scenario() -> None:
    same_scenario(BASE, other(party="Northwind Limited"))


def test_reworded_policy_prose_is_not_a_scenario() -> None:
    same_scenario(BASE, other(policy_text="Face value settles invoices."))


# --- and the mirror: a real difference must stay a difference ----------------


def test_a_changed_amount_is_a_different_scenario() -> None:
    assert BASE.structural_fingerprint != other(amount="900.00").structural_fingerprint


def test_a_changed_record_count_is_a_different_scenario() -> None:
    assert BASE.structural_fingerprint != other(pairs=2).structural_fingerprint


def test_a_changed_reference_is_a_different_scenario() -> None:
    records = [{**r, "ref": "PO-9"} for r in template_body()["left"]]
    assert BASE.structural_fingerprint != other(left=records).structural_fingerprint


def test_a_changed_policy_identifier_is_a_different_scenario() -> None:
    renumbered = [{**p, "id": "P-9"} for p in template_body()["policy"]]
    assert BASE.structural_fingerprint != other(policy=renumbered).structural_fingerprint


def test_a_different_family_is_a_different_scenario() -> None:
    assert BASE.structural_fingerprint != other(family="fee_at_source").structural_fingerprint


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
    assert BASE.structural_fingerprint != other(left=records).structural_fingerprint


def test_a_changed_document_is_a_different_scenario() -> None:
    # The documents a packet carries are evidence the answer may cite.
    assert (
        BASE.structural_fingerprint
        != other(documents=[{"id": "D-9", "text": "x"}]).structural_fingerprint
    )


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
    body = template_body(family="missing_record", pairs=2)
    alpha = Template.from_mapping({**body, "id": "t-alpha"})
    other_right = [
        {"ref": "ZZZZ-9999", "party": "Totally Other Co", "date": "1999-01-01", "amount": "42.00"},
        body["right"][1],
    ]
    beta = Template.from_mapping({**body, "id": "t-beta", "right": other_right})
    return alpha, beta


def test_two_templates_that_emit_the_same_case_are_one_scenario() -> None:
    alpha, beta = missing_record_pair()
    assert built(alpha).packet == built(beta).packet
    assert built(alpha).expected == built(beta).expected
    assert alpha.body["right"] != beta.body["right"]
    same_scenario(alpha, beta)


def test_content_a_deformation_overwrites_is_not_a_scenario() -> None:
    # `timing_cutoff` overwrites the date with a constant, so the date it
    # overwrote cannot be seen in the packet and must not decide the split.
    body = template_body(family="timing_cutoff", pairs=2)
    a = Template.from_mapping({**body, "id": "t-001"})
    moved = [{**r, "date": "1998-07-04"} for r in body["right"]]
    b = Template.from_mapping({**body, "id": "t-002", "right": moved})
    if built(a).packet == built(b).packet:
        same_scenario(a, b)


def test_two_templates_that_emit_different_cases_are_different_scenarios() -> None:
    a = Template.from_mapping(template_body(id="t-001"))
    b = Template.from_mapping(template_body(id="t-002", amount="900.00"))
    assert built(a).packet != built(b).packet
    assert a.scenario != b.scenario


def test_the_scenario_is_the_same_whatever_the_corpus_seed_is() -> None:
    # Identity has to be stable across corpora. If it moved with the root seed,
    # the same template would change identity between builds and every leak
    # check would be relative to the corpus that happened to be built.
    a = Template.from_mapping(template_body(id="t-001"))
    first = a.scenario
    built(a, root_seed=999_999)
    assert a.scenario == first


def test_the_scenario_probes_more_than_one_case() -> None:
    # Two different templates coinciding at one probe index is unlikely; at
    # three it is negligible. The failure mode of a single probe is a silent
    # merge of distinct scenarios, which is the property being exterminated —
    # so this is collision insurance, not ceremony.
    from consylr.identity import PROBE_INDICES

    assert len(PROBE_INDICES) >= 3
