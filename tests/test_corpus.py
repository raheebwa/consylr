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

from consylr.corpus import check, content_digest, template_digest, write
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
        write(tmp_path, rows, templates=[template])
    assert list(tmp_path.iterdir()) == [], "a refused corpus left files behind"


def test_a_clean_corpus_is_written_as_rfc_0003_describes(tmp_path: Path) -> None:
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(2)]
    rows = [built(t, case_index=0, role="train") for t in templates]
    write(tmp_path, rows, templates=templates)

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
    template = a_template(id="t-001")
    rows = [built(template, budget=tiny, tokeniser=PerCharacter())]
    assert rows[0].violations
    with pytest.raises(ValueError, match="packet_over_budget"):
        write(tmp_path, rows, templates=[template])


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
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(4)]
    rows = [built(t, case_index=0, role="holdout") for t in templates]
    write(tmp_path, rows, templates=templates)
    before = content_digest(tmp_path)

    assert before == content_digest(tmp_path), "the digest moved without the corpus moving"

    edited = next(tmp_path.iterdir()) / "packet.json"
    edited.write_text(edited.read_text().replace("100.00", "999.00"), encoding="utf-8")
    assert content_digest(tmp_path) != before


def test_the_content_digest_does_not_depend_on_the_order_files_are_read(tmp_path: Path) -> None:
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(3)]
    rows = [built(t, case_index=0, role="holdout") for t in templates]
    write(tmp_path, rows, templates=templates)
    first = content_digest(tmp_path)
    for case_dir in tmp_path.iterdir():
        case_dir.touch()
    assert content_digest(tmp_path) == first


# --- every check reaches the corpus through the one caller -------------------


def test_a_corpus_cannot_be_written_without_the_templates_it_came_from() -> None:
    """Three checks had no production caller at all.

    `templates.check`, `identity.check` and `quota.check` were reachable only
    from tests — so the closed-world shape rules, the duplicate-scenario audit
    and RFC-0002's certainty bands were enforced by nothing. That is the same
    class as the two found earlier today, and the count is why this is now
    structural: a corpus is written from templates, so the writer takes them and
    checks them.
    """
    rows = [built(a_template(id="t-001"), case_index=0, role="train")]
    with pytest.raises(TypeError):
        write(Path("/tmp/never"), rows)  # type: ignore[call-arg]


def test_a_template_defect_stops_the_corpus(tmp_path: Path) -> None:
    body = template_body(id="t-001")
    body["left"] = [{k: v for k, v in r.items() if k != "amount"} for r in body["left"]]
    broken = Template.from_mapping(body)
    good = a_template(id="t-002", amount="900.00")
    rows = [built(good, case_index=0, role="train")]
    with pytest.raises(ValueError, match="missing_field"):
        write(tmp_path, rows, templates=[good, broken])


def test_a_quota_breach_stops_the_corpus_when_a_plan_is_given(tmp_path: Path) -> None:
    from consylr.quota import Plan

    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(4)]
    rows = [built(t, case_index=0, role="train") for t in templates]
    plan = Plan(families=frozenset({"clean_match"}), family_floor=1)
    # Every case here is clean_match/supported: 100% clearly supported, well
    # above RFC-0002's 65-75% band.
    with pytest.raises(ValueError, match="supported_share_high"):
        write(tmp_path, rows, templates=templates, plan=plan)


def test_a_corpus_with_its_templates_and_no_plan_is_written(tmp_path: Path) -> None:
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(3)]
    rows = [built(t, case_index=0, role="train") for t in templates]
    assert len(write(tmp_path, rows, templates=templates)) == 3


def test_a_training_packet_that_is_in_the_exam_is_refused(tmp_path: Path) -> None:
    """train x sealed is the comparison that matters most.

    Within-corpus checks cannot see it: the exam is a different corpus, written
    earlier, and a training packet identical to one in it means the model is
    examined on what it was trained on — the leak that raises measured accuracy
    rather than lowering it.
    """
    template = a_template(id="t-001")
    exam = built(template, case_index=0, role="holdout")
    training = built(template, case_index=0, role="train")

    v = next(
        x
        for x in check([training], templates=[template], held_out=[exam.packet])
        if x.code == "packet_in_the_exam"
    )
    assert "t-001" in v.detail


def test_a_training_corpus_disjoint_from_the_exam_passes(tmp_path: Path) -> None:
    exam_template = a_template(id="t-001")
    exam = built(exam_template, case_index=0, role="holdout")
    templates = [a_template(id=f"t-{i:03d}", amount=f"{200 + i}.00") for i in range(3)]
    rows = [built(t, case_index=0, role="train") for t in templates]
    assert check(rows, templates=templates, held_out=[exam.packet]) == []


def test_the_template_digest_covers_the_directory(tmp_path: Path) -> None:
    """`docs/sealed-set.md` records a template digest as "sha256 over the sorted
    per-file digests of `templates/`". Nothing computed it, so the document
    described enforcement that did not exist — the nastier variant of the
    written-down-but-never-gated defect, because the checklist only covers what
    someone remembered to put on it."""
    (tmp_path / "a.json").write_text('{"id": "a"}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": "b"}', encoding="utf-8")
    first = template_digest(tmp_path)
    assert len(first) == 64
    assert template_digest(tmp_path) == first


def test_it_is_order_independent_but_content_sensitive(tmp_path: Path) -> None:
    """Renaming a file must not change the digest of the same set of templates;
    editing one must."""
    (tmp_path / "a.json").write_text('{"id": "a"}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"id": "b"}', encoding="utf-8")
    before = template_digest(tmp_path)

    (tmp_path / "a.json").rename(tmp_path / "z.json")
    assert template_digest(tmp_path) == before, "a rename is not a change of content"

    (tmp_path / "z.json").write_text('{"id": "a", "edited": true}', encoding="utf-8")
    assert template_digest(tmp_path) != before, "an edit must move the digest"


def test_an_added_template_moves_the_digest(tmp_path: Path) -> None:
    """The failure the per-template fingerprints cannot see: a case references
    the templates it used, so a template added and never referenced leaves every
    fingerprint matching while the directory has changed."""
    (tmp_path / "a.json").write_text('{"id": "a"}', encoding="utf-8")
    before = template_digest(tmp_path)
    (tmp_path / "b.json").write_text('{"id": "b"}', encoding="utf-8")
    assert template_digest(tmp_path) != before


def test_a_directory_with_no_templates_is_refused(tmp_path: Path) -> None:
    """A digest over nothing is a well-formed sixty-four characters that asserts
    the absence of what it was asked to describe."""
    with pytest.raises(ValueError):
        template_digest(tmp_path)
