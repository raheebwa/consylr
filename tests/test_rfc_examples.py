# SPDX-License-Identifier: MIT
"""Every JSON example in RFC-0001 is executed against the validator.

A specification whose own examples do not satisfy it is worse than one with no
examples: readers copy the examples, and the corpus is built to match them.

Each example is paired with an **explicitly declared packet**. Deriving the
packet from the output instead would make `unresolved_id` unreachable by
construction and the residue rule trivially satisfiable — the test would be
unable to fail on the two rules it most needs to check.

The RFC is read inside a fixture, not at import. At import, a missing or renamed
RFC aborts collection for the whole suite — including tests that have nothing to
do with it — and the pre-commit hook then blocks the very commit that would fix
the path.
"""

import json
import pathlib
import re

import pytest

from consylr.schema import validate

RFC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "rfcs" / "0001-output-schema.md"

#: One packet per example, in document order. Written out rather than inferred.
PACKETS: list[dict[str, object]] = [
    {"records": {"A-017", "B-004", "A-019", "B-011"}, "policy": {"P-02"}, "documents": set()},
    {"records": {"A-017", "B-004"}, "policy": set(), "documents": set()},
    {"records": {"A-021", "B-008", "B-009"}, "policy": set(), "documents": set()},
    {"records": {"A-019", "B-012"}, "policy": {"P-02"}, "documents": set()},
    {"records": {"A-031", "B-020", "A-032", "B-021"}, "policy": set(), "documents": set()},
    {"records": {"A-044", "B-030"}, "policy": {"P-05"}, "documents": set()},
]


@pytest.fixture(scope="module")
def blocks() -> list[str]:
    text = RFC.read_text(encoding="utf-8")
    return re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)


def test_the_rfc_contains_the_examples_this_file_declares_packets_for(blocks: list[str]) -> None:
    # Otherwise this file passes by checking fewer examples than exist, or by
    # checking none at all.
    assert len(blocks) == len(PACKETS)


def test_every_rfc_example_is_valid_json_and_satisfies_the_schema(blocks: list[str]) -> None:
    failures: list[str] = []
    for index, (block, packet) in enumerate(zip(blocks, PACKETS)):
        output = json.loads(block)
        for violation in validate(output, packet):
            failures.append(f"example {index}: {violation.code}: {violation.detail}")
    assert failures == []


def test_an_example_that_omits_a_packet_record_is_caught(blocks: list[str]) -> None:
    # Guards the guard: if the packet were derived from the output, adding a
    # record here would change nothing and this test could never fail.
    output = json.loads(blocks[1])
    packet = {"records": {"A-017", "B-004", "A-777"}, "policy": set(), "documents": set()}
    assert [v.code for v in validate(output, packet)] == ["residue_wrong"]
