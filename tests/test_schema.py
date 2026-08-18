# SPDX-License-Identifier: MIT
"""Tests for the model-output validator defined by RFC-0001.

The validator ships in the product *and* validates the training corpus, so a
defect here corrupts both the thing being measured and the measurement.
"""

from consylr.schema import Violation, validate

# A packet's identifiers. The validator resolves references against this.
PACKET = {
    "records": {"A-017", "A-019", "A-021", "A-044", "B-004", "B-008", "B-030"},
    "policy": {"P-02:L7", "P-05:L3"},
}


def ok(**over: object) -> dict[str, object]:
    """A minimal valid output, overridable per test."""
    base: dict[str, object] = {
        "matches": [{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017", "B-004"]}],
        "exceptions": [],
        "open": [],
        "residue": {"l": [], "r": []},
        "do": [{"act": "accept", "on": ["A-017", "B-004"]}],
    }
    base.update(over)
    return base


def codes(out: dict[str, object], packet: dict[str, set[str]] = PACKET) -> list[str]:
    return sorted({v.code for v in validate(out, packet)})


# --- the happy path, so a failing test elsewhere means something ---------------


def test_a_minimal_correct_output_has_no_violations() -> None:
    assert validate(ok(), PACKET) == []


def test_violations_are_returned_not_raised() -> None:
    # A caller needs every problem at once, not the first one.
    out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": []}], do=[])
    assert len(validate(out, PACKET)) >= 1
    assert all(isinstance(v, Violation) for v in validate(out, PACKET))


# --- structural requirements --------------------------------------------------


def test_residue_is_required_even_when_empty() -> None:
    out = ok()
    del out["residue"]
    assert "residue_missing" in codes(out)


def test_unknown_certainty_is_rejected() -> None:
    assert "bad_certainty" in codes(
        ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "probably", "why": ["A-017"]}])
    )


def test_unknown_disposition_act_is_rejected() -> None:
    assert "bad_act" in codes(ok(do=[{"act": "post", "on": ["A-017"]}]))


def test_unknown_exception_kind_is_rejected() -> None:
    out = ok(exceptions=[{"on": ["A-017"], "kind": "vibes", "c": "supported", "why": ["P-02:L7"]}])
    assert "bad_kind" in codes(out)


def test_missing_record_is_not_a_kind_any_more() -> None:
    # RFC-0002 removed it: residue plus an open entry already say this.
    out = ok(
        exceptions=[
            {"on": ["A-017"], "kind": "missing_record", "c": "supported", "why": ["P-02:L7"]}
        ]
    )
    assert "bad_kind" in codes(out)


# --- citations ----------------------------------------------------------------


def test_supported_match_without_a_citation_is_invalid() -> None:
    assert "uncited_claim" in codes(
        ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": []}])
    )


def test_ambiguous_match_may_omit_a_citation() -> None:
    out = ok(
        matches=[{"l": ["A-017"], "r": ["B-004"], "c": "ambiguous", "why": []}],
        residue={"l": [], "r": []},
        do=[{"act": "hold", "on": ["A-017"]}],
    )
    assert "uncited_claim" not in codes(out)


def test_cause_not_established_may_have_an_empty_why() -> None:
    out = ok(
        exceptions=[
            {
                "on": ["A-017", "B-004"],
                "kind": "cause_not_established",
                "c": "unsupported",
                "why": [],
            }
        ]
    )
    assert "uncited_claim" not in codes(out)


def test_a_supported_exception_needs_a_citation() -> None:
    out = ok(exceptions=[{"on": ["A-017"], "kind": "fee_at_source", "c": "supported", "why": []}])
    assert "uncited_claim" in codes(out)


def test_an_identifier_absent_from_the_packet_is_invalid() -> None:
    assert "unresolved_id" in codes(
        ok(matches=[{"l": ["A-999"], "r": ["B-004"], "c": "supported", "why": ["A-999"]}])
    )


# --- the residue rule, RFC-0001 §Residue --------------------------------------


def test_a_record_matched_only_unsupported_is_residue() -> None:
    # The decoy case. Cited and rejected, and still unaccounted for.
    out = ok(
        matches=[
            {
                "l": ["A-044"],
                "r": ["B-030"],
                "c": "unsupported",
                "why": ["A-044", "B-030", "P-05:L3"],
            }
        ],
        residue={"l": [], "r": []},
        do=[{"act": "escalate", "on": ["A-044", "B-030"]}],
    )
    assert "residue_wrong" in codes(out)


def test_declaring_that_residue_is_correct() -> None:
    out = ok(
        matches=[
            {
                "l": ["A-044"],
                "r": ["B-030"],
                "c": "unsupported",
                "why": ["A-044", "B-030", "P-05:L3"],
            }
        ],
        residue={"l": ["A-044"], "r": ["B-030"]},
        do=[{"act": "escalate", "on": ["A-044", "B-030"]}],
    )
    assert "residue_wrong" not in codes(out)


def test_a_supported_match_must_not_be_listed_as_residue() -> None:
    assert "residue_wrong" in codes(ok(residue={"l": ["A-017"], "r": []}))


def test_a_record_in_no_match_at_all_must_be_residue() -> None:
    out = ok(
        open=[{"on": ["A-021"], "need": "counterparty entry"}],
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-021"]}],
    )
    # A-021 is reasoned about but matched to nothing, and is not in residue.
    assert "residue_wrong" in codes(out)


# --- no record in two supported matches ---------------------------------------


def test_a_record_may_not_appear_in_two_supported_matches() -> None:
    out = ok(
        matches=[
            {"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017"]},
            {"l": ["A-017"], "r": ["B-008"], "c": "supported", "why": ["A-017"]},
        ],
        do=[{"act": "accept", "on": ["A-017"]}],
    )
    assert "double_matched" in codes(out)


def test_two_candidates_in_one_ambiguous_match_is_fine() -> None:
    out = ok(
        matches=[{"l": ["A-017"], "r": ["B-004", "B-008"], "c": "ambiguous", "why": []}],
        do=[{"act": "hold", "on": ["A-017"]}],
    )
    assert "double_matched" not in codes(out)


# --- the two cross-output invariants added at review ---------------------------


def test_a_request_must_be_covered_by_an_open_entry() -> None:
    out = ok(
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
        residue={"l": ["A-019"], "r": []},
    )
    assert "dangling_request" in codes(out)


def test_a_request_with_a_matching_open_entry_is_fine() -> None:
    out = ok(
        open=[{"on": ["A-019"], "need": "settlement breakdown"}],
        residue={"l": ["A-019"], "r": []},
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
    )
    assert "dangling_request" not in codes(out)


def test_a_disposed_identifier_must_appear_elsewhere_in_the_output() -> None:
    # Resolvable in the packet, but never reasoned about.
    out = ok(
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "hold", "on": ["A-021"]}],
        residue={"l": ["A-021"], "r": []},
    )
    assert "dangling_request" not in codes(out)  # hold is not a request
    out2 = ok(do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "hold", "on": ["A-021"]}])
    assert "incoherent_disposition" in codes(out2)


# --- refusals -----------------------------------------------------------------


def test_a_numeric_confidence_is_refused_wherever_it_appears() -> None:
    out = ok(
        matches=[
            {"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017"], "confidence": 0.87}
        ]
    )
    assert "numeric_confidence" in codes(out)


def test_open_why_is_optional_but_must_resolve_when_present() -> None:
    fine = ok(
        open=[{"on": ["A-019"], "need": "breakdown"}],
        residue={"l": ["A-019"], "r": []},
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
    )
    assert codes(fine) == []
    bad = ok(
        open=[{"on": ["A-019"], "need": "breakdown", "why": ["P-99:L1"]}],
        residue={"l": ["A-019"], "r": []},
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
    )
    assert "unresolved_id" in codes(bad)
