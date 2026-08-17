# ADR-0002 — keep the name "Consylr"

- **Status:** accepted
- **Date:** 2026-08-18
- **Deciders:** Aheebwa Ramadhan

## Context

"Consylr" had been carried as a *working* name since the project started, with no clearance
behind it. [`README.md`](../../README.md) and [`docs/HANDOFF.md`](../HANDOFF.md) both said so
in as many words, and [ADR-0001](0001-mit-licence-and-public-repository.md) recorded the
unresolved name as an accepted cost of publishing the repository.

What forces the decision now is that the cost of a rename rises every week and is about to
rise sharply. The name is already in a public repository. It is about to enter a public
submission fork, a `metadata.json`, a technical report, a two-minute demo recorded for
judging, and a DevPost entry — and Gate 1 closes **2026-08-24 23:45 PDT**. Deciding after
those exist means changing all of them or living with an inconsistency in front of judges.

The competing pressure is that a full registry clearance is not a thing this project can
complete inside that window, and treating "no formal clearance" as a reason to keep deferring
would mean deferring until the expensive moment arrives on its own.

## Decision

**Keep the name "Consylr".**

The basis is a **knock-out-level search only**, run on 2026-08-18:

- zero hits for the exact string "Consylr";
- the nearest marks found were **"Consyl"** — HR and consulting, a different field and a
  different spelling — and **"Consensys"**, blockchain, distinct on both sight and sound.

That is enough to rule out the obvious collision. It is **not** a clearance.

## Consequences

**Made easy.** The name can now be committed to across every Gate 1 surface at once —
submission fork, metadata, report, demo — instead of each one being provisional.

**The residual risk, stated plainly rather than implied:**

- **No formal registry clearance was performed.** No USPTO, no EUIPO, and no URSB search.
  A knock-out search finds collisions that are easy to find; it says nothing about a
  registered mark that a search engine does not surface, nor about classes, nor about
  jurisdictions. A conflict discovered later is not excluded by this decision — it is
  accepted as a risk taken knowingly.
- **This is not legal advice and no legal review was obtained.**
- **The risk grows with reach.** It is small while the audience is a competition. It would
  need revisiting before any commercial launch, and certainly before any registration
  attempt, which is a different exercise with a different standard of evidence.

**What this decision does not license.** Clearing the name at knock-out level does not
release the brand artwork. The mark stays unpublished until it is redrawn as clean vector
geometry, because the current draft is a generated concept reference rather than shippable
artwork. Verbal identity — the name, the descriptor, the tagline, the boundary sentence — is
usable now; visual identity is not, and the two were deliberately decided separately.

## Alternatives considered

| Option | Why not |
|---|---|
| Formal registry clearance first | Cannot complete before Gate 1, and the deadline does not move. Deferring on these grounds means the name is still undecided at the moment it becomes expensive to change. |
| Rename now to something pre-cleared | Pays a certain cost to avoid an uncertain one. Nothing found in the search suggests the certain cost is warranted, and a rushed replacement name would carry the same knock-out-only evidence this one has. |
| Keep it as a working name, decide later | This is the option that was already running, and its cost is the one this ADR exists to stop paying. "Later" arrives after the name is in a submission, a report and a recorded demo. |

## Evidence

- The name's prior unclear status: [`README.md`](../../README.md) and
  [`docs/HANDOFF.md`](../HANDOFF.md), before this ADR.
- The rename-cost argument as an accepted consequence of publishing:
  [ADR-0001](0001-mit-licence-and-public-repository.md) §Consequences.
- The search itself was run outside this repository and is not reproducible from it. That is
  a real weakness of this record: what is written above is the finding, not the method, and a
  later reader cannot re-derive it. Recorded as such rather than dressed up.
