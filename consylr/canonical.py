# SPDX-License-Identifier: MIT
"""One order for an answer, for **comparing** answers and nothing else.

RFC-0001's answer is sets wearing lists. `matches` is a set of correspondences,
`why` a set of citations, `residue` two sets of leftover identifiers — none of
them says anything by being second rather than first. The JSON shape carries an
order because JSON has no set.

The gold carries an arbitrary one. Across the training corpus only 3.6% of
targets list their matches in the order the packet lists the records, and across
the exam 49.5% — a coin flip, so no model can derive it. Scoring it counted a
correct answer wrong 46 times in 204 on one checkpoint and reported a whole
family at 0% exact match with every case in it right.

**Do not order a training target with this.** It is safe for comparison because
both sides are sorted alike, and unsafe for emission for a reason the first
version of this module got exactly backwards. Record ids are assigned *after*
the shuffle (`cases._records`), so an id *is* a packet position — sorting an
entry by its own JSON therefore sorts by packet position wherever certainty does
not split the list first. Measured on train-v2: matches in packet order rise
from 4.0% to 26.2% overall, and to **100% on twelve of the fourteen families**.
That regularity is the positional crutch permutation exists to destroy, and
`score.positional` scores 0.809 against a corpus that has it. The emitter
therefore writes the corpus order untouched, and `consylr.emit` says so at the
line that does it.

`do` is ordered here too, which RFC-0001 Open Question 2 leaves open: it is a
set today and becomes a sequence if a disposition ever depends on another. This
matches the schema as it stands rather than settling the question — and the day
it is settled the other way, this module has to grow a schema-aware exception
rather than keep quietly generalising. The frozen prompt's one-shot example is
the standing reminder: it demonstrates `do` as request-then-accept, which is not
the order this produces.

This reorders an answer. It never changes one: no entry is added, dropped or
edited, so a comparison through it stays as strict as it was on everything
except sequence. That is the risk worth naming — a normalisation that widens
equality would turn wrong answers into right ones, which is a worse failure than
the one being fixed, and it is what
`test_reordering_does_not_make_two_different_answers_equal` is there to catch.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _key(value: Any) -> str:
    # No `default=`: a value with no canonical JSON form must raise rather than
    # be stringified into a plausible sort key, the same rule `consylr.templates`
    # states for the digests it takes.
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def ordered(value: Any) -> Any:
    """The same value with every list in canonical order, recursively."""
    if isinstance(value, Mapping):
        return {k: ordered(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted((ordered(v) for v in value), key=_key)
    return value
