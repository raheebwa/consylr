# SPDX-License-Identifier: MIT
"""Author the training-only pattern templates, per RFC-0003 and issue #20.

The sibling of `author_templates.py`, and deliberately a second tool rather than
a flag on the first. `templates/` is frozen with the exam; this writes
`templates-train/`, which the exam never loads. Two tools cannot be pointed at
the wrong directory by a typo the way one tool with a `--role` switch can, and
that is the same reasoning RFC-0003 gives for `build` and `seal` being separate
commands.

**A pattern declares a pool where a fixed template declares a value.** That is
what lifts a template past the three-or-fewer distinct cases its deformation can
distinguish, and it is why the first training corpus stopped at 903 against the
8,000-15,000 the RFC asks for.

**Every template must declare a different pattern, and that is a hard
constraint rather than a nicety.** Template identity is a digest over the body
with the declared id excluded, so templates sharing one set of pools are one
scenario however many ids they carry — and the audit would refuse the set as
duplicate scenarios. Each template therefore takes a distinct window into each
vocabulary, which is also what keeps the split meaningful: two templates that
draw from the same candidates are not two scenarios.

Everything emitted is synthetic. The counterparties are invented sector words,
the references follow a documented shape, and no real business, person, account
or ledger entry appears — RFC-0003 forbids it, and a corpus is published
evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.author_templates import (
    BASE_POLICY,
    CAUSE_LINES,
    FAMILIES,
)

OUT = Path(__file__).resolve().parent.parent / "templates-train"

#: Wider than the frozen set's, because a pool of one is a value. These are the
#: candidates a case draws from; the frozen exam's narrower surface is a subset
#: of this shape, which is the safe direction — a model trained on the wider
#: surface and examined on the narrower is under-claimed, never over-claimed.
PARTIES = [
    "Northwind Ltd",
    "Southgate Ltd",
    "Eastvale Trading Ltd",
    "Westbrook Services Ltd",
    "Harbourline Freight Ltd",
    "Copperfield Supply Ltd",
    "Marlowe Consulting Ltd",
    "Ashgrove Logistics Ltd",
    "Pennine Metals Ltd",
    "Quayside Packaging Ltd",
    "Ravensworth Utilities Ltd",
    "Thornbury Chemicals Ltd",
    "Ullswater Textiles Ltd",
    "Vantage Print Ltd",
    "Wexford Agriculture Ltd",
    "Bramfield Haulage Ltd",
    "Calderstone Foods Ltd",
    "Dunmore Electrical Ltd",
    "Elmsworth Joinery Ltd",
    "Fenwick Instruments Ltd",
]

#: Spread across three orders of magnitude, so a proportional cut is observable
#: at the small end and a batched total is plausible at the large.
AMOUNTS = [
    "12.60",
    "42.05",
    "63.15",
    "88.75",
    "142.30",
    "480.00",
    "755.00",
    "925.50",
    "1250.00",
    "1904.40",
    "3075.25",
    "4820.90",
    "6300.00",
    "9145.75",
    "12480.00",
    "17400.00",
    "23650.50",
    "29840.00",
    "36215.80",
    "42150.00",
]

REF_PREFIXES = ["INV", "PO", "CN", "STM", "REM"]

#: Raised and settled dates are drawn from *separate* pools, which is the
#: expressive form RFC-0003 requires where the two sides must differ: the draw is
#: keyed by the pool's contents, so one shared pool would resolve a raised date
#: and its settlement to the same day and every `timing_cutoff` would lose its
#: gap.
RAISED = [
    "2026-01-08",
    "2026-01-21",
    "2026-02-03",
    "2026-02-17",
    "2026-03-02",
    "2026-03-11",
    "2026-03-19",
    "2026-04-02",
    "2026-04-14",
    "2026-04-27",
    "2026-05-08",
    "2026-05-21",
    "2026-06-03",
    "2026-06-16",
    "2026-06-29",
    "2026-07-13",
]
SETTLED = [
    "2026-01-13",
    "2026-01-27",
    "2026-02-09",
    "2026-02-24",
    "2026-03-05",
    "2026-03-13",
    "2026-03-24",
    "2026-04-06",
    "2026-04-17",
    "2026-05-04",
    "2026-05-12",
    "2026-05-26",
    "2026-06-09",
    "2026-06-22",
    "2026-07-02",
    "2026-07-20",
]

#: How many candidates each field offers a case. Large enough that a template
#: supports many distinct draws, small enough that the windows below stay
#: distinct across templates.
POOL = {"party": 6, "amount": 7, "date": 6, "ref": 5}

#: Templates per family, and the arithmetic is different from the frozen set's.
#:
#: There, yield varied by family — `clean_match`, `batched_vs_itemised` and
#: `decoy` gave one distinct case per template where others gave three — so the
#: template counts were weighted to compensate. A pattern template yields the
#: same thirty regardless, so **family share is now simply template share** and
#: the old weighting stopped meaning what it meant.
#:
#: The first build under the old band was refused for exactly that: clearly
#: supported came out at 65.1% against a 50% ceiling, and `cause_not_established`
#: at 9.3% against its 10% floor. The quota gate caught it before a line reached
#: disk.
#:
#: **Eleven families produce a clearly-supported answer, not ten.**
#: `missing_record` is the one that is easy to miss: it abstains through its
#: `open` entry while its matches are genuinely supported, so it counts as
#: supported here and as declining in behaviour. The two are different questions.
#:
#: Below: supported 280/400 = 70.0%, the target of RFC-0002's 65-75% band.
#: Abstention is no longer a family count — the 16 `cause_not_established`
#: templates and the 40 withheld twins both carry that answer, and together they
#: are 14.0% inside a 10-15% band.
PER_FAMILY = {
    # The eleven settled families take 280 templates. At 30 cases each that is
    # 8,400 of 12,000 — the 70% RFC-0002 §The supported band asks for.
    "clean_match": 26,
    "batched_vs_itemised": 25,
    "duplicate": 25,
    "missing_record": 26,
    "name_variant": 25,
    "partial_payment": 25,
    "reference_mangled": 25,
    "reversal": 25,
    "fee_at_source": 26,
    "withholding": 26,
    "timing_cutoff": 26,
    # `cause_not_established` at 16 templates is 4% of the mix, not the 11% a
    # first pass gave it. The band it sits in is measured from the ANSWER now,
    # and the 40 withheld twins carry a `cause_not_established` answer too — so
    # the two compete for one 10-15% budget and together make 14%. The family
    # loses the mass rather than the twins, because a withheld twin is the same
    # lesson taught better: it wears a settled family's shape, so the model
    # cannot reach the answer by recognising the family.
    "cause_not_established": 16,
    # 40 templates, 1,200 cases, 10% — down from 21% of train-v2. Recorded so a
    # move in its exact match can be read against the change rather than guessed
    # at. It is the family the tuned model never once declined on.
    "ambiguous_pair": 40,
    # 24 templates, 720 cases, 6%. It was cut to 10 templates in a first pass
    # with no tuning-log line and nothing to gate it, because the unsupported
    # class had no band. It has one now.
    "decoy": 24,
}

#: Withheld twins, per RFC-0003 §Withheld causes. Each is the settled template of
#: the same index with its cause line removed and `twin_of` naming that template,
#: so the pair seeds identically and differs in exactly one policy line.
#:
#: All three cause-bearing families, deliberately. Withholding in one family only
#: would teach that *that* family is uncertain — the same shortcut with one more
#: rule in it. 40 templates is 1,200 cases, 10% of the mix, pre-registered here
#: before the corpus is built rather than measured out of it afterwards.
WITHHELD_PER_FAMILY = {"fee_at_source": 14, "withholding": 13, "timing_cutoff": 13}


def _window(source: list[str], start: int, size: int) -> list[str]:
    """A rotating window, so each template's pool differs from its neighbours'.

    Rotation rather than a random subset: a reviewer reading two templates should
    be able to see why they differ, and a diff should change only where the
    scenario does.
    """
    return [source[(start + n) % len(source)] for n in range(size)]


def count_for(family: str) -> int:
    # No default. A family that falls through would take a count nobody chose and
    # move the mix silently, which is how `decoy` lost 8.5× of its mass.
    return PER_FAMILY[family]


def template(family: str, index: int) -> dict[str, Any]:
    seed = sum(count_for(f) for f in FAMILIES[: FAMILIES.index(family)]) + index

    # Three or four correspondence units, as in the frozen set: deformations add
    # and remove records on top of this, and a Gate 1 packet holds five to ten.
    pairs = 3 + ((seed * 3 + index) % 2)

    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    for i in range(pairs):
        # Each field's window is offset by a different multiple of the seed, so
        # two templates agreeing on one vocabulary still differ on the rest.
        refs = [
            f"{REF_PREFIXES[(seed + i + n) % len(REF_PREFIXES)]}-{10000 + seed * 37 + i * 11 + n * 7:05d}"
            for n in range(POOL["ref"])
        ]
        party = _window(PARTIES, seed * 3 + i, POOL["party"])
        amount = _window(AMOUNTS, seed * 5 + i * 2, POOL["amount"])
        raised = _window(RAISED, seed * 2 + i, POOL["date"])
        settled = _window(SETTLED, seed * 2 + i, POOL["date"])
        # The same pool object on both sides for ref, party and amount — the draw
        # is keyed by the pool's contents, so identical pools resolve alike and
        # the clean pair survives instantiation.
        left.append({"ref": refs, "party": party, "date": raised, "amount": amount})
        right.append({"ref": refs, "party": party, "date": settled, "amount": amount})

    policy: list[dict[str, str]] = [{"id": "P-1", "text": BASE_POLICY}]
    body: dict[str, Any] = {
        "id": f"{family}-{index:03d}",
        "family": family,
        "left": left,
        "right": right,
    }
    if family in CAUSE_LINES:
        policy.append({"id": "P-2", "text": CAUSE_LINES[family]})
        body["cause"] = "P-2"

    body["policy"] = policy
    body["documents"] = [{"id": "D-1", "text": f"Remittance advice, batch {seed:03d}."}]
    return body


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()

    written = withheld = 0
    for family in FAMILIES:
        for index in range(count_for(family)):
            body = template(family, index)
            path = OUT / f"{body['id']}.json"
            path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written += 1

        # The twin is the settled body with one field added, written from the same
        # call rather than re-derived — a second construction could drift, and a
        # pair that differs anywhere but the flag stops being contrastive.
        for index in range(WITHHELD_PER_FAMILY.get(family, 0)):
            body = {
                **template(family, index),
                "id": f"{family}-withheld-{index:03d}",
                "withhold_cause": True,
                # Seeds from its settled twin, so the pair resolves the same
                # pools to the same values, deforms the same pair and permutes
                # the same way. Without it the id feeds `case_seed` and the two
                # differ in every field their pools vary — the policy line stops
                # being the only difference and the pair stops being a minimal
                # one, with every test still green.
                "twin_of": f"{family}-{index:03d}",
            }
            path = OUT / f"{body['id']}.json"
            path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written += 1
            withheld += 1

    print(f"{written} pattern templates in {OUT}, {withheld} of them withheld twins")


if __name__ == "__main__":
    main()
