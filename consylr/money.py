# SPDX-License-Identifier: MIT
"""How an amount is written, everywhere it is written.

One module because two things need the same answer and must not each have their
own. The generator writes amounts into packets; the identity model reads them to
decide whether two templates are the same scenario. When those disagreed, a
deformation wrote `str(Decimal)` into the record it touched while untouched
records kept whatever the template had — and the deformed record became the only
string-typed amount in the packet, so the answer key could be read off the JSON
types with no reconciliation at all.

Rounding is half-up because this is money. Two per cent of 12.25 is 0.2450, and
banker's rounding takes that to 0.24.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")


def parse(value: Any) -> Decimal:
    """An amount as a number, however the template happened to write it.

    `'1000.00'`, `'1000.0'`, `1000` and `1000.0` are one amount. They were four
    scenarios as far as the split was concerned, which is a difference no model
    reading the packet could see.
    """
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"{value!r} is not an amount") from e


def canonical(value: Any) -> str:
    """The one way an amount is written into a packet."""
    return str(parse(value).quantize(CENT, rounding=ROUND_HALF_UP))


def reduced_by(amount: Decimal, rate: Decimal, what: str) -> Decimal:
    """A cut that is a share of the amount, at least a cent, and observable.

    Refused rather than clamped when the amount cannot carry it: a cut that
    leaves the record unchanged makes the packet a clean match beneath an answer
    key asserting an exception on it, which the shipping validator passes and
    which scores a correct answer as wrong.
    """
    cut = max(CENT, (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP))
    if cut >= amount:
        raise ValueError(
            f"an amount of {amount} cannot carry a {what}: the cut would be {cut}, "
            "which leaves nothing to observe"
        )
    return cut
