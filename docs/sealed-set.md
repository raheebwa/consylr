# The corpora

Neither corpus is committed — RFC-0003 keeps corpora out of the repository and
makes them reproducible from a configuration and a seed instead. This is that
record.

**The templates are frozen with the exam.** Re-authoring them broke an earlier
exam outright: thirteen of its templates ceased to exist and 169 of its 209
packets no longer matched the template content they recorded. The exam detected
that itself, because every case carries the fingerprint of the template that
produced it — but the lesson is that the exam and `templates/` are one artefact
with two halves.

## The exam: sealed-v4

Frozen 2026-08-18, from 540 templates.

| | |
|---|---|
| Seed | `20260818` — **reserved; never a training seed** |
| Packets | **204, every one distinct** |
| Records per packet | 5–10, none outside *[competition constraint — ADTC profiler]* |
| Families | 14, between 14 and 16 packets each |
| Certainty | 161 supported · 29 ambiguous · 14 unsupported |
| Worst rendered prompt | 821 tokens against a 1,448 cap |
| Role | `holdout`, and nothing in the configuration can say otherwise |
| Corpus digest | `consylr.corpus.content_digest(<exam dir>)` |
| Template digest | sha256 over the sorted per-file digests of `templates/` |

## The training corpus: train-v1

| | |
|---|---|
| Seed | `7` |
| Cases | **903, every one distinct**, from 442 templates |
| Duplicates refused | 1,749 of 2,652 asked |
| Clearly supported | **48%** — train-v1 met the 40–50% band in force when it was built; RFC-0002 now states 65–75% |
| `cause_not_established` | **11%** — RFC-0002 wants 10–15% |
| Smallest family | 36 cases, against a floor of 20 |
| Corpus digest | `consylr.corpus.content_digest(<corpus dir>)` |

**903 is short of RFC-0003's 8,000–15,000, and it is not padded to reach it.**
A template yields as many distinct cases as its deformation can distinguish —
three for most families, exactly one for the three whose deformation does not
draw on the generator. Reaching the RFC's figure needs per-case instantiation
([#20](https://github.com/raheebwa/consylr/issues/20)), where a template carries
drawn amounts, references, dates and counterparties rather than fixed ones.
Padding to the number would mean duplicates, which the writer refuses.

**No digest is transcribed here.** A transcribed digest is a second source of
truth that can disagree with the first, and it has to be re-copied every time
the artefact moves — so the table names the function that computes it instead.
A scoring run asserts the value it computes, not a value someone typed.

## The template mix is deliberately unequal

Eleven of the fourteen families produce a clearly-supported answer, so an equal
split gives 80% supported, above RFC-0002's 65-75% band. A corpus that meets
the quota needs a template set weighted toward the cases the model finds hard,
which is the quota's whole point: a model trained on a mix that is four-fifths
clean learns that most things reconcile.

`clean_match` and `batched_vs_itemised` carried the most templates for a
different reason — their deformations ignore the case index, so each template
yields exactly one distinct case where others yield three. Twenty templates gave
six training cases against a floor of twenty, and the quota gate refused the
corpus until the counts were raised.

## What was checked before either reached disk

Nothing was audited afterwards. `consylr.corpus.write` refuses, so a corpus that
reached disk had already passed:

- every case against the validator that ships in the product;
- every packet inside the token budget, measured with the frozen tokeniser;
- every packet inside the 5–10 record range;
- the template set's shape rules and its duplicate-scenario audit;
- **no two packets identical under different answers**;
- **no packet twice**;
- **no packet in both roles**;
- **no training packet that the exam already asks** — compared byte for byte
  against all 204, which is the pair that matters most;
- the certainty bands and family floors, for the training corpus.

Every one of those is exhaustive rather than sampled.

## Earlier attempts, and why they are gone

Three sets were built and discarded before this one, none of which produced a
single number. They are recorded because each failed for a reason worth keeping.

- **v1** — 196 packets, **73 distinct**. 63% duplicates, the most repeated seven
  times, so any metric would have carried a hidden sevenfold weighting.
  Near-duplicate detection was specified in RFC-0003's audit stack and the audit
  command does not exist.
- **v2** — **101 of 206 packets outside the 5–10 record range**. Also specified,
  also ungated: a template's pair count was chosen freely while deformations add
  and remove records on top of it.
- **v3** — sound, then invalidated by its own templates being re-authored to meet
  the quota. Which is why the templates are now frozen with the exam.

All three defect classes are closed, and every specified constraint has been
swept for the same failure — see [constraints.md](constraints.md).

## Positioning

RFC-0002 makes the exam the set that decides positioning. After it is frozen the
argument about positioning is over — which is the point of freezing it.
