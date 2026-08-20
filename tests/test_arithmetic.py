# SPDX-License-Identifier: MIT
"""Tests for deterministic verification of what an answer asserts, per #26.

`docs/decisions.md` says arithmetic is deterministic and **generation is never
the authority for a number**. The answer schema carries no numbers — `c` is one
of three words, `kind` and `act` are enums, and every other field is an
identifier — so there is no model-quoted figure to re-derive. What there is, is
a *characterisation*: the model says a difference is a fee, a duplicate, a
batch. The packet's own amounts either support that or they do not, and which is
decidable without the model.

A disagreement is **reported, not corrected and not discarded**. A model that
labels a difference `fee_at_source` where the right side is larger has told us
something, and tidying it away destroys the signal.
"""

from typing import Any

from consylr.arithmetic import disagreements


def packet(*records: dict[str, Any]) -> dict[str, Any]:
    return {
        "documents": [{"id": "D-1", "text": "Remittance advice."}],
        "policy": [{"id": "P-1", "text": "A settlement fee is deducted at source."}],
        "records": list(records),
    }


def rec(rid: str, amount: str) -> dict[str, Any]:
    return {"id": rid, "amount": amount, "date": "2026-03-02", "party": "Acme", "ref": "PO-1"}


def answer(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"matches": [], "exceptions": [], "residue": {"l": [], "r": []}}
    base.update(over)
    return base


def test_a_deduction_that_is_not_a_deduction_is_reported() -> None:
    """`fee_at_source` asserts money was taken off. If the right side is larger,
    the cause is fabricated and the packet says so without being asked."""
    p = packet(rec("A-001", "100.00"), rec("B-001", "120.00"))
    a = answer(
        matches=[{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["P-1"]}],
        exceptions=[{"on": ["B-001"], "kind": "fee_at_source", "c": "supported", "why": ["P-1"]}],
    )
    found = disagreements(a, p)
    assert [v.code for v in found] == ["arithmetic_disagreement"]
    assert "fee_at_source" in found[0].detail and "120.00" in found[0].detail


def test_a_real_deduction_passes() -> None:
    p = packet(rec("A-001", "100.00"), rec("B-001", "98.00"))
    a = answer(
        matches=[{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["P-1"]}],
        exceptions=[{"on": ["B-001"], "kind": "fee_at_source", "c": "supported", "why": ["P-1"]}],
    )
    assert disagreements(a, p) == []


def test_a_duplicate_whose_amounts_differ_is_reported() -> None:
    """Two records called the same payment must carry the same amount."""
    p = packet(rec("B-001", "100.00"), rec("B-002", "100.01"))
    a = answer(
        exceptions=[
            {"on": ["B-001", "B-002"], "kind": "duplicate", "c": "supported", "why": ["P-1"]}
        ]
    )
    assert [v.code for v in disagreements(a, p)] == ["arithmetic_disagreement"]


def test_a_batch_that_does_not_sum_is_reported() -> None:
    """Recomputed in exact decimal, not floating point: 0.1 + 0.2 must not
    become a disagreement, and a real 0.01 discrepancy must not be lost."""
    p = packet(rec("A-001", "0.30"), rec("B-001", "0.10"), rec("B-002", "0.20"))
    fine = answer(
        matches=[{"l": ["A-001"], "r": ["B-001", "B-002"], "c": "supported", "why": ["P-1"]}],
        exceptions=[
            {"on": ["A-001"], "kind": "batched_vs_itemised", "c": "supported", "why": ["P-1"]}
        ],
    )
    assert disagreements(fine, p) == []

    q = packet(rec("A-001", "0.31"), rec("B-001", "0.10"), rec("B-002", "0.20"))
    assert [v.code for v in disagreements(fine, q)] == ["arithmetic_disagreement"]


def test_a_figure_in_need_that_the_packet_does_not_contain_is_reported() -> None:
    """`need` is the one place the model writes prose, and an invented figure
    there reaches an operator reading it as evidence."""
    p = packet(rec("A-001", "100.00"))
    a = answer(open=[{"on": ["A-001"], "need": "the advice covering 1904.40"}])
    assert [v.code for v in disagreements(a, p)] == ["figure_not_in_packet"]


def test_a_figure_in_need_that_the_packet_does_contain_passes() -> None:
    p = packet(rec("A-001", "1904.40"))
    a = answer(open=[{"on": ["A-001"], "need": "the advice covering 1904.40"}])
    assert disagreements(a, p) == []


def test_an_unmatched_or_malformed_answer_is_not_a_disagreement() -> None:
    """Shape is the schema's authority. An exception on a record with no match
    has nothing to compare against and must not be reported as bad arithmetic."""
    p = packet(rec("B-001", "100.00"))
    a = answer(
        exceptions=[{"on": ["B-001"], "kind": "fee_at_source", "c": "supported", "why": ["P-1"]}]
    )
    assert disagreements(a, p) == []
    assert disagreements({"exceptions": "not a list"}, p) == []


def test_a_reversal_at_a_rounding_boundary_does_not_fire() -> None:
    """False-positive guard. Amounts that round to the same cent under HALF_UP
    are equal for this purpose; flagging them would report the arithmetic
    library's own convention as a model error."""
    p = packet(rec("A-001", "100.005"), rec("B-001", "-100.01"))
    a = answer(
        matches=[{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["P-1"]}],
        exceptions=[{"on": ["B-001"], "kind": "reversal", "c": "supported", "why": ["P-1"]}],
    )
    assert disagreements(a, p) == []


def test_an_equal_pair_is_not_a_deduction() -> None:
    """False-positive guard's mirror: equal amounts genuinely are not a fee, so
    this one must fire. Kept beside the guard so neither can be loosened alone."""
    p = packet(rec("A-001", "100.00"), rec("B-001", "100.00"))
    a = answer(
        matches=[{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["P-1"]}],
        exceptions=[{"on": ["B-001"], "kind": "fee_at_source", "c": "supported", "why": ["P-1"]}],
    )
    assert [v.code for v in disagreements(a, p)] == ["arithmetic_disagreement"]


def test_a_thousands_separator_is_not_a_fabrication() -> None:
    """False-positive guard. `1,904.40` and `1904.40` are the same figure; a
    fabrication flag on a formatting difference would be the scorer bug's
    cousin — a correct answer marked wrong by our own convention."""
    p = packet(rec("A-001", "1904.40"))
    a = answer(open=[{"on": ["A-001"], "need": "the advice covering 1,904.40"}])
    assert disagreements(a, p) == []


def test_a_bare_year_in_need_is_not_a_figure() -> None:
    """False-positive guard. Prose contains numbers that are not claims about
    money — an issue number, a batch count, a year. Only figures shaped like an
    amount are checked, and the rule is stated rather than inferred."""
    p = packet(rec("A-001", "100.00"))
    a = answer(open=[{"on": ["A-001"], "need": "the 2026 remittance advice"}])
    assert disagreements(a, p) == []
