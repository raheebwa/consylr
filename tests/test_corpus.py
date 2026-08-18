# SPDX-License-Identifier: MIT
"""Tests for the corpus audit and the writer, per RFC-0003.

These are the checks the exam's integrity actually rests on, and they are
deliberately dull. They compare the artefacts that will be written — every one
of them, byte for byte — rather than reasoning about the templates that produced
them. Nothing here needs the identity model to be well designed, the probe to
sample well, or a policy line to be read correctly.

That is the point. Two earlier attempts put the integrity property inside a
clever component and were defeated by the component being subtly wrong; this
one can only be defeated by two identical packets carrying different answers,
which is the thing itself.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from consylr.corpus import check, content_digest, write
from consylr.templates import Template
from tests.support import PerCharacter, a_template, built, template_body

ROLES = ("train", "holdout")


def case_rows(template: Template, role: str, indices: tuple[int, ...] = (0,)) -> list[Any]:
    """Cases from one template.

    One index by default: a `clean_match` template yields exactly one distinct
    case however many are asked for, and asking for two now produces a duplicate
    the writer refuses — which is the behaviour, not an inconvenience.
    """
    return [built(template, case_index=i, role=role) for i in indices]


def test_a_clean_corpus_passes() -> None:
    rows = case_rows(a_template(id="t-001"), "train") + case_rows(
        a_template(id="t-002", amount="900.00"), "holdout"
    )
    assert check(rows) == []


def test_a_corpus_of_one_case_per_distinct_template_passes() -> None:
    rows = [
        built(a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00"), case_index=0, role="train")
        for i in range(5)
    ]
    assert check(rows) == []


def test_one_packet_under_two_answers_is_fatal_wherever_it_occurs() -> None:
    """Exhaustive over the built corpus, not sampled from a probe.

    The earlier check compared three probe indices per template, which sampled a
    third to a half of a template's pairs and always the same ones — so two
    templates differing on an unsampled pair passed while emitting identical
    packets under contradictory answers. Comparing what will actually be written
    has no unsampled anything.
    """
    line = [{"id": "P-1", "text": "A withholding tax fee is deducted before remittance."}]
    body = template_body(pairs=1)
    fee = Template.from_mapping(
        {**body, "id": "t-fee", "family": "fee_at_source", "policy": line, "cause": "P-1"}
    )
    tax = Template.from_mapping(
        {**body, "id": "t-tax", "family": "withholding", "policy": line, "cause": "P-1"}
    )
    rows = case_rows(fee, "train") + case_rows(tax, "train")
    v = next(x for x in check(rows) if x.code == "contradictory_ground_truth")
    assert "t-fee" in v.detail and "t-tax" in v.detail


def test_one_packet_in_both_roles_is_fatal() -> None:
    # The leak, made exhaustive: whatever the partition believed, these two cases
    # are the same question asked on both sides of it.
    template = a_template(id="t-001")
    rows = case_rows(template, "train", (0,)) + case_rows(template, "holdout", (0,))
    v = next(x for x in check(rows) if x.code == "packet_in_two_roles")
    assert "train" in v.detail and "holdout" in v.detail


def test_the_same_packet_twice_in_one_role_is_not_a_leak() -> None:
    # A duplicate within a role wastes a row; it does not put an examined case in
    # training. Reporting it as a leak would inflate the count that means one.
    template = a_template(id="t-001")
    rows = case_rows(template, "train", (0,)) + case_rows(template, "train", (0,))
    assert "packet_in_two_roles" not in [x.code for x in check(rows)]


def test_an_empty_corpus_is_a_failure_not_a_vacuous_pass() -> None:
    assert check([]) != []


# --- the writer is the caller, and it cannot be bypassed ---------------------


def test_a_corpus_that_fails_its_audit_does_not_reach_disk(tmp_path: Path) -> None:
    """The check that has a caller on the path, rather than beside it.

    The previous backstops were library functions nothing called: `grep` for
    production imports found none. A check someone must remember to run is the
    same defect one level up, so the writer runs it and refuses.
    """
    template = a_template(id="t-001")
    rows = case_rows(template, "train", (0,)) + case_rows(template, "holdout", (0,))
    with pytest.raises(ValueError, match="packet_in_two_roles"):
        write(tmp_path, rows)
    assert list(tmp_path.iterdir()) == [], "a refused corpus left files behind"


def test_a_clean_corpus_is_written_as_rfc_0003_describes(tmp_path: Path) -> None:
    rows = [
        built(a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00"), case_index=0, role="train")
        for i in range(2)
    ]
    write(tmp_path, rows)

    written = sorted(p.name for p in tmp_path.iterdir())
    assert len(written) == len(rows)
    for case_dir in tmp_path.iterdir():
        assert sorted(p.name for p in case_dir.iterdir()) == [
            "expected.json",
            "meta.json",
            "packet.json",
        ]
        meta = json.loads((case_dir / "meta.json").read_text())
        assert meta["template_id"].startswith("t-")
        assert meta["role"] == "train"
        assert meta["prompt_digest"], "a case must record the interface it was rendered against"


def test_a_case_carrying_violations_does_not_reach_disk(tmp_path: Path) -> None:
    # `Case.violations` is the builder's verdict, and the writer is the caller
    # that was always supposed to act on it.
    from consylr.budget import Budget

    tiny = Budget(context=1000, packet_max=50, template_overhead=0, output_reserve=100)
    rows = [built(a_template(id="t-001"), budget=tiny, tokeniser=PerCharacter())]
    assert rows[0].violations
    with pytest.raises(ValueError, match="packet_over_budget"):
        write(tmp_path, rows)


def test_the_same_packet_twice_in_one_corpus_is_refused() -> None:
    """The check that was missing, one over from the one we built.

    RFC-0003 lists near-duplicate detection in the audit command's stack, and
    the audit command does not exist — the same no-caller class closed for
    contradictions and not for duplicates. sealed-v1 was written with 196
    packets and 73 distinct ones: 63% duplicates, the most repeated appearing
    seven times, so every metric computed on it would have carried a hidden
    sevenfold weighting on those cases.

    It is the comparison already being made. Two cases sharing a packet are a
    contradiction when their answers differ and a duplicate when they agree, and
    neither belongs in a corpus.
    """
    template = a_template(id="t-001")
    rows = case_rows(template, "train", (0,)) + case_rows(template, "train", (0,))
    v = next(x for x in check(rows) if x.code == "duplicate_packet")
    assert "t-001" in v.detail


def test_the_duplicate_report_says_how_many_so_template_poverty_is_visible() -> None:
    # Absorbed silently, a thin template set looks like a large corpus. Named,
    # it looks like what it is: the same question asked repeatedly.
    template = a_template(id="t-001")
    rows = case_rows(template, "train", (0,)) * 4
    v = next(x for x in check(rows) if x.code == "duplicate_packet")
    assert "4" in v.detail


def test_distinct_packets_in_one_corpus_pass() -> None:
    rows = case_rows(a_template(id="t-001"), "train", (0,)) + case_rows(
        a_template(id="t-002", amount="900.00"), "train", (0,)
    )
    assert [v.code for v in check(rows)] == []


# --- a corpus that can change between runs is not an exam --------------------


def test_the_content_digest_covers_every_packet(tmp_path: Path) -> None:
    """What #23 asserts before it scores anything.

    An exam that can silently change between runs is not an exam, and the seed
    alone does not establish that the set on disk is the set the numbers were
    computed on — a file edited afterwards still has the seed in its metadata.
    """
    rows = [
        built(a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00"), case_index=0, role="holdout")
        for i in range(4)
    ]
    write(tmp_path, rows)
    before = content_digest(tmp_path)

    assert before == content_digest(tmp_path), "the digest moved without the corpus moving"

    edited = next(tmp_path.iterdir()) / "packet.json"
    edited.write_text(edited.read_text().replace("100.00", "999.00"), encoding="utf-8")
    assert content_digest(tmp_path) != before


def test_the_content_digest_does_not_depend_on_the_order_files_are_read(tmp_path: Path) -> None:
    rows = [
        built(a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00"), case_index=0, role="holdout")
        for i in range(3)
    ]
    write(tmp_path, rows)
    first = content_digest(tmp_path)
    for case_dir in tmp_path.iterdir():
        case_dir.touch()
    assert content_digest(tmp_path) == first
