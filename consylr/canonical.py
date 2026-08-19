# SPDX-License-Identifier: MIT
"""One order for an answer, derived from what the answer says.

RFC-0001's answer is sets wearing lists. `matches` is a set of correspondences,
`do` a set of dispositions, `why` a set of citations, `residue` two sets of
leftover identifiers — none of them says anything by being second rather than
first. The JSON shape carries an order because JSON has no set, not because the
schema wanted one.

The gold carries an arbitrary one. Across the training corpus only **3.6%** of
targets list their matches in the order the packet lists the records, and across
the exam **49.5%** — a coin flip. So the order is not derivable from the packet
by any rule, and a model cannot learn it. Scoring it counted a correct answer
wrong 46 times in 204 on one checkpoint, and reported a whole family at 0% exact
match when every case in it was right.

**The key is the entry's own canonical JSON, and nothing else.** Ordering by
where a record sits in the packet would work equally well on today's numbers and
would reintroduce exactly the positional crutch the corpus was permuted to
remove — a model could then read the order off the packet instead of the
content. Content-only means two answers holding the same entries order alike
whichever way they arrived, and the packet never enters the comparison.

This reorders an answer. It never changes one: no entry is added, dropped or
edited, so a comparison through it stays as strict as it was on everything
except sequence. That is the risk worth naming — a normalisation that widens
equality would turn wrong answers into right ones, which is what
`test_reordering_does_not_make_two_different_answers_equal` is there to catch.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def ordered(value: Any) -> Any:
    """The same value with every list in canonical order, recursively."""
    if isinstance(value, Mapping):
        return {k: ordered(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted((ordered(v) for v in value), key=_key)
    return value
