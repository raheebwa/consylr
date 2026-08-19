# SPDX-License-Identifier: MIT
"""Tests for the twin-probe report, per the decoupling work on #65.

The probe answers one question the sealed exam cannot: does the model change its
answer when a single policy line is withheld from an otherwise byte-identical
packet? Aggregate scores move for many reasons. A flip does not.

So the metric is pair-level, and the two ways of failing are counted apart. A
model that declines everything scores perfectly on the withheld halves and is
useless; a model that asserts everything scores perfectly on the settled halves
and is the model we already have. Only both together mean anything.
"""

from __future__ import annotations

import json
from typing import Any

from tools.probe_report import Pair, report

SETTLED = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["A-001", "B-001"]}],
    "exceptions": [{"on": ["B-001"], "kind": "fee_at_source", "c": "supported", "why": ["P-2"]}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "accept", "on": ["A-001", "B-001"]}],
}
WITHHELD = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "ambiguous", "why": ["A-001", "B-001"]}],
    "exceptions": [
        {"on": ["B-001"], "kind": "cause_not_established", "c": "unsupported", "why": []}
    ],
    "open": [{"on": ["B-001"], "need": "the policy line"}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "request", "on": ["B-001"]}],
}


def pair(settled: Any, withheld: Any, family: str = "fee_at_source") -> Pair:
    return Pair(family=family, settled=json.dumps(settled), withheld=json.dumps(withheld))


def test_a_pair_answered_both_ways_is_a_flip() -> None:
    r = report([pair(SETTLED, WITHHELD)])
    assert r.flips == 1
    assert r.flip_rate == 1.0
    assert r.asserted_on_withheld == 0 and r.declined_on_settled == 0


def test_a_model_that_declines_everything_scores_no_flips() -> None:
    """The failure the exam's correct-abstention number cannot see on its own."""
    r = report([pair(WITHHELD, WITHHELD)])
    assert r.flips == 0
    assert r.declined_on_settled == 1
    assert r.asserted_on_withheld == 0


def test_a_model_that_asserts_everything_scores_no_flips() -> None:
    """The model we already have: certainty read off the family, not the policy."""
    r = report([pair(SETTLED, SETTLED)])
    assert r.flips == 0
    assert r.asserted_on_withheld == 1
    assert r.declined_on_settled == 0


def test_an_unparseable_half_is_counted_and_not_scored() -> None:
    """Same rule the exam scorer holds: two different failures, two remedies."""
    r = report([Pair(family="fee_at_source", settled="not json", withheld=json.dumps(WITHHELD))])
    assert r.flips == 0
    assert r.unparsed == 1
    assert r.declined_on_settled == 0, "a half that never parsed did not decline"


def test_the_directions_are_reported_per_family() -> None:
    r = report(
        [
            pair(SETTLED, WITHHELD, family="fee_at_source"),
            pair(SETTLED, SETTLED, family="withholding"),
        ]
    )
    assert r.per_family["fee_at_source"].flips == 1
    assert r.per_family["withholding"].asserted_on_withheld == 1
    assert r.flip_rate == 0.5
