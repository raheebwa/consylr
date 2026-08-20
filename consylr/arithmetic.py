# SPDX-License-Identifier: MIT
"""Deterministic verification of what an answer asserts, per #26.

`docs/decisions.md` says arithmetic is deterministic and **generation is never
the authority for a number**. Making that true needed a consumer on the
answering side: `consylr.money` existed but only the generator used it, so
nothing re-derived anything from a produced answer.

**There is no model-quoted figure to re-derive.** The answer schema carries no
numbers — `c` is one of three words, `kind` and `act` are enums, every other
field is an identifier, and the frozen prompt says `never a number`. A check
that compared quoted amounts against the packet would be a check that can never
fire, which is worse than no check because it reads as enforcement.

What the answer does carry is a **characterisation**: the model says a
difference is a fee, a duplicate, a batch. The packet's own amounts either
support that or they do not, and which is decidable without the model. So this
module verifies meaning against arithmetic rather than matching strings.

**Disagreement is reported, never corrected and never discarded.** A model that
labels a difference `fee_at_source` where the right side is larger has told the
operator something true about itself, and tidying it away destroys the signal.

Shape is `consylr.schema`'s authority. Everything here tolerates malformed input
by ignoring it: an exception on a record with no match has nothing to compare
against and is not bad arithmetic.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from consylr import money
from consylr.violation import Violation

#: Kinds that assert money came *off*: the right side must be strictly less.
DEDUCTIONS = frozenset({"fee_at_source", "withholding", "timing_cutoff", "partial_payment"})

#: A figure in prose. Requires a decimal part, so an issue number, a batch count
#: or a bare year is not mistaken for a claim about money — those are numbers,
#: not amounts, and flagging them would be a false fabrication report.
FIGURE = re.compile(r"\d[\d,]*\.\d{2}\b")


def _amounts(packet: Mapping[str, Any]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for entry in packet.get("records", []) or []:
        if not isinstance(entry, Mapping) or entry.get("id") is None:
            continue
        try:
            # Cent precision, through `money.canonical` rather than a second
            # rounding convention here. Amounts that round to the same cent are
            # the same amount for every rule below — flagging a pair that
            # differs only past the cent would report the arithmetic library's
            # own convention as a model error.
            out[str(entry["id"])] = Decimal(money.canonical(entry.get("amount")))
        except (InvalidOperation, ValueError, TypeError, ArithmeticError):
            continue
    return out


def _sum(ids: Sequence[str], amounts: Mapping[str, Decimal]) -> Decimal | None:
    known = [amounts[i] for i in ids if i in amounts]
    return sum(known, Decimal(0)) if len(known) == len(ids) and known else None


def _sides(output: Mapping[str, Any]) -> dict[str, tuple[list[str], list[str]]]:
    """For each record named in a match, the two sides of that match."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    entries = output.get("matches")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        left = [i for i in entry.get("l", []) or [] if isinstance(i, str)]
        right = [i for i in entry.get("r", []) or [] if isinstance(i, str)]
        for rid in (*left, *right):
            out[rid] = (left, right)
    return out


def _characterisations(output: Mapping[str, Any], packet: Mapping[str, Any]) -> list[Violation]:
    amounts = _amounts(packet)
    sides = _sides(output)
    found: list[Violation] = []
    entries = output.get("exceptions")
    if not isinstance(entries, list):
        return found
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        kind = entry.get("kind")
        on = [i for i in entry.get("on", []) or [] if isinstance(i, str)]
        if not on:
            continue

        if kind == "duplicate":
            # Two records called the same payment must carry the same amount.
            values = [amounts[i] for i in on if i in amounts]
            if len(values) == len(on) and len(set(values)) > 1:
                found.append(
                    Violation(
                        "arithmetic_disagreement",
                        f"duplicate on {on} but the amounts differ: "
                        f"{[money.canonical(v) for v in values]}",
                    )
                )
            continue

        left, right = sides.get(on[0], ([], []))
        if not left or not right:
            # No match names this record, so there is nothing to compare it to.
            continue
        total_left, total_right = _sum(left, amounts), _sum(right, amounts)
        if total_left is None or total_right is None:
            continue

        if kind in DEDUCTIONS and total_right >= total_left:
            found.append(
                Violation(
                    "arithmetic_disagreement",
                    f"{kind} on {on} asserts a deduction, but the right side "
                    f"{money.canonical(total_right)} is not less than the left "
                    f"{money.canonical(total_left)}",
                )
            )
        elif kind == "batched_vs_itemised" and total_left != total_right:
            found.append(
                Violation(
                    "arithmetic_disagreement",
                    f"batched_vs_itemised on {on} but the itemised side "
                    f"{money.canonical(total_right)} does not sum to the batched "
                    f"{money.canonical(total_left)}",
                )
            )
        elif kind == "reversal" and total_left + total_right != Decimal(0):
            found.append(
                Violation(
                    "arithmetic_disagreement",
                    f"reversal on {on} but {money.canonical(total_left)} and "
                    f"{money.canonical(total_right)} do not cancel",
                )
            )
    return found


def _figures(output: Mapping[str, Any], packet: Mapping[str, Any]) -> list[Violation]:
    """Figures written into `need`, the answer's only prose.

    **Normalisation, decided and stated rather than inferred:** thousands
    separators are stripped and the figure compared as an exact decimal, so
    `1,904.40` and `1904.40` are the same figure. A fabrication flag raised on a
    formatting difference would mark a correct answer wrong by our own
    convention.
    """
    known = {money.canonical(v) for v in _amounts(packet).values()}
    found: list[Violation] = []
    entries = output.get("open")
    if not isinstance(entries, list):
        return found
    for entry in entries:
        need = entry.get("need") if isinstance(entry, Mapping) else None
        if not isinstance(need, str):
            continue
        for raw in FIGURE.findall(need):
            try:
                figure = money.canonical(money.parse(raw.replace(",", "")))
            except (InvalidOperation, ValueError, TypeError, ArithmeticError):
                continue
            if figure not in known:
                found.append(
                    Violation(
                        "figure_not_in_packet",
                        f"the needed evidence names {raw!r}, which no record in the packet carries",
                    )
                )
    return found


def disagreements(output: Mapping[str, Any], packet: Mapping[str, Any]) -> list[Violation]:
    """Everything the packet's own arithmetic contradicts, reported not corrected."""
    if not isinstance(output, Mapping) or not isinstance(packet, Mapping):
        return []
    return _characterisations(output, packet) + _figures(output, packet)
