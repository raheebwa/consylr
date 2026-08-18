# SPDX-License-Identifier: MIT
"""Validation of model output against RFC-0001.

This validator ships in the product and also validates the training corpus, so a
corpus is never graded by a second implementation that only tests itself.

Three properties it has to hold, because a corpus audit depends on all three:

* **It never raises.** Malformed output is the normal case, not the exception —
  a corpus audit that aborts on the first bad case cannot count violations.
* **It reports every violation**, so a caller fixing a case sees the whole list.
* **One defect produces one violation.** Cascades inflate a count that a quota
  audit reads as a number.

Structure is checked before meaning. A section of the wrong type is reported and
then skipped, rather than being fed to rules that assume it parsed.
"""

from __future__ import annotations

import re
from typing import Any

from consylr.violation import Violation

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

#: The field set is frozen by RFC-0001, so unknown keys are refused rather than
#: ignored. An allowlist subsumes a denylist of confidence-like names — which
#: could never enforce "no numeric confidence" anyway, since it only catches the
#: spellings someone thought of — and it catches a misspelled section name, which
#: would otherwise make a whole array invisible to every rule at once.
FIELDS: dict[str, frozenset[str]] = {
    "": frozenset({"matches", "exceptions", "open", "residue", "do"}),
    "matches": frozenset({"l", "r", "c", "why"}),
    "exceptions": frozenset({"on", "kind", "c", "why"}),
    "open": frozenset({"on", "need", "why"}),
    "do": frozenset({"act", "on"}),
    "residue": frozenset({"l", "r"}),
}

REQUIRED: dict[str, frozenset[str]] = {
    "matches": frozenset({"l", "r", "c", "why"}),
    "exceptions": frozenset({"on", "kind", "c", "why"}),
    "open": frozenset({"on", "need"}),
    "do": frozenset({"act", "on"}),
}

#: `need` is the one free-text field RFC-0001 allows, and it is capped so a
#: paragraph cannot eat the generation budget the schema's token measurements
#: assume. Long enough for "processor settlement breakdown"; far short of prose.
NEED_MAX = 120

_POLICY_REF = re.compile(r"^(P-\d+)(?::L\d+(?:-L\d+)?)?$")


def _norm(values: Any) -> set[str]:
    """Identifiers from a packet section, accepting bare ids or objects with one."""
    out: set[str] = set()
    if isinstance(values, dict):
        values = values.values()
    if not isinstance(values, (list, tuple, set, frozenset)):
        return out
    for v in values:
        if isinstance(v, str):
            out.add(v)
        elif isinstance(v, dict) and isinstance(v.get("id"), str):
            out.add(v["id"])
    return out


def _side(record_id: str) -> str:
    return "r" if record_id.startswith("B-") else "l"


def validate(output: Any, packet: Any) -> list[Violation]:
    """Return every way `output` violates RFC-0001, given the packet it describes."""
    v: list[Violation] = []

    if not isinstance(output, dict):
        return [Violation("bad_type", f"output must be an object, got {type(output).__name__}")]
    if not isinstance(packet, dict):
        return [Violation("bad_type", f"packet must be an object, got {type(packet).__name__}")]

    records = _norm(packet.get("records"))
    policies = _norm(packet.get("policy"))
    documents = _norm(packet.get("documents"))

    def resolves(rid: str) -> bool:
        if rid in records or rid in documents:
            return True
        m = _POLICY_REF.match(rid)
        return bool(m and m.group(1) in policies)

    for key in sorted(set(output) - FIELDS[""]):
        v.append(Violation("unknown_field", f"{key!r} is not a field of the output"))

    # --- sections: type first, so no rule below is handed something unparsed
    sections: dict[str, list[dict[str, Any]]] = {}
    for name in ("matches", "exceptions", "open", "do"):
        raw = output.get(name, [])
        if not isinstance(raw, list):
            v.append(Violation("bad_type", f"{name} must be an array, got {type(raw).__name__}"))
            sections[name] = []
            continue
        good: list[dict[str, Any]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                v.append(Violation("bad_type", f"{name} entry must be an object, got {entry!r}"))
                continue
            for key in sorted(set(entry) - FIELDS[name]):
                v.append(Violation("unknown_field", f"{key!r} is not a field of {name}"))
            for key in sorted(REQUIRED[name] - set(entry)):
                v.append(Violation("missing_field", f"{name} entry has no {key!r}"))
            good.append(entry)
        sections[name] = good

    def id_list(entry: dict[str, Any], name: str, key: str) -> list[str]:
        """The ids at `key`, reporting rather than coercing anything else."""
        raw = entry.get(key)
        if raw is None:
            return []
        if not isinstance(raw, list):
            v.append(Violation("bad_type", f"{name}.{key} must be an array, got {raw!r}"))
            return []
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            else:
                v.append(
                    Violation("bad_type", f"{name}.{key} entry must be a string, got {item!r}")
                )
        return out

    # --- residue is required even when empty, so "everything matched" is never silence
    residue_raw = output.get("residue")
    residue: dict[str, list[str]] = {"l": [], "r": []}
    if not isinstance(residue_raw, dict):
        v.append(
            Violation("residue_missing", "residue with 'l' and 'r' is required on every output")
        )
    else:
        for key in sorted(set(residue_raw) - FIELDS["residue"]):
            v.append(Violation("unknown_field", f"{key!r} is not a field of residue"))
        if not FIELDS["residue"] <= set(residue_raw):
            v.append(Violation("residue_missing", "residue needs both 'l' and 'r'"))
        # Keep whichever side was declared: reporting a record as missing from a
        # list it is literally in is worse than the original defect.
        for side in ("l", "r"):
            residue[side] = id_list(residue_raw, "residue", side)

    matches, exceptions, opens, dispositions = (
        sections["matches"],
        sections["exceptions"],
        sections["open"],
        sections["do"],
    )

    # --- enumerations
    for m in matches:
        if "c" in m and m["c"] not in CERTAINTIES:
            v.append(Violation("bad_certainty", f"match certainty {m['c']!r}"))
    for e in exceptions:
        if "c" in e and e["c"] not in CERTAINTIES:
            v.append(Violation("bad_certainty", f"exception certainty {e['c']!r}"))
        if "kind" in e and e["kind"] not in KINDS:
            v.append(Violation("bad_kind", f"exception kind {e['kind']!r}"))
    for d in dispositions:
        if "act" in d and d["act"] not in ACTS:
            v.append(Violation("bad_act", f"disposition act {d['act']!r}"))

    # --- the free-text field is bounded
    for o in opens:
        need = o.get("need")
        if isinstance(need, str) and len(need) > NEED_MAX:
            v.append(
                Violation("need_too_long", f"need is {len(need)} characters; the cap is {NEED_MAX}")
            )
        elif need is not None and not isinstance(need, str):
            v.append(Violation("bad_type", f"open.need must be a string, got {need!r}"))

    # --- gather ids once, reporting any that are not strings
    m_ids = [(m, id_list(m, "matches", "l") + id_list(m, "matches", "r")) for m in matches]
    e_ids = [(e, id_list(e, "exceptions", "on")) for e in exceptions]
    o_ids = [(o, id_list(o, "open", "on")) for o in opens]
    d_ids = [(d, id_list(d, "do", "on")) for d in dispositions]
    whys = (
        [id_list(m, "matches", "why") for m in matches]
        + [id_list(e, "exceptions", "why") for e in exceptions]
        + [id_list(o, "open", "why") for o in opens]
    )

    # --- a supported claim must cite something; an absent cause is itself the claim
    for m in matches:
        if m.get("c") == "supported" and isinstance(m.get("why"), list) and not m["why"]:
            v.append(Violation("uncited_claim", "a supported match cites nothing"))
    for e in exceptions:
        if e.get("kind") == "cause_not_established":
            continue
        if isinstance(e.get("why"), list) and not e["why"]:
            v.append(Violation("uncited_claim", f"exception {e.get('kind')!r} cites nothing"))

    # --- every referenced identifier resolves in the supplied packet
    referenced: set[str] = set()
    for _, ids in (*m_ids, *e_ids, *o_ids, *d_ids):
        referenced |= set(ids)
    for w in whys:
        referenced |= set(w)
    referenced |= set(residue["l"]) | set(residue["r"])
    for rid in sorted(r for r in referenced if not resolves(r)):
        v.append(Violation("unresolved_id", f"{rid} is not in the supplied packet"))

    # --- the residue rule, quantified over the PACKET (RFC-0001 §Residue).
    # A record is residue if and only if it appears in no match whose certainty
    # is supported or ambiguous. Quantifying over what the output happens to
    # name would let an output that says nothing about a record certify clean,
    # which is the omission this field exists to make impossible.
    matched: set[str] = set()
    for m, ids in m_ids:
        if m.get("c") in {"supported", "ambiguous"}:
            matched |= set(ids)
    expected = {r for r in records if r not in matched}
    declared = set(residue["l"]) | set(residue["r"])
    if expected != declared:
        v.append(
            Violation(
                "residue_wrong",
                f"missing {sorted(expected - declared)}, unexpected {sorted(declared - expected)}",
            )
        )
    else:
        for rid in sorted(declared):
            if rid not in residue[_side(rid)]:
                v.append(Violation("residue_wrong", f"{rid} is listed on the wrong side"))

    # --- a record belongs to the side its identifier names
    for m, _ in m_ids:
        for key in ("l", "r"):
            for rid in (m.get(key) or []) if isinstance(m.get(key), list) else []:
                if isinstance(rid, str) and rid in records and _side(rid) != key:
                    v.append(Violation("wrong_side", f"{rid} is on side {key!r}, not its own"))

    # --- no record in two supported matches
    seen: set[str] = set()
    for m, ids in m_ids:
        if m.get("c") != "supported":
            continue
        for rid in ids:
            if rid in seen:
                v.append(Violation("double_matched", f"{rid} appears in two supported matches"))
            seen.add(rid)

    # --- a request must be covered by an open entry naming the same records
    open_ids: set[str] = set()
    for _, ids in o_ids:
        open_ids |= set(ids)
    for d, ids in d_ids:
        if d.get("act") != "request":
            continue
        for rid in ids:
            if rid not in open_ids:
                v.append(
                    Violation(
                        "dangling_request",
                        f"request names {rid}, which no open entry records as needed",
                    )
                )

    # --- every disposed identifier is reasoned about somewhere in the output
    reasoned: set[str] = set(open_ids) | set(residue["l"]) | set(residue["r"])
    for _, ids in (*m_ids, *e_ids):
        reasoned |= set(ids)
    for _, ids in d_ids:
        for rid in ids:
            if rid not in reasoned:
                v.append(
                    Violation(
                        "incoherent_disposition",
                        f"{rid} is disposed of but appears nowhere else in the output",
                    )
                )

    return v
