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

from consylr.violation import Violation


class Tokeniser(Protocol):
    """Whatever the frozen model tokenises with."""

    def encode(self, text: str) -> Sequence[int]:
        """Every token the runtime will charge against the window.

        Including the ones the caller did not write: BOS, EOS and any chat
        template markers occupy the same context as the prompt does. An adapter
        that suppresses them undercounts by exactly the amount that decides the
        boundary, and the check passes a prompt the runtime will truncate.
        """
        ...


@dataclass(frozen=True)
class Budget:
    """*[competition constraint — ADTC profiler]* The window is the harness's."""

    context: int = 2048
    packet_max: int = 1200
    template_overhead: int = 0
    output_reserve: int = 600

    @property
    def prompt_max(self) -> int:
        """What the *rendered* prompt may cost.

        RFC-0003 sizes the packet and asserts on the rendered prompt, and those
        are different strings. The wrapper between them is a measured number the
        caller declares; it defaults to zero so an undeclared wrapper is
        rejected rather than silently charged against the packet allowance.
        """
        return self.packet_max + self.template_overhead

    def validate(self) -> Budget:
        """Refuse a budget no case could satisfy.

        Without this, a misconfigured budget fails every case and each message
        blames the case rather than the configuration.
        """
        if self.prompt_max + self.output_reserve > self.context:
            raise ValueError(
                f"packet_max {self.packet_max} + template_overhead {self.template_overhead} "
                f"+ output_reserve {self.output_reserve} cannot fit context {self.context}"
            )
        return self


DEFAULT = Budget()


def check_packet(
    packet_text: str,
    tokeniser: Tokeniser,
    budget: Budget = DEFAULT,
    *,
    case: str | None = None,
) -> list[Violation]:
    """The packet against its own allowance, before a template is wrapped round it.

    Separate from `check` because the two measure different strings against
    different caps, and using one for the other is a mistake that fails safe in
    neither direction. Measuring the packet against the *prompt* cap turns every
    declared token of wrapper into an extra token of packet allowance — so the
    more honestly a caller describes its template, the weaker the gate becomes.
    """
    used = len(tokeniser.encode(packet_text))
    if used > budget.packet_max:
        return [
            Violation(
                "packet_over_budget",
                f"packet is {used} tokens; the allowance is {budget.packet_max} "
                f"before the template's {budget.template_overhead} is added",
                case,
            )
        ]
    return []


def check(
    rendered_prompt: str,
    tokeniser: Tokeniser,
    budget: Budget = DEFAULT,
    *,
    case: str | None = None,
) -> list[Violation]:
    """Every way the rendered prompt breaks the budget.

    `rendered_prompt` is the exact string the runtime sends, after templating —
    not the packet before it. A packet inside the cap can exceed it once the
    instructions are wrapped around it, and that is the case this catches.
    """
    used = len(tokeniser.encode(rendered_prompt))
    violations: list[Violation] = []

    if used > budget.prompt_max:
        violations.append(
            Violation(
                "prompt_over_budget",
                f"rendered prompt is {used} tokens; the cap is {budget.prompt_max} "
                f"(packet_max {budget.packet_max} + template_overhead "
                f"{budget.template_overhead})",
                case,
            )
        )

    remaining = budget.context - used
    if remaining < 0:
        violations.append(
            Violation(
                "headroom_lost",
                f"rendered prompt is {used} tokens and overruns the "
                f"{budget.context}-token context by {-remaining}; "
                f"{budget.output_reserve} was reserved for output",
                case,
            )
        )
    elif remaining < budget.output_reserve:
        violations.append(
            Violation(
                "headroom_lost",
                f"rendered prompt is {used} tokens, leaving {remaining} of the "
                f"{budget.output_reserve} reserved for output in a "
                f"{budget.context}-token context",
                case,
            )
        )

    return violations
