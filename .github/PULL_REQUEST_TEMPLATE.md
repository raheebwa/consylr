## What this changes

<!-- The state before, and the state after. -->

## Which record it implements or amends

<!--
Name the ADR in docs/adrs/ or the RFC in docs/rfcs/ this change carries out — for example
"implements RFC-0001" or "amends ADR-0001".

A change that answers "none" is either outside the scope set by docs/prd/prd.md, or it is
a design decision nobody has written down yet — in which case the RFC comes first.
-->

## How it was verified

<!--
The commands you ran and what they reported.

Behaviour changes arrive test-first: the failing test, confirmed failing for the expected
reason, then the code that makes it pass. Tests written against code that already existed
are characterization tests and are named as such.

There is no test suite yet. Until there is, say how a reader can check this — the document
you cross-read it against, or the passage it contradicts.
-->

## Effect on published figures

<!--
Whether any number in the README or docs/ changes. Every published figure traces to a
recorded run, so a changed figure means a new record, not an edited one. Write "none" if
nothing published moves. Unmeasured values are written TBD, never estimated.
-->

## Checklist

- [ ] Every commit is signed off (`git commit -s`), adding the `Signed-off-by:` trailer
      required by the Developer Certificate of Origin. No other trailer is used.
- [ ] Commit subjects follow `<type>(<scope>): <subject>` — present tense, lowercase type
      and scope, under 50 characters.
- [ ] Any new source file carries its SPDX identifier as the first comment line
      (`# SPDX-License-Identifier: MIT` for Python).
- [ ] Any new fixture or example is synthetic — no real people, businesses, account
      numbers, ledger entries, or locale-plausible phone or ID numbers.
- [ ] No credential, key, token, or connection string is added, in any file.
- [ ] Any new term is in `docs/glossary.md`.
- [ ] `CHANGELOG.md` records the change under `## [Unreleased]`, unless nothing a reader
      would notice moved.
