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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from consylr.violation import Violation

REQUIRED = ("id", "family", "left", "right", "policy")

#: The fields a paraphrase is permitted to rewrite (RFC-0003). Everything else —
#: labels, numbers, references, correspondence decisions — it may not touch, so
#: an identity taken over the complement is invariant under paraphrase.
SURFACE_FIELDS = frozenset({"description", "name", "merchant", "narrative", "memo"})


def _without_surface(value: Any) -> Any:
    """The template with every paraphrasable field removed, recursively."""
    if isinstance(value, dict):
        return {k: _without_surface(v) for k, v in value.items() if k not in SURFACE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_without_surface(v) for v in value]
    return value


def _canonical(body: Mapping[str, Any]) -> str:
    """The template's content, in a form two equal templates always share.

    Sorted keys and fixed separators, so reformatting a data file does not read
    as a new template — a corpus regenerated after a whitespace change would
    otherwise no longer match the one the published numbers came from.
    """
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Template:
    id: str
    family: str
    body: Mapping[str, Any] = field(compare=False)

    @classmethod
    def from_mapping(cls, body: Mapping[str, Any]) -> Template:
        return cls(id=str(body.get("id", "")), family=str(body.get("family", "")), body=dict(body))

    @property
    def fingerprint(self) -> str:
        """Content identity, with the declared id excluded.

        Excluded deliberately: a fingerprint that included the id would make two
        copies of one scenario distinct, which is precisely the aliasing the
        split has to catch.
        """
        without_id = {k: v for k, v in self.body.items() if k != "id"}
        return hashlib.sha256(_canonical(without_id).encode()).hexdigest()

    @property
    def structural_fingerprint(self) -> str:
        """Identity that a paraphrase cannot change.

        Two templates one rewording apart are the same scenario twice, and the
        model that trained on one has effectively seen the other. Exact content
        identity misses them by construction, because rewording is exactly what
        makes the content differ.
        """
        without_id = {k: v for k, v in self.body.items() if k != "id"}
        return hashlib.sha256(_canonical(_without_surface(without_id)).encode()).hexdigest()


def load(directory: Path) -> list[Template]:
    """Every template in a directory, or a failure naming the file that broke.

    A malformed file is not skipped. A generator that quietly ignored one would
    produce a corpus missing a scenario nobody could see was missing.
    """
    templates: list[Template] = []
    for path in sorted(directory.glob("*.json")):
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
    return templates


def check(templates: Iterable[Template], families: frozenset[str]) -> list[Violation]:
    """Every way a template set is unfit to be split on."""
    items = list(templates)
    violations: list[Violation] = []

    by_id: dict[str, list[Template]] = {}
    by_fingerprint: dict[str, list[Template]] = {}
    for t in items:
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

    aliased = {t.id for ts in by_fingerprint.values() if len({x.id for x in ts}) > 1 for t in ts}
    by_structure: dict[str, list[Template]] = {}
    for t in items:
        by_structure.setdefault(t.structural_fingerprint, []).append(t)
    for ts in sorted(by_structure.values(), key=lambda g: sorted(t.id for t in g)):
        ids = sorted({t.id for t in ts})
        # An exact alias already collides on content; reporting it again here
        # would make one defect look like two.
        if len(ids) > 1 and not aliased.issuperset(ids):
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
