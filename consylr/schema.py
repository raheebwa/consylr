# SPDX-License-Identifier: MIT
"""Validation of model output against RFC-0001.

This validator ships in the product and also validates the training corpus. A
second validator written for the corpus would only test the second validator.

It reports every violation it finds rather than raising on the first, because a
caller fixing a generated case wants the whole list, and because a corpus audit
counts violations.

Scope: this checks that an output is internally coherent and that its
references resolve. Whether the output *covered* every record in the packet is a
different question — completeness — and it is not answered here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

CERTAINTIES = frozenset({"supported", "ambiguous", "unsupported"})
ACTS = frozenset({"accept", "hold", "escalate", "request"})

#: The exception families, per RFC-0002. `missing_record` is deliberately absent:
#: residue plus an `open` entry already say it, and two ways to state one fact
#: produce inconsistent ground truth.
KINDS = frozenset(
    {
        "fee_at_source",
        "withholding",
        "timing_cutoff",
        "reference_mangled",
        "name_variant",
        "partial_payment",
        "duplicate",
        "reversal",
        "batched_vs_itemised",
        "cause_not_established",
    }
)

#: Keys that would express an uncalibrated numeric certainty. Refused outright:
#: a number that looks calibrated and is not is worse than no number, because a
#: reader will act on it.
NUMERIC_CERTAINTY_KEYS = frozenset({"confidence", "score", "probability", "certainty_score"})


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.code}: {self.detail}"


def _ids(entry: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for k in keys:
        v = entry.get(k)
        if isinstance(v, list):
            out.extend(str(x) for x in v)
    return out


def _side(record_id: str) -> str:
    """Which side a record belongs to, from the identifier itself (RFC-0001)."""
    return "r" if record_id.startswith("B-") else "l"


def _walk(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def validate(output: dict[str, Any], packet: dict[str, Any]) -> list[Violation]:
    """Return every way `output` violates RFC-0001, given the packet it describes."""
    v: list[Violation] = []
    known = set(packet.get("records", ())) | set(packet.get("policy", ()))

    matches = output.get("matches") or []
    exceptions = output.get("exceptions") or []
    opens = output.get("open") or []
    dispositions = output.get("do") or []

    # --- residue is required even when empty, so "everything matched" is never silence
    residue = output.get("residue")
    if not isinstance(residue, dict) or "l" not in residue or "r" not in residue:
        v.append(
            Violation("residue_missing", "residue with 'l' and 'r' is required on every output")
        )
        residue = {"l": [], "r": []}

    # --- enumerations
    for m in matches:
        if m.get("c") not in CERTAINTIES:
            v.append(Violation("bad_certainty", f"match certainty {m.get('c')!r}"))
    for e in exceptions:
        if e.get("c") not in CERTAINTIES:
            v.append(Violation("bad_certainty", f"exception certainty {e.get('c')!r}"))
        if e.get("kind") not in KINDS:
            v.append(Violation("bad_kind", f"exception kind {e.get('kind')!r}"))
    for d in dispositions:
        if d.get("act") not in ACTS:
            v.append(Violation("bad_act", f"disposition act {d.get('act')!r}"))

    # --- a supported claim must cite something
    for m in matches:
        if m.get("c") == "supported" and not m.get("why"):
            v.append(
                Violation("uncited_claim", f"supported match {_ids(m, 'l', 'r')} cites nothing")
            )
    for e in exceptions:
        # An absent cause is the claim, so cause_not_established may cite nothing.
        if (
            e.get("c") == "supported"
            and e.get("kind") != "cause_not_established"
            and not e.get("why")
        ):
            v.append(
                Violation("uncited_claim", f"supported exception {e.get('kind')} cites nothing")
            )

    # --- every referenced identifier resolves in the supplied packet
    referenced: set[str] = set()
    for m in matches:
        referenced |= set(_ids(m, "l", "r", "why"))
    for e in exceptions:
        referenced |= set(_ids(e, "on", "why"))
    for o in opens:
        referenced |= set(_ids(o, "on", "why"))
    for d in dispositions:
        referenced |= set(_ids(d, "on"))
    referenced |= set(residue.get("l") or []) | set(residue.get("r") or [])
    for rid in sorted(referenced - known):
        v.append(Violation("unresolved_id", f"{rid} is not in the supplied packet"))

    # --- the residue rule (RFC-0001 §Residue)
    # A record is residue iff it appears in no match whose certainty is
    # supported or ambiguous. An unsupported match does not count as matched.
    matched: set[str] = set()
    for m in matches:
        if m.get("c") in {"supported", "ambiguous"}:
            matched |= set(_ids(m, "l", "r"))
    mentioned: set[str] = set()
    for m in matches:
        mentioned |= set(_ids(m, "l", "r"))
    for e in exceptions:
        mentioned |= set(_ids(e, "on"))
    for o in opens:
        mentioned |= set(_ids(o, "on"))
    for d in dispositions:
        mentioned |= set(_ids(d, "on"))
    mentioned |= set(residue.get("l") or []) | set(residue.get("r") or [])

    expected = {r for r in mentioned if r not in matched}
    declared = set(residue.get("l") or []) | set(residue.get("r") or [])
    if expected != declared:
        missing = sorted(expected - declared)
        spurious = sorted(declared - expected)
        v.append(
            Violation(
                "residue_wrong",
                f"residue should be {sorted(expected)}; missing {missing}, unexpected {spurious}",
            )
        )
    else:
        for rid in sorted(declared):
            side = _side(rid)
            if rid not in (residue.get(side) or []):
                v.append(Violation("residue_wrong", f"{rid} is listed on the wrong side"))

    # --- no record in two supported matches
    seen: set[str] = set()
    for m in matches:
        if m.get("c") != "supported":
            continue
        for rid in _ids(m, "l", "r"):
            if rid in seen:
                v.append(Violation("double_matched", f"{rid} appears in two supported matches"))
            seen.add(rid)

    # --- a request must be covered by an open entry naming the same records
    open_ids: set[str] = set()
    for o in opens:
        open_ids |= set(_ids(o, "on"))
    for d in dispositions:
        if d.get("act") != "request":
            continue
        for rid in _ids(d, "on"):
            if rid not in open_ids:
                v.append(
                    Violation(
                        "dangling_request",
                        f"request names {rid}, which no open entry records as needed",
                    )
                )

    # --- every disposed identifier is reasoned about somewhere in the output
    reasoned: set[str] = set()
    for m in matches:
        reasoned |= set(_ids(m, "l", "r"))
    for e in exceptions:
        reasoned |= set(_ids(e, "on"))
    reasoned |= open_ids
    reasoned |= set(residue.get("l") or []) | set(residue.get("r") or [])
    for d in dispositions:
        for rid in _ids(d, "on"):
            if rid not in reasoned:
                v.append(
                    Violation(
                        "incoherent_disposition",
                        f"{rid} is disposed of but appears nowhere else in the output",
                    )
                )

    # --- no uncalibrated numeric certainty, anywhere
    for key, _value in _walk(output):
        if key in NUMERIC_CERTAINTY_KEYS:
            v.append(
                Violation("numeric_confidence", f"{key!r} is refused; certainty is categorical")
            )

    return v
