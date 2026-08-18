# SPDX-License-Identifier: MIT
"""What makes two templates the same scenario, per RFC-0003.

**Identity is what `build()` emits, not what the template says.** If two
templates produce the same packet and the same answer key, they are one
scenario, whatever their sources hold — and a model examined on one has been
trained on the other.

It is taken over the whole case — the packet and the expected output, every
field of both. An earlier version dropped the counterparty and the policy prose to be
invariant under paraphrase, and paid for it in false merges: two templates whose
packets differed materially were reported as differing "only in what never
reaches a packet", which a diff of those packets disproved. RFC-0003 keeps
paraphrase off by default and never paraphrases the sealed set, so the
invariance was defending against a transformation this project does not apply.
If it is ever switched on, a paraphrased corpus is a preserved derived artefact
with its provenance recorded, not two independently authored templates that must
collide.

Strings are still normalised, which is a different thing and was conflated with
the first for a round. A zero-width space in a reference renders identically to
a human and is invisible in a diff, so without normalisation a corpus can be
poisoned with no visible edit; dropping a counterparty merged packets that
genuinely differed. The first is worth doing and the second was not.

That distinction is the whole module, and it took three attempts to reach.
Identity was first taken over the template body, then over a projection of the
fields the builder reads. Both approximated the principle one level short,
because a deformation *deletes and overwrites* what it takes: `missing_record`
removes a right-hand record, `timing_cutoff` overwrites the date with a
constant, `reference_mangled` truncates the reference, `batched_vs_itemised`
folds one record into another and drops it. Every one of those is invisible in
the packet and was load-bearing in the fingerprint, so two templates emitting
byte-identical cases took opposite sides of the split with the audit silent.

Digesting the emitted case closes the class by construction rather than by
enumerating what each deformation happens to touch — a list that grows whenever
a family is added, and that is wrong the first time someone forgets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

from consylr.cases import build
from consylr.templates import Template, _text
from consylr.violation import Violation

#: Reserved, and never a corpus seed. Identity has to be stable across corpora:
#: if it moved with the root seed, a template would change identity between
#: builds and every leak check would be relative to whichever corpus happened to
#: have been built.
PROBE_SEED = 0

#: One probe catches the leaks this module exists for, and its own failure mode
#: is a *silent* merge of two distinct scenarios that happen to coincide at that
#: index. Three is collision insurance against exactly that, not ceremony.
PROBE_INDICES = (0, 1, 2)

#: The id is replaced before probing, because `case_seed` mixes it in — so two
#: copies of one scenario under different ids would otherwise draw differently
#: and emit different cases, which is the aliasing this has to catch.
PROBE_ID = "probe"

PROBE_ROLE = "train"

#: Keyed on the content digest, because identical content emits identical cases.
#: Holds the emitted cases rather than only their digest, so the corpus-level
#: contradiction check below costs no further builds.
#: Without it `split.check` recomputed this inside a nested loop — N squared
#: calls, each running three builds, which at RFC-0003's three to five hundred
#: templates is a quarter of a million calls and minutes per audit, on the path
#: every corpus runs.
_SEEN: dict[str, list[tuple[str, str]]] = {}


class _NoTokens:
    """A tokeniser for probing only.

    `build` requires one, and the probe has no opinion about budgets: it wants
    the packet and the answer. Counting nothing keeps the budget silent without
    letting the probe pretend to have checked it.
    """

    def encode(self, text: str) -> Sequence[int]:
        return ()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalised(value: Any) -> Any:
    """The case with differences no reader could perceive removed.

    Normalisation is not paraphrase-invariance, and conflating the two cost a
    round: dropping the counterparty and the policy prose made materially
    different packets collide, whereas normalising a zero-width space or an NFD
    accent removes a difference that renders identically to a human *and* is
    invisible in a diff. The first is a false merge; the second is a corpus
    someone could poison with no visible edit.

    So every field stays and every string is canonicalised.
    """
    if isinstance(value, dict):
        return {k: _normalised(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalised(v) for v in value]
    if isinstance(value, str):
        return _text(value)
    return value


def scenario(template: Template) -> str:
    """The digest of what this template emits, across the probe indices.

    Raises whatever `build` raises. A template that cannot be built has no
    scenario, and inventing one would let it take a role in a partition it can
    never contribute a case to.
    """
    return hashlib.sha256(" ".join(p + e for p, e in emitted(template)).encode()).hexdigest()


def emitted(template: Template) -> list[tuple[str, str]]:
    """What this template emits at each probe index: (packet, answer) digests.

    Kept apart so the contradiction check below can compare packets and answers
    separately — a packet two templates share is only a defect when the answers
    they attach to it differ.
    """
    cached = _SEEN.get(template.fingerprint)
    if cached is not None:
        return cached

    probe = Template.from_mapping({**template.body, "id": PROBE_ID})
    cases = []
    for index in PROBE_INDICES:
        case = build(
            probe,
            root_seed=PROBE_SEED,
            case_index=index,
            role=PROBE_ROLE,
            tokeniser=_NoTokens(),
            render=_canonical,
        )
        cases.append(
            (
                _canonical(_normalised(case.packet)),
                _canonical(_normalised(case.expected)),
            )
        )
    _SEEN[template.fingerprint] = cases
    return cases


def check(templates: Iterable[Template]) -> list[Violation]:
    """Every way a template set holds one scenario more than once.

    Separate from `templates.check`, which asks whether each template is
    well-formed on its own. This asks what the set of them emits, and needs the
    builder to answer — so it lives here rather than inverting that dependency.
    """
    items = list(templates)
    violations: list[Violation] = []

    # One packet may carry one answer. Two templates emitting the same packet
    # under different answers are, between them, teaching the model that one
    # input has two correct outputs — and grading it on a distinction the packet
    # does not carry. This needs no opinion about what any policy line says,
    # which is why it is the gate and the word list is only authoring lint: a
    # vocabulary can always be satisfied by prose that means something else.
    answers: dict[str, dict[str, list[str]]] = {}

    by_scenario: dict[str, list[Template]] = {}
    for t in items:
        try:
            for packet, answer in emitted(t):
                answers.setdefault(packet, {}).setdefault(answer, []).append(t.id)
            by_scenario.setdefault(scenario(t), []).append(t)
        except ValueError as e:
            violations.append(
                Violation(
                    "unbuildable_template",
                    f"{t.id or '<no id>'} emits no case, so it has no scenario: {e}",
                    t.id or None,
                )
            )

    for by_answer in answers.values():
        if len(by_answer) > 1:
            named = sorted({i for ids in by_answer.values() for i in ids})
            violations.append(
                Violation(
                    "contradictory_ground_truth",
                    f"{', '.join(repr(i) for i in named)} emit one packet under "
                    f"{len(by_answer)} different answers; a packet that cannot distinguish them "
                    "grades the model on something it was never shown",
                )
            )

    for group in sorted(by_scenario.values(), key=lambda g: sorted(t.id for t in g)):
        ids = sorted({t.id for t in group})
        if len(ids) > 1:
            identical = len({t.fingerprint for t in group}) == 1
            violations.append(
                Violation(
                    "duplicate_scenario",
                    f"{', '.join(repr(i) for i in ids)} emit the same case"
                    + (
                        "; they are one file under two ids"
                        if identical
                        else ", though their templates differ - whatever they disagree about "
                        "never reaches a packet"
                    ),
                )
            )

    return violations
