# SPDX-License-Identifier: MIT
"""What every gate in this package returns when it rejects something.

One shape, shared, because the three gates are read together: a build runs the
schema, the budget and the quota checks and reports their rejections as one
list. Three structurally identical types would let that list hold values that
compare unequal for no reason a reader could see.

A rejection is always a machine-readable `code` and a `detail` that names the
measurement and the limit. RFC-0003 requires both, and also that a rejection
name the case it came from where there is one — in a corpus-wide audit a list of
counts with no case attached sends the reader back through the corpus to find
which packet produced it. `case` is optional because the corpus-level gates
reject the corpus, not any case within it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    case: str | None = None
