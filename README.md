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

## The twin probe, and its answers

The twin probe is the instrument behind the abstention claim, and the one number
from this project most likely to travel without its context. So the answers are
committed, not just the scores.

Each of the 75 pairs is two packets whose records, amounts, dates and documents are
byte-identical and whose policy differs by one line. The metric is an
**abstention-direction flip**: the settled half answered, the withheld half declined
for a cause the packet does not establish. The two ways of failing are counted apart,
because a model that declines everything gets every withheld half right and is useless.

**It scores direction, not full correctness.** It does not check which record the
declined cause was attached to, whether the output was schema-valid, or whether the
correspondences were right. Scored strictly on all three, the shipped artefact reaches
**37 of 75** rather than 58 — 11 of the 58 name the wrong record, 7 have a
schema-invalid half, and only 3 pairs are exact on both complete outputs. Both figures
are recomputable from the files below with `tools/probe_report.py` and the corpus.

`evidence-probe/` holds the raw generations — every one of the 150 answers, verbatim,
for ten runs. They fall into two artefact classes, and the tables are not
interchangeable.

### The shipped class: the quantisation ablation

Eight builds of the same fused weights. This is the ablation the report's
quantisation argument rests on, and the shipped artefact is one row of it.

| result file | build | flip rate | asserted on withheld |
|---|---|---|---|
| `eval-probe-v1-fused-v5.json` | MLX parent, before conversion | 84.0% | 12 |
| `eval-probe-v1-consylr-v5-f16-profiler.json` | f16 GGUF, unquantised | 84.0% | 12 |
| `eval-probe-v1-consylr-v5-Q6_K-imat-profiler.json` | **Q6_K + imatrix — shipped** | **77.3%** | 17 |
| `eval-probe-v1-consylr-v5-Q6_K-plain-profiler.json` | Q6_K, no imatrix | 58.7% | 31 |
| `eval-probe-v1-consylr-v5-Q5_K_M-imat-profiler.json` | Q5_K_M + imatrix | 82.7% | 13 |
| `eval-probe-v1-consylr-v5-Q5_K_M-profiler.json` | Q5_K_M, no imatrix | 57.3% | 32 |
| `eval-probe-v1-consylr-v5-Q4_K_M-imat-profiler.json` | Q4_K_M + imatrix | 20.0% | 60 |
| `eval-probe-v1-consylr-v5-Q4_K_M-profiler.json` | Q4_K_M, no imatrix | 1.3% | 74 |

The conversion out of the training framework costs nothing — the f16 GGUF matches its
MLX parent pair for pair, 63 flips each — so the whole 84.0 → 1.3 collapse belongs to
quantisation, which is what the importance-matrix work exists to answer.

### The shortlist class: unfused adapter probes

Two runs against the base model with a LoRA adapter attached, before any fusing or
conversion. These are the instrument the training ladder was judged on — they say which
checkpoint to keep, not how the shipped artefact behaves. **They are not comparable to
the table above**, and no claim about the shipped model should be read off them.

| result file | checkpoint | flip rate | asserted on withheld |
|---|---|---|---|
| `eval-probe-v1-Qwen3-4B-Instruct-2507-4bit-adapters-v5-0008000.json` | rung 8,000 — **rejected** | 0.0% | 75 |
| `eval-probe-v1-Qwen3-4B-Instruct-2507-4bit-adapters-v5.json` | final adapter — kept | 78.7% | 16 |

Rung 8,000 asserts a cause on all 75 withheld halves: 0.0% in every family, no
exception. That is the behaviour the ladder exists to catch, and it is why the
checkpoint two thirds of the way through training was thrown away rather than shipped.
The evidence for a rejection is worth as much as the evidence for a choice.

**Declined on settled is 0, and unparsed halves is 0, in all ten runs.** Nothing here is
a model that learned to decline its way to a score.

### Reproducing it end to end

Three ingredients, all in this repository:

1. **The prompts.** Rebuild the corpus from `templates-probe/` — the build is seeded
   and prints a content digest, so an independent rebuild is checkable rather than
   trusted:

       CONSYLR_TOKENISER=/path/to/tokenizer.json \
       python -m tools.build_probe_corpus <exam dir> <train corpus dir> <out dir>

2. **The answers.** The files above.

3. **The scorer.** Point it at both:

       python -m tools.probe_report <probe corpus dir> \
           evidence-probe/eval-probe-v1-consylr-v5-Q6_K-imat-profiler.json

   which prints `flip rate 77.3% (58 both halves right)` — the scorer's own wording for
   the direction metric described above — plus `asserted on withheld 17`,
   `declined on settled 0`, `unparsed halves 0`, and the per-family split.

Every result file carries `exam_digest` and `prompt_digest`. All ten share one value of
each — `1d7ef9d5…` and `fad3f869…` — so within a class the arms are comparable by
construction: the same packets, the same prompt, one variable changed.

That digest pair is also why these files are here at all, when this project's own rule is
that run output is regenerated rather than committed. Regenerable output is not evidence;
it is a promise that evidence could be produced. These are pinned: an independent rebuild
of the corpus can be checked against `exam_digest` before the answers are scored, so what
is committed is verifiable rather than merely available.

Three fields are not verbatim. `eval-probe-v1-fused-v5.json` recorded its `model`, and the
two adapter runs recorded their `adapter`, as absolute paths on the machine that produced
them; each is normalised here to the path relative to the corpus root. No other field in
any file was touched, and no answer in any file was touched.

## The benchmark number, at full sample

The twin probe above measures one specific behaviour. The general-capability number
is `arc_easy`, and `evidence-arc/` holds it at the full test split rather than a
sample — 2,376 items, not the 50 the tooling defaults to.

| | |
|---|---|
| benchmark | `arc_easy`, metric `acc_norm` |
| samples | 2,376 — the entire test split |
| **acc_norm** | **0.8123** |
| CI95 | 0.7966 – 0.8280 (binomial SE 0.0080) |
| wall clock | 9,544 s |

Measured on the shipped artefact in its quantised form, `consylr-v5-Q6_K-imat.gguf`,
whose sha256 was verified against the frozen pin both before the run and after it. Not
the unquantised parent, not an adapter — the file the download script fetches. This is
the same quantity a laptop-LLM accuracy stage measures when it is pointed at the raw
GGUF, which is why it is worth stating at full sample instead of at a default.

The result file is named for the measurement it was originally run as — a ceiling check
on the shipped 4B — and the `label` field inside carries the same name.

Harness, pinned:

| | |
|---|---|
| `lm_eval` | 0.4.12 |
| `llama-cpp-python` | 0.3.35 |
| Python | 3.13.11 |
| seed | 42 |
| context window | 2,048 tokens |

The call, against the official profiler's own accuracy stage:

    from adtc_profiler import accuracy
    accuracy.run_benchmark(Path("consylr-v5-Q6_K-imat.gguf"),
                           task="arc_easy", limit=2376, seed=42)

Evaluated in-process against the quantised weights: context and continuation are
tokenised, evaluated once, and the continuation log-probabilities read from the logits.
The alternative backends are unusable here — one dequantises the GGUF to FP32 and needs
roughly 12 GB for a model whose quantised file fits in an eighth of that, and the other
returns echoed log-probabilities shifted by one position, which makes every ranking
near-random.

One field is not verbatim: `model_path` recorded an absolute path on the machine that
produced the result, normalised here to the artefact's bare filename. Nothing else in
the file was touched.

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
