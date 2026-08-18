# SPDX-License-Identifier: MIT
"""Building one case from a template, per RFC-0003.

**Ground truth is known by construction rather than inferred.** A case is built
by applying a named deformation to a clean pair, so the correct answer falls out
of building it instead of being a judgement made afterwards. That is what makes
the evaluation honest, and it is the whole of the provenance story: a corpus
that can be regenerated from a seed needs no claims made about where it came
from.

Two refusals hold that property up.

A family with no deformation is refused rather than approximated. Emitting the
nearest case the builder can manage would produce a corpus whose ground truth is
a guess wearing the same shape as a construction.

And every case is put to the validator that ships in the product before it is
emitted. "Correct by construction" is a claim about the builder, and a claim
needs something able to contradict it — so the case faces the same check the
model's output will face.

What it does with the answer is *report*, not raise. A build over thousands of
cases needs the whole list of what is wrong with it, and a builder that aborted
on the first bad case could not produce one. `Case.violations` is therefore the
verdict, and a non-empty verdict is a case the caller must not write — the
refusal belongs to whoever is assembling the corpus, and it has what it needs to
make it. A malformed *template*, by contrast, raises here: that is a defect in
an input, and no amount of reporting makes the case buildable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from random import Random
from typing import Any

from consylr import money, prompt, schema
from consylr.budget import Budget, Tokeniser, check_packet
from consylr.budget import check as budget_check
from consylr.templates import Template, shape_violations
from consylr.violation import Violation


def case_seed(root_seed: int, template_id: str, case_index: int) -> int:
    """The seed for one case, from the root seed, its template and its index.

    Derived rather than drawn from one shared stream. A shared stream makes case
    *n* depend on how many draws were taken before it, so adding a family at the
    front silently changes every case behind it and a corpus regenerated after an
    unrelated edit no longer matches the one the published numbers came from.
    """
    digest = hashlib.sha256(f"{root_seed}:{template_id}:{case_index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class Case:
    packet: dict[str, Any]
    expected: dict[str, Any]
    meta: dict[str, Any]
    violations: list[Violation] = field(default_factory=list)


@dataclass
class Draft:
    """The clean packet a deformation is applied to.

    `pairs` holds the correspondence explicitly rather than by list position.
    Position is not identity: a deformation that appends a decoy to both sides
    would, under positional pairing, silently create a supported match between
    the two records it had just built to be unmatchable.
    """

    a: list[dict[str, Any]]
    b: list[dict[str, Any]]
    policy: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    pairs: list[tuple[str, str]]

    #: The policy line bearing this family's cause, where the family asserts one.
    #: Declared by the template rather than assumed to be the first line: citing
    #: `policy[0]` regardless of what it says is a citation pointing at nothing,
    #: and it is what let two families share one packet under two answer keys.
    cause: str = ""

    @property
    def warrant(self) -> str:
        """The policy line a supported claim cites when nothing narrower applies."""
        return self.cause or str(self.policy[0]["id"])

    def new_id(self, prefix: str) -> str:
        """An identifier no record on that side already holds."""
        side = self.a if prefix == "A" else self.b
        taken = {int(str(r["id"]).split("-")[1]) for r in side}
        return f"{prefix}-{max(taken, default=0) + 1:03d}"

    def record(self, rid: str) -> dict[str, Any]:
        return next(r for r in (*self.a, *self.b) if r["id"] == rid)


#: Every deformation that reduces an amount takes this share of it, never less
#: than a cent, and never so much that nothing is left to observe.
CUT_RATE = Decimal("0.02")

#: The families whose answer asserts a cause, and the words a policy line has to
#: use for a packet to carry it. RFC-0002 distinguishes these by the cause being
#: *described in policy* — so without this, `fee_at_source` and `withholding` are
#: one scenario under two contradictory answer keys, and the exam grades a
#: distinction the model cannot possibly recover. Deliberately crude: it asks
#: whether the cited line is about the right thing, which is a question a
#: template author can answer and a reader can check.
CAUSE_TERMS: dict[str, frozenset[str]] = {
    "fee_at_source": frozenset({"fee", "charge", "commission"}),
    "withholding": frozenset({"withhold", "withholding", "tax"}),
    "timing_cutoff": frozenset({"cut-off", "cutoff", "period", "closes", "close"}),
}


#: What `cause_not_established` removes: a share, because a fixed sum turned a
#: small obligation negative and moved a large one barely at all.
SHORTFALL_RATE = Decimal("0.075")

_money = money.parse
_amount = money.canonical
_reduced_by = money.reduced_by


def _supported(left: Sequence[str], right: Sequence[str], why: Sequence[str]) -> dict[str, Any]:
    return {"l": list(left), "r": list(right), "c": "supported", "why": list(why)}


def _clean(draft: Draft, skip: str | None = None) -> list[dict[str, Any]]:
    """A supported match for every pair the deformation did not touch."""
    return [
        _supported([left], [right], [draft.warrant]) for left, right in draft.pairs if left != skip
    ]


def _residue(draft: Draft, matches: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Every record in no match whose certainty is supported or ambiguous.

    Computed from the matches rather than declared beside them, so an expected
    output cannot disagree with itself about what was left over.
    """
    claimed: set[str] = set()
    for m in matches:
        if m.get("c") in ("supported", "ambiguous"):
            claimed |= set(m.get("l", [])) | set(m.get("r", []))
    return {
        "l": [r["id"] for r in draft.a if r["id"] not in claimed],
        "r": [r["id"] for r in draft.b if r["id"] not in claimed],
    }


def _finish(
    draft: Draft,
    matches: list[dict[str, Any]],
    exceptions: list[dict[str, Any]] | None = None,
    opens: list[dict[str, Any]] | None = None,
    act: str = "accept",
) -> dict[str, Any]:
    residue = _residue(draft, matches)
    disposed = {i for m in matches for i in (*m["l"], *m["r"])}
    disposed |= set(residue["l"]) | set(residue["r"])

    # A `request` covers exactly what an `open` entry records as needed. Asking
    # about everything at once would leave most of it dangling — the disposition
    # would name records that nothing says are missing anything.
    requested = {i for o in (opens or []) for i in o["on"]}
    dispositions: list[dict[str, Any]] = []
    if requested:
        dispositions.append({"act": "request", "on": sorted(requested)})
    remainder = sorted(disposed - requested)
    if remainder:
        dispositions.append({"act": act, "on": remainder})

    out: dict[str, Any] = {"matches": matches, "residue": residue, "do": dispositions}
    if exceptions:
        out["exceptions"] = exceptions
    if opens:
        out["open"] = opens
    return out


# --- the deformations ---------------------------------------------------------
#
# Each takes the clean draft and a seeded generator, may modify the draft, and
# returns the output that is correct for what it did.


def _clean_match(draft: Draft, rng: Random) -> dict[str, Any]:
    return _finish(draft, _clean(draft))


def _reduced_on_the_right(kind: str) -> Callable[[Draft, Random], dict[str, Any]]:
    """A right-side amount reduced by something the policy describes."""

    def deform(draft: Draft, rng: Random) -> dict[str, Any]:
        left, right = rng.choice(draft.pairs)
        record = draft.record(right)
        whole = _money(record["amount"])
        record["amount"] = _amount(whole - _reduced_by(whole, CUT_RATE, kind))
        matches = [*_clean(draft, skip=left), _supported([left], [right], [draft.warrant])]
        exception = {"on": [right], "kind": kind, "c": "supported", "why": [draft.warrant]}
        return _finish(draft, matches, [exception])

    return deform


def _timing_cutoff(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    draft.record(right)["date"] = "2026-04-01"
    matches = [*_clean(draft, skip=left), _supported([left], [right], [draft.warrant])]
    exception = {"on": [right], "kind": "timing_cutoff", "c": "supported", "why": [draft.warrant]}
    return _finish(draft, matches, [exception])


def _reference_mangled(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    record = draft.record(right)
    ref = str(record["ref"])
    record["ref"] = ref[:-1] if len(ref) > 1 else ref
    # The correspondence is carried by the other evidence on the two records,
    # which is the point of the family: the reference alone cannot settle it.
    matches = [*_clean(draft, skip=left), _supported([left], [right], [left, right])]
    exception = {"on": [right], "kind": "reference_mangled", "c": "supported", "why": [left, right]}
    return _finish(draft, matches, [exception])


def _name_variant(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    record = draft.record(right)
    record["party"] = str(record["party"]).upper().replace(" LTD", " LIMITED")
    matches = [*_clean(draft, skip=left), _supported([left], [right], [left, right])]
    exception = {"on": [right], "kind": "name_variant", "c": "supported", "why": [left, right]}
    return _finish(draft, matches, [exception])


def _partial_payment(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    record = draft.record(right)
    whole = _money(record["amount"])
    first = (whole / 2).quantize(money.CENT, rounding=ROUND_HALF_UP)
    if not 0 < first < whole:
        raise ValueError(f"an amount of {whole} cannot be split into two observable parts")
    record["amount"] = _amount(first)
    second = {**record, "id": draft.new_id("B"), "amount": _amount(whole - first)}
    draft.b.append(second)
    evidence = [left, right, second["id"]]
    matches = [*_clean(draft, skip=left), _supported([left], [right, second["id"]], evidence)]
    exception = {
        "on": [right, second["id"]],
        "kind": "partial_payment",
        "c": "supported",
        "why": evidence,
    }
    return _finish(draft, matches, [exception])


def _batched_vs_itemised(draft: Draft, rng: Random) -> dict[str, Any]:
    if len(draft.pairs) < 2:
        raise ValueError("batched_vs_itemised needs a template with at least two pairs")
    (left_one, right_one), (left_two, right_two) = draft.pairs[0], draft.pairs[1]
    kept, folded = draft.record(right_one), draft.record(right_two)
    kept["amount"] = _amount(_money(kept["amount"]) + _money(folded["amount"]))
    draft.b.remove(folded)
    draft.pairs = [p for p in draft.pairs if p[0] not in (left_one, left_two)]
    evidence = [left_one, left_two, right_one]
    matches = [*_clean(draft), _supported([left_one, left_two], [right_one], evidence)]
    exception = {
        "on": [right_one],
        "kind": "batched_vs_itemised",
        "c": "supported",
        "why": evidence,
    }
    return _finish(draft, matches, [exception])


def _duplicate(draft: Draft, rng: Random) -> dict[str, Any]:
    _, right = rng.choice(draft.pairs)
    copy = {**draft.record(right), "id": draft.new_id("B")}
    draft.b.append(copy)
    # Flagged and deliberately **not** matched a second time, so it falls to
    # residue by the same rule every other unmatched record does. No pair is
    # recorded for it, because it corresponds to nothing.
    exception = {
        "on": [copy["id"]],
        "kind": "duplicate",
        "c": "supported",
        "why": [right, copy["id"]],
    }
    return _finish(draft, _clean(draft), [exception])


def _reversal(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    original = draft.record(right)
    reversing = {
        **original,
        "id": draft.new_id("B"),
        "amount": _amount(-_money(original["amount"])),
    }
    draft.b.append(reversing)
    reinstated = {**original, "id": draft.new_id("B")}
    draft.b.append(reinstated)
    # The match spans all three postings: the original, its reversal, and the
    # re-posting that actually settles the obligation.
    matches = [
        *_clean(draft, skip=left),
        _supported([left], [right, reversing["id"], reinstated["id"]], [draft.warrant]),
    ]
    exception = {
        "on": [right, reversing["id"]],
        "kind": "reversal",
        "c": "supported",
        "why": [right, reversing["id"]],
    }
    return _finish(draft, matches, [exception])


def _missing_record(draft: Draft, rng: Random) -> dict[str, Any]:
    orphan, gone = rng.choice(draft.pairs)
    draft.b.remove(draft.record(gone))
    draft.pairs = [p for p in draft.pairs if p[0] != orphan]
    # Correct is an `open` entry *and* residue. Producing only one of the two is
    # the silent-residue failure the schema exists to prevent — and this family
    # carries no exception kind, because its answer is not an exception.
    opens = [{"on": [orphan], "need": "the counterpart record or an explanation of its absence"}]
    return _finish(draft, _clean(draft), None, opens)


def _cause_not_established(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    record = draft.record(right)
    whole = _money(record["amount"])
    record["amount"] = _amount(whole - _reduced_by(whole, SHORTFALL_RATE, "shortfall"))
    matches = [
        *_clean(draft, skip=left),
        {"l": [left], "r": [right], "c": "ambiguous", "why": [left, right]},
    ]
    # The difference is named and its cause declined. Emitting a plausible cause
    # is a hallucination; emitting no exception at all is a miss. `why` is empty
    # rather than absent: a citation is what a cause would rest on, and there is
    # none — which is the claim itself, not an omission.
    exception = {"on": [right], "kind": "cause_not_established", "c": "unsupported", "why": []}
    opens = [{"on": [right], "need": "the document explaining the shortfall"}]
    return _finish(draft, matches, [exception], opens)


def _decoy(draft: Draft, rng: Random) -> dict[str, Any]:
    amount = _amount(_money(draft.a[0]["amount"]) + Decimal("11.00"))
    left = {
        "id": draft.new_id("A"),
        "ref": "INV-7100",
        "party": "Eastvale Trading",
        "date": "2026-03-11",
        "amount": amount,
    }
    right = {
        "id": draft.new_id("B"),
        "ref": "PMT-4420",
        "party": "Westbrook Services",
        "date": "2026-03-12",
        "amount": amount,
    }
    # Appended without a pair: they look alike and are not the same event.
    draft.a.append(left)
    draft.b.append(right)
    # An `unsupported` match is not a wasted entry. It says the pair was
    # considered and rejected, which is a different and more useful statement
    # than never naming it — and both records still fall to residue, because an
    # unsupported match claims no correspondence.
    matches = [
        *_clean(draft),
        {
            "l": [left["id"]],
            "r": [right["id"]],
            "c": "unsupported",
            "why": [left["id"], right["id"]],
        },
    ]
    return _finish(draft, matches, None, None, act="hold")


def _ambiguous_pair(draft: Draft, rng: Random) -> dict[str, Any]:
    left, right = rng.choice(draft.pairs)
    twin = {**draft.record(right), "id": draft.new_id("B")}
    twin["ref"] = f"{twin['ref']}-A"
    draft.b.append(twin)
    # One ambiguous match naming both candidates, never two supported ones: two
    # supported matches would assert a correspondence the evidence cannot pick.
    matches = [
        *_clean(draft, skip=left),
        {"l": [left], "r": [right, twin["id"]], "c": "ambiguous", "why": [left, right, twin["id"]]},
    ]
    return _finish(draft, matches, None, None, act="hold")


DEFORMATIONS: dict[str, Callable[[Draft, Random], dict[str, Any]]] = {
    "clean_match": _clean_match,
    "fee_at_source": _reduced_on_the_right("fee_at_source"),
    "withholding": _reduced_on_the_right("withholding"),
    "timing_cutoff": _timing_cutoff,
    "reference_mangled": _reference_mangled,
    "name_variant": _name_variant,
    "partial_payment": _partial_payment,
    "batched_vs_itemised": _batched_vs_itemised,
    "duplicate": _duplicate,
    "reversal": _reversal,
    "missing_record": _missing_record,
    "cause_not_established": _cause_not_established,
    "decoy": _decoy,
    "ambiguous_pair": _ambiguous_pair,
}


def _prove_cause(template: Template, policy: list[dict[str, Any]]) -> str:
    """The policy line this family's cause rests on, checked rather than assumed.

    Refused three ways, because each of them produces an answer key asserting
    something the packet does not carry — the exact failure the prompt artefact
    instructs the model never to commit, asked of the model but not of the
    corpus that grades it.
    """
    terms = CAUSE_TERMS.get(template.family)
    if terms is None:
        return ""

    declared = str(template.body.get("cause", ""))
    ids = [str(line.get("id", "")) for line in policy]
    if not declared:
        raise ValueError(
            f"a {template.family} template must declare which policy line states the cause; "
            f"without it the answer cites whichever line came first"
        )
    if declared not in ids:
        raise ValueError(
            f"{template.family} names {declared!r} as its cause, which is not a policy line "
            f"this template carries ({', '.join(ids) or 'none'})"
        )

    text = next(str(line.get("text", "")) for line in policy if str(line.get("id")) == declared)
    if not any(term in text.lower() for term in terms):
        raise ValueError(
            f"{template.family} cites {declared!r}, whose text says nothing about it: "
            f"{text!r}. A packet that does not describe the cause cannot carry the "
            f"distinction, and grading it asks the model to supply what it was not shown."
        )
    return declared


def _prove_effect(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Any],
    family: str,
) -> None:
    """Check the answer's truth against the packet, not just its form.

    The shipping validator checks the answer's *form*: that every identifier
    resolves and the sections cohere. It cannot check that the packet was
    actually deformed in the way the answer key claims, because it never saw the
    clean packet. So an exception whose named records are all byte-identical to
    the clean ones passes it — a claim about nothing, and exactly what a cut that
    quantised to zero produced: a packet that was a clean match beneath an answer
    asserting an exception on it, with a correct answer scored wrong.

    Raised rather than reported, because this is a defect in the generator or in
    a template, and no corpus should contain the case at all.
    """
    changed = {rid for rid in set(before) | set(after) if before.get(rid) != after.get(rid)}

    if family == "clean_match":
        if changed:
            raise ValueError(f"clean_match deformed {sorted(changed)}; it must deform nothing")
        return

    if not changed:
        raise ValueError(
            f"{family} deformed nothing; its answer describes a packet it did not make"
        )

    for exception in expected.get("exceptions", []):
        # Per exception rather than per record: `reversal` legitimately names the
        # original posting beside the reversing one. What cannot be legitimate is
        # an exception none of whose records the packet shows anything about.
        if not set(exception.get("on", [])) & changed:
            raise ValueError(
                f"{family} asserts {exception.get('kind')!r} on "
                f"{sorted(exception.get('on', []))}, all unchanged from the clean packet"
            )


def _certainty(expected: Mapping[str, Any]) -> str:
    """The case's own certainty, which `quota.check` counts.

    A property of the case rather than of its family, per RFC-0002: a fee case
    with a supporting policy line is itself a clearly-supported case. Taken from
    the weakest correspondence the answer asserts, because a case is only as
    confident as its least confident claim.

    Every deformation already knew this; nothing recorded it, so the quota gate
    read zero clearly-supported cases on every corpus the builder could produce
    and its contradiction check was unreachable.
    """
    asserted = {m.get("c") for m in expected.get("matches", [])}
    if "ambiguous" in asserted:
        return "ambiguous"
    if "unsupported" in asserted:
        return "unsupported"
    return "supported"


def _records(body: Mapping[str, Any], key: str, prefix: str) -> list[dict[str, Any]]:
    raw = body.get(key)
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"template {key!r} must be a non-empty list of records")
    out: list[dict[str, Any]] = []
    for n, record in enumerate(raw, start=1):
        if not isinstance(record, dict):
            # ValueError rather than TypeError: the caller passed a template, not
            # a badly-typed argument. This is malformed data in a data file.
            raise ValueError(  # noqa: TRY004
                f"template {key!r} entry {n} is not a record"
            )
        # The generated id last, so a record carrying its own cannot override it.
        # Identifiers are the packet's, assigned by side and position; a record
        # supplying one could collide across sides, and every `why` in the
        # expected output is written against the generated id rather than that.
        normalised = {**record, "id": f"{prefix}-{n:03d}"}
        if "amount" in normalised:
            # Here rather than in each deformation, so a clean record and a
            # deformed one are written identically by construction.
            normalised["amount"] = _amount(normalised["amount"])
        out.append(normalised)
    return out


def _serialise(packet: Mapping[str, Any]) -> str:
    """The packet as text, for counting only. Not a rendered prompt."""
    return json.dumps(packet, sort_keys=True, separators=(",", ":"))


def build(
    template: Template,
    *,
    root_seed: int,
    case_index: int,
    role: str,
    tokeniser: Tokeniser,
    render: Callable[[Mapping[str, Any]], str],
    budget: Budget | None = None,
) -> Case:
    """One case, with the answer that is correct for how it was built."""
    if not template.id:
        raise ValueError("a template with no id cannot be built; the split separates on it")

    # One definition of what a template is, shared with the audit. A key the
    # builder does not read still changed what counted as this scenario, so the
    # closed world is enforced here rather than tolerated and reported later.
    malformed = shape_violations(template)
    if malformed:
        raise ValueError("; ".join(v.detail for v in malformed))

    deform = DEFORMATIONS.get(template.family)
    if deform is None:
        raise ValueError(f"no deformation for family {template.family!r}")

    policy = template.body.get("policy")
    if not isinstance(policy, list) or not policy:
        raise ValueError("template 'policy' must be a non-empty list")

    left = _records(template.body, "left", "A")
    right = _records(template.body, "right", "B")
    if len(left) != len(right):
        raise ValueError("a template's two sides must describe the same clean pairs")

    resolved = [dict(p) for p in policy]
    draft = Draft(
        a=left,
        b=right,
        cause=_prove_cause(template, resolved),
        policy=resolved,
        documents=[dict(d) for d in template.body.get("documents", [])],
        pairs=[(a["id"], b["id"]) for a, b in zip(left, right, strict=True)],
    )

    # The frozen template's budget unless the caller has a different template. A
    # default assuming no wrapper was wrong in both directions at once: it
    # rejected a valid 1,448-token prompt and admitted 61 packet tokens it
    # should not have, while naming an overhead of zero for a 308-token wrapper.
    budget = (prompt.BUDGET if budget is None else budget).validate()

    seed = case_seed(root_seed, template.id, case_index)
    before = {r["id"]: deepcopy(r) for r in (*draft.a, *draft.b)}
    expected = deform(draft, Random(seed))
    _prove_effect(before, {r["id"]: r for r in (*draft.a, *draft.b)}, expected, template.family)

    packet = {"records": draft.a + draft.b, "policy": draft.policy, "documents": draft.documents}
    meta: dict[str, Any] = {
        "template_id": template.id,
        "template_fingerprint": template.fingerprint,
        "family": template.family,
        "role": role,
        "seed": seed,
        "case_index": case_index,
        "certainty": _certainty(expected),
    }

    violations = schema.validate(expected, packet)

    # Neither `tokeniser` nor `render` has a default, and that is the point. Both
    # were optional, so the ordinary path enforced nothing: a packet six times
    # the default cap came back with no violations, and a deliberately tiny
    # budget changed nothing because the argument was accepted and ignored. An
    # opt-in gate is an off gate. A caller who cannot say how tokens are counted,
    # or what prompt the packet is rendered into, cannot assert the budget — and
    # is now told so at the call rather than trusted at the audit.
    serialised = _serialise(packet)
    meta["packet_tokens"] = len(tokeniser.encode(serialised))
    violations = violations + check_packet(serialised, tokeniser, budget, case=template.id)

    rendered = render(packet)
    meta["prompt_tokens"] = len(tokeniser.encode(rendered))
    violations = violations + budget_check(rendered, tokeniser, budget, case=template.id)

    return Case(packet=packet, expected=expected, meta=meta, violations=violations)
