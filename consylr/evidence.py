# SPDX-License-Identifier: MIT
"""Every identifier an answer names, checked against what the packet held, per #27.

The provenance scheme is deliberately minimal — immutable record, policy and
document ids and nothing heavier, because the harness's 2,048-token context and
model-centric judging make a retrieval subsystem a poor use of Gate 1's time.
Minimal only works if the ids are load-bearing, and they are load-bearing only
if every one of them resolves.

**A reference to something absent is a failure of the output, not a cosmetic
flaw.** It is the model naming evidence it was never given, which is the exact
shape of a confident wrong answer: the disposition looks reconstructible, cites
a source, and cannot be checked against anything.

**Shape is not this module's business.** An answer that is structurally wrong is
the schema's to reject; reporting it here as invented evidence would send a
reader looking for a model that lied when it merely produced the wrong shape.
So every traversal below tolerates malformed input by ignoring it.

This is a different check from `score.citation_resolution`, which measures how
often `why` entries resolve across a run. That is a metric over a corpus; this
is a gate over one answer, and it reads every field an identifier can appear in
rather than `why` alone — an action against a record the packet never contained
is the same failure wearing a different field name.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from consylr.violation import Violation

#: Where identifiers live, by section. `why` cites any id; the rest name records.
ID_FIELDS: dict[str, tuple[str, ...]] = {
    "matches": ("l", "r", "why"),
    "exceptions": ("on", "why"),
    "open": ("on", "why"),
    "do": ("on",),
}

#: The certainty that obliges a citation. `ambiguous` and `unsupported` do not:
#: demanding a reference from a claim that is explicitly not established would
#: push the model to invent one to keep the gate quiet, and the gate would then
#: manufacture the failure it exists to catch.
CITED_CERTAINTY = "supported"


def known_ids(packet: Mapping[str, Any]) -> set[str]:
    """Every identifier the packet actually supplied."""
    out: set[str] = set()
    for section in ("records", "policy", "documents"):
        for entry in packet.get(section, []) or []:
            if isinstance(entry, Mapping) and entry.get("id") is not None:
                out.add(str(entry["id"]))
    return out


def _named(output: Mapping[str, Any]) -> Iterator[tuple[str, str, str]]:
    """(section, field, identifier) for every id an answer names."""
    for section, fields in ID_FIELDS.items():
        entries = output.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            for field in fields:
                values = entry.get(field)
                if not isinstance(values, list):
                    continue
                for value in values:
                    if isinstance(value, str):
                        # `why` may carry a qualifier after a colon; the id is
                        # the part before it, which is what has to resolve.
                        yield section, field, value.split(":")[0]
    residue = output.get("residue")
    if isinstance(residue, Mapping):
        for side in ("l", "r"):
            values = residue.get(side)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        yield "residue", side, value


def unresolved(output: Mapping[str, Any], packet: Mapping[str, Any]) -> list[Violation]:
    """Everything the answer names that the packet did not supply.

    All of them, not the first: an operator fixing one and rerunning to find the
    next is an operator doing the tool's work.
    """
    known = known_ids(packet)
    found = [
        Violation(
            "unresolved_reference",
            f"{section}.{field} names {identifier!r}, which the packet does not contain",
        )
        for section, field, identifier in _named(output)
        if identifier not in known
    ]

    matches = output.get("matches")
    if isinstance(matches, list):
        for entry in matches:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("c") != CITED_CERTAINTY:
                continue
            why = entry.get("why")
            if not isinstance(why, list) or not why:
                found.append(
                    Violation(
                        "uncited_claim",
                        f"a {CITED_CERTAINTY} match on {entry.get('l')} cites nothing; "
                        "an uncited claim reads as evidenced and is not",
                    )
                )
    return found
