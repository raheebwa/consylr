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
]

#: Amounts spread across three orders of magnitude, so a proportional cut is
#: observable at the small end and a batched total is plausible at the large.
AMOUNTS = ["480.00", "1250.00", "17400.00", "925.50", "6300.00", "88.75", "42150.00"]

DATES = [
    ("2026-03-02", "2026-03-05"),
    ("2026-03-11", "2026-03-13"),
    ("2026-03-19", "2026-03-24"),
    ("2026-04-02", "2026-04-06"),
    ("2026-04-14", "2026-04-17"),
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

#: Five scenarios per family. Enough that a per-family metric is a number rather
#: than an anecdote, and that the grouped split has something to hold back.
PER_FAMILY = 5


def records(seed: int, pairs: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """One clean correspondence, varied by position rather than by chance.

    Deliberately not random: a reviewer reading two templates should be able to
    see why they differ, and a diff should change only where the scenario does.
    """
    left, right = [], []
    for i in range(pairs):
        n = seed * 13 + i * 7
        ref = f"INV-{4000 + n:04d}"
        party = PARTIES[(seed + i) % len(PARTIES)]
        amount = AMOUNTS[(seed * 3 + i) % len(AMOUNTS)]
        raised, settled = DATES[(seed + i) % len(DATES)]
        left.append({"ref": ref, "party": party, "date": raised, "amount": amount})
        right.append({"ref": ref, "party": party, "date": settled, "amount": amount})
    return left, right


def template(family: str, index: int) -> dict[str, object]:
    seed = FAMILIES.index(family) * PER_FAMILY + index
    # `batched_vs_itemised` folds two pairs into one, so it needs at least two;
    # the rest vary between three and five so a packet is a real reconciliation
    # rather than a single comparison.
    pairs = 2 + ((seed + index) % 4)
    left, right = records(seed, pairs)

    policy: list[dict[str, str]] = [{"id": "P-1", "text": BASE_POLICY}]
    body: dict[str, object] = {
        "id": f"{family}-{index:02d}",
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
        for index in range(PER_FAMILY):
            body = template(family, index)
            path = OUT / f"{body['id']}.json"
            path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written += 1

    total = sum(
        Decimal(r["amount"])
        for f in FAMILIES
        for i in range(PER_FAMILY)
        for r in template(f, i)["left"]
    )  # type: ignore[union-attr,index]
    print(f"{written} templates in {OUT}")
    print(f"{len(FAMILIES)} families x {PER_FAMILY}; left-side total {total}")


if __name__ == "__main__":
    main()
