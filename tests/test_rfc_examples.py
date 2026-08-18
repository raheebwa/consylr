# SPDX-License-Identifier: MIT
"""Every JSON example in RFC-0001 is executed against the validator.

A specification whose own examples do not satisfy it is worse than one with no
examples: readers copy the examples, and the training corpus is built to match
them.
"""

import json
import pathlib
import re

import pytest

from consylr.schema import validate

RFC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "rfcs" / "0001-output-schema.md"
BLOCKS = re.findall(r"```json\n(.*?)\n```", RFC.read_text(encoding="utf-8"), re.DOTALL)


def packet_for(output: object) -> dict[str, set[str]]:
    """Every identifier the output names, so only structural rules are exercised."""
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and re.fullmatch(r"[ABDP]-\d+(:L\d+(-L\d+)?)?", node):
            found.add(node)

    walk(output)
    return {
        "records": {i for i in found if i[0] in "AB"},
        "policy": {i for i in found if i[0] in "DP"},
    }


def test_the_rfc_actually_contains_examples() -> None:
    # Otherwise this file passes by finding nothing, which is not a pass.
    assert len(BLOCKS) >= 5


@pytest.mark.parametrize("index", range(len(BLOCKS)))
def test_every_rfc_example_is_valid_json_and_satisfies_the_schema(index: int) -> None:
    output = json.loads(BLOCKS[index])
    assert validate(output, packet_for(output)) == []
