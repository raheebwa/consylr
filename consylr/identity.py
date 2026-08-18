# SPDX-License-Identifier: MIT
"""What makes two templates the same scenario, per RFC-0003.

**Identity is what `build()` emits, not what the template says.** If two
templates produce the same packet and the same answer key, they are one
scenario, whatever their sources hold — and a model examined on one has been
trained on the other.

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
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from consylr import money
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


def _record(record: Mapping[str, Any]) -> list[str]:
    """One emitted record, as the model can distinguish it.

    The counterparty is dropped, because RFC-0003 lets a paraphrase rewrite it.
    The identifier is dropped because it is positional: it says where a record
    sits, not which record it is. What is left is normalised, so a form the
    reader of a rendered packet cannot perceive is not a second scenario.
    """
    amount = record.get("amount")
    return [
        _text(record.get("ref", "")),
        _text(record.get("date", "")),
        money.canonical(amount) if amount is not None else "",
    ]


def _projection(packet: Mapping[str, Any], family: str) -> dict[str, Any]:
    """The emitted packet, as a scenario rather than as bytes.

    Sorted per side: assigning identifiers by position means permuting both
    sides relabels every record without changing the problem, and a model
    trained on one labelling has seen the other.
    """
    records = packet.get("records", [])
    return {
        "family": _text(family),
        "left": sorted(_record(r) for r in records if str(r.get("id", "")).startswith("A-")),
        "right": sorted(_record(r) for r in records if str(r.get("id", "")).startswith("B-")),
        # Which lines are cited is structural; their prose is not.
        "policy": sorted(_text(p.get("id", "")) for p in packet.get("policy", [])),
        "documents": sorted(_text(d.get("id", "")) for d in packet.get("documents", [])),
    }


def scenario(template: Template) -> str:
    """The digest of what this template emits, across the probe indices.

    Raises whatever `build` raises. A template that cannot be built has no
    scenario, and inventing one would let it take a role in a partition it can
    never contribute a case to.
    """
    probe = Template.from_mapping({**template.body, "id": PROBE_ID})
    emitted = []
    for index in PROBE_INDICES:
        case = build(
            probe,
            root_seed=PROBE_SEED,
            case_index=index,
            role=PROBE_ROLE,
            tokeniser=_NoTokens(),
            render=_canonical,
        )
        emitted.append(_canonical(_projection(case.packet, template.family)))
    return hashlib.sha256(" ".join(emitted).encode()).hexdigest()


def check(templates: Iterable[Template]) -> list[Violation]:
    """Every way a template set holds one scenario more than once.

    Separate from `templates.check`, which asks whether each template is
    well-formed on its own. This asks what the set of them emits, and needs the
    builder to answer — so it lives here rather than inverting that dependency.
    """
    items = list(templates)
    violations: list[Violation] = []

    by_scenario: dict[str, list[Template]] = {}
    for t in items:
        try:
            by_scenario.setdefault(scenario(t), []).append(t)
        except ValueError as e:
            violations.append(
                Violation(
                    "unbuildable_template",
                    f"{t.id or '<no id>'} emits no case, so it has no scenario: {e}",
                    t.id or None,
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
