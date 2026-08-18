# SPDX-License-Identifier: MIT
"""Tests for scenario template identity, per RFC-0003.

A template is the unit of the grouped split, so what counts as "the same
template" is what the split rests on. RFC-0003 makes templates data files with
stable ids precisely so that identity is auditable from artefacts rather than
from trust in the process that produced them.
"""

import json
from pathlib import Path

from consylr.templates import Template, check, load

FAMILIES = frozenset({"clean_match", "fee_at_source", "cause_not_established"})


def write(tmp_path: Path, name: str, body: dict[str, object]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(body))
    return p


def a_template(id: str = "t-001", family: str = "clean_match", **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": id,
        "family": family,
        "left": {"description": "consultancy retainer", "amount": "1000.00"},
        "right": {"description": "retainer settlement", "amount": "1000.00"},
        "policy": ["P-1: retainers settle at face value"],
    }
    body.update(over)
    return body


def test_a_well_formed_template_loads() -> None:
    t = Template.from_mapping(a_template())
    assert t.id == "t-001" and t.family == "clean_match"


def test_identity_comes_from_content_not_from_the_declared_id() -> None:
    # The id is a label over the content, not the identity itself. If it were the
    # identity, committing the same scenario twice under two ids would give the
    # split two distinct templates and the eval case would already be in train.
    same = Template.from_mapping(a_template(id="t-001"))
    aliased = Template.from_mapping(a_template(id="t-999"))
    assert same.fingerprint == aliased.fingerprint


def test_a_changed_field_changes_the_fingerprint() -> None:
    original = Template.from_mapping(a_template())
    edited = Template.from_mapping(a_template(policy=["P-1: retainers settle net of fees"]))
    assert original.fingerprint != edited.fingerprint


def test_key_order_does_not_change_the_fingerprint() -> None:
    # Otherwise a reformatting of the data file reads as a new template, and a
    # corpus regenerated after it no longer matches the one the numbers came from.
    a = Template.from_mapping({"id": "t-1", "family": "clean_match", "left": 1, "right": 2})
    b = Template.from_mapping({"family": "clean_match", "right": 2, "left": 1, "id": "t-1"})
    assert a.fingerprint == b.fingerprint


def test_two_ids_for_one_scenario_are_reported() -> None:
    # The first of the three ways a partition check passes on a corpus that leaks.
    templates = [
        Template.from_mapping(a_template(id="t-001")),
        Template.from_mapping(a_template(id="t-002")),
    ]
    v = next(x for x in check(templates, FAMILIES) if x.code == "aliased_template")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_one_id_used_twice_is_reported() -> None:
    templates = [
        Template.from_mapping(a_template(id="t-001")),
        Template.from_mapping(a_template(id="t-001", family="fee_at_source")),
    ]
    assert "duplicate_template_id" in [x.code for x in check(templates, FAMILIES)]


def test_a_family_outside_the_taxonomy_is_reported() -> None:
    templates = [Template.from_mapping(a_template(family="vibes"))]
    v = next(x for x in check(templates, FAMILIES) if x.code == "unknown_family")
    assert "vibes" in v.detail


def test_a_template_missing_a_required_field_is_reported_not_guessed() -> None:
    body = a_template()
    del body["policy"]
    v = next(x for x in check([Template.from_mapping(body)], FAMILIES) if x.code == "missing_field")
    assert "policy" in v.detail


def test_a_distinct_scenario_is_not_flagged() -> None:
    templates = [
        Template.from_mapping(a_template(id="t-001")),
        Template.from_mapping(a_template(id="t-002", family="fee_at_source", policy=["P-2: fees"])),
    ]
    assert check(templates, FAMILIES) == []


def test_templates_load_from_data_files_on_disk(tmp_path: Path) -> None:
    # RFC-0003: a template is a data file, not a function, so that "no template
    # crossed the boundary" is checkable by a reader rather than trusted.
    write(tmp_path, "a.json", a_template(id="t-001"))
    write(tmp_path, "b.json", a_template(id="t-002", family="fee_at_source", policy=["P-2: fees"]))
    loaded = load(tmp_path)
    assert sorted(t.id for t in loaded) == ["t-001", "t-002"]


def test_a_data_file_that_is_not_a_template_is_refused_loudly(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json")
    try:
        load(tmp_path)
    except ValueError as e:
        assert "broken.json" in str(e)
    else:  # pragma: no cover - the assertion is that this branch is unreachable
        raise AssertionError("a malformed template file must fail the build, not be skipped")


# --- the identity that survives a paraphrase ---------------------------------


def test_two_templates_one_paraphrase_apart_share_a_structural_identity() -> None:
    # Exact content identity cannot catch this: the scenario is duplicated and
    # then reworded, so the fingerprints differ and the split sees two templates.
    # RFC-0003 bounds paraphrase to free-text surface fields and forbids it
    # touching a label, a number, a reference or a correspondence decision — so
    # an identity taken over everything it may *not* touch is invariant under it.
    original = Template.from_mapping(a_template(id="t-001"))
    reworded = Template.from_mapping(
        a_template(
            id="t-002",
            left={"description": "advisory retainer fee", "amount": "1000.00"},
            right={"description": "payment against retainer", "amount": "1000.00"},
        )
    )
    assert original.fingerprint != reworded.fingerprint
    assert original.structural_fingerprint == reworded.structural_fingerprint


def test_a_changed_amount_changes_the_structural_identity() -> None:
    original = Template.from_mapping(a_template())
    edited = Template.from_mapping(
        a_template(right={"description": "retainer settlement", "amount": "900.00"})
    )
    assert original.structural_fingerprint != edited.structural_fingerprint


def test_a_changed_policy_reference_changes_the_structural_identity() -> None:
    original = Template.from_mapping(a_template())
    edited = Template.from_mapping(a_template(policy=["P-2: retainers settle at face value"]))
    assert original.structural_fingerprint != edited.structural_fingerprint


def test_near_duplicate_templates_are_reported() -> None:
    templates = [
        Template.from_mapping(a_template(id="t-001")),
        Template.from_mapping(
            a_template(id="t-002", left={"description": "advisory retainer", "amount": "1000.00"})
        ),
    ]
    v = next(x for x in check(templates, FAMILIES) if x.code == "near_duplicate_template")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_an_alias_is_reported_as_an_alias_rather_than_twice() -> None:
    # An exact duplicate collides on both identities. Reporting it under both
    # codes would make one defect look like two.
    templates = [
        Template.from_mapping(a_template(id="t-001")),
        Template.from_mapping(a_template(id="t-002")),
    ]
    codes = [x.code for x in check(templates, FAMILIES)]
    assert codes.count("aliased_template") == 1
    assert "near_duplicate_template" not in codes
