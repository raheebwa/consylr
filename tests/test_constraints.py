# SPDX-License-Identifier: MIT
"""Every constraint the specifications state, and the code that enforces it.

This exists because one defect class produced four separate instances in a
single day: a rule written down, agreed, and never made into a gate.

- `identity.check` — the duplicate-scenario audit — had no production caller.
- Near-duplicate detection was listed in RFC-0003's audit stack; the audit
  command does not exist, and an exam shipped with 63% duplicate packets.
- The 5-10 record Gate 1 packet size sat in RFC-0001 and RFC-0003 and no code
  read it; half an exam was outside the range.
- `quota.check` and `templates.check` likewise had no caller, so RFC-0002's
  certainty bands and the closed-world template rules were enforced by nothing.

Each was found by accident, one at a time, after it had already cost something.
The table below is the exhaustive version of that search, and this test is what
stops it becoming a document that drifts: an enforcer named here has to exist,
and the module holding it has to be reachable from production code rather than
only from tests.

**An empty enforcer is allowed and must carry a reason.** A constraint measured
rather than enforced is a legitimate state; a constraint nobody decided about is
not.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class Constraint:
    """One specified rule and the code that holds it."""

    source: str
    rule: str
    #: `module.symbol`, or empty when nothing enforces it.
    enforcer: str
    #: The violation code a corpus sees, or why there is none.
    note: str


ENFORCED = [
    # --- RFC-0001, the output contract -----------------------------------
    Constraint(
        "RFC-0001",
        "`open[].need` at most 120 characters",
        "consylr.schema.NEED_MAX",
        "need_too_long",
    ),
    Constraint(
        "RFC-0001", "output fields are a closed set", "consylr.schema.FIELDS", "unknown_field"
    ),
    Constraint(
        "RFC-0001",
        "certainty is one of three words, never a number",
        "consylr.schema.CERTAINTIES",
        "bad_certainty",
    ),
    Constraint(
        "RFC-0001",
        "exception kind is from the frozen family list",
        "consylr.schema.KINDS",
        "bad_kind",
    ),
    Constraint("RFC-0001", "disposition act is one of four", "consylr.schema.ACTS", "bad_act"),
    Constraint(
        "RFC-0001",
        "every cited identifier resolves in the packet",
        "consylr.schema.validate",
        "unresolved_id",
    ),
    Constraint(
        "RFC-0001",
        "residue is exactly the records in no supported or ambiguous match",
        "consylr.schema.validate",
        "residue_wrong",
    ),
    Constraint(
        "RFC-0001",
        "a request disposition is covered by an open entry",
        "consylr.schema.validate",
        "dangling_request",
    ),
    Constraint(
        "RFC-0001", "a supported claim cites evidence", "consylr.schema.validate", "uncited_claim"
    ),
    Constraint(
        "RFC-0001",
        "a Gate 1 packet holds 5 to 10 records",
        "consylr.cases.PACKET_RECORDS",
        "packet_too_small / packet_too_large",
    ),
    Constraint(
        "RFC-0001",
        "rendered prompt within its token cap",
        "consylr.budget.check",
        "prompt_over_budget",
    ),
    Constraint("RFC-0001", "generation headroom reserved", "consylr.budget.check", "headroom_lost"),
    # --- RFC-0002, the taxonomy and the quotas ---------------------------
    Constraint(
        "RFC-0002",
        "a case belongs to exactly one family",
        "consylr.templates.check",
        "unknown_family; one family per template by construction",
    ),
    Constraint(
        "RFC-0002",
        "clearly-supported cases are 40-50% of the mix",
        "consylr.quota.check",
        "supported_share_low / supported_share_high",
    ),
    Constraint(
        "RFC-0002",
        "cause_not_established is 10-15% of the mix",
        "consylr.quota.check",
        "abstention_share_low / abstention_share_high",
    ),
    Constraint(
        "RFC-0002",
        "every family present in measurable numbers",
        "consylr.quota.check",
        "family_below_floor",
    ),
    Constraint(
        "RFC-0002",
        "a family's answer cannot contradict its certainty",
        "consylr.quota.check",
        "contradictory_certainty",
    ),
    # --- RFC-0003, the generator -----------------------------------------
    Constraint(
        "RFC-0003",
        "a template is a closed world",
        "consylr.templates.shape_violations",
        "unknown_field / missing_field / bad_type",
    ),
    Constraint(
        "RFC-0003",
        "a packet is within the packet allowance",
        "consylr.budget.check_packet",
        "packet_over_budget",
    ),
    Constraint(
        "RFC-0003",
        "every case from one template lands in exactly one role",
        "consylr.corpus.check",
        "packet_in_two_roles",
    ),
    Constraint(
        "RFC-0003",
        "no two cases share a packet under different answers",
        "consylr.corpus.check",
        "contradictory_ground_truth",
    ),
    Constraint(
        "RFC-0003",
        "near-duplicate detection over the corpus",
        "consylr.corpus.check",
        "duplicate_packet",
    ),
    Constraint(
        "RFC-0003",
        "one scenario is not two templates",
        "consylr.identity.check",
        "duplicate_scenario",
    ),
    Constraint(
        "RFC-0003",
        "a template that emits no case is reported",
        "consylr.identity.check",
        "unbuildable_template",
    ),
    Constraint(
        "RFC-0003",
        "the answer describes the packet it was built from",
        "consylr.cases._prove_effect",
        "raises; a defect in the generator, not the corpus",
    ),
    Constraint(
        "RFC-0003",
        "the packet carries the cause its family is graded on",
        "consylr.cases._prove_cause",
        "raises; authoring lint, backed by the byte check",
    ),
    Constraint(
        "RFC-0003",
        "a corpus binds to the prompt template it was rendered against",
        "consylr.prompt.DIGEST",
        "recorded per case as prompt_digest",
    ),
    Constraint(
        "RFC-0003",
        "an exam cannot silently change between runs",
        "consylr.corpus.content_digest",
        "asserted by a scoring run before it scores",
    ),
    Constraint(
        "RFC-0003",
        "the budget's own numbers fit the context",
        "consylr.budget.Budget.validate",
        "raises at construction",
    ),
    Constraint(
        "RFC-0003",
        "amounts are written one way",
        "consylr.money.canonical",
        "applied to every record at construction",
    ),
]

#: Specified, and deliberately not enforced. Each carries the reason, because a
#: constraint measured rather than gated is a legitimate state and a constraint
#: nobody decided about is not.
UNENFORCED = [
    Constraint(
        "RFC-0001",
        "structured-output parse rate at or above 99%",
        "",
        "a property of the trained model, measured by the evaluation (#23), not of a corpus",
    ),
    Constraint(
        "RFC-0001",
        "amount/reference/date exact-copy rate at or above 99.5%",
        "",
        "measured at evaluation; the corpus cannot constrain what the model copies",
    ),
    Constraint(
        "RFC-0001",
        "evidence citation precision at or above 98%",
        "",
        "measured at evaluation (#23); the corpus side is `_clean` citing its own records",
    ),
    Constraint(
        "RFC-0001",
        "correct abstention at or above 90%, false abstention under 5%",
        "",
        "measured at evaluation (#16); the corpus side is the quota bands above",
    ),
    Constraint(
        "RFC-0001",
        "output fits inside 256 generation tokens",
        "",
        "a property of model output; the corpus side is the reserved headroom",
    ),
    Constraint(
        "RFC-0003",
        "300 to 500 gold scenario templates",
        "",
        "a target for corpus size, not a property of a valid corpus; 350 authored",
    ),
    Constraint(
        "RFC-0003",
        "8,000 to 15,000 training examples",
        "",
        "NOT MET at Gate 1 and stated plainly: a template yields as many distinct cases "
        "as its deformation can distinguish, so this needs per-case instantiation (#20). "
        "Padding to the number would mean duplicates, which the writer now refuses.",
    ),
    Constraint(
        "RFC-0003",
        "the sealed set is never paraphrased",
        "",
        "paraphrase is not implemented; the refusal cannot be violated by absent code",
    ),
]


@pytest.mark.parametrize("constraint", ENFORCED, ids=lambda c: c.rule[:48])
def test_every_enforced_constraint_names_code_that_exists(constraint: Constraint) -> None:
    module_name, _, symbol = constraint.enforcer.rpartition(".")
    # `Budget.validate` and friends: walk the dotted path rather than assuming
    # two segments.
    parts = constraint.enforcer.split(".")
    for split in range(len(parts) - 1, 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        target: object = module
        for attribute in parts[split:]:
            target = getattr(target, attribute)
        return
    raise AssertionError(f"{constraint.enforcer} names nothing importable ({module_name}/{symbol})")


@pytest.mark.parametrize("constraint", ENFORCED, ids=lambda c: c.rule[:48])
def test_every_enforcing_module_is_reachable_from_production(constraint: Constraint) -> None:
    """The failure mode this file exists for.

    A check importable only from tests protects nothing. `identity.check`,
    `quota.check` and `templates.check` were each in exactly that state, and
    each was found by accident after it had cost something.
    """
    module = constraint.enforcer.split(".")[1]
    package = pathlib.Path(__file__).resolve().parent.parent / "consylr"

    def imports(source: str) -> bool:
        """Both import forms, because missing one is a false clean bill.

        `from consylr.money import canonical` and `from consylr import money`
        are the same dependency, and a check that saw only the first would have
        reported four live modules as unreachable.
        """
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == f"consylr.{module}":
                    return True
                if node.module == "consylr" and any(a.name == module for a in node.names):
                    return True
            elif isinstance(node, ast.Import):
                if any(a.name == f"consylr.{module}" for a in node.names):
                    return True
        return False

    importers = [
        path.name
        for path in package.glob("*.py")
        if path.stem != module and imports(path.read_text())
    ]
    assert importers, f"consylr.{module} is imported by no other module in the package"


def test_every_unenforced_constraint_carries_a_reason() -> None:
    for constraint in UNENFORCED:
        assert not constraint.enforcer, f"{constraint.rule} has an enforcer; move it up"
        assert len(constraint.note) > 40, f"{constraint.rule} has no reason worth the name"


def test_the_table_covers_both_lists_without_overlap() -> None:
    rules = [c.rule for c in (*ENFORCED, *UNENFORCED)]
    assert len(rules) == len(set(rules)), "a constraint appears twice"
