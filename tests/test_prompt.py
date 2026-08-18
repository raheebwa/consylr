# SPDX-License-Identifier: MIT
"""Tests for the prompt template, per RFC-0003.

The profiler applies no chat template of its own, so this artefact is the whole
of the model's interface. It is pinned like the tokeniser is pinned, and every
corpus binds to a specific one.
"""

import hashlib
import os
from pathlib import Path

import pytest

from consylr.prompt import BUDGET, DIGEST, OVERHEAD_TOKENS, TEMPLATE, render
from tests.support import template_body

PACKET = {"records": [{"id": "A-001", "ref": "INV-1"}], "policy": [], "documents": []}


def test_the_digest_is_of_the_artefact_on_disk() -> None:
    # It goes into every corpus's configuration, and a corpus whose recorded
    # digest does not match this file fails its audit. A digest computed over
    # anything but the file would make that check a formality.
    path = Path(__file__).parent.parent / "consylr" / "artefacts" / "prompt-v1.txt"
    assert DIGEST == hashlib.sha256(path.read_bytes()).hexdigest()


def test_changing_the_template_changes_the_digest() -> None:
    assert (
        hashlib.sha256(TEMPLATE.encode()).hexdigest()
        != hashlib.sha256((TEMPLATE + " ").encode()).hexdigest()
    )


def test_the_packet_comes_first_and_the_instructions_last() -> None:
    """The harness left-truncates, so the earliest tokens are the ones at risk.

    Instructions last also puts them closest to generation, where adherence is
    best. The trade is named in the module docstring: this fails quietly rather
    than loudly if a prompt ever exceeds the window, and is only acceptable
    because the budget is asserted at inference as well as at build.
    """
    rendered = render(PACKET)
    assert rendered.index("A-001") < rendered.index("Reply with one JSON object")
    assert rendered.rstrip().endswith("does not support.")


def test_the_template_carries_every_enumeration_the_schema_will_check() -> None:
    # A model cannot produce a value it was never shown, and the validator
    # rejects anything outside these sets — so an omission here is a case the
    # model must fail.
    from consylr.schema import ACTS, CERTAINTIES, KINDS

    for value in (*KINDS, *CERTAINTIES, *ACTS):
        assert value in TEMPLATE, f"{value} is enforced but never shown"


def test_the_template_names_every_section_of_the_output() -> None:
    for section in ("matches", "exceptions", "open", "residue", "do"):
        assert f'"{section}"' in TEMPLATE


def test_the_budget_fits_the_window_it_claims() -> None:
    assert BUDGET.prompt_max == BUDGET.context - BUDGET.output_reserve
    assert BUDGET.packet_max + BUDGET.template_overhead + BUDGET.output_reserve == BUDGET.context


def test_a_packet_at_its_allowance_renders_inside_the_window() -> None:
    # The whole point of deriving the packet allowance rather than declaring it:
    # the three numbers have to fit the context, and a round number that does not
    # is a budget that fails every case and blames the case.
    class PerCharacter:
        def encode(self, text: str) -> list[int]:
            return [0] * len(text)

    from consylr.budget import check

    assert check("x" * BUDGET.prompt_max, PerCharacter(), BUDGET) == []
    # Both, and necessarily: the prompt cap *is* the context less the reserve, so
    # one token past it is one token into the room left to answer in.
    assert sorted(v.code for v in check("x" * (BUDGET.prompt_max + 1), PerCharacter(), BUDGET)) == [
        "headroom_lost",
        "prompt_over_budget",
    ]


def test_a_real_packet_leaves_room_to_answer_in() -> None:
    # Ten records is the top of RFC-0003's Gate 1 range.
    body = template_body(pairs=5)
    packet = {
        "records": [{"id": f"A-{i:03d}", **r} for i, r in enumerate(body["left"], 1)]
        + [{"id": f"B-{i:03d}", **r} for i, r in enumerate(body["right"], 1)],
        "policy": body["policy"],
        "documents": body["documents"],
    }
    rendered = render(packet)
    # A character count is not a token count, and is used here only as a
    # sanity bound: four characters per token is generous for JSON.
    assert len(rendered) / 4 < BUDGET.prompt_max


TOKENISER = os.environ.get("CONSYLR_TOKENISER")


@pytest.mark.skipif(not TOKENISER, reason="frozen tokeniser not configured")
def test_the_pinned_overhead_is_what_the_frozen_tokeniser_counts() -> None:
    """The one number here that a heuristic cannot supply.

    It was measured three times while the template was drafted, and twice went
    *up* when the text was shortened — which is exactly why RFC-0003 refuses a
    character or word estimate at the boundary. Skipped where the tokeniser is
    absent rather than approximated, because an approximate check here would be
    worse than none: it would report agreement it had not established.
    """
    from tokenizers import Tokenizer  # type: ignore[import-not-found]

    tok = Tokenizer.from_file(TOKENISER)
    measured = len(tok.encode(TEMPLATE.replace("{packet}", "")).ids)
    assert measured == OVERHEAD_TOKENS, (
        f"the template costs {measured} tokens, not the pinned {OVERHEAD_TOKENS}; "
        "the budget and every corpus built against it are stale"
    )
