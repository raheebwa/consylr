# Glossary

Terms used precisely in this repo, plus the confusions worth heading off. Add an entry the
moment a term causes a second question.

## Repo terms

| Term | Meaning |
|---|---|
| **ADR** | Architecture Decision Record — `docs/adrs/`. Records a decision and what it foreclosed. Current: if an ADR and a research document disagree, the ADR wins. |
| **RFC** | Request for Comments — `docs/rfcs/`. Records a design: interface, behaviour, refusals, verification. Depends on an ADR. |
| **PRD** | Product Requirements Document — `docs/prd/prd.md`. What we're building and for whom. |
| **SFT** | Supervised fine-tuning — the training stage that teaches the task families. |
| **QLoRA** | Quantised low-rank adaptation — a parameter-efficient fine-tuning method. The training backend is not yet frozen; see the base-model epic. |
| **GGUF** | The quantised model file format `llama.cpp` loads. The artefact that ships, and therefore the one that gets measured. |
| **TPS** | Tokens per second — the throughput measure. The product target is a session that feels responsive on ordinary hardware; the ADTC harness additionally weights it at 30% of its score (see Competition terms). |

## Product terms

| Term | Meaning here |
|---|---|
| **Evidence packet** | The bounded input to one analysis: 2–20 records across two sides, plus policy/context excerpts and notes. The unit the model reasons over. Not a database. |
| **Correspondence** | The judgement that two or more records describe the same economic event. Deliberately not called "matching" — matching implies a deterministic join, which this is not. |
| **Exception** | A recorded difference between corresponding records that needs a disposition — a fee, a reversal, a partial payment, a duplicate. |
| **Cause** | The classified reason for an exception. Only asserted when the packet contains support for it; otherwise `CAUSE_NOT_ESTABLISHED`. |
| **Support** | The specific cited evidence (record ID, policy line range) behind a claim. A claim without support is a defect, not a weaker claim. |
| **Abstention** | Refusing to conclude when evidence is insufficient. A first-class trained behaviour and a scored metric, not a fallback. |
| **Disposition** | The operational next step a human authorises: accept, hold, escalate, request evidence. |
| **Residue** | Records left unmatched after analysis. Named explicitly so "everything matched" can never be silent. |

## Competition terms

| Term | Meaning |
|---|---|
| **ADTC** | Africa Deep Tech Challenge 2026 — "The Laptop LLM Challenge". |
| **Gate 1 / 2 / 3** | Screening submission (2026-08-24) → reproducibility + technical defence (2026-09-08 → 09-29) → live defence (2026-10-17). |
| **The profiler** | The organisers' official scoring harness. Its `accuracy.py` is the implementation contract for anything it actually executes. |
| **Peak RSS** | Resident set size at its maximum during profiling. Scored, with a hard 7 GB ceiling and a score of zero at the ceiling. |
| **Hidden prompts** | Organiser-supplied evaluation prompts not published in advance. Assume ≥3 and assume domain variation beyond reconciliation. |

## Confusions already worth naming

**"Reconciliation" means two different things.** In *finance* it means matching records
across sources and explaining differences — this product. In *record linkage* it means
resolving whether two rows refer to the same entity — that is `joinless`, a separate prior
project. Consylr's runtime contains no `joinless` component; the connection is founder
experience, not architecture.

**"The model can't do maths" is wrong, and so is the opposite.** Compact 4B models perform
substantial numerical reasoning. The reason arithmetic stays deterministic is not incapacity
— it is that there is no reason to accept probabilistic error where exact computation is
available. State it that way; the incapacity framing loses the argument to a judge holding a
GSM8K score.

**"Offline" is a data-disclosure property, not a legal one.** Offline inference removes an
external-processing dependency. It does not remove access-control, retention, audit or
data-protection obligations. Never claim offline is "the only lawful architecture."

**The submission repo is not this repo.** *(Competition-scoped.)* ADTC Gate 1 is entered from a
public **fork** of the official ADTC template — the upstream repository is not marked as a
template, so the mechanism is a fork rather than a template instantiation. This repo holds the
product and its reasoning; the fork is an artefact produced from it for one evaluation.

**Q4_K_M is a baseline, not a preference.** It is the default because the product has to run
in memory an ordinary laptop can spare while other work is open, and a heavier quantisation has
to earn that memory back in accuracy before it is worth taking.

*[competition constraint — ADTC profiler]* The same trade-off is priced explicitly by the
scoring formula: each additional gigabyte of peak RSS costs roughly 2.86 total points, so a
heavier quantisation must earn about 5.71 raw accuracy points per gigabyte just to break even.
That arithmetic is the harness's, but it points the same way the product requirement does.
