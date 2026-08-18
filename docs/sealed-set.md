# The sealed evaluation set

The corpus is not committed — RFC-0003 keeps corpora out of the repository and
makes them reproducible from a configuration and a seed instead. This is that
record: what the exam is, how to rebuild it, and what binds it.

## Current: sealed-v2

Frozen 2026-08-18.

| | |
|---|---|
| Seed | `20260818` — **reserved; never a training seed** |
| Templates | 350 authored, 63 sealed |
| Packets | **209, every one distinct** |
| Records per packet | 5–10, none outside *[competition constraint — ADTC profiler]* |
| Families | 14, between 14 and 17 packets each |
| Certainty | 162 supported · 33 ambiguous · 14 unsupported |
| Abstention families | 31 packets (15%) |
| Worst rendered prompt | 915 tokens against a 1,448 cap |
| Role | `holdout`, and nothing in the configuration can say otherwise |
| Content digest | `08e313c8a642ef9c…` — the authoritative value is `consylr.corpus.content_digest`, computed from the corpus rather than transcribed |

Rebuild it with `consylr.sealed.seal`, the 350 templates in `templates/`, the
seed above, and the frozen model's tokeniser per
[ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md). A different
tokeniser gives different counts and therefore a different budget verdict, which
is why it is named rather than assumed.

## Retired: sealed-v1

**Invalidated, never used for any number.** It held 196 packets and **73
distinct ones** — 63% duplicates, the most repeated appearing seven times, so
any metric computed on it would have carried a hidden sevenfold weighting.
Verified by digesting every packet on disk.

The reason it happened is the reason it is recorded here rather than deleted.
RFC-0003 listed near-duplicate detection in the audit command's stack, and the
audit command does not exist — so the writer refused a corpus whose packets
carried two answers and accepted one that asked the same question seven times.
A rule written down and never made into a gate.

A second defect was found in the same set before it was digested: **101 of its
206 packets were outside the 5–10 record range**, because a template's pair
count was chosen freely while deformations add and remove records on top of it.
Also specified, also ungated.

Both classes are closed now, and every specified constraint has been swept for
the same defect — see [constraints.md](constraints.md).

## What binds the current set

The prompt template, by digest. **Changing it invalidates this set**: budgets
re-assert over every case and the exam is rebuilt. The model was trained against
one interface, and a changed interface is a different one whatever the diff
looks like.

The templates in `templates/`. Re-authoring them changes what the exam asks.

## What was checked before it was written

Nothing here was audited afterwards. `consylr.corpus.write` refuses, so a set
that reached disk had already passed:

- every case against the validator that ships in the product;
- every packet inside the token budget, measured with the frozen tokeniser;
- every packet inside the 5–10 record range;
- the template set's shape rules and duplicate-scenario audit;
- **no two packets identical under different answers** — contradictory ground
  truth, which trains the model on one answer and examines it on the other;
- **no packet in both roles** — the leak that raises measured accuracy;
- **no packet twice** — the defect that invalidated v1.

The last three are exhaustive over the whole corpus rather than sampled.

## Positioning

RFC-0002 makes this the set that decides positioning. After it is frozen the
argument about positioning is over — which is the point of freezing it.
