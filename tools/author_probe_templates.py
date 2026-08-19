# SPDX-License-Identifier: MIT
"""Author the twin-probe templates: minimal pairs on scenarios never trained on.

**This is a diagnostic probe, not an exam.** It shares its mechanism with the
training corpus — the same `withhold_cause` twins — so it measures whether the
behaviour generalises to new instances of a construction the model has seen, not
whether the model has a general capability. That caveat travels with every number
it produces, and it is written into the corpus provenance as well as here.

It exists because the sealed exam cannot answer the question. sealed-v4 carries
one certainty per family by construction — the coupling this work exists to break
— so its gold never varies within a family, and no aggregate score over it can
show that the model reads the policy rather than the family. A pair can.

**The metric is pair-level.** For each pair the model sees two packets whose
records, amounts, dates and documents are byte-identical and whose policy differs
by one line. Right on both halves is a flip; right on one is a failure with a
direction. A model that changes its answer when a single policy line is withheld
from an otherwise identical packet is reading evidence, and nothing else explains
it.

Fresh draws: the pool windows are taken from indices far beyond any the training
set uses, so no probe template is a training scenario. That is asserted rather
than intended — the builder passes every training packet and every exam packet as
held-out, so the writer refuses a probe case that either has already asked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.author_train_templates import template

OUT = Path(__file__).resolve().parent.parent / "templates-probe"

#: The three families whose answer rests on a policy line, which are the only
#: ones that can have that line withheld. Twenty-five pairs each: enough that a
#: per-family flip rate is a number rather than an anecdote, few enough that the
#: probe stays a probe.
FAMILIES = ("fee_at_source", "withholding", "timing_cutoff")
PAIRS_PER_FAMILY = 25

#: Far beyond the training set's highest index, so every pool window differs.
#: `template()` derives its windows from an index-dependent seed, so a disjoint
#: index range is a disjoint set of scenarios — checked by the builder rather
#: than trusted.
INDEX_BASE = 500


def bodies() -> list[dict[str, Any]]:
    """Every probe template, settled and withheld, in pairs."""
    out: list[dict[str, Any]] = []
    for family in FAMILIES:
        for n in range(PAIRS_PER_FAMILY):
            index = INDEX_BASE + n
            settled = template(family, index)
            out.append(settled)
            out.append(
                {
                    **settled,
                    "id": f"{family}-probe-{n:03d}",
                    "withhold_cause": True,
                    "twin_of": str(settled["id"]),
                }
            )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()

    for body in bodies():
        path = OUT / f"{body['id']}.json"
        path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pairs = len(FAMILIES) * PAIRS_PER_FAMILY
    print(f"{pairs * 2} probe templates in {OUT} — {pairs} minimal pairs")


if __name__ == "__main__":
    main()
