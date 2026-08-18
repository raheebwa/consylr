# SPDX-License-Identifier: MIT
"""What every gate in this package returns when it rejects something.

One shape, shared, because the three gates are read together: a build runs the
schema, the budget and the quota checks and reports their rejections as one
list. Three structurally identical types would let that list hold values that
compare unequal for no reason a reader could see.

A rejection is always a machine-readable `code` and a `detail` that names the
measurement and the limit. RFC-0003 requires the second: a rejection that says
only that something is wrong sends the reader back to the corpus to find out
what.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
