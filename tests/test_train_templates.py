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

from consylr.cases import Case, build
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


# --- the mix the set is authored to, checked before a corpus is built --------


def test_the_authored_mix_lands_inside_the_rfc_band() -> None:
    """Pre-registered rather than discovered afterwards.

    Every case a template yields carries that template's certainty, so the mix a
    corpus will have is a property of the template set and can be asserted here —
    before a build spends anything. The last corpus met a band that has since
    moved; this fails the moment the counts drift out of the one RFC-0002 now
    states, instead of a writer refusing 12,000 cases at the end of a build.
    """
    from consylr.quota import Plan

    templates = load(TRAIN)
    band = Plan(families=frozenset()).supported_share
    supported = sum(1 for t in templates if _certainty_of(t) == "supported")
    share = supported / len(templates)
    assert band[0] <= share <= band[1], f"{share:.1%} supported against {band}"


def test_a_withheld_twin_exists_for_every_cause_bearing_family() -> None:
    """The decoupling is worthless if it covers one family.

    Certainty stops being a function of family only for the families that carry
    both forms. A set with withheld cases in `fee_at_source` alone teaches that
    `fee_at_source` is uncertain, which is the same shortcut with one more rule.
    """
    withheld = collections.Counter(
        str(t.family) for t in load(TRAIN) if t.body.get("withhold_cause")
    )
    assert set(withheld) == {"fee_at_source", "withholding", "timing_cutoff"}
    assert all(n >= 10 for n in withheld.values()), withheld


def test_every_withheld_template_has_a_settled_twin() -> None:
    """Contrastive by construction, at the level of the set rather than the case.

    A withheld template whose body differs from its twin in more than the flag
    lets the model tell them apart without reading the policy — the shortcut
    rebuilt one coordinate over, which is the thing this whole change is about.
    """
    by_id = {t.id: t for t in load(TRAIN)}
    withheld = [t for t in by_id.values() if t.body.get("withhold_cause")]
    assert withheld
    for t in withheld:
        twin = by_id.get(str(t.id).replace("-withheld-", "-"))
        assert twin is not None, f"{t.id} has no settled twin"
        assert {
            k: v for k, v in t.body.items() if k not in ("id", "withhold_cause", "twin_of")
        } == {k: v for k, v in twin.body.items() if k != "id"}
        assert t.body["twin_of"] == twin.id


def _certainty_of(template: Template) -> str:
    """The certainty this template actually emits, from a build.

    Not from a family table. A table would hardcode the family-to-certainty map
    this whole change exists to break, and would keep passing while the real
    corpus failed `quota.check` at the end of a 12,000-case build — the exact
    failure the test above says it prevents.
    """
    return str(
        build(
            template,
            root_seed=7,
            case_index=0,
            role="train",
            tokeniser=PerCharacter(),
            render=render,
            budget=FAKE_BUDGET,
        ).meta["certainty"]
    )


def test_a_withheld_twin_resolves_to_the_same_case() -> None:
    """The property RFC-0003 claims, checked on the artefact rather than a fixture.

    The unit test for this builds both cases from one body under one id, so the
    seeds coincide and the records match by construction — it asserts a property
    the authored set does not have to possess. Here the two real templates are
    built, ids and all, which is the only place the claim can actually fail.

    It did fail: `case_seed` mixes in the template id, and the id seeds the pool
    draw, the deformation's choice of pair and the permutation. The twins shared
    pools and resolved to entirely different amounts, dates and counterparties,
    so the policy line was one difference among many rather than the only one.
    """
    by_id = {t.id: t for t in load(TRAIN)}
    pairs = [
        (by_id[str(t.id).replace("-withheld-", "-")], t)
        for t in by_id.values()
        if t.body.get("withhold_cause")
    ]
    assert pairs

    for settled, withheld in pairs[:SAMPLE]:
        a = _case(settled)
        b = _case(withheld)
        assert a.packet["records"] == b.packet["records"], f"{settled.id} vs {withheld.id}"
        assert a.packet["documents"] == b.packet["documents"]
        dropped = [p for p in a.packet["policy"] if p not in b.packet["policy"]]
        assert len(dropped) == 1, dropped


def test_the_twin_check_can_actually_fail() -> None:
    """The planted failure for the test above, because it once passed on a defect.

    The unit-level version built both halves from one body under one id, so the
    seeds coincided and the records matched by construction — green on a set whose
    twins differed in every field their pools vary. Here a twin is deliberately
    stripped of `twin_of`, which is exactly the state the authored set was in, and
    the property must fail.
    """
    by_id = {t.id: t for t in load(TRAIN)}
    withheld = next(t for t in by_id.values() if t.body.get("withhold_cause"))
    settled = by_id[str(withheld.id).replace("-withheld-", "-")]
    diverged = Template.from_mapping({k: v for k, v in withheld.body.items() if k != "twin_of"})

    assert _case(settled).packet["records"] == _case(withheld).packet["records"]
    assert _case(settled).packet["records"] != _case(diverged).packet["records"]


def test_a_twin_pair_is_not_a_contradiction() -> None:
    """Two packets, two answers, and the writer must not read that as a conflict.

    `corpus.write` refuses a corpus holding one packet under two different
    answers. A twin pair is the near-miss: same records, same documents, opposite
    answers — legitimate precisely because the packets differ by the policy line.
    Asserted rather than assumed, because the distance between "differs by one
    line" and "identical" is one bug in the emitter.
    """
    from consylr.corpus import check as corpus_check

    by_id = {t.id: t for t in load(TRAIN)}
    withheld = next(t for t in by_id.values() if t.body.get("withhold_cause"))
    settled = by_id[str(withheld.id).replace("-withheld-", "-")]
    pair = [settled, withheld]
    codes = {v.code for v in corpus_check([_case(t) for t in pair], templates=pair)}
    assert "contradictory_ground_truth" not in codes
    assert "duplicate_packet" not in codes


def _case(template: Template) -> Case:
    return build(
        template,
        root_seed=7,
        case_index=0,
        role="train",
        tokeniser=PerCharacter(),
        render=render,
        budget=FAKE_BUDGET,
        permute=True,
    )
