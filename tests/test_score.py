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

from consylr.score import Answer, record, score

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
