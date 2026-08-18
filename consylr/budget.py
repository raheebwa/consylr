# SPDX-License-Identifier: MIT
"""The token-budget assertion, per RFC-0003.

This is the only place the harness's silent failure is visible, so it rejects
rather than warns.

The harness does not truncate output when the window is exceeded. It reserves
the generation budget first and then **left-truncates the prompt**, so an
over-budget packet still produces well-formed JSON and a healthy parse rate
while the model has lost the beginning of its input — the earliest records, and
any instructions above them. It then answers confidently about evidence it was
never shown, and nothing downstream can tell.

Counting is done by a tokeniser the caller supplies. A character or word
heuristic is wrong by exactly the amount that matters at the boundary, and the
real tokeniser is fetched at setup rather than reached for at build time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class Tokeniser(Protocol):
    """Whatever the frozen model tokenises with."""

    def encode(self, text: str) -> Sequence[int]: ...


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str


@dataclass(frozen=True)
class Budget:
    """*[competition constraint — ADTC profiler]* The window is the harness's."""

    context: int = 2048
    packet_max: int = 1200
    output_reserve: int = 600

    def validate(self) -> Budget:
        """Refuse a budget no case could satisfy.

        Without this, a misconfigured budget fails every case and each message
        blames the case rather than the configuration.
        """
        if self.packet_max + self.output_reserve > self.context:
            raise ValueError(
                f"packet_max {self.packet_max} + output_reserve {self.output_reserve} "
                f"cannot fit context {self.context}"
            )
        return self


DEFAULT = Budget()


def check(rendered_prompt: str, tokeniser: Tokeniser, budget: Budget = DEFAULT) -> list[Violation]:
    """Every way the rendered prompt breaks the budget.

    `rendered_prompt` is the exact string the runtime sends, after templating —
    not the packet before it. A packet inside the cap can exceed it once the
    instructions are wrapped around it, and that is the case this catches.
    """
    used = len(tokeniser.encode(rendered_prompt))
    violations: list[Violation] = []

    if used > budget.packet_max:
        violations.append(
            Violation(
                "packet_over_budget",
                f"rendered prompt is {used} tokens; the cap is {budget.packet_max}",
            )
        )

    remaining = budget.context - used
    if remaining < budget.output_reserve:
        violations.append(
            Violation(
                "headroom_lost",
                f"rendered prompt is {used} tokens, leaving {remaining} of the "
                f"{budget.output_reserve} reserved for output in a {budget.context}-token context",
            )
        )

    return violations
