# SPDX-License-Identifier: MIT
"""Tests for scoring a model's answers, per RFC-0001's metric table and #16.

The metrics are stated in RFC-0001 and this is what computes them. Two of them
need care rather than arithmetic:

* **Abstention has two directions**, and only one of them looks like a failure.
  Correct abstention on unsupported cases is the capability; false abstention on
  clearly-supported cases is the cost of it, and a model that refuses everything
  scores perfectly on the first.
* **`missing_record` abstains through its `open` entry**, not its certainty. Its
  matches are supported, so reading certainty alone counts it as a confident
  answer and the refusal rate misses a whole family.
"""

import json
from typing import Any

from consylr.score import Answer, positional, record, score

PACKET = {
    "records": [{"id": "A-001"}, {"id": "B-001"}],
    "policy": [{"id": "P-1"}],
    "documents": [],
}
CLEAN = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["A-001", "B-001"]}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "accept", "on": ["A-001", "B-001"]}],
}


def answer(text: str, expected: dict[str, Any], family: str = "clean_match") -> Answer:
    return Answer(packet=PACKET, expected=expected, produced=text, family=family)


def test_unparseable_output_is_counted_and_not_scored() -> None:
    report = score([answer("I think these match!", CLEAN)])
    assert report.parse_rate == 0.0
    assert report.exact_match == 0.0


def test_an_exact_answer_scores_everywhere() -> None:
    report = score([answer(json.dumps(CLEAN), CLEAN)])
    assert report.parse_rate == 1.0
    assert report.schema_valid == 1.0
    assert report.exact_match == 1.0
    assert report.correspondence_f1 == 1.0


def test_a_wrong_correspondence_costs_f1_but_not_the_parse_rate() -> None:
    wrong = {**CLEAN, "matches": [{"l": ["A-001"], "r": [], "c": "supported", "why": ["A-001"]}]}
    report = score([answer(json.dumps(wrong), CLEAN)])
    assert report.parse_rate == 1.0
    assert report.exact_match == 0.0
    assert report.correspondence_f1 < 1.0


def test_a_cited_identifier_that_does_not_resolve_is_counted() -> None:
    invented = {
        **CLEAN,
        "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["Z-999"]}],
    }
    report = score([answer(json.dumps(invented), CLEAN)])
    assert report.citation_resolution < 1.0


def test_abstaining_on_an_unsupported_case_is_correct_abstention() -> None:
    expected = {
        "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "unsupported", "why": ["A-001"]}],
        "residue": {"l": ["A-001"], "r": ["B-001"]},
        "do": [{"act": "hold", "on": ["A-001", "B-001"]}],
    }
    report = score([answer(json.dumps(expected), expected, family="decoy")])
    assert report.correct_abstention == 1.0
    assert report.false_abstention == 0.0


def test_abstaining_on_a_clearly_supported_case_is_false_abstention() -> None:
    hedged = {
        "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "ambiguous", "why": ["A-001"]}],
        "residue": {"l": [], "r": []},
        "do": [{"act": "hold", "on": ["A-001", "B-001"]}],
    }
    report = score([answer(json.dumps(hedged), CLEAN)])
    assert report.false_abstention == 1.0


def test_missing_record_abstains_through_its_open_entry() -> None:
    """The #16 measurement-design point, made executable.

    Its matches are supported, so certainty alone reads it as a confident
    answer — and a refusal rate computed that way misses the family entirely.
    """
    expected = {
        "matches": [],
        "open": [{"on": ["A-001"], "need": "the counterpart"}],
        "residue": {"l": ["A-001"], "r": []},
        "do": [{"act": "request", "on": ["A-001"]}],
    }
    report = score([answer(json.dumps(expected), expected, family="missing_record")])
    assert report.correct_abstention == 1.0


def test_per_family_accuracy_is_reported_separately() -> None:
    report = score(
        [
            answer(json.dumps(CLEAN), CLEAN, family="clean_match"),
            answer("nonsense", CLEAN, family="decoy"),
        ]
    )
    assert report.per_family["clean_match"].exact_match == 1.0
    assert report.per_family["decoy"].exact_match == 0.0


def test_a_run_record_keeps_what_the_model_actually_said() -> None:
    """RFC-0001 open question 3, answered by evidence rather than by preference.

    The first scaffolded reference run produced a correspondence F1 of exactly
    0.500 on nine of fourteen families. The arithmetic was sound, so the number
    could only be explained by reading what the model emitted — and the run had
    scored the answers and discarded them. Nothing about the metric was wrong;
    it was simply undiagnosable.

    Retention is therefore always, not on failure. An implausible number on a
    **parseable** answer is exactly the case failure-only retention misses.
    """
    answers = [answer("not json at all", CLEAN), answer(json.dumps(CLEAN), CLEAN)]

    kept = record(answers, score(answers), exam="sealed-v4", model="m", mode="profiler")

    assert [c["produced"] for c in kept["cases"]] == ["not json at all", json.dumps(CLEAN)]
    assert [c["family"] for c in kept["cases"]] == ["clean_match", "clean_match"]


def test_a_run_record_still_carries_the_metrics_it_always_did() -> None:
    """The retention is an addition. A record that dropped a metric to make room
    would trade one undiagnosable number for a missing one."""
    answers = [answer(json.dumps(CLEAN), CLEAN)]

    kept = record(answers, score(answers), exam="sealed-v4", model="m", mode="profiler")

    for key in ("parse_rate", "correspondence_f1", "correct_abstention", "false_abstention"):
        assert key in kept, f"{key} is no longer recorded"
    assert kept["mode"] == "profiler" and kept["packets"] == 1


def test_a_run_record_names_the_artefact_that_produced_it() -> None:
    """Provenance the file must carry, or a number cannot be attributed.

    The tuned model is the base plus an adapter, so a result file that names
    only the base names something that did not produce it. The existing baseline
    file on disk already demonstrates the cost of this: it lacks a `mode` field,
    was written by code held in memory, and cannot be told apart from a
    scaffolded run without re-running it.
    """
    answers = [answer(json.dumps(CLEAN), CLEAN)]

    kept = record(
        answers,
        score(answers),
        exam="sealed-v4",
        model="base",
        mode="profiler",
        adapter="adapters-v1",
        exam_digest="abc",
    )

    assert kept["adapter"] == "adapters-v1"
    assert kept["exam_digest"] == "abc"


def test_the_null_answer_pairs_by_position_and_reads_nothing() -> None:
    """The control every reported F1 must sit beside.

    A model that pairs record n on one side with record n on the other, claims
    every pair supported, and cites only the two records, scores 0.839
    correspondence F1 on sealed-v4 — because the generator emits records in
    correspondence order. A tuned model at 0.904 is therefore 0.065 above
    reading nothing, not 0.904 above it.

    It is built from the packet's ids alone. If it ever consults `expected`,
    it stops being a control and becomes a cheat.
    """
    produced = json.loads(positional(PACKET))

    assert produced["matches"] == [
        {"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["A-001", "B-001"]}
    ]
    assert produced["residue"] == {"l": [], "r": []}


def test_the_null_answer_leaves_an_unpaired_record_as_residue() -> None:
    """Sides of unequal length are the case the null model cannot pair away.

    Declaring them matched anyway would make the control score better than
    reading nothing actually can, which would understate the real gain.
    """
    packet = {"records": [{"id": "A-001"}, {"id": "A-002"}, {"id": "B-001"}], "policy": []}

    produced = json.loads(positional(packet))

    assert len(produced["matches"]) == 1
    assert produced["residue"] == {"l": ["A-002"], "r": []}


# --- canonical answer order -------------------------------------------------
#
# Exact match compares the whole answer, and dict equality reads lists in order.
# The gold's own order is arbitrary — only 3.6% of the training corpus lists its
# matches in packet order and 49.5% of the exam — so nothing in a packet lets a
# model derive it. Scoring it counted a correct answer wrong 46 times in 204 on
# one checkpoint, and reported a family at 0% when every case in it was right.
#
# The order is dropped from the comparison, not from the answer: `matches` is a
# set of correspondences by RFC-0001, and `_correspondences` already scores it as
# one. The risk in doing so is the opposite error — a comparison so forgiving
# that two different answers become equal — which is what the second test is for.

PAIR_PACKET = {
    "records": [{"id": "A-001"}, {"id": "A-002"}, {"id": "B-001"}, {"id": "B-002"}],
    "policy": [{"id": "P-1"}],
    "documents": [],
}
TWO: dict[str, Any] = {
    "matches": [
        {"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["A-001", "B-001"]},
        {"l": ["A-002"], "r": ["B-002"], "c": "supported", "why": ["A-002", "B-002"]},
    ],
    "residue": {"l": [], "r": []},
    "do": [{"act": "accept", "on": ["A-001", "A-002", "B-001", "B-002"]}],
}


def pair_answer(text: str, expected: dict[str, Any]) -> Answer:
    return Answer(packet=PAIR_PACKET, expected=expected, produced=text, family="clean_match")


def test_a_reordered_answer_is_the_same_answer() -> None:
    shuffled = {**TWO, "matches": list(reversed(TWO["matches"]))}
    report = score([pair_answer(json.dumps(shuffled), TWO)])
    assert report.exact_match == 1.0


def test_reordering_does_not_make_two_different_answers_equal() -> None:
    """The guard on the fix above: one element differs, order or not."""
    altered = {
        **TWO,
        "matches": [
            TWO["matches"][1],
            {**TWO["matches"][0], "r": ["B-002"]},
        ],
    }
    report = score([pair_answer(json.dumps(altered), TWO)])
    # Anchored on the parse: `exact_match == 0.0` is also what an answer that
    # never parsed scores, so without this the guard would stay green for a
    # typo in the fixture or a refactor that made `ordered` raise first —
    # proving nothing about strictness.
    assert report.parse_rate == 1.0
    assert report.exact_match == 0.0


def test_the_canonical_order_is_derived_from_content_alone() -> None:
    """Pinned so the sort key cannot drift.

    The key is the entry's own canonical JSON, so two answers holding the same
    entries order alike whatever order they arrived in.

    It is emphatically NOT a packet-independent order: ids are assigned after the
    shuffle, so sorting by id sorts by position. That is harmless here, where
    both sides are sorted the same way, and it is why `consylr.emit` must not use
    this on a training target — see the module docstring.
    """
    from consylr.canonical import ordered

    entries = [{"l": ["A-002"], "c": "supported"}, {"l": ["A-001"], "c": "supported"}]
    assert ordered(entries) == [
        {"c": "supported", "l": ["A-001"]},
        {"c": "supported", "l": ["A-002"]},
    ]
    assert ordered(entries) == ordered(list(reversed(entries)))
    assert ordered({"do": [{"act": "hold"}, {"act": "accept"}]}) == {
        "do": [{"act": "accept"}, {"act": "hold"}]
    }


def test_a_withheld_twin_declines_correctly_whatever_its_family() -> None:
    """The scorer classified abstention by family, so a twin whose cause was
    withheld from a `fee_at_source` packet counted its correct decline as a
    FALSE abstention. `consylr.quota` was fixed to read `unestablished` from the
    case; this is the same defect in the other instrument, and the two now agree
    by construction rather than by coincidence.

    It reached nothing reported — sealed-v4 carries no withheld twins — but the
    published test-prompt pair is exactly such a twin, and our own scorer marked
    the model's correct answer wrong."""
    declining = (
        '{"matches":[],"exceptions":[{"on":["B-1"],"kind":"cause_not_established",'
        '"c":"unsupported","why":[]}],"open":[{"on":["B-1"],"need":"the document"}],'
        '"residue":{"l":[],"r":[]}}'
    )
    withheld = Answer(
        packet={"records": [{"id": "B-1"}]},
        expected=json.loads(declining),
        produced=declining,
        family="fee_at_source",
        unestablished=True,
    )
    report = score([withheld])
    assert report.correct_abstention == 1.0
    assert report.false_abstention == 0.0


def test_a_settled_case_of_the_same_family_still_counts_a_false_decline() -> None:
    """The guard's mirror: `unestablished=False` must not become a licence to
    decline. Kept beside it so neither can be loosened alone."""
    declining = (
        '{"matches":[],"exceptions":[{"on":["B-1"],"kind":"cause_not_established",'
        '"c":"unsupported","why":[]}],"open":[{"on":["B-1"],"need":"the document"}],'
        '"residue":{"l":[],"r":[]}}'
    )
    settled = Answer(
        packet={"records": [{"id": "B-1"}]},
        expected={"matches": [], "residue": {"l": [], "r": []}},
        produced=declining,
        family="fee_at_source",
        unestablished=False,
    )
    assert score([settled]).false_abstention == 1.0
