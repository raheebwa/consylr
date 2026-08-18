# SPDX-License-Identifier: MIT
"""Tests for how an amount is written, per RFC-0003.

One module answers this because two things depend on it and must not each have
their own answer: the generator writes amounts into packets, and the identity
model reads them to decide whether two templates are the same scenario. When
those disagreed, the deformed record was the only string-typed amount in the
packet and the answer key could be read off the JSON types.
"""

from decimal import Decimal

import pytest

from consylr import money


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("1000.00", "1000.00"),
        ("1000.0", "1000.00"),
        ("1000", "1000.00"),
        (1000, "1000.00"),
        (1000.0, "1000.00"),
        (Decimal(1000), "1000.00"),
    ],
)
def test_one_amount_written_six_ways_is_one_amount(written: object, canonical: str) -> None:
    assert money.canonical(written) == canonical


@pytest.mark.parametrize(
    ("written", "canonical"),
    [("1.005", "1.01"), ("2.675", "2.68"), ("0.125", "0.13"), ("1.015", "1.02")],
)
def test_a_half_cent_rounds_up_because_this_is_money(written: str, canonical: str) -> None:
    # Banker's rounding sends half of these down, and Python's default is
    # banker's. The difference is a cent per case and a systematic bias across a
    # corpus, in the field the whole task reconciles.
    assert money.canonical(written) == canonical


def test_something_that_is_not_an_amount_is_refused() -> None:
    with pytest.raises(ValueError, match="not an amount"):
        money.canonical("about a thousand")


@pytest.mark.parametrize(
    ("amount", "cut"), [("1000.00", "20.00"), ("12.25", "0.25"), ("1.00", "0.02"), ("0.25", "0.01")]
)
def test_a_cut_is_a_share_of_the_amount_and_never_below_a_cent(amount: str, cut: str) -> None:
    assert money.reduced_by(money.parse(amount), Decimal("0.02"), "fee") == money.parse(cut)


@pytest.mark.parametrize("amount", ["0.01", "0.00"])
def test_an_amount_that_cannot_carry_a_cut_is_refused_rather_than_clamped(amount: str) -> None:
    # Clamping produces a packet that is a clean match beneath an answer key
    # asserting an exception on it: ground truth factually wrong, passed by the
    # validator, and a correct answer scored wrong.
    with pytest.raises(ValueError, match="nothing to observe"):
        money.reduced_by(money.parse(amount), Decimal("0.02"), "fee")
