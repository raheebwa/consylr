# Consylr

**Offline enterprise exception analyst.**

*Evidence, reconciled.*

> We don't use a language model where exact software is already perfect.
> We use it where reconciliation turns into evidence judgement.

A compact model that runs entirely on ordinary CPU hardware, offline, and does the judgement
step in reconciliation: which records correspond, which exceptions the evidence actually
supports, what is missing, and where the honest answer is that it cannot tell. Output is a
traceable disposition a person authorises — not an adjustment it posts by itself.

Two record streams that disagree, converging on the one piece of evidence that settles them.
That is the shape of the product, and everything below is an elaboration of it.

> [!NOTE]
> **Status: early.** Docs first, by design — the product definition, the decisions and the
> evidence came before the build so the build has something to be checked against. The first
> modules have landed. See [Where this stands](#where-this-stands).

⚠️ The name is cleared at knock-out level only — no registry clearance has been run.
See [ADR-0002](docs/adrs/0002-keep-the-name-consylr.md) for the residual risk.

## Start here


| If you want… | Read |
|---|---|
| To start working | **[Issues](https://github.com/raheebwa/consylr/issues)**, grouped under epics |
| What is decided, and what is not | **[docs/decisions.md](docs/decisions.md)** |
| What we're building and why | [docs/prd/prd.md](docs/prd/prd.md) |
| Why it's built this way | [docs/adrs/](docs/adrs/) |
| How each piece works | [docs/rfcs/](docs/rfcs/) |
| The evidence underneath all of it | [docs/research/](docs/research/) |
| What a term means | [docs/glossary.md](docs/glossary.md) |
| To contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |

## The problem


Reconciliation is where money goes missing quietly.

Two records describe what should be the same economic event and disagree — by a fee, by a day,
by a mangled reference, by a reversal, by a partial payment. Somebody has to decide whether
they are the same event, why they differ, and what to do about it.

That work is **judgement, not arithmetic**. Today it is either done by hand, slowly, or handed
to a hosted model along with the confidential ledger it concerns. Both routes are bad, and the
second one is bad in a way that is easy to miss until it matters.

Full statement, including who this is and is not for: [docs/prd/prd.md](docs/prd/prd.md). The
README sells; the PRD specifies.

## The boundary that defines it


Parsing and verification are **deterministic**. Correspondence and interpretation inside a
bounded evidence packet are **model-led**. Consequential actions are **authorised by a human**.

Three consequences worth stating outright, because each is a place this kind of product usually
overreaches:

- **Generation is never the authority for a number.** Arithmetic is verified deterministically.
  Where the model's figure and the computed figure disagree, the disagreement is reported — it
  is the useful signal, not noise to be smoothed over.
- **Abstention is a trained behaviour with a measured rate**, not a prompt asking nicely.
  "The evidence does not support a conclusion" is a first-class output, and refusing when the
  answer *is* supported is measured and penalised too.
- **Every conclusion names its source.** A disposition can be reconstructed from the packet it
  came from, or it does not ship.

## Scope discipline


**In scope:** 2–20 records across two sides; one-to-one, one-to-many and many-to-one
correspondence; misspelled names; mangled references; timing/cut-off drift; fees and
withholding described in evidence; reversals; duplicates; partial payments; batched vs
itemised transactions; missing records; cause classification from supplied policy; explicit
ambiguous / no-match conclusions.

**Out of scope, and never claimed:** brute-force search over millions of rows; maintaining a
general ledger; unconstrained many-to-many optimisation at scale; fraud attribution; unsourced
causal claims; autonomous posting of adjustments; generation as the authority for arithmetic.

The out-of-scope list is the more load-bearing half. It is what makes the in-scope claims
checkable.

### One claim this project does not make

Offline inference removes a major disclosure and external-processing dependency for workflows
over sensitive records. It **does not** remove access-control, retention, audit or
data-protection obligations, and **offline operation alone does not make a workflow compliant
or lawful.** "Offline" is a data-disclosure property, not a legal one — see
[docs/glossary.md](docs/glossary.md).

## Where this stands


Documents first, deliberately: the reasoning was written before the build so that the build has
something to be checked against, and so that a decision can be found later instead of guessed at.
Three modules have landed: the output validator against RFC-0001, and the token-budget and
quota assertions against RFC-0002 and RFC-0003.

**Decided** — the positioning; that the model itself decides correspondence, with no external
deterministic matcher in the runtime; deterministic arithmetic; trained abstention; the 3.8–4B
band, frozen on the quantised artefact rather than the checkpoint; Q4_K_M as the baseline; a
≤5 GB peak-memory target; CLI as the only surface for now; and that this repository is MIT and
public.

**Open** — the base model, pending a bake-off that starts with a hard-timeboxed conversion
spike.

Both lists, with the reasoning behind each and where it was argued, are in
[docs/decisions.md](docs/decisions.md) — the canonical index. What is above is a summary and will
lag it. Work in progress is tracked in
[issues](https://github.com/raheebwa/consylr/issues), grouped under epics.

## The immediate vehicle


Everything above is the product. This section is the one place the competition appears, and it
is deliberately contained: Consylr is being built on its own terms, and a challenge is the
first place it gets tested by people who did not build it.

**Africa Deep Tech Challenge 2026 — "The Laptop LLM Challenge."**
Gate 1 submission closes **2026-08-24 23:45 PDT** (≈ **2026-08-25 09:45 EAT**).
Gate 2 runs 2026-09-08 → 09-29 (reproducibility + technical defence).
Gate 3 final live defence 2026-10-17.
Grand prize USD 8,000 (UGX 29,600,000) + 6-month residency; USD 4,000 second; USD 3,000 third;
USD 1,500 Best African Use Case.

**What the competition imposes that the product would not choose for itself:** a fixed
2,048-token context in the official profiler, a hard 7 GB peak-resident-memory ceiling, and a
scoring split of 50% accuracy and quality · 30% throughput · 20% memory efficiency, with a
thermal penalty. These are real constraints and they are honoured, but they belong to the
harness rather than to the product — the profiler's context limit is why Gate 1 packets are
capped below the range the PRD specifies, for instance, and that cap expires with the gate.

**Contest terms.** The Participation Agreement was read in full and accepted on 2026-08-18. IP
stays with the participant; entering grants a non-exclusive royalty-free licence over the
submission for promotion only, which is consistent with this repository being MIT. The terms may
change under their own §9, so the accepted text is kept and **re-checked against the published
version at submission** — see [docs/decisions.md](docs/decisions.md) §Contest terms.

> [!IMPORTANT]
> **This is not the submission repo.** ADTC Gate 1 is entered from a public **fork of the
> official ADTC template**, carrying an idempotent `download_model.sh` and no committed
> weights. This repo is where the product and its reasoning live; the submission repo is a
> separate artefact produced from it.

## Licensing


Three different things are licensed three different ways here, and collapsing them is the
mistake worth avoiding.

| What | Licence |
|---|---|
| **This repository** — docs, decisions, and the tooling that lands here | **MIT** ([LICENSE](LICENSE), [ADR-0001](docs/adrs/0001-mit-licence-and-public-repository.md)) |
| **The submission repository** — a separate public fork of the official ADTC template | **GPL-3.0-only**, inherited from the template, with every upstream notice retained |
| **Model weights** | The licence of the **exact base checkpoint used**, recorded when the base model is frozen |
| **Datasets and the generator** | Recorded per source in `DATA_PROVENANCE.md`, which exists before the first training run |
| **Brand artwork** | Not published yet, and not published until the mark is redrawn as vector geometry |

Two things that follow, and one that does not:

- **MIT code from here may flow into the GPL-3.0 fork. The reverse is never true.** The
  compatibility runs one way only, and treating the boundary as symmetric is an easy mistake
  to make close to a deadline.
- **Base-model licences matter per checkpoint, not per family.** The Qwen model cards state
  Apache-2.0; Gemma 3 carries the Gemma licensing regime instead, with its own notice and
  redistribution requirements. Whichever wins the bake-off, its terms are recorded from the
  artefact actually downloaded.
- **The template's GPL-3.0 does not make the weights or the training corpus GPL.** Code, model
  and data licences are documented separately and upstream notices are preserved.

## Contributing


Read [CONTRIBUTING.md](CONTRIBUTING.md) first. The short version:

- **GitHub Flow.** Short-lived branch off `main`, pull request in, branch deleted on merge.
  `main` is rebase-only and force-pushing it is refused by the host, not by a policy.
- **Conventional Commits**, lowercase, subject under 50 characters.
- **Sign off every commit** (`git commit -s`). There is no CLA — the
  [DCO](https://developercertificate.org/) is the whole of it, and `Signed-off-by:` is the only
  trailer this project uses.
- **Every pull request names the ADR or RFC it implements or amends.** If the answer is "none",
  the RFC probably comes first.
- **Fixtures are synthetic.** No real people, businesses, ledgers, or locale-plausible phone
  and ID numbers — ever.
- **Test-driven development is the policy**, and the commit sequence is the evidence for it.
  There is no test command yet; `CONTRIBUTING.md` says so plainly rather than implying one.

Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). For a suspected vulnerability, do not open
an issue — follow [SECURITY.md](SECURITY.md).
