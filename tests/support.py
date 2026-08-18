# SPDX-License-Identifier: MIT
"""One template fixture, in the shape the generator actually consumes.

Every test module that touches template identity uses this. The reason is a
defect it was written to end: the identity tests and the builder tests each had
their own fixture, and only the builder's was a shape `cases.build()` accepts.
`SURFACE_FIELDS` was therefore written against a shape nothing in the product
produces, so the paraphrase-invariance it names held over a data model that
never reaches the generator — a property vacuously true, tested green, and worth
nothing.

A fixture that the product refuses is not a fixture. `test_the_fixture_is
_something_the_generator_can_actually_build` holds this file to that.
"""

from __future__ import annotations

from typing import Any

from consylr.budget import Budget
from consylr.cases import Case, build
from consylr.prompt import TEMPLATE, render
from consylr.templates import Template

#: A policy line that actually names each cause-bearing family's cause. The
#: builder refuses a template whose policy cannot support its family, so a
#: fixture without these is a fixture the product rejects — and a fixture the
#: product refuses is not a fixture.
CAUSE_LINES = {
    "fee_at_source": "A settlement fee is deducted at source.",
    "withholding": "Withholding tax is deducted before remittance.",
    "timing_cutoff": "The period closes on the last business day; later value dates fall after.",
}

FAMILIES = frozenset({"clean_match", "fee_at_source", "cause_not_established", "decoy", "reversal"})


def template_body(
    id: str = "t-001",
    family: str = "clean_match",
    *,
    party: str = "Northwind Ltd",
    policy_text: str = "Invoices settle at face value unless a deduction is stated.",
    amount: str = "1000.00",
    pairs: int = 4,
    **over: Any,
) -> dict[str, Any]:
    """A template in the shape `cases.build()` reads.

    `party` and `policy_text` are the two fields RFC-0003 permits a paraphrase to
    rewrite, exposed as parameters so a test can reword a scenario without
    touching anything a paraphrase may not touch.
    """
    body: dict[str, Any] = {
        "id": id,
        "family": family,
        "left": [
            {
                "ref": f"INV-{2000 + i}",
                "party": party,
                "date": "2026-03-02",
                "amount": amount,
            }
            for i in range(pairs)
        ],
        "right": [
            {
                "ref": f"INV-{2000 + i}",
                "party": party,
                "date": "2026-03-04",
                "amount": amount,
            }
            for i in range(pairs)
        ],
        "policy": [
            {"id": "P-1", "text": policy_text},
            {"id": "P-2", "text": CAUSE_LINES.get(family, "Amounts settle in full.")},
        ],
        "documents": [{"id": "D-1", "text": "Remittance advice for March 2026."}],
    }
    if family in CAUSE_LINES:
        body["cause"] = "P-2"
    body.update(over)
    return body


def a_template(id: str = "t-001", family: str = "clean_match", **over: Any) -> Template:
    return Template.from_mapping(template_body(id, family, **over))


class PerCharacter:
    """One token per character. Deterministic, offline, and inspectable.

    The real tokeniser is fetched at setup; a build that reached for it would be
    network-dependent, which RFC-0003 refuses.
    """

    def encode(self, text: str) -> list[int]:
        return [0] * len(text)


def built(template: Template, **over: Any) -> Case:
    """A case, with the two things `build` refuses to proceed without.

    `tokeniser` and `render` have no defaults in `build`, because both were once
    optional and the ordinary path therefore enforced no budget at all. Supplying
    them here keeps that strictness at the call site it belongs to rather than
    softening it for the tests.
    """
    kwargs: dict[str, Any] = {
        "root_seed": 1,
        "case_index": 0,
        "role": "train",
        "tokeniser": PerCharacter(),
        "render": render,
        "budget": FAKE_BUDGET,
    }
    kwargs.update(over)
    return build(template, **kwargs)


#: A budget scaled for `PerCharacter`, so the tests can render through the real
#: template. One token per character is roughly four times the frozen tokeniser's
#: count, and the alternative — a second renderer for the tests — is the "four
#: surfaces rendering three ways" this artefact exists to prevent.
_WRAPPER_CHARS = len(TEMPLATE.replace("{packet}", ""))
FAKE_BUDGET = Budget(
    context=8192,
    packet_max=8192 - 2048 - _WRAPPER_CHARS,
    template_overhead=_WRAPPER_CHARS,
    output_reserve=2048,
).validate()
