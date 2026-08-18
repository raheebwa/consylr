# SPDX-License-Identifier: MIT
"""Author the gold scenario templates from a committed pattern configuration.

Templates are data files, per RFC-0003, and this is what writes them. It is a
tool rather than part of the package: the generator *interprets* templates and
must not be able to invent them, or "ground truth known by construction" would
rest on a construction nothing outside the process could inspect.

Everything it emits is synthetic. The counterparty names are invented sector
words, the references follow a documented shape, and no real business, person,
account or ledger entry appears anywhere — RFC-0003 forbids it, and a corpus is
published evidence.

Run it, review the diff, commit the templates. Re-running with the same
configuration produces byte-identical files, so a review is a review of the
scenarios rather than of a shuffle.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "templates"

#: Counterparties, invented. Two words each so a `name_variant` deformation has
#: something to abbreviate, and none of them is a real trading name.
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
]

#: Amounts spread across three orders of magnitude, so a proportional cut is
#: observable at the small end and a batched total is plausible at the large.
#: Co-prime in count with the party and date lists, so positions do not fall into
#: step and repeat a scenario under a different name.
AMOUNTS = [
    "480.00",
    "1250.00",
    "17400.00",
    "925.50",
    "6300.00",
    "88.75",
    "42150.00",
    "3075.25",
    "12.60",
    "755.00",
    "29840.00",
    "1904.40",
    "63.15",
]

#: Reference shapes, documented rather than incidental: a reconciliation sees
#: invoices, purchase orders, credit notes and statements, and a mangled
#: reference has to be mangled from something with structure.
REF_PREFIXES = ["INV", "PO", "CN", "STM", "REM"]

DATES = [
    ("2026-03-02", "2026-03-05"),
    ("2026-03-11", "2026-03-13"),
    ("2026-03-19", "2026-03-24"),
    ("2026-04-02", "2026-04-06"),
    ("2026-04-14", "2026-04-17"),
    ("2026-04-27", "2026-05-04"),
    ("2026-05-08", "2026-05-12"),
    ("2026-05-21", "2026-05-26"),
    ("2026-06-03", "2026-06-09"),
    ("2026-06-16", "2026-06-22"),
    ("2026-06-29", "2026-07-02"),
]

#: One cause-bearing line per family that asserts a cause, worded so the lint in
#: `cases._prove_cause` can see what it is about. The generator refuses a
#: template whose policy cannot support its family, which is why these are not
#: interchangeable prose.
CAUSE_LINES = {
    "fee_at_source": "A settlement fee is deducted at source on every remittance.",
    "withholding": "Withholding tax is deducted before remittance at the statutory rate.",
    "timing_cutoff": "The period closes on the last business day; a later value date falls after.",
}

BASE_POLICY = "Invoices settle at face value unless a deduction is stated in this schedule."

FAMILIES = [
    "clean_match",
    "fee_at_source",
    "withholding",
    "timing_cutoff",
    "reference_mangled",
    "name_variant",
    "partial_payment",
    "batched_vs_itemised",
    "duplicate",
    "reversal",
    "missing_record",
    "cause_not_established",
    "decoy",
    "ambiguous_pair",
]

#: Scenarios per family, deliberately unequal.
#:
#: RFC-0002 puts clearly-supported cases at 40-50% of the training mix and
#: `cause_not_established` at 10-15%. Eleven of the fourteen families produce a
#: clearly-supported answer, so an equal split gives 80% supported — nearly
#: double the band. A corpus that meets the quota needs a template set weighted
#: toward the cases the model finds hard, which is the quota's whole point: a
#: model trained on a mix that is four-fifths clean learns that most things
#: reconcile.
#:
#: `decoy` gets the most because its deformation ignores the case index, so each
#: of its templates yields exactly one distinct case where others yield three.
#: `clean_match`, `batched_vs_itemised` and `decoy` yield exactly one distinct
#: case per template, because their deformations do not draw on the generator.
#: They therefore need enough templates to supply the exam AND the training
#: floor separately — twenty gave six training cases against a floor of twenty,
#: and the quota gate refused the corpus.
PER_FAMILY = {
    "clean_match": 50,
    "batched_vs_itemised": 50,
    "cause_not_established": 40,
    "ambiguous_pair": 100,
    "decoy": 120,
}
DEFAULT_PER_FAMILY = 20


def records(seed: int, pairs: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """One clean correspondence, varied by position rather than by chance.

    Deliberately not random: a reviewer reading two templates should be able to
    see why they differ, and a diff should change only where the scenario does.
    """
    left, right = [], []
    for i in range(pairs):
        n = seed * 37 + i * 11
        ref = f"{REF_PREFIXES[(seed + i) % len(REF_PREFIXES)]}-{4000 + n:05d}"
        party = PARTIES[(seed * 5 + i) % len(PARTIES)]
        amount = AMOUNTS[(seed * 7 + i * 3) % len(AMOUNTS)]
        raised, settled = DATES[(seed * 3 + i) % len(DATES)]
        left.append({"ref": ref, "party": party, "date": raised, "amount": amount})
        right.append({"ref": ref, "party": party, "date": settled, "amount": amount})
    return left, right


def count_for(family: str) -> int:
    return PER_FAMILY.get(family, DEFAULT_PER_FAMILY)


def template(family: str, index: int) -> dict[str, object]:
    seed = sum(count_for(f) for f in FAMILIES[: FAMILIES.index(family)]) + index
    # Three or four correspondence units, which is six or eight records before
    # the deformation runs. A Gate 1 packet holds five to ten
    # *[competition constraint — ADTC profiler]*, and deformations move the count:
    # a decoy or a reversal adds two, a duplicate or a split adds one, a missing
    # record or a batched total removes one. Three or four keeps every family
    # inside the range afterwards; five put `decoy` and `reversal` at twelve.
    pairs = 3 + ((seed * 3 + index) % 2)
    left, right = records(seed, pairs)

    policy: list[dict[str, str]] = [{"id": "P-1", "text": BASE_POLICY}]
    body: dict[str, object] = {
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

    written = 0
    for family in FAMILIES:
        for index in range(count_for(family)):
            body = template(family, index)
            path = OUT / f"{body['id']}.json"
            path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written += 1

    total = sum(
        Decimal(r["amount"])
        for f in FAMILIES
        for i in range(count_for(f))
        for r in template(f, i)["left"]
    )  # type: ignore[union-attr,index]
    print(f"{written} templates in {OUT}")
    print(f"{len(FAMILIES)} families, weighted for the quota; left-side total {total}")


if __name__ == "__main__":
    main()
