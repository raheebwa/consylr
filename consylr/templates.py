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
import unicodedata
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from consylr.violation import Violation

REQUIRED = ("id", "family", "left", "right", "policy")

#: The template is a closed world. A key nobody classified used to reach the
#: packet through `_records`, or sit in the body unread — and either way it
#: changed the identity while changing nothing the model could see, so one
#: scenario became two and the split had no way to know. Refusing the unknown
#: makes the classification complete by construction, which is the same
#: principle the ground truth already rests on.
BODY_FIELDS = frozenset({"id", "family", "left", "right", "policy", "documents", "cause"})
RECORD_FIELDS = frozenset({"ref", "party", "date", "amount"})
CITATION_FIELDS = frozenset({"id", "text"})


def _text(value: Any) -> str:
    """A string as the model would read it, with what it cannot see removed.

    Unicode normal form, format characters, and surrounding or repeated
    whitespace are differences no reader of a rendered packet can perceive — and
    each of them used to split one scenario across both roles. A zero-width space
    in a reference is the worst of them, because it is invisible in a diff too,
    so a corpus could be poisoned with no visible edit. NFD against NFC is macOS
    against everything else.
    """
    text = unicodedata.normalize("NFC", str(value))
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return " ".join(text.split())


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


def shape_violations(template: Template) -> list[Violation]:
    """Every way a template is outside the closed world the builder reads.

    Reported here and raised by the builder, from one definition, because the
    audit and the build have to agree about what a template is. A key nobody
    classified used to reach the packet or sit unread in the body, and either way
    it changed the identity while changing nothing the model could see.
    """
    out: list[Violation] = []
    body = template.body
    name = template.id or "<no id>"

    for key in sorted(set(body) - BODY_FIELDS):
        out.append(
            Violation(
                "unknown_field",
                f"{name}: {key!r} is not part of a template; the builder never reads it, so it "
                "would change what counts as this scenario without changing the packet",
                template.id or None,
            )
        )

    for side in ("left", "right"):
        for n, record in enumerate(body.get(side, []) or [], start=1):
            if not isinstance(record, dict):
                out.append(
                    Violation("bad_type", f"{name}: {side} entry {n} is not a record", template.id)
                )
                continue
            for key in sorted(set(record) - RECORD_FIELDS):
                out.append(
                    Violation(
                        "unknown_field",
                        f"{name}: {side} entry {n} carries {key!r}, which is not a record field. "
                        "A denylist of prose names can only chase the ones someone thought of.",
                        template.id or None,
                    )
                )
            # The allowlist said what a record may not carry and never what it
            # must. A record short of one of these was certified clean and then
            # indexed raw by whichever deformation reads it, so a KeyError
            # escaped an audit written to keep going and count every problem.
            for key in sorted(RECORD_FIELDS - set(record)):
                out.append(
                    Violation(
                        "missing_field",
                        f"{name}: {side} entry {n} has no {key!r}; the builder reads it",
                        template.id or None,
                    )
                )
            # A pattern template declares a pool where a fixed one declares a
            # value, and `cases.build` resolves it before a record is read — so a
            # well-formed pool is a legitimate artefact here and must not be
            # rejected. What is refused is a pool nothing can be drawn from, or a
            # container that is not a pool at all. Both would otherwise reach a
            # packet through fields no canonicaliser inspects: only 'amount' was
            # ever caught, and only because `money.canonical` could not read a
            # list, while a pool on 'party' built clean and rendered
            # `['Northwind Ltd', 'Southgate Ltd']` into a prompt as a
            # counterparty name.
            for key in sorted(RECORD_FIELDS & set(record)):
                value = record[key]
                if isinstance(value, list):
                    if not value:
                        out.append(
                            Violation(
                                "bad_type",
                                f"{name}: {side} entry {n} declares an empty pool for {key!r}; "
                                "a pool with no candidates has nothing to draw",
                                template.id or None,
                            )
                        )
                    elif not all(isinstance(candidate, str) for candidate in value):
                        out.append(
                            Violation(
                                "bad_type",
                                f"{name}: {side} entry {n} declares a pool for {key!r} holding "
                                "something that is not text; a drawn value reaches the packet",
                                template.id or None,
                            )
                        )
                elif isinstance(value, (dict, set, tuple)):
                    # Not a value and not a pool. RFC-0003 canonicalises amounts,
                    # so a bare `1000` or `1000.0` is a legitimate amount and is
                    # deliberately not named here.
                    out.append(
                        Violation(
                            "bad_type",
                            f"{name}: {side} entry {n} has a {key!r} that is neither a value nor "
                            "a pool; the builder cannot read it and it would reach the packet",
                            template.id or None,
                        )
                    )

    for section in ("policy", "documents"):
        for n, entry in enumerate(body.get(section, []) or [], start=1):
            if not isinstance(entry, dict):
                out.append(
                    Violation(
                        "bad_type", f"{name}: {section} entry {n} is not an object", template.id
                    )
                )
                continue
            for key in sorted(set(entry) - CITATION_FIELDS):
                out.append(
                    Violation(
                        "unknown_field",
                        f"{name}: {section} entry {n} carries {key!r}",
                        template.id or None,
                    )
                )
            for key in sorted(CITATION_FIELDS - set(entry)):
                out.append(
                    Violation(
                        "missing_field",
                        f"{name}: {section} entry {n} has no {key!r}",
                        template.id or None,
                    )
                )
            if "text" in entry and not isinstance(entry["text"], str):
                # Prose that is not prose was deleted whole from the identity,
                # so a nested object holding rates and caps vanished and two
                # different scenarios were reported as one.
                out.append(
                    Violation(
                        "bad_type",
                        f"{name}: {section} entry {n} has a 'text' that is not prose; identity "
                        "does not read it, so anything hidden in it is invisible to the split",
                        template.id or None,
                    )
                )

    return out


def check(templates: Iterable[Template], families: frozenset[str]) -> list[Violation]:
    """Every way a template set is unfit to be split on."""
    items = list(templates)
    if not items:
        return [
            Violation("no_templates", "a template set with nothing in it satisfies no coverage")
        ]

    violations: list[Violation] = []
    for t in items:
        violations.extend(shape_violations(t))

    by_id: dict[str, list[Template]] = {}
    for t in items:
        # An id-less template is already reported as a missing field. Grouping it
        # under the empty string would report it a second time as an alias of
        # every other id-less template — one defect wearing two codes, and the
        # second naming nothing a reader could act on.
        if t.id:
            by_id.setdefault(t.id, []).append(t)

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

    for family in sorted({t.family for t in items} - families):
        named = sorted(t.id for t in items if t.family == family)
        violations.append(
            Violation(
                "unknown_family",
                f"{family!r} is not a family the taxonomy names, declared by {', '.join(named)}",
            )
        )

    return violations
