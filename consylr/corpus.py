# SPDX-License-Identifier: MIT
"""The corpus audit, and the writer that will not write without it.

These are the checks the exam's integrity actually rests on, and they are
deliberately dull. They compare the artefacts that will be written — every one
of them, byte for byte — rather than reasoning about the templates that produced
them.

Two earlier attempts put this property inside a cleverer component and each was
defeated by that component being subtly wrong. The last one sampled three probe
cases per template, which covered a third to a half of a template's pairs and
always the same ones, so two templates differing on an unsampled pair emitted
identical packets under contradictory answers with every gate clean. Detection
was luck.

Nothing here needs the identity model to be well designed, the probe to sample
well, or a policy line to be read correctly. It can only be defeated by two
identical packets carrying different answers, which is the thing itself.

**The writer is the caller.** The checks this replaces were library functions
nothing called — a `grep` for production imports of them found none — so a
corpus could reach disk having been audited by nobody. A check someone must
remember to run is the same defect one level up, so there is no way to write a
corpus that does not audit it first, and no audit offered alongside the writer
for a caller to skip.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from consylr.cases import DEFORMATIONS, Case
from consylr.identity import check as identity_check
from consylr.prompt import DIGEST
from consylr.quota import Plan
from consylr.quota import check as quota_check
from consylr.templates import Template
from consylr.templates import check as templates_check
from consylr.violation import Violation


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _named(ids: Iterable[str]) -> str:
    return ", ".join(repr(i) for i in sorted(set(ids)))


def check(
    cases: Iterable[Case],
    *,
    templates: Iterable[Template] | None = None,
    plan: Plan | None = None,
    held_out: Iterable[Mapping[str, Any]] | None = None,
) -> list[Violation]:
    """Every way a corpus is unfit to be trained on or examined with.

    Exhaustive over the cases given, because a corpus is a finite list of
    artefacts and comparing all of them costs a dictionary.

    `templates.check`, `identity.check` and `quota.check` run from here because
    they had no production caller at all — the closed-world shape rules, the
    duplicate-scenario audit and RFC-0002's certainty bands were reachable only
    from tests. Three separate checks written, agreed, and never made into
    gates; the count is why this is now the one place a corpus is assembled and
    the one place everything is asked.
    """
    rows = list(cases)
    if not rows:
        return [Violation("empty_corpus", "a corpus with no cases teaches and measures nothing")]

    violations: list[Violation] = []

    if templates is not None:
        held = list(templates)
        violations.extend(templates_check(held, frozenset(DEFORMATIONS)))
        violations.extend(identity_check(held))

    if plan is not None:
        # The certainty bands are a property of a mix, so they are asked of a
        # corpus rather than of a case. A sealed set has its own distribution
        # and is not held to the training quota, which is why this is optional
        # rather than absent.
        violations.extend(quota_check([case.meta for case in rows], plan))

    for case in rows:
        for problem in case.violations:
            violations.append(
                Violation(
                    problem.code,
                    f"{case.meta.get('template_id', '<unknown>')}: {problem.detail}",
                    problem.case,
                )
            )

    answers: dict[str, dict[str, list[str]]] = {}
    roles: dict[str, dict[str, list[str]]] = {}
    for case in rows:
        packet = _canonical(case.packet)
        answers.setdefault(packet, {}).setdefault(_canonical(case.expected), []).append(
            str(case.meta.get("template_id", ""))
        )
        roles.setdefault(packet, {}).setdefault(str(case.meta.get("role", "")), []).append(
            str(case.meta.get("template_id", ""))
        )

    for by_answer in answers.values():
        if len(by_answer) > 1:
            violations.append(
                Violation(
                    "contradictory_ground_truth",
                    f"{_named(i for ids in by_answer.values() for i in ids)} produce one packet "
                    f"under {len(by_answer)} different answers; the model is trained on one and "
                    "examined on the other, and no packet distinguishes them",
                )
            )
            continue

        # Same packet, same answer: not a contradiction, and not a corpus
        # either. The first sealed set held 196 packets and 73 distinct ones,
        # so a metric computed on it weighted the repeated cases sevenfold —
        # measurement with a bent ruler. The count is named rather than
        # absorbed, because a thin template set otherwise reads as a large
        # corpus rather than as the same question asked repeatedly.
        ids = next(iter(by_answer.values()))
        if len(ids) > 1:
            violations.append(
                Violation(
                    "duplicate_packet",
                    f"{_named(ids)} produce one identical packet {len(ids)} times; every metric "
                    "computed on this corpus would weight it that many times over",
                )
            )

    # train x sealed, which no within-corpus check can see: the exam is a
    # different corpus, written earlier. A training packet identical to one in
    # it means the model is examined on what it was trained on.
    if held_out is not None:
        exam = {_canonical(packet) for packet in held_out}
        for case in rows:
            if _canonical(case.packet) in exam:
                violations.append(
                    Violation(
                        "packet_in_the_exam",
                        f"{case.meta.get('template_id', '<unknown>')} produces a packet the "
                        "sealed set already asks; the model would be examined on what it "
                        "was trained on",
                        str(case.meta.get("template_id", "")) or None,
                    )
                )

    for by_role in roles.values():
        if len(by_role) > 1:
            violations.append(
                Violation(
                    "packet_in_two_roles",
                    f"{_named(i for ids in by_role.values() for i in ids)} put one packet in "
                    f"{', '.join(sorted(by_role))}; whatever the partition believed, this is the "
                    "same question asked on both sides of it",
                )
            )

    return violations


def content_digest(directory: Path) -> str:
    """One digest over every packet in a corpus, order-independent.

    What a scoring run asserts before it scores. An exam that can silently
    change between runs is not an exam, and the seed alone does not establish
    that the set on disk is the set a number was computed on — a file edited
    afterwards still carries the seed in its metadata.

    Over the packets rather than the whole tree: the packets are what the model
    is asked, and metadata a run adds afterwards should not read as the exam
    having changed.
    """
    packets = sorted(
        hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*/packet.json")
    )
    return hashlib.sha256(" ".join(packets).encode()).hexdigest()


def write(
    directory: Path,
    cases: Iterable[Case],
    *,
    templates: Iterable[Template],
    plan: Plan | None = None,
    held_out: Iterable[Mapping[str, Any]] | None = None,
) -> list[Path]:
    """Write a corpus, or refuse to.

    There is no unaudited path to disk. The audit is not a step a caller
    performs before calling this — it is what this does first, and a corpus that
    fails it leaves nothing behind.
    """
    rows = list(cases)
    problems = check(rows, templates=templates, plan=plan, held_out=held_out)
    if problems:
        raise ValueError(
            "this corpus was not written; "
            + "; ".join(f"{v.code}: {v.detail}" for v in problems[:10])
            + (f" (and {len(problems) - 10} more)" if len(problems) > 10 else "")
        )

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for case in rows:
        name = f"{case.meta['template_id']}-{case.meta['case_index']:04d}"
        home = directory / name
        home.mkdir(parents=True, exist_ok=True)
        # The interface the case was rendered against, recorded per case. RFC-0003
        # binds a corpus to a specific prompt template, and a corpus whose
        # recorded digest does not match the artefact fails its audit.
        meta = {**case.meta, "prompt_digest": DIGEST}
        (home / "packet.json").write_text(_canonical(case.packet), encoding="utf-8")
        (home / "expected.json").write_text(_canonical(case.expected), encoding="utf-8")
        (home / "meta.json").write_text(_canonical(meta), encoding="utf-8")
        written.append(home)
    return written
