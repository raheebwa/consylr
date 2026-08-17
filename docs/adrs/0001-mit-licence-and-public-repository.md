# ADR-0001 — MIT licence, and this repository is public

- **Status:** accepted
- **Date:** 2026-08-18
- **Deciders:** Aheebwa Ramadhan

## Context

Two questions had been left open in this project's decision index — now
[`docs/decisions.md`](../decisions.md) — namely which licence this
repository carries, and whether it goes public at all.

They are not independent. A repository with no `LICENSE` file is not "unlicensed pending a
decision" — it is all rights reserved, and anyone who clones it while it is public has no
right to use what they cloned. Adding a licence later does not reach those clones. So the
licence has to be decided *before* the first public push, not after it.

What forces the timing is the competition. Africa Deep Tech Challenge 2026 Gate 1 closes
**2026-08-24 23:45 PDT** and requires a **public** repository. That requirement lands on the
submission repository — a fork of the official ADTC template, a separate artefact from this
one — but the product and its reasoning live here, and a private product repository behind a
public submission is a worse arrangement than one story told once. The reasoning in
[`docs/research/`](../research/) is the strongest evidence this project has that its scope
was argued rather than assumed, and it is only evidence if it can be read.

The one constraint pulling the other way is that the research document was captured with a
sentence naming a current employer in a data-handling warning. That is a redaction task, not
a reason to stay private, and it was done before this decision took effect.

## Decision

**This repository is public, and it is licensed MIT**, with the copyright line
`Copyright (c) 2026 Aheebwa Ramadhan`, matching the precedent set by the author's
`joinless` repository so that a reader moving between them meets one set of terms.

MIT is chosen for permissiveness: this repository holds documents, decision records and (in
time) tooling that the author wants reusable without conditions attached. The ADTC
submission template is GPL-3.0, which governs the fork made from it — **not** this
repository, and not the model weights or training corpus, whose licences are tracked
separately in `DATA_PROVENANCE.md` when it is created.

## Consequences

**Made easy.** The evidence layer becomes citable and checkable. Health files, decision
records and conventions can be written once and apply to both repositories. Reuse of
anything here needs no permission.

**Made hard, and the cost stated honestly:**

- **Public is irreversible in practice.** Making a repository private again does not
  un-publish it; forks and clones persist. Every future commit is written on that
  assumption, which is a permanent discipline cost on every file added — health files
  included, since a `CONTRIBUTING.md` is exactly as public as a `README.md`.
- **The commit author email publishes forever.** It is `hello@badrama.com`, a project
  address, decided before the first push rather than discovered after it.
- **MIT gives away the reciprocity a copyleft licence would keep.** Someone may build a
  closed competitor from this without contributing back. Accepted: the asset here is the
  reasoning and the measurements, not the text.
- **MIT is not a patent grant.** Apache-2.0 would carry an express one. Judged not worth
  the extra file weight for a repository of this shape; revisit if a patentable method
  emerges from the model work.

**What this does not resolve.** Going public settles neither of the two remaining open
items, and must not be read as settling them:

- **Trademark clearance for the name "Consylr"** — no knock-out search has been run.
  Publishing under a working name does not clear it, and increases the cost of changing it.
- **The ADTC Participation Agreement IP terms** — unread. This remains a pre-submission
  blocker in its own right. Nothing in this ADR licenses, waives, or pre-commits anything
  under that agreement, and the box is not to be ticked before the terms are read.

## Alternatives considered

| Option | Why not |
|---|---|
| Stay private until Gate 1 | Does not avoid the decision, only delays it past the point where it is cheap. The public submission fork would still need a licence, and a private product repo behind a public submission splits one story into two. |
| Apache-2.0 | The express patent grant and `NOTICE` machinery buy clarity this repository does not need yet, at the cost of diverging from the author's other repository. Revisit if a patentable method emerges. |
| GPL-3.0, matching the ADTC template | The template's licence governs the fork made from it, not this repository. Copyleft here would make the documents and tooling less reusable for no gain the project wants. |
| No licence, decide later | Not a neutral state. It means all rights reserved, and it leaves every clone taken in the meantime with no rights at all. |

## Evidence

- Public-repository requirement, the submission fork being a separate artefact, and the
  Gate 1 deadline: [`README.md`](../../README.md) §The immediate vehicle, which carries both,
  and [`docs/decisions.md`](../decisions.md) for what remains open.
- Template licensing, and that it does not extend to weights or corpus:
  [`docs/research/2026-08-18-entry-decision-research.md`](../research/2026-08-18-entry-decision-research.md)
  §Base-model licensing.
- The employer reference that had to be redacted before publication: same document,
  §Training-data provenance policy, with the redaction declared in its header callout.
