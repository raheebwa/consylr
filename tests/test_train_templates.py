# SPDX-License-Identifier: MIT
"""Tests over the authored pattern template set, per RFC-0003 and issue #20.

These check an artefact rather than a function. `templates-train/` is committed
data, and the properties below are the ones that make it usable at all — a set
that fails any of them produces a corpus which looks correct and is not.

The frozen `templates/` set has no equivalent test here, which is worth saying
plainly rather than leaving implicit: its integrity currently rests on the corpus
writer refusing bad output rather than on anything asserting the set itself.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

from consylr.cases import build
from consylr.identity import scenario
from consylr.prompt import render
from consylr.templates import Template, check, load, shape_violations
from tests.support import FAKE_BUDGET, PerCharacter

TRAIN = Path(__file__).resolve().parent.parent / "templates-train"

#: Sampled rather than exhaustive, so the suite stays fast. Every template is
#: checked for shape and identity below; only the expensive build property is
#: sampled, and a systematic fault in the authoring tool shows up in any sample.
SAMPLE = 5
CASES = 20


def templates() -> list[Template]:
    return load(TRAIN)


def test_every_pattern_template_is_inside_the_closed_world() -> None:
    faults = [v for t in templates() for v in shape_violations(t)]

    assert faults == []


def test_the_set_passes_the_check_that_gates_a_corpus() -> None:
    loaded = templates()

    assert check(loaded, frozenset(t.family for t in loaded)) == []


def test_no_two_patterns_are_the_same_scenario() -> None:
    """Identity excludes the declared id, so templates sharing one set of pools
    are one scenario under many names — and the split would separate nothing.

    This is the constraint that forces each template to take a distinct window
    into each vocabulary rather than every template declaring the same pools.
    """
    loaded = templates()
    seen = collections.Counter(scenario(t) for t in loaded)

    assert len(seen) == len(loaded), f"{len(loaded) - len(seen)} templates are aliases"


def test_a_pattern_yields_many_distinct_cases() -> None:
    """The whole point of #20, stated as a property the set must keep.

    A fixed template yields as many cases as its deformation can distinguish —
    three for most families, one for three of them — which is why the first
    training corpus stopped at 903. If this regresses, the corpus silently stops
    growing and the writer's duplicate refusal turns it into a smaller corpus
    rather than a louder failure.
    """
    tok = PerCharacter()
    for template in templates()[:: len(templates()) // SAMPLE][:SAMPLE]:
        packets = set()
        for index in range(CASES):
            case = build(
                template,
                root_seed=7,
                case_index=index,
                role="train",
                tokeniser=tok,
                render=render,
                budget=FAKE_BUDGET,
            )
            assert case.violations == [], f"{template.id} case {index}: {case.violations}"
            packets.add(json.dumps(case.packet, sort_keys=True))

        assert len(packets) == CASES, f"{template.id} produced {len(packets)} of {CASES} distinct"
