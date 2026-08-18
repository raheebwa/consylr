# SPDX-License-Identifier: MIT
"""The prompt template, which is a frozen artefact, per RFC-0003.

The profiler applies **no chat template of its own**, so this file is the whole
of the model's interface. Four surfaces rendering three ways would be the
four-mode trap self-inflicted, and so nothing renders a prompt any other way: the
CLI, the training-data emission, the sealed set and the profiler run all come
through here.

It is pinned like the tokeniser is pinned, and for the same reason — the budget
is asserted on the *rendered* prompt, so a corpus cannot be generated without it
and every corpus binds to a specific one. `DIGEST` goes into the corpus
configuration, and a corpus whose recorded digest does not match this file fails
its audit. **Changing the wording invalidates the corpus**: budgets re-assert
over every case and the sealed set is re-validated or rebuilt. The model was
trained against one interface, and a changed interface is a different interface
whatever the diff looks like.

**The packet comes first and the instructions last.** The harness left-truncates
the prompt, so the earliest tokens are the ones at risk, and this puts the
instructions closest to generation where adherence is best. That is a deliberate
trade: instructions-first would fail *loudly* if a prompt ever exceeded the
window — the model would lose the schema and emit something unparseable, which
the parse rate shows — whereas this fails *quietly*, as well-formed JSON about
evidence that was truncated away. It is only acceptable because the budget
assertion runs at inference as well as at build, so the truncation case does not
arise. A caller that skips the check turns this ordering from an optimisation
into a liability.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from consylr.budget import Budget

_PATH = Path(__file__).parent / "artefacts" / "prompt-v1.txt"

TEMPLATE = _PATH.read_text()

#: SHA-256 of the artefact, recorded in every corpus's configuration.
DIGEST = hashlib.sha256(_PATH.read_bytes()).hexdigest()

#: What the wrapper costs, measured once with the frozen model's tokeniser
#: (ADR-0003) rather than estimated. A character or word heuristic is wrong by
#: exactly the amount that matters at the boundary — and this number was measured
#: three times during drafting, twice going *up* when the text was shortened.
#: `test_the_pinned_overhead_is_what_the_frozen_tokeniser_counts` re-measures it
#: wherever the tokeniser is present.
OVERHEAD_TOKENS = 308

#: Derived rather than declared. RFC-0003 gives the packet "~1,200 tokens", but
#: the constraint that actually binds is the window: the context, less what is
#: reserved for output, less what the wrapper costs. Asserting the round number
#: instead would mean either shaving the model's only interface to reach it, or
#: a budget whose three numbers cannot fit the context at all.
BUDGET = Budget(
    context=2048,
    packet_max=2048 - 600 - OVERHEAD_TOKENS,
    template_overhead=OVERHEAD_TOKENS,
    output_reserve=600,
).validate()


def render(packet: Mapping[str, Any], *, serialise: Any = None) -> str:
    """The exact string the runtime sends, for a packet.

    `serialise` exists so the caller that builds a case and the caller that runs
    one cannot disagree about how a packet becomes text — the disagreement that
    put a packet count under a prompt name once already.
    """
    if serialise is None:
        import json

        def serialise(value: Mapping[str, Any]) -> str:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))

    return TEMPLATE.replace("{packet}", serialise(packet))
