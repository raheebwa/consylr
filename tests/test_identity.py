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

from consylr.cases import build
from consylr.split import partition
from consylr.templates import Template, check
from tests.support import FAMILIES, template_body


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
        build(other(comment="copied from t-000"), root_seed=1, case_index=0, role="train")


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
        build(other(left=left), root_seed=1, case_index=0, role="train")


# --- the same scenario written differently ------------------------------------


@pytest.mark.parametrize("amount", ["1000.0", "1000.000", 1000, 1000.0])
def test_the_way_an_amount_is_written_is_not_a_scenario(amount: object) -> None:
    # `_money` collapses every one of these to the same Decimal wherever the
    # builder reasons, so a difference the model cannot see was splitting the
    # split.
    same_scenario(BASE, other(amount=amount))


@pytest.mark.parametrize(
    "ref", ["INV-2000​", " INV-2000 ", "INV-2000\t", "INV-2000 "]
)
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


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount", "900.00"), ("pairs", 2)],
)
def test_a_difference_the_model_can_see_is_a_different_scenario(field: str, value: object) -> None:
    changed = Template.from_mapping(template_body(id="t-002", **{field: value}))
    assert BASE.structural_fingerprint != changed.structural_fingerprint


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
        build(other(policy=nested), root_seed=1, case_index=0, role="train")
