# SPDX-License-Identifier: MIT
"""Tests for the per-family certainty census, per the decoupling work on #65.

The instrument that found the defect in the first place. Counting how often a
tuned model declined, by family, gave nine families at exactly 100% and five at
exactly 0% with nothing in between — the signature of a model reading family
identity rather than evidence. Aggregate abstention rates showed none of that;
they averaged the two groups into a number that looked like a threshold problem.

So the census reports the distribution, and reports **strictly-between** as its
own figure: a family that is neither always nor never is a family whose answer
depends on something in the packet.
"""

from __future__ import annotations

import json
from typing import Any

from tools.certainty_census import census

SUPPORTED: dict[str, Any] = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "supported", "why": ["A-001"]}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "accept", "on": ["A-001", "B-001"]}],
}
DECLINED: dict[str, Any] = {
    "matches": [{"l": ["A-001"], "r": ["B-001"], "c": "ambiguous", "why": ["A-001"]}],
    "exceptions": [
        {"on": ["B-001"], "kind": "cause_not_established", "c": "unsupported", "why": []}
    ],
    "open": [{"on": ["B-001"], "need": "the policy line"}],
    "residue": {"l": [], "r": []},
    "do": [{"act": "request", "on": ["B-001"]}],
}


def rows(**counts: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, n in counts.items():
        family, kind = key.rsplit("__", 1)
        body = SUPPORTED if kind == "answers" else DECLINED
        out.extend((family, json.dumps(body)) for _ in range(n))
    return out


def test_a_family_that_always_declines_is_reported_as_all_or_nothing() -> None:
    c = census(rows(decoy__declines=14, clean_match__answers=14))
    assert c.per_family["decoy"].decline_rate == 1.0
    assert c.per_family["clean_match"].decline_rate == 0.0
    assert c.graded == 0, "neither family varies within itself"


def test_a_family_that_varies_within_itself_is_reported_as_graded() -> None:
    """The signal the intervention is meant to produce.

    A decline rate strictly between 0 and 1 means the answer moved with something
    other than the family, which is the whole claim. It is counted separately
    because it is the finding, not a rounding of the rate.
    """
    c = census(rows(fee_at_source__answers=9, fee_at_source__declines=5))
    assert 0.0 < c.per_family["fee_at_source"].decline_rate < 1.0
    assert c.graded == 1


def test_the_certainty_shares_are_reported_per_family() -> None:
    c = census(rows(fee_at_source__answers=6, fee_at_source__declines=4))
    t = c.per_family["fee_at_source"]
    assert t.shares["supported"] == 0.6
    assert t.shares["ambiguous"] == 0.4


def test_an_unparseable_answer_is_counted_and_not_scored() -> None:
    c = census([("clean_match", "not json"), ("clean_match", json.dumps(SUPPORTED))])
    assert c.per_family["clean_match"].unparsed == 1
    assert c.per_family["clean_match"].decline_rate == 0.0
