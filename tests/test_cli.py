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
    assert "unresolved_reference" in said


def test_a_clean_answer_says_nothing_about_references(tmp_path: Path, capsys: Any) -> None:
    """A tool that prints a reassurance on every run trains its operator to
    stop reading."""
    run(a_packet(tmp_path), generate=lambda _: ANSWER, tokeniser=Tok())
    assert "unresolved_reference" not in capsys.readouterr().out
