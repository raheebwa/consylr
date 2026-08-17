# Consylr — PRD

- **Status:** shell — sections marked TODO are unwritten, not decided-and-omitted
- **Date:** 2026-08-18

## Problem

Reconciliation is where money goes missing quietly. Two records describe what should be the
same economic event and disagree — by a fee, a day, a mangled reference, a reversal, a
partial payment — and somebody has to decide whether they are the same event, why they
differ, and what to do about it. That work is judgement, not arithmetic, and today it is
either done by hand or sent to a hosted model along with the confidential ledger it concerns.

## What Consylr is

A compact model that runs entirely on ordinary CPU hardware, offline, and performs the
judgement step: correspondence inside a bounded evidence packet, exception classification
with cited support, explicit abstention when evidence is insufficient, and an audit-ready
disposition a human authorises.

## Who it is for

TODO — the research report establishes the pain and the market boundary but does not name a
buyer. Resolve before any commercial claim. Candidate frames: African SME finance
operations; internal control/audit functions handling confidential ledgers; organisations
whose data cannot leave the premises.

## The boundary that defines the product

> Parsing and verification are deterministic.
> Correspondence and interpretation inside the bounded packet are model-led.
> Humans authorise consequential actions.

Restated for a sceptical reader:

> We don't use a language model where exact software is already perfect.
> We use it where reconciliation turns into evidence judgement.

## Scope

**In:** 2–20 records across two sides · one-to-one, one-to-many, many-to-one · misspelled
names · mangled references · timing and cut-off drift · fees and withholding described in
evidence · reversals · duplicates · partial payments · batched vs itemised · missing records
· cause classification from supplied policy · explicit ambiguous and no-match conclusions.

**Out, and never claimed:** brute-force search over millions of rows · maintaining a general
ledger · unconstrained many-to-many optimisation at scale · fraud attribution · unsourced
causal claims · autonomous posting of adjustments · generation as the authority for
arithmetic.

## Output contract

Structured JSON with categorical certainty states — `supported`, `ambiguous`, `unsupported`
— never uncalibrated numeric confidence. Shape drafted in the research report; to be
promoted to an RFC before the generator is written.

## Success criteria (Gate 1)

These are engineering go/no-go thresholds, not organiser requirements.

| Metric | Threshold |
|---|---|
| Correspondence F1 | ≥0.90 target, ≥0.85 minimum |
| Ambiguous-case false-match rate | <5% |
| Unsupported-cause hallucination rate | <3% |
| Correct abstention rate | ≥90% |
| Evidence citation precision | ≥98% |
| Amount/reference/date exact-copy rate | ≥99.5% |
| Structured-output parse rate | ≥99% |
| General enterprise capability vs untuned base | ≥95% |
| Peak RSS | ≤5 GB hard, ≤4 GB preferred |
| Official profiler accuracy | Beat untuned base, no regression |

**Fallback if correspondence misses:** drop direct matching from the headline and ship the
same model as an evidence-grounded Exception Analyst. The project does not die on that
threshold.

## Non-functional

- Fully offline after model download. No network at inference.
- CPU-only, ordinary laptop hardware.
- Single GGUF artefact at submission.

## Roadmap beyond the competition

TODO — the research report deliberately stops at Gate 3. Anything past it is unwritten.

## Open questions

1. Who is the buyer? (blocks any commercial claim)
2. ~~Repo licence.~~ **Answered:** MIT, and this repository is public —
   [ADR-0001](../adrs/0001-mit-licence-and-public-repository.md).
3. ~~Trademark clearance for "Consylr".~~ **Answered at knock-out level only:** keep the name
   — [ADR-0002](../adrs/0002-keep-the-name-consylr.md). No registry clearance was performed
   and that residual risk is recorded there. Revisit before any commercial launch, which is
   the same trigger question 1 carries.
4. ADTC Participation Agreement IP terms — **blocks submission**, not just the roadmap. A
   preliminary working read exists; the owner's full read is still required. See
   [docs/HANDOFF.md](../HANDOFF.md).
