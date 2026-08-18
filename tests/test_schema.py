# SPDX-License-Identifier: MIT
"""Tests for the model-output validator defined by RFC-0001.

The validator ships in the product *and* validates the training corpus, so a
defect here corrupts both the thing being measured and the measurement.

Every test states the packet it analyses. The residue rule is quantified over
the packet, so a fixture that omits a record is a different test.
"""

from consylr.schema import Violation, validate

POLICY = {"P-02", "P-05"}
DOCUMENTS = {"D-01"}


def P(*record_ids: str) -> dict[str, object]:
    return {"records": set(record_ids), "policy": set(POLICY), "documents": set(DOCUMENTS)}


PACKET = P("A-017", "B-004")
FULL = P("A-017", "A-019", "A-021", "B-004", "B-011")


def ok(**over: object) -> dict[str, object]:
    """A complete, correct analysis of PACKET."""
    base: dict[str, object] = {
        "matches": [{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017", "B-004"]}],
        "exceptions": [],
        "open": [],
        "residue": {"l": [], "r": []},
        "do": [{"act": "accept", "on": ["A-017", "B-004"]}],
    }
    base.update(over)
    return base


def codes(out: object, packet: object = PACKET) -> list[str]:
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
    assert codes(out, P("A-044", "B-030")) == []


def test_a_supported_match_must_not_be_listed_as_residue() -> None:
    assert "residue_wrong" in codes(ok(residue={"l": ["A-017"], "r": []}))


def test_a_record_in_no_match_at_all_must_be_residue() -> None:
    out = ok(
        open=[{"on": ["A-021"], "need": "counterparty entry"}],
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-021"]}],
    )
    # A-021 is reasoned about but matched to nothing, and is not in residue.
    assert "residue_wrong" in codes(out, P("A-017", "B-004", "A-021"))


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
    # An allowlist subsumes the old denylist: any unknown key is refused, so
    # near-miss spellings cannot slip through the names someone thought of.
    assert "unknown_field" in codes(out)


def test_open_why_is_optional_but_must_resolve_when_present() -> None:
    fine = ok(
        open=[{"on": ["A-019"], "need": "breakdown"}],
        residue={"l": ["A-019"], "r": []},
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
    )
    pkt = P("A-017", "B-004", "A-019")
    assert codes(fine, pkt) == []
    bad = ok(
        open=[{"on": ["A-019"], "need": "breakdown", "why": ["P-99:L1"]}],
        residue={"l": ["A-019"], "r": []},
        do=[{"act": "accept", "on": ["A-017", "B-004"]}, {"act": "request", "on": ["A-019"]}],
    )
    assert "unresolved_id" in codes(bad, pkt)


# ============================================================================
# Regression tests for defects found in review. Each fails against the
# implementation as first written.
# ============================================================================

FULL = {"records": {"A-017", "A-019", "A-021", "B-004", "B-011"},
        "policy": {"P-02", "P-05"}, "documents": {"D-01"}}


def test_a_record_the_output_never_mentions_is_still_residue() -> None:
    # The rule is "if and only if", quantified over the PACKET's records.
    # Quantifying over what the output happens to name lets an empty analysis
    # of a full packet certify clean — the failure residue exists to prevent.
    empty: dict[str, object] = {"matches": [], "exceptions": [], "open": [],
                                "residue": {"l": [], "r": []}, "do": []}
    assert "residue_wrong" in codes(empty, FULL)


def test_a_complete_analysis_of_every_packet_record_is_clean() -> None:
    out: dict[str, object] = {
        "matches": [{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017"]}],
        "exceptions": [],
        "open": [{"on": ["A-019"], "need": "settlement breakdown"}],
        "residue": {"l": ["A-019", "A-021"], "r": ["B-011"]},
        "do": [{"act": "accept", "on": ["A-017", "B-004"]},
               {"act": "request", "on": ["A-019"]},
               {"act": "escalate", "on": ["A-021", "B-011"]}],
    }
    assert codes(out, FULL) == []


# --- identifier classes the RFC defines --------------------------------------

def test_a_policy_line_span_resolves_against_its_policy_document() -> None:
    out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["P-02:L7"]}],
             residue={"l": ["A-019", "A-021"], "r": ["B-011"]},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "escalate", "on": ["A-019", "A-021", "B-011"]}])
    assert "unresolved_id" not in codes(out, FULL)


def test_a_document_identifier_resolves() -> None:
    out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["D-01"]}],
             residue={"l": ["A-019", "A-021"], "r": ["B-011"]},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "escalate", "on": ["A-019", "A-021", "B-011"]}])
    assert "unresolved_id" not in codes(out, FULL)


def test_a_span_on_an_unknown_policy_does_not_resolve() -> None:
    out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["P-99:L1"]}],
             residue={"l": ["A-019", "A-021"], "r": ["B-011"]},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "escalate", "on": ["A-019", "A-021", "B-011"]}])
    assert "unresolved_id" in codes(out, FULL)


def test_a_packet_whose_records_are_objects_is_accepted() -> None:
    # RFC-0003 defines packet.json records as objects, not bare strings.
    packet = {"records": [{"id": "A-017"}, {"id": "B-004"}], "policy": [], "documents": []}
    assert codes(ok(), packet) == []


# --- malformed output is reported, never raised ------------------------------

def test_a_string_where_a_list_belongs_is_reported_not_raised() -> None:
    # The single most likely malformed model output there is.
    assert "bad_type" in codes(ok(matches=["A-017 -> B-004"]))


def test_a_non_list_section_is_reported_not_raised() -> None:
    assert "bad_type" in codes(ok(matches="A-017"))
    assert "bad_type" in codes(ok(matches={"l": ["A-017"]}))
    assert "bad_type" in codes(ok(exceptions=0))


def test_a_string_residue_side_is_reported_not_iterated() -> None:
    out = ok(residue={"l": "A-019", "r": []})
    c = codes(out)
    assert "bad_type" in c
    assert "unresolved_id" not in c  # never character-by-character


def test_a_citation_sent_as_a_string_is_rejected() -> None:
    out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": "P-99:L1"}])
    assert "bad_type" in codes(out)


# --- required fields ---------------------------------------------------------

def test_an_output_missing_every_section_is_not_clean() -> None:
    assert codes({"residue": {"l": [], "r": []}}) != []


def test_a_match_without_sides_is_invalid() -> None:
    assert "missing_field" in codes(ok(matches=[{"c": "supported", "why": ["A-017"]}]))


def test_an_open_entry_without_a_need_is_invalid() -> None:
    out = ok(open=[{"on": ["A-019"]}], residue={"l": ["A-019"], "r": []},
             do=[{"act": "accept", "on": ["A-017", "B-004"]}])
    assert "missing_field" in codes(out)


def test_a_disposition_without_records_is_invalid() -> None:
    assert "missing_field" in codes(ok(do=[{"act": "accept"}]))


def test_an_ambiguous_match_still_needs_a_why_key() -> None:
    assert "missing_field" in codes(ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "ambiguous"}]))


# --- the free-text field is capped -------------------------------------------

def test_an_unbounded_need_is_rejected() -> None:
    out = ok(open=[{"on": ["A-019"], "need": "x" * 4000}],
             residue={"l": ["A-019"], "r": []},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "request", "on": ["A-019"]}])
    assert "need_too_long" in codes(out)


# --- unknown keys, rather than a denylist ------------------------------------

def test_a_near_miss_confidence_key_is_rejected() -> None:
    for key in ("certainty", "conf", "p", "likelihood", "confidence_score"):
        out = ok(matches=[{"l": ["A-017"], "r": ["B-004"], "c": "supported",
                           "why": ["A-017"], key: 0.87}])
        assert "unknown_field" in codes(out), key


def test_a_misspelled_section_is_rejected_not_ignored() -> None:
    out = {"matches": [], "exception": [{"on": ["A-017"], "kind": "vibes", "c": "nope"}],
           "opens": [{"on": ["A-019"]}], "residue": {"l": [], "r": []}, "do": []}
    assert "unknown_field" in codes(out)


# --- an exception's citation rule is not gated on certainty -------------------

def test_a_hedged_exception_still_needs_a_citation() -> None:
    out = ok(exceptions=[{"on": ["A-017"], "kind": "fee_at_source", "c": "ambiguous", "why": []}])
    assert "uncited_claim" in codes(out)


# --- one defect produces one violation ---------------------------------------

def test_a_missing_residue_key_does_not_cascade() -> None:
    out = {"matches": [{"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017"]}],
           "exceptions": [], "open": [],
           "do": [{"act": "accept", "on": ["A-017", "B-004"]}]}
    assert codes(out, {"records": {"A-017", "B-004"}, "policy": set(), "documents": set()}) \
        == ["residue_missing"]


def test_a_half_present_residue_keeps_the_side_it_declared() -> None:
    out = ok(residue={"l": ["A-019"]})
    c = codes(out, FULL)
    assert "residue_missing" in c
    # A-019 was declared; it must not also be reported as missing from residue.
    detail = " ".join(v.detail for v in validate(out, FULL) if v.code == "residue_wrong")
    assert "missing ['A-019']" not in detail


# --- rules that had no failing test behind them ------------------------------

def test_an_exception_certainty_is_checked_too() -> None:
    out = ok(exceptions=[{"on": ["A-017"], "kind": "fee_at_source", "c": "probably",
                          "why": ["P-02"]}])
    assert "bad_certainty" in codes(out, FULL)


def test_residue_listed_on_the_wrong_side_is_caught() -> None:
    # Membership correct, placement wrong.
    out = ok(residue={"l": ["B-011"], "r": ["A-019", "A-021"]},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "escalate", "on": ["A-019", "A-021", "B-011"]}])
    assert "residue_wrong" in codes(out, FULL)


def test_cause_not_established_exemption_holds_at_supported() -> None:
    out = ok(exceptions=[{"on": ["A-017"], "kind": "cause_not_established", "c": "supported",
                          "why": []}],
             residue={"l": ["A-019", "A-021"], "r": ["B-011"]},
             do=[{"act": "accept", "on": ["A-017", "B-004"]},
                 {"act": "escalate", "on": ["A-019", "A-021", "B-011"]}])
    assert "uncited_claim" not in codes(out, FULL)


def test_the_empty_packet_answer_the_rfc_prescribes_validates() -> None:
    # RFC-0001 §Behaviour. This failed before the RFC and the invariant were
    # reconciled: the prescribed answer carried a request with no open entry.
    packet = P("A-001", "A-002")
    out: dict[str, object] = {
        "matches": [], "exceptions": [],
        "open": [{"on": ["A-001", "A-002"], "need": "records for the other side"}],
        "residue": {"l": ["A-001", "A-002"], "r": []},
        "do": [{"act": "request", "on": ["A-001", "A-002"]}],
    }
    assert codes(out, packet) == []
