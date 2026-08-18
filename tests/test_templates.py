# SPDX-License-Identifier: MIT
"""Tests for scenario template identity, per RFC-0003.

A template is the unit of the grouped split, so what counts as "the same
template" is what the split rests on. RFC-0003 makes templates data files with
stable ids precisely so that identity is auditable from artefacts rather than
from trust in the process that produced them.

Every fixture here is in the shape `cases.build()` consumes. An earlier version
had its own shape, which the generator refuses — so the identity these tests
checked was an identity over a data model nothing in the product produces, and
they passed while the property was vacuous.
"""

import json
from pathlib import Path

import pytest

from consylr.templates import SURFACE_FIELDS, Template, check, load
from tests.support import FAMILIES, a_template, built, template_body


def test_the_fixture_is_something_the_generator_can_actually_build() -> None:
    """The test that would have caught the defect this file was rewritten for.

    Identity is a property of templates the product produces. Checked against
    any other shape it is a property of nothing.
    """
    assert built(a_template()).violations == []


def test_the_surface_fields_are_fields_a_real_template_has() -> None:
    """`SURFACE_FIELDS` must name keys that occur in the shape being hashed.

    It once named five keys, none of which appeared in any template the
    generator accepts. `_without_surface` therefore stripped nothing, the
    structural identity equalled the exact one, and the near-duplicate check
    could not fire — with every test green.
    """
    body = template_body()
    present: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            present.update(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(body)
    assert SURFACE_FIELDS & present, "no surface field occurs in a real template"
    assert {"party", "text"} <= SURFACE_FIELDS, "RFC-0003 names both as paraphrasable"


def test_a_well_formed_template_loads() -> None:
    t = a_template()
    assert t.id == "t-001" and t.family == "clean_match"


def test_identity_comes_from_content_not_from_the_declared_id() -> None:
    # The id is a label over the content, not the identity itself. If it were the
    # identity, committing the same scenario twice under two ids would give the
    # split two distinct templates and the eval case would already be in train.
    assert a_template(id="t-001").fingerprint == a_template(id="t-999").fingerprint


def test_a_changed_amount_changes_the_fingerprint() -> None:
    assert a_template().fingerprint != a_template(amount="900.00").fingerprint


def test_key_order_does_not_change_the_fingerprint() -> None:
    # Otherwise a reformatting of the data file reads as a new template, and a
    # corpus regenerated after it no longer matches the one the numbers came from.
    body = template_body()
    reordered = dict(reversed(list(body.items())))
    assert Template.from_mapping(body).fingerprint == Template.from_mapping(reordered).fingerprint


def test_two_ids_for_one_scenario_are_reported() -> None:
    templates = [a_template(id="t-001"), a_template(id="t-002")]
    v = next(x for x in check(templates, FAMILIES) if x.code == "aliased_template")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_one_id_used_twice_is_reported() -> None:
    templates = [a_template(id="t-001"), a_template(id="t-001", family="fee_at_source")]
    assert "duplicate_template_id" in [x.code for x in check(templates, FAMILIES)]


def test_a_family_outside_the_taxonomy_is_reported() -> None:
    v = next(x for x in check([a_template(family="vibes")], FAMILIES) if x.code == "unknown_family")
    assert "vibes" in v.detail


def test_a_template_missing_a_required_field_is_reported_not_guessed() -> None:
    body = template_body()
    del body["policy"]
    v = next(x for x in check([Template.from_mapping(body)], FAMILIES) if x.code == "missing_field")
    assert "policy" in v.detail


def test_a_distinct_scenario_is_not_flagged() -> None:
    templates = [
        a_template(id="t-001"),
        a_template(id="t-002", family="fee_at_source", amount="777.00"),
    ]
    assert check(templates, FAMILIES) == []


def test_templates_load_from_data_files_on_disk(tmp_path: Path) -> None:
    # RFC-0003: a template is a data file, not a function, so that "no template
    # crossed the boundary" is checkable by a reader rather than trusted.
    (tmp_path / "a.json").write_text(json.dumps(template_body(id="t-001")))
    (tmp_path / "b.json").write_text(json.dumps(template_body(id="t-002", amount="12.00")))
    assert sorted(t.id for t in load(tmp_path)) == ["t-001", "t-002"]


def test_a_data_file_that_is_not_a_template_is_refused_loudly(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json")
    with pytest.raises(ValueError, match="broken.json"):
        load(tmp_path)


def test_a_data_file_that_is_not_an_object_is_refused_loudly(tmp_path: Path) -> None:
    (tmp_path / "list.json").write_text("[1, 2, 3]")
    with pytest.raises(ValueError, match="list.json"):
        load(tmp_path)


# --- the identity that survives a paraphrase ---------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [("party", "Northwind Limited"), ("policy_text", "Face value settles invoices.")],
)
def test_a_reworded_scenario_keeps_its_structural_identity(field: str, value: str) -> None:
    # Exact content identity cannot catch this: the scenario is duplicated and
    # then reworded, so the fingerprints differ and the split sees two templates.
    # RFC-0003 bounds paraphrase to free-text surface fields and forbids it
    # touching a label, a number, a reference or a correspondence decision — so
    # an identity taken over everything it may *not* touch is invariant under it.
    original = a_template(id="t-001")
    reworded = a_template(id="t-002", **{field: value})
    assert original.fingerprint != reworded.fingerprint
    assert original.structural_fingerprint == reworded.structural_fingerprint


def test_a_changed_amount_changes_the_structural_identity() -> None:
    assert a_template().structural_fingerprint != a_template(amount="900.00").structural_fingerprint


def test_a_changed_record_count_changes_the_structural_identity() -> None:
    assert a_template().structural_fingerprint != a_template(pairs=3).structural_fingerprint


def test_a_changed_policy_identifier_changes_the_structural_identity() -> None:
    # The text of a policy line is paraphrasable; which line is cited is not.
    other = [{"id": "P-9", "text": "Invoices settle at face value."}]
    assert a_template().structural_fingerprint != a_template(policy=other).structural_fingerprint


def test_near_duplicate_templates_are_reported() -> None:
    templates = [a_template(id="t-001"), a_template(id="t-002", party="Northwind Limited")]
    v = next(x for x in check(templates, FAMILIES) if x.code == "near_duplicate_template")
    assert "t-001" in v.detail and "t-002" in v.detail


def test_an_alias_is_reported_as_an_alias_rather_than_twice() -> None:
    # An exact duplicate collides on both identities. Reporting it under both
    # codes would make one defect look like two.
    templates = [a_template(id="t-001"), a_template(id="t-002")]
    codes = [x.code for x in check(templates, FAMILIES)]
    assert codes.count("aliased_template") == 1
    assert "near_duplicate_template" not in codes


def test_a_further_copy_does_not_silence_the_near_duplicate_report() -> None:
    # The suppression once asked whether the ids appeared in *any* alias group,
    # so a fourth copy of one scenario made a defect that three had raised
    # disappear — a larger defect reporting less than a smaller one.
    templates = [
        a_template(id="t-a"),
        a_template(id="t-b"),
        a_template(id="t-c", party="Northwind Limited"),
        a_template(id="t-d", party="Northwind Limited"),
    ]
    codes = [x.code for x in check(templates, FAMILIES)]
    assert "near_duplicate_template" in codes


# --- frozen has to mean frozen ------------------------------------------------


def test_editing_the_mapping_a_template_was_made_from_cannot_change_its_identity() -> None:
    # `Template` is a frozen dataclass whose fingerprints were recomputed on
    # every read over a shallow copy of the caller's mapping. A template already
    # used to partition a corpus would then report a different identity to the
    # audit, surfacing as `template_drifted` against a file nobody edited.
    source = template_body()
    t = Template.from_mapping(source)
    before = (t.fingerprint, t.structural_fingerprint)
    source["left"][0]["amount"] = "9999.99"
    assert (t.fingerprint, t.structural_fingerprint) == before


def test_two_templates_with_one_id_and_different_bodies_are_not_equal() -> None:
    # Equality covering only (id, family) collapsed unrelated scenarios into one
    # set member, so a de-duplicating caller would drop a template silently.
    a = Template.from_mapping(template_body(id="t-001", amount="1.00"))
    b = Template.from_mapping(template_body(id="t-001", amount="2.00"))
    assert a != b
    assert len({a, b}) == 2


def test_two_templates_with_the_same_content_are_equal() -> None:
    assert a_template(id="t-001") == a_template(id="t-001")


def test_a_body_with_no_canonical_json_form_is_refused_rather_than_hashed() -> None:
    # `default=str` hashed whatever it was given. A set has no stable repr
    # across runs, so a template carrying one re-partitioned the corpus between
    # runs of a build that is supposed to be reproducible from a seed.
    with pytest.raises(TypeError):
        Template.from_mapping(template_body(extra={1, 2, 3}))


# --- loading is a build step, and a build step fails loudly -------------------


def test_a_directory_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nowhere"):
        load(tmp_path / "nowhere")


def test_a_directory_with_no_templates_is_refused(tmp_path: Path) -> None:
    # Returning an empty list let a build proceed with no scenarios at all.
    with pytest.raises(ValueError, match="no templates"):
        load(tmp_path)


def test_a_file_that_is_not_a_json_template_is_refused_rather_than_skipped(
    tmp_path: Path,
) -> None:
    # `*.json` is case-sensitive, so a directory of `.JSON`, `.jsonc` and
    # `.json5` files loaded zero templates and reported nothing.
    (tmp_path / "good.json").write_text(json.dumps(template_body()))
    (tmp_path / "t-002.JSON").write_text(json.dumps(template_body(id="t-002")))
    with pytest.raises(ValueError, match="t-002.JSON"):
        load(tmp_path)


def test_templates_nested_in_directories_are_found(tmp_path: Path) -> None:
    # RFC-0003 anticipates 300-500 templates; a flat directory is not the only
    # way anyone will lay that out.
    (tmp_path / "clean_match").mkdir()
    (tmp_path / "clean_match" / "a.json").write_text(json.dumps(template_body(id="t-001")))
    assert [t.id for t in load(tmp_path)] == ["t-001"]


def test_an_empty_template_set_is_a_failure_not_a_vacuous_pass() -> None:
    assert check([], FAMILIES) != []


def test_a_template_with_no_id_is_named_by_something_a_reader_can_act_on() -> None:
    # It was reported as "2 template(s) have no 'id': , " with a phantom alias
    # for the empty string — a message naming nothing, about a defect that is
    # only findable by reading every file.
    body = template_body()
    del body["id"]
    codes = [x.code for x in check([Template.from_mapping(body)], FAMILIES)]
    assert "missing_field" in codes
    assert "duplicate_template_id" not in codes


def test_a_changed_reference_changes_the_structural_identity() -> None:
    # A reference is exactly what RFC-0003 says a paraphrase may not touch, so
    # adding `ref` to the surface list would make two different scenarios one.
    other = [{"ref": "PO-9", "party": "Northwind Ltd", "date": "2026-03-02", "amount": "1000.00"}]
    changed = Template.from_mapping(template_body(pairs=1, left=other))
    assert a_template(pairs=1).structural_fingerprint != changed.structural_fingerprint


def test_a_changed_policy_id_alone_changes_the_structural_identity() -> None:
    # Only the identifier differs; the prose is untouched. Stripping `id` at
    # every depth would erase which policy line a case cites.
    body = template_body()
    renumbered = template_body()
    renumbered["policy"] = [{**p, "id": f"P-{9 + i}"} for i, p in enumerate(body["policy"])]
    assert (
        Template.from_mapping(body).structural_fingerprint
        != Template.from_mapping(renumbered).structural_fingerprint
    )


def test_a_template_does_not_share_state_with_the_mapping_it_was_made_from() -> None:
    # The fingerprints are computed once, so a shallow copy no longer moves them
    # — but `body` is read by the builder, and aliasing the caller's nested dicts
    # means an edit anywhere changes what gets built without changing identity.
    source = template_body()
    t = Template.from_mapping(source)
    source["left"][0]["amount"] = "9999.99"
    assert t.body["left"][0]["amount"] == "1000.00"


def test_a_missing_directory_says_it_is_missing_not_that_it_is_empty(tmp_path: Path) -> None:
    # "holds no templates" for a path that does not exist sends a reader looking
    # for files in a directory they have not created.
    with pytest.raises(ValueError, match="is not a directory"):
        load(tmp_path / "nowhere")


def test_templates_load_in_a_stable_order(tmp_path: Path) -> None:
    # The order templates are read in must not depend on the filesystem: nothing
    # downstream may vary with it, and a reader comparing two runs needs the
    # lists to line up.
    for name in ("m.json", "a.json", "z.json", "c.json"):
        (tmp_path / name).write_text(
            json.dumps(template_body(id=name[0], amount=f"{ord(name[0])}.00"))
        )
    assert [t.id for t in load(tmp_path)] == ["a", "c", "m", "z"]
