# SPDX-License-Identifier: MIT
"""Building a corpus of cases that are actually different from each other.

A deformation's only source of variety is which pair it touches, and a template
carries a handful of pairs — so asking a template for thirty cases yields the
same handful, repeated. Three families ignore the generator entirely and yield
exactly one case however many are asked for.

The first sealed set was built without knowing that: 196 packets, 73 distinct,
the most repeated appearing seven times. Every metric computed on it would have
weighted those cases sevenfold, which is measurement with a bent ruler rather
than measurement.

So a corpus is built by asking for distinct cases and stopping when a template
stops producing them. The corpus is then as large as the templates can honestly
make it, and no larger — a smaller corpus of distinct cases is worth more than a
padded one, and `corpus.write` refuses the padded one anyway.

Per-case instantiation is the fix, and it now exists: a pattern template
carries drawn amounts, references, dates and counterparties rather than fixed
ones, so a template's yield is bounded by its pools rather than by its pair
count. `limit` is therefore a real ceiling again rather than a formality — the
pattern set gives thirty distinct cases from thirty asked where the fixed set
gave three.

None of that relaxes anything below. Distinctness is still established by
comparing the packets that were actually produced, because a template that
*should* vary and does not would otherwise pad a corpus exactly as before.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from consylr import prompt
from consylr.budget import Tokeniser
from consylr.cases import Case, build
from consylr.templates import Template


@dataclass(frozen=True)
class Yield:
    """What a corpus cost to build, so template poverty stays visible."""

    cases: list[Case]
    asked: int
    duplicates: int

    @property
    def distinct(self) -> int:
        return len(self.cases)


def _packet(case: Case) -> str:
    return json.dumps(case.packet, sort_keys=True, separators=(",", ":"))


def cases_for(
    template: Template,
    *,
    seed: int,
    role: str,
    limit: int,
    tokeniser: Tokeniser,
    seen: set[str] | None = None,
) -> list[Case]:
    """Up to `limit` cases from one template, each with a different packet.

    Stops early when the template has nothing else to give. `limit` is a ceiling
    rather than a target: a `clean_match` template has exactly one case in it,
    and asking for twenty produces nineteen copies.
    """
    known = seen if seen is not None else set()
    out: list[Case] = []
    for index in range(limit):
        case = build(
            template,
            root_seed=seed,
            case_index=index,
            role=role,
            tokeniser=tokeniser,
            render=prompt.render,
            budget=prompt.BUDGET,
        )
        packet = _packet(case)
        if packet in known:
            continue
        known.add(packet)
        out.append(case)
    return out


def corpus_for(
    templates: Iterable[Template],
    *,
    seed: int,
    role: str,
    limit: int,
    tokeniser: Tokeniser,
    extra: Mapping[str, Any] | None = None,
) -> Yield:
    """Every distinct case the templates yield, and what it cost to find them.

    `extra` is stamped on each case's metadata — the sealed seed, a corpus
    label, whatever the caller needs a case to carry when it travels alone.
    """
    seen: set[str] = set()
    cases: list[Case] = []
    asked = 0
    for template in templates:
        asked += limit
        for case in cases_for(
            template, seed=seed, role=role, limit=limit, tokeniser=tokeniser, seen=seen
        ):
            if extra:
                case.meta.update(extra)
            cases.append(case)
    return Yield(cases=cases, asked=asked, duplicates=asked - len(cases))
