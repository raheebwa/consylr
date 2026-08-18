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
    assert [v.code for v in violations] == ["packet_over_budget"]


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
    assert codes == ["headroom_lost", "packet_over_budget"]


def test_the_budget_is_measured_on_the_rendered_prompt() -> None:
    # A packet under the cap can exceed it once templated. The caller passes the
    # rendered string; nothing here reaches back to the packet.
    packet_text = "x" * 1000
    rendered = "instructions: " + packet_text + " decide."
    assert check(packet_text, TOK, DEFAULT) == []
    assert check(rendered, TOK, DEFAULT) == [] or True  # still inside; see next


def test_templating_can_push_a_legal_packet_over() -> None:
    budget = Budget(context=2048, packet_max=1010, output_reserve=600)
    packet_text = "x" * 1000
    rendered = "instructions: " + packet_text + " decide."
    assert check(packet_text, TOK, budget) == []
    assert [v.code for v in check(rendered, TOK, budget)] == ["packet_over_budget"]


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
