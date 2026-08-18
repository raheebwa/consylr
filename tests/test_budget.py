# SPDX-License-Identifier: MIT
"""Tests for the token-budget assertion defined by RFC-0003.

This is the only place the harness's silent failure is visible. An over-budget
packet is not truncated in its output — the harness reserves generation room and
then left-truncates the *prompt*, so the model answers confidently about records
it never saw while the output stays well-formed and the parse rate looks healthy.
"""

import pytest

from consylr.budget import DEFAULT, Budget, check


class FakeTokeniser:
    """One token per character. Deterministic, offline, and inspectable.

    The real tokeniser is fetched at setup; a build that reached for it would be
    network-dependent, which RFC-0003 refuses.
    """

    def encode(self, text: str) -> list[int]:
        return [ord(c) for c in text]


TOK = FakeTokeniser()


def test_a_prompt_inside_every_limit_passes() -> None:
    assert check("x" * 100, TOK, DEFAULT) == []


def test_an_over_budget_prompt_is_rejected() -> None:
    # The planted failure. If this ever passes, the gate has become a stub.
    violations = check("x" * (DEFAULT.packet_max + 1), TOK, DEFAULT)
    assert [v.code for v in violations] == ["prompt_over_budget"]


def test_the_rejection_names_the_measurement_and_the_limit() -> None:
    v = check("x" * 1500, TOK, DEFAULT)[0]
    assert "1500" in v.detail and str(DEFAULT.packet_max) in v.detail


def test_headroom_being_eaten_is_its_own_failure() -> None:
    # Inside the packet cap, but leaves less than the reserved output room.
    budget = Budget(context=1000, packet_max=900, output_reserve=600)
    codes = [v.code for v in check("x" * 800, TOK, budget)]
    assert "headroom_lost" in codes


def test_a_prompt_that_breaks_both_limits_reports_both() -> None:
    budget = Budget(context=1000, packet_max=500, output_reserve=600)
    codes = sorted(v.code for v in check("x" * 800, TOK, budget))
    assert codes == ["headroom_lost", "prompt_over_budget"]


def test_the_budget_is_measured_on_the_rendered_prompt() -> None:
    # A packet under the cap can exceed it once templated. The caller passes the
    # rendered string; nothing here reaches back to the packet.
    packet_text = "x" * 1000
    rendered = "instructions: " + packet_text + " decide."
    assert check(packet_text, TOK, DEFAULT) == []
    assert check(rendered, TOK, DEFAULT) == []


def test_templating_can_push_a_legal_packet_over() -> None:
    budget = Budget(context=2048, packet_max=1010, output_reserve=600)
    packet_text = "x" * 1000
    rendered = "instructions: " + packet_text + " decide."
    assert check(packet_text, TOK, budget) == []
    assert [v.code for v in check(rendered, TOK, budget)] == ["prompt_over_budget"]


def test_a_tokeniser_that_undercounts_is_still_the_authority() -> None:
    # No character or word heuristic: the count comes from the tokeniser given.
    class Halving:
        def encode(self, text: str) -> list[int]:
            return [0] * (len(text) // 2)

    assert check("x" * 2000, Halving(), DEFAULT) == []


def test_the_defaults_match_the_specification() -> None:
    assert (DEFAULT.context, DEFAULT.packet_max, DEFAULT.output_reserve) == (2048, 1200, 600)


def test_a_budget_that_cannot_be_satisfied_is_refused_at_construction() -> None:
    # packet_max + output_reserve must fit the context, or every case fails and
    # the message blames the case rather than the configuration.
    with pytest.raises(ValueError, match="cannot fit"):
        Budget(context=1000, packet_max=900, output_reserve=200).validate()


# --- the wrapper is part of the prompt, and has to be declared ---------------


def test_a_packet_at_the_documented_cap_passes_once_its_wrapper_is_declared() -> None:
    # RFC-0003 gives the *packet* ~1,200 tokens and asserts on the *rendered
    # prompt*. Those are different strings, so the wrapper between them has to be
    # a number the budget carries — otherwise a generator honouring the RFC's
    # stated packet size has every case rejected.
    wrapper = "instructions: " + " decide."
    budget = Budget(template_overhead=len(wrapper)).validate()
    rendered = "instructions: " + "x" * budget.packet_max + " decide."
    assert check(rendered, TOK, budget) == []


def test_an_undeclared_wrapper_is_rejected_and_the_message_names_both_numbers() -> None:
    # Conservative by construction: overhead defaults to zero, so an undeclared
    # wrapper fails loudly rather than eating the packet allowance in silence.
    rendered = "instructions: " + "x" * DEFAULT.packet_max + " decide."
    v = check(rendered, TOK, DEFAULT)[0]
    assert v.code == "prompt_over_budget"
    assert str(DEFAULT.packet_max) in v.detail and "template_overhead" in v.detail


def test_the_wrapper_cannot_be_used_to_buy_back_output_headroom() -> None:
    # Declaring a wrapper large enough to breach the reserve is a misconfigured
    # budget, not a licence to overrun the context.
    with pytest.raises(ValueError, match="cannot fit"):
        Budget(context=2048, packet_max=1200, template_overhead=300, output_reserve=600).validate()


def test_a_prompt_that_overruns_the_context_says_so_rather_than_reporting_a_negative() -> None:
    budget = Budget(context=1000, packet_max=900, output_reserve=100).validate()
    v = next(x for x in check("x" * 1200, TOK, budget) if x.code == "headroom_lost")
    assert "overruns" in v.detail and "200" in v.detail
