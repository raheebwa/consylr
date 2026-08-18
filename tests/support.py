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

from consylr.templates import Template

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
            {"id": "P-2", "text": "Settlement fees are deducted at source."},
        ],
        "documents": [{"id": "D-1", "text": "Remittance advice for March 2026."}],
    }
    body.update(over)
    return body


def a_template(id: str = "t-001", family: str = "clean_match", **over: Any) -> Template:
    return Template.from_mapping(template_body(id, family, **over))
