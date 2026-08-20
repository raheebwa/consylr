# SPDX-License-Identifier: MIT
"""Tests for evidence-reference validation, per #27.

The provenance scheme is deliberately minimal — immutable record, policy and
document ids, and nothing heavier. That only works if every identifier in an
answer resolves to something the packet actually contained. A reference to
something absent is a failure of the output, not a cosmetic flaw: it is the
model naming evidence it was never given, which is the exact shape of a
confident wrong answer.

Every violation here is planted, and each is asserted to be *named as
fabricated* rather than merely to produce some error. An answer that fails
schema validation for an unrelated reason would otherwise look like a caught
fabrication.
"""

from typing import Any

from consylr.evidence import known_ids, unresolved

PACKET: dict[str, Any] = {
    "documents": [{"id": "D-1", "text": "Remittance advice."}],
    "policy": [{"id": "P-1", "text": "Invoices settle at face value."}],
    "records": [
        {"id": "A-001", "amount": "10.00", "date": "2026-03-02", "party": "Acme", "ref": "PO-1"},
        {"id": "B-001", "amount": "10.00", "date": "2026-03-05", "party": "Acme", "ref": "PO-1"},
    ],
}

GOOD: dict[str, Any] = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["P-1"]}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "accept", "on": ["A-001", "B-001"]}],
}


def test_an_answer_that_names_only_what_it_was_given_passes() -> None:
    assert unresolved(GOOD, PACKET) == []


def test_the_known_ids_are_records_policy_and_documents() -> None:
    assert known_ids(PACKET) == {"A-001", "B-001", "P-1", "D-1"}


def test_a_fabricated_citation_is_named_as_fabricated() -> None:
    """`P-9` does not exist. The failure must say so, and say where."""
    bad = {**GOOD, "matches": [{**GOOD["matches"][0], "why": ["P-9"]}]}
    found = unresolved(bad, PACKET)
    assert [v.code for v in found] == ["unresolved_reference"]
    assert "P-9" in found[0].detail
    assert "matches" in found[0].detail


def test_a_fabricated_record_in_an_action_is_caught_too() -> None:
    """Citations are not the only place an identifier appears. An action against
    a record that was never in the packet is the same failure wearing a
    different field name."""
    bad = {**GOOD, "do": [{"act": "accept", "on": ["A-999"]}]}
    found = unresolved(bad, PACKET)
    assert [v.code for v in found] == ["unresolved_reference"]
    assert "A-999" in found[0].detail


def test_a_fabricated_record_in_residue_is_caught() -> None:
    bad = {**GOOD, "residue": {"l": ["A-404"], "r": []}}
    found = unresolved(bad, PACKET)
    assert [v.code for v in found] == ["unresolved_reference"]
    assert "A-404" in found[0].detail


def test_a_supported_claim_with_no_citation_is_a_failure() -> None:
    """The frozen prompt requires at least one citation on a supported claim.
    An uncited `supported` is an assertion with nothing behind it, which is
    worse than an unsupported one because it reads as evidenced."""
    bad = {**GOOD, "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": []}]}
    assert [v.code for v in unresolved(bad, PACKET)] == ["uncited_claim"]


def test_an_ambiguous_claim_may_stand_without_a_citation() -> None:
    """Only `supported` carries the citation requirement. Demanding one of an
    ambiguous claim would push the model to invent a reference to keep a gate
    quiet — the gate would then be manufacturing the failure it exists to catch."""
    fine = {**GOOD, "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "ambiguous", "why": []}]}
    assert unresolved(fine, PACKET) == []


def test_every_fabrication_is_reported_not_just_the_first() -> None:
    """An operator fixing one and rerunning to find the next is an operator
    doing the tool's work."""
    bad = {
        **GOOD,
        "matches": [{"l": ["A-777"], "r": ["B-001"], "c": "supported", "why": ["P-9"]}],
        "residue": {"l": [], "r": ["B-888"]},
    }
    assert len(unresolved(bad, PACKET)) == 3


def test_a_malformed_answer_is_not_mistaken_for_a_fabrication() -> None:
    """Shape is the schema's job. Reporting a structural problem as invented
    evidence would send the reader looking for a model that lied when the model
    merely produced the wrong shape."""
    assert unresolved({"matches": "not a list"}, PACKET) == []
