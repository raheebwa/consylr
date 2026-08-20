# SPDX-License-Identifier: MIT
"""Tests for the command surface, per #25-#28.

The CLI is where every property this project claims either holds at run time or
turns out to have been a statement in a document. Three of them are load-bearing
and each is asserted here against a planted failure rather than a happy path:

- the prompt the operator's packet is rendered into is the frozen one, or the
  run refuses;
- a packet that will not fit the window is refused rather than silently
  left-truncated by the harness, which is the failure that produces a confident
  answer about evidence the model never saw;
- generation happens inside the offline guard, proven by planting a network call
  inside generation itself.

Generation is injected. A test that needed the real model would exercise the
model rather than the surface, and would not run anywhere the weights are absent.
"""

import json
import socket
from pathlib import Path
from typing import Any

import pytest

from consylr import prompt
from consylr.cli import CliRefused, run
from consylr.offline import NetworkAttempted

PACKET = {
    "documents": [{"id": "D-1", "text": "Remittance advice."}],
    "policy": [{"id": "P-1", "text": "Invoices settle at face value."}],
    "records": [
        {
            "amount": "10.00",
            "date": "2026-03-02",
            "id": "A-001",
            "party": "Acme Ltd",
            "ref": "PO-1",
        },
        {
            "amount": "10.00",
            "date": "2026-03-05",
            "id": "B-001",
            "party": "Acme Ltd",
            "ref": "PO-1",
        },
    ],
}

ANSWER = '{"matches":[],"residue":{"l":[],"r":[]}}'


class Tok:
    """A stand-in at roughly the real tokeniser's rate — about four characters
    to the token. The gate reads a count, so what matters is that a normal
    packet fits and an oversized one does not, at the same order of magnitude
    the frozen tokeniser works at."""

    def encode(self, text: str) -> list[int]:
        return [0] * (len(text) // 4)


def a_packet(tmp_path: Path, packet: object = None) -> Path:
    p = tmp_path / "packet.json"
    p.write_text(json.dumps(packet if packet is not None else PACKET), encoding="utf-8")
    return p


def test_it_says_what_it_parsed_before_it_generates(tmp_path: Path, capsys: Any) -> None:
    """Three seconds of silence before the first token is a long time for an
    operator holding an exception queue. What the packet held is knowable
    immediately and is worth more than shaving the latency."""
    seen: list[str] = []

    def generate(prompt: str) -> str:
        seen.append(capsys.readouterr().out)
        return ANSWER

    run(a_packet(tmp_path), generate=generate, tokeniser=Tok())
    assert "2 records" in seen[0]


def test_a_packet_that_will_not_fit_is_refused_not_trimmed(tmp_path: Path) -> None:
    """The harness reserves the generation budget and then left-truncates the
    prompt, so an over-budget packet still produces well-formed JSON about
    evidence the model was never shown. Nothing downstream can tell."""
    fat = {**PACKET, "documents": [{"id": "D-1", "text": "x" * 100_000}]}
    with pytest.raises(CliRefused) as refused:
        run(a_packet(tmp_path, fat), generate=lambda _: ANSWER, tokeniser=Tok())
    assert "budget" in str(refused.value).lower() or "token" in str(refused.value).lower()


def test_generation_runs_inside_the_offline_guard(tmp_path: Path) -> None:
    """Planted inside generation, which is the only place it matters. A guard
    that wrapped argument parsing would pass this project's own tests and let a
    model loader phone home."""

    def generate_that_dials(prompt: str) -> str:
        socket.getaddrinfo("example.invalid", 80)
        return ANSWER

    with pytest.raises(NetworkAttempted):
        run(a_packet(tmp_path), generate=generate_that_dials, tokeniser=Tok())


def test_a_packet_that_is_not_a_packet_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CliRefused):
        run(
            a_packet(tmp_path, {"records": "not a list"}),
            generate=lambda _: ANSWER,
            tokeniser=Tok(),
        )


def test_the_answer_comes_back(tmp_path: Path) -> None:
    out = run(a_packet(tmp_path), generate=lambda _: ANSWER, tokeniser=Tok())
    assert out == json.loads(ANSWER)


def test_a_fabricated_reference_is_reported_to_the_operator(tmp_path: Path, capsys: Any) -> None:
    """Reported, not swallowed and not silently corrected. The disagreement is
    the useful signal — an operator who is told the model cited `P-9` knows
    something an operator handed a tidied answer does not."""
    invented = (
        '{"matches":[{"l":["A-001"],"r":["B-001"],"c":"supported","why":["P-9"]}],'
        '"residue":{"l":[],"r":[]}}'
    )
    run(a_packet(tmp_path), generate=lambda _: invented, tokeniser=Tok())
    said = capsys.readouterr().out
    assert "P-9" in said
    # The schema's vocabulary, because the schema is the only implementation of
    # this rule now. A second one in this package disagreed with it in three
    # places and was deleted rather than repaired.
    assert "unresolved_id" in said


def test_a_clean_answer_says_nothing_about_references(tmp_path: Path, capsys: Any) -> None:
    """A tool that prints a reassurance on every run trains its operator to
    stop reading."""
    run(a_packet(tmp_path), generate=lambda _: ANSWER, tokeniser=Tok())
    assert "unresolved_id" not in capsys.readouterr().out


def test_a_template_that_is_not_the_frozen_one_is_refused(tmp_path: Path) -> None:
    """The digest was printed and never compared, while this file's header and
    the module's docstring both claimed the run would refuse. Edit the frozen
    artefact and every answer afterwards measures a system the model was never
    trained against, byte-indistinguishable from a correct one."""
    with pytest.raises(CliRefused) as refused:
        run(
            a_packet(tmp_path),
            generate=lambda _: ANSWER,
            tokeniser=Tok(),
            expect_digest="0" * 64,
        )
    assert "0000" in str(refused.value) and prompt.DIGEST[:12] in str(refused.value)


def test_the_matching_digest_passes(tmp_path: Path) -> None:
    out = run(
        a_packet(tmp_path),
        generate=lambda _: ANSWER,
        tokeniser=Tok(),
        expect_digest=prompt.DIGEST,
    )
    assert out == json.loads(ANSWER)


def test_an_answer_that_is_not_an_object_is_refused_not_a_traceback(tmp_path: Path) -> None:
    """`[]` and `[{...}]` are routine shape slips and parse as JSON. They used to
    reach the reference checker and die with AttributeError -- a raw traceback
    out of a function whose whole contract is refusing with a named reason,
    after the generation wait was already paid."""
    for said in ("[]", '[{"matches":[]}]', '"hello"', "3", "null", "true"):

        def answer(_: str, text: str = said) -> str:
            return text

        with pytest.raises(CliRefused):
            run(a_packet(tmp_path), generate=answer, tokeniser=Tok())


def test_a_structurally_invalid_answer_is_reported(tmp_path: Path, capsys: Any) -> None:
    """The schema is the authority on shape and the CLI never consulted it, so
    every defect it exists to catch reached the operator in silence -- while the
    scorer counted the same answer invalid."""
    run(a_packet(tmp_path), generate=lambda _: '{"matches":[]}', tokeniser=Tok())
    assert "residue" in capsys.readouterr().out


def test_the_model_is_loaded_inside_the_guard(tmp_path: Path) -> None:
    """The docstring justifies wrapping generation rather than setup 'because a
    model loader reaching the network at load time is exactly the case a guard
    placed anywhere else would miss' -- and then took an already-loaded model,
    putting the load outside. A lazy loader makes the stated property real."""
    from consylr.cli import lazily

    def loader() -> Any:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raise AssertionError("unreachable: the guard should have refused first")

    with pytest.raises(NetworkAttempted):
        run(a_packet(tmp_path), generate=lazily(loader), tokeniser=Tok())


def test_there_is_something_to_invoke(tmp_path: Path) -> None:
    """`python -m consylr.cli packet.json` printed nothing and exited 0. Mode 4
    of the four modes was not an invocable thing."""
    from consylr.cli import main

    assert main([]) == 2


def test_a_cause_the_arithmetic_contradicts_is_reported(tmp_path: Path, capsys: Any) -> None:
    """`docs/decisions.md`: generation is never the authority for a number. The
    model labels a difference; the packet's own amounts decide whether that
    label can be true, and the disagreement reaches the operator."""
    said = (
        '{"matches":[{"l":["A-001"],"r":["B-001"],"c":"supported","why":["A-001","B-001"]}],'
        '"exceptions":[{"on":["B-001"],"kind":"fee_at_source","c":"supported","why":["P-1"]}],'
        '"residue":{"l":[],"r":[]},"do":[{"act":"accept","on":["A-001","B-001"]}]}'
    )
    # Both records carry 10.00, so nothing was deducted and the cause cannot hold.
    run(a_packet(tmp_path), generate=lambda _: said, tokeniser=Tok())
    out = capsys.readouterr().out
    assert "arithmetic_disagreement" in out
    assert "fee_at_source" in out
