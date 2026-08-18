# SPDX-License-Identifier: MIT
"""Scenario templates and what makes two of them the same, per RFC-0003.

A template is a parameterised scenario in data with a stable id, interpreted by
the generator rather than expressed as code. That is not a storage preference:
the template is the unit of the grouped split, so "no template crossed the
boundary" has to be checkable from the artefacts by a reader who does not trust
the process that produced them. Behaviour hidden in a function makes that claim
unfalsifiable from outside.

**Identity is the content, and the id is a label over it.** If the declared id
were the identity, the same scenario committed twice under two ids would be two
templates as far as the split is concerned — and the case the model was examined
on would be one it had already been trained on, while every check passed. That
failure raises measured accuracy, so nothing downstream reports it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from consylr.violation import Violation

REQUIRED = ("id", "family", "left", "right", "policy")

#: The fields a paraphrase is permitted to rewrite (RFC-0003): free-text surface
#: only — a counterparty as written, and the prose of a policy or document. Never
#: a label, a number, a reference or a correspondence decision, so an identity
#: taken over the complement is invariant under paraphrase.
#:
#: These are the names that appear in the shape the generator consumes. An
#: earlier list named fields belonging to no shape the product produces, which
#: made this whole layer strip nothing while every test passed — so
#: `test_the_surface_fields_are_fields_a_real_template_has` now holds the
#: constant to the data model rather than to a fixture.
SURFACE_FIELDS = frozenset({"party", "text", "description", "memo", "narrative"})

#: What a paraphrase may never touch. Named positively as well as negatively: a
#: field added to a record later is structural until someone decides otherwise,
#: and this is what says so if the surface list is edited carelessly.
STRUCTURAL_FIELDS = frozenset({"id", "family", "ref", "date", "amount"})


def _without_surface(value: Any) -> Any:
    """The template with every paraphrasable field removed, recursively."""
    if isinstance(value, dict):
        return {k: _without_surface(v) for k, v in value.items() if k not in SURFACE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_without_surface(v) for v in value]
    return value


def _digest(body: Any) -> str:
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


def _canonical(body: Mapping[str, Any]) -> str:
    """The template's content, in a form two equal templates always share.

    Sorted keys and fixed separators, so reformatting a data file does not read
    as a new template — a corpus regenerated after a whitespace change would
    otherwise no longer match the one the published numbers came from.
    """
    # No `default=`: a value with no canonical JSON form must raise rather than
    # be stringified. A set has no stable repr across runs, so hashing one
    # silently re-partitions a corpus between runs of a build whose whole claim
    # is that a seed reproduces it.
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, eq=False)
class Template:
    """A scenario template and the two identities taken over its content.

    Frozen in more than name: the body is deep-copied at construction and the
    fingerprints are computed once. Holding the caller's mapping and recomputing
    on every read meant a template already used to partition a corpus could
    report a different identity to the audit — surfacing as `template_drifted`
    against a file nobody had edited.
    """

    id: str
    family: str
    body: Mapping[str, Any]
    fingerprint: str
    structural_fingerprint: str

    @classmethod
    def from_mapping(cls, body: Mapping[str, Any]) -> Template:
        frozen = deepcopy(dict(body))
        without_id = {k: v for k, v in frozen.items() if k != "id"}
        return cls(
            id=str(frozen.get("id", "")),
            family=str(frozen.get("family", "")),
            body=frozen,
            # The id is excluded deliberately: a fingerprint including it would
            # make two copies of one scenario distinct, which is precisely the
            # aliasing the split has to catch.
            fingerprint=_digest(without_id),
            # And this one drops what a paraphrase may rewrite, so two templates
            # one rewording apart collide. Exact identity misses them by
            # construction, because rewording is what makes the content differ.
            structural_fingerprint=_digest(_without_surface(without_id)),
        )

    def __eq__(self, other: object) -> bool:
        """Identity is the content and the id, never the id alone.

        Equality over `(id, family)` collapsed unrelated scenarios into one set
        member, so a caller de-duplicating templates dropped one silently.
        """
        if not isinstance(other, Template):
            return NotImplemented
        return (self.id, self.fingerprint) == (other.id, other.fingerprint)

    def __hash__(self) -> int:
        return hash((self.id, self.fingerprint))


def load(directory: Path) -> list[Template]:
    """Every template under a directory, or a failure naming what broke.

    Nothing here is skipped. A generator that quietly ignored a file would
    produce a corpus missing a scenario nobody could see was missing — and the
    ways to be quietly ignored were plentiful: a directory that does not exist,
    a directory with nothing in it, and a `.JSON` or `.jsonc` that the
    case-sensitive glob passed over. Each of those returned an empty list.
    """
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a directory of templates")

    stray = sorted(p.name for p in directory.rglob("*") if p.is_file() and p.suffix != ".json")
    if stray:
        raise ValueError(
            f"{directory} holds files that are not templates: {', '.join(stray)}. "
            "A template is a .json file; anything else is a mistake, not a comment."
        )

    templates: list[Template] = []
    for path in sorted(directory.rglob("*.json")):
        try:
            body = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name} is not readable as a template: {e}") from e
        if not isinstance(body, dict):
            # ValueError rather than TypeError: the caller passed a directory, not
            # a badly-typed argument. Both failures here are one thing from where
            # it stands — this file on disk is not a readable template.
            raise ValueError(  # noqa: TRY004
                f"{path.name} is not readable as a template: not an object"
            )
        templates.append(Template.from_mapping(body))

    if not templates:
        raise ValueError(f"{directory} holds no templates")
    return templates


def check(templates: Iterable[Template], families: frozenset[str]) -> list[Violation]:
    """Every way a template set is unfit to be split on."""
    items = list(templates)
    if not items:
        return [
            Violation("no_templates", "a template set with nothing in it satisfies no coverage")
        ]

    violations: list[Violation] = []

    by_id: dict[str, list[Template]] = {}
    by_fingerprint: dict[str, list[Template]] = {}
    for t in items:
        # An id-less template is already reported as a missing field. Grouping it
        # under the empty string would report it a second time as an alias of
        # every other id-less template — one defect wearing two codes, and the
        # second naming nothing a reader could act on.
        if t.id:
            by_id.setdefault(t.id, []).append(t)
        by_fingerprint.setdefault(t.fingerprint, []).append(t)

    for missing in sorted({f for t in items for f in REQUIRED if f not in t.body}):
        named = sorted(t.id for t in items if missing not in t.body)
        violations.append(
            Violation(
                "missing_field",
                f"{len(named)} template(s) have no {missing!r}: {', '.join(named)}",
            )
        )

    for template_id in sorted(i for i, ts in by_id.items() if len(ts) > 1):
        violations.append(
            Violation(
                "duplicate_template_id",
                f"{template_id!r} is declared by {len(by_id[template_id])} templates; an id has "
                "to name one scenario or the split cannot separate on it",
            )
        )

    for ts in sorted(by_fingerprint.values(), key=lambda g: sorted(t.id for t in g)):
        ids = sorted({t.id for t in ts})
        if len(ids) > 1:
            violations.append(
                Violation(
                    "aliased_template",
                    f"{', '.join(repr(i) for i in ids)} are the same scenario under different "
                    "ids; split on the declared id and one role's cases appear in the other",
                )
            )

    by_structure: dict[str, list[Template]] = {}
    for t in items:
        by_structure.setdefault(t.structural_fingerprint, []).append(t)
    for ts in sorted(by_structure.values(), key=lambda g: sorted(t.id for t in g)):
        ids = sorted({t.id for t in ts})
        # An exact alias already collides on content, and reporting it again here
        # would make one defect look like two. The test is whether *this* group is
        # entirely one exact copy — asking instead whether its ids appear anywhere
        # in some alias group made the report vanish as copies accumulated, so a
        # fourth copy of a scenario silenced a defect that three had raised.
        if len(ids) > 1 and len({t.fingerprint for t in ts}) > 1:
            violations.append(
                Violation(
                    "near_duplicate_template",
                    f"{', '.join(repr(i) for i in ids)} differ only in wording; a paraphrase "
                    "cannot change a label, a number or a reference, so these are one scenario",
                )
            )

    for family in sorted({t.family for t in items} - families):
        named = sorted(t.id for t in items if t.family == family)
        violations.append(
            Violation(
                "unknown_family",
                f"{family!r} is not a family the taxonomy names, declared by {', '.join(named)}",
            )
        )

    return violations
