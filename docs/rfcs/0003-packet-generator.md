# RFC-0003 — the packet generator

- **Status:** draft
- **Date:** 2026-08-18
- **Depends on:** [RFC-0001](0001-output-schema.md) (the output it must produce),
  [RFC-0002](0002-case-taxonomy.md) (the families and quotas it must satisfy),
  [ADR-0003](../adrs/0003-freeze-base-model-and-training-backend.md) (the tokeniser it budgets in)

## Summary

The generator is the source of every training and evaluation packet. Nothing else produces one.

Its defining property is that **ground truth is known by construction rather than inferred**: a
case is built by applying a named deformation to a clean pair, so the correct answer is a
by-product of the construction and not a judgement made afterwards. That is what makes the
evaluation honest, and it is also the whole of the provenance story — a corpus that can be
regenerated from a seed needs no claims made about where it came from. That is why the sealed
evaluation set is never paraphrased, and why the reproducibility guarantee below is stated against
the deterministic layer rather than against every artefact this produces.

It is also the last line before the silent failure this project is most exposed to: an
over-budget packet is **left-truncated by the harness**, producing valid JSON about evidence the
model never saw ([RFC-0001](0001-output-schema.md) §Behaviour). The generator is the only place
that failure is visible, so it refuses to emit one.

## Interface

### Command surface

```
consylr-gen build   --config <path> --seed <int> --out <dir>
consylr-gen seal    --config <sealed-config> --seed <int> --out <dir>
consylr-gen audit   --corpus <dir> [--deep]
consylr-gen inspect --corpus <dir> --case <id>
```

**`build` and `seal` are separate commands, and that is a safety property rather than tidiness.**
A single command with `--role sealed` can be pointed at the training config by a typo, and the
resulting corpus would look correct. `seal` accepts only a sealed-specific configuration whose
family distribution is frozen independently of the training mix
([RFC-0002](0002-case-taxonomy.md) guardrail 4) and **rejects a training configuration
structurally**, not by convention.

`audit` re-runs every check against a corpus already on disk and is what CI calls. `inspect`
renders one case — its packet, its expected output, its family, and its template lineage —
because a corpus nobody can read case-by-case is a corpus nobody can check.

### What a case is

```
case/
  packet.json     the evidence packet handed to the model
  expected.json   the correct model output, per RFC-0001
  meta.json       family, template id, seed, role, rendered prompt token count
```

`meta.json` is not decoration. `template_id` is what the grouped split separates on, and
`prompt_tokens` is what the fast audit path re-checks without re-tokenising the whole corpus.

### A template is a data file, not a function

A scenario template is a **parameterised description in data, with a stable id**, interpreted by
the generator. It is not code.

This follows from what a template is *for*: it is the unit of the grouped split, so the split
check has to be auditable from artefacts alone. Behaviour hidden in a function makes "no template
crossed the boundary" unfalsifiable from outside the process that produced the corpus — a reader
would have to trust the generator rather than check it. In data, a template is diffable, its id is
stable across refactors of the code that reads it, and a reviewer can see what changed.

### What makes two templates the same scenario

The split separates on templates, so "the same template" is load-bearing: get it wrong in one
direction and one scenario is trained on and examined on; wrong in the other and two different
scenarios are merged and one is never used. The first failure **raises** measured accuracy, which
is why this is spec rather than an implementation detail.

**Identity is a digest over a projection of what the builder reads, in the form the model will see
it — never over the file.** The projection is exactly:

| In the projection | Not in it | Why |
|---|---|---|
| `family` | the declared `id` | the id is a label over the scenario, so two ids for one scenario are an alias, not two templates |
| each record's `ref`, `date`, `amount` | each record's `party` | a counterparty as written is free-text surface, which paraphrase may rewrite |
| the `id` of each policy and document | their `text` | *which* line is cited is structural; its prose is not |

with three normalisations, each closing a difference no reader of a rendered packet can perceive:

- **Amounts** are canonicalised before comparison. `"1000.00"`, `"1000.0"`, `1000` and `1000.0`
  are one amount, because the generator collapses them to one `Decimal` everywhere it reasons.
- **Text** is NFC-normalised, stripped of Unicode format characters, and has its whitespace
  collapsed. A zero-width space in a reference is invisible in a rendered packet *and in a diff*,
  so without this a corpus can be poisoned with no visible edit; NFD against NFC is macOS against
  everything else.
- **Record order** does not count. Applying one permutation to both sides preserves every clean
  pair, and a JSON dump with sorted keys sorts keys and never arrays.

**A template is a closed world.** The body carries `id`, `family`, `left`, `right`, `policy` and
`documents`; a record carries `ref`, `party`, `date` and `amount`; a policy or document entry
carries `id` and `text`, and that `text` is prose. **Anything else is refused, by the audit and by
the builder, from one definition.** This is not tidiness. An unclassified key either reaches the
packet — where it is a difference the model can see that nothing classified — or sits in the body
unread, where it changes what counts as this scenario while changing nothing the model sees. Both
are leaks, and a denylist of prose field names can only ever chase the spellings someone thought
of. Refusing the unknown makes the classification complete **by construction**, which is the same
property the ground truth already rests on.

Two identities are kept, and they answer different questions. The **content** digest covers the
whole file and answers "has this template changed since the corpus was built" — drift, where any
edit is worth reporting. The **projection** digest answers "is this the same scenario" and is what
the split, the alias check and the near-duplicate check use.

### The prompt template is a frozen artefact

The budget is asserted on the **rendered prompt**, so a corpus cannot be generated without the
template that renders it. That dependency was invisible while the budget check was optional, and
it is not a nuisance — it is the same relationship the corpus already has with the tokeniser, and
it gets the same treatment.

**The template is pinned, versioned, and referenced by digest.** It is frozen before the sealed
set is built, its SHA-256 is recorded in every corpus's configuration beside the tokeniser's, and
a corpus whose recorded template digest does not match the frozen artefact **fails audit**. The
corpus is versioned with its configuration already; the template joins it.

**One artefact, rendered by everything.** The CLI, the training-data emission, the sealed set, and
the profiler run all render through it. The profiler applies **no chat template of its own**, so
this file is the model's entire interface — and four surfaces rendering three ways would be the
four-mode trap, self-inflicted. Nothing may render a prompt any other way.

**Changing it invalidates the corpus.** Every budget assertion is re-asserted over the whole
corpus and the sealed set is re-validated or rebuilt. This is stated here so that a "small wording
tweak" is visibly a corpus-invalidating event rather than a tidy-up: the model was trained on one
interface and a changed one is a different interface, whatever the diff looks like.

**Ordering: what the model cannot afford to lose goes last.** The harness left-truncates the
prompt, so the *earliest* tokens are the ones at risk. The packet therefore comes first and the
instructions last, which also puts the instructions closest to generation where adherence is
best.

That ordering is a deliberate trade with three consequences, and all three are named here rather
than only the one that motivated it.

**It fails quietly rather than loudly.** If a prompt ever exceeded the window, instructions-first
would lose the schema and emit something unparseable, which the parse rate would show.
Instructions-last emits well-formed JSON about evidence that was truncated away. That is only
acceptable because the budget assertion runs **at inference as well as at build**, so the
truncation case does not arise; a CLI that skipped the check would turn this ordering from an
optimisation into a liability.

**It puts the instructions closest to generation**, where instruction-following is strongest. That
is the gain being bought.

**And it ends the prompt in instruction register**, which was discovered by measurement rather
than reasoning. An untuned model's most natural continuation of a document that ends in
instructions is *more instructions*: asked to reconcile a packet, the base model wrote further
rules in the same voice — "A record with no counterpart at all is not an exception: leave it out
of every match…" — rather than answering. It scored zero on every metric, and not because it could
not produce JSON.

A fine-tune learns the transition, so this is a property of the base rather than a defect in the
template. It is recorded because it shapes how a baseline must be read: the honest comparison is
three-way — what the base cannot format, what it can do once an answer cue is supplied, and what
the fine-tune does in the mode the profiler actually runs. Reporting only the first invites the
question of whether the training taught reconciliation or merely taught JSON.

**The template's own tokens count.** It sits inside the ~1,200-token allowance, not beside it —
which is what `template_overhead` in the budget records, and why the packet allowance is the
remainder rather than the whole.

### Configuration

One file, versioned with the corpus it produced. It carries the quota plan, the family list, the
budget limits, and a reference to the **pattern configuration** — the committed, aggregate-only
formatting conventions, amount and date distributions, sector vocabulary and mangling patterns
distilled from real-world records ([#20](https://github.com/raheebwa/consylr/issues/20)).

**The generator plus its committed configuration must regenerate the whole corpus anywhere, with
no external data dependency.** That property is not negotiable: it is what lets someone with none
of the source material reproduce the evidence.

## Behaviour

### Determinism, and exactly how far it reaches

**The deterministic layer — the corpus before any paraphrase — is byte-for-byte reproducible from
config and seed, on any machine, with no network.** That is the guarantee, and §Optional paraphrase
is scoped against it rather than quietly contradicting it.

Every random draw comes from a seed derived from `(root_seed, template_id, case_index)` rather
than from one shared stream. A shared stream makes case *n* depend on how many cases were drawn
before it, so adding a family at the front silently changes every case behind it, and a corpus
regenerated after an unrelated edit no longer matches the one the numbers came from.

### The token-budget assertion

The generator **rejects** any case whose rendered prompt exceeds the budget. Not a warning, not a
log line — a rejection, and the build fails.

- Counted with the **frozen model's tokeniser** ([ADR-0003](../adrs/0003-freeze-base-model-and-training-backend.md)),
  never a character or word heuristic. A heuristic is wrong by exactly the amount that matters at
  the boundary.

  **Where that tokeniser comes from** follows the artefact policy this repository already has —
  model weights are *fetched at setup, never committed*, and a tokeniser is the same class of
  thing. So: a documented one-command fetch into the standard cache; resolution order **explicit
  config or environment path → cache**; the **SHA-256 of the tokeniser file pinned in the
  committed generator config**; and the **build itself makes zero network calls**, failing loudly
  with the exact fetch command when the file is absent. "No network at build" was never "no
  network at setup".
- Asserted on the **rendered prompt** — the exact string the runtime sends, after templating —
  not on the packet before it.
- Output headroom is reserved explicitly, so the check fails when headroom is eaten rather than
  only when the prompt alone overflows.
- A rejection names the case, the measured count, the limit, and which of the two it broke.

*[competition constraint — ADTC profiler]* Budget: packet ≤ ~1,200 tokens, ≥ ~600 tokens output
headroom, 5–10 records per Gate 1 packet, inside a 2,048-token window where the harness reserves
256 generation tokens by default.

### Quota satisfaction, and failing honestly

Both constraints from [RFC-0002](0002-case-taxonomy.md) — the certainty allocation and family
coverage — are checked **before** a corpus is written, not after.

If they cannot be jointly satisfied at the requested size, the generator **fails and says which
constraint it could not meet and by how much.** It does not silently produce the nearest corpus it
can, because a corpus that quietly missed its quota still produces a score, and that score looks
exactly like a good one.

### The grouped split

Roles are separated by **scenario template**, not by row.

A template may produce many cases; **every case from one template lands in exactly one role.** The
generator refuses to write a corpus where a template appears in both — that is the check, and it
is mechanical rather than a matter of care.

Family assignment is by construction and is exactly one family per case, which is what makes
splitting on family well-defined at all.

### Optional paraphrase, and the promise it cannot keep

A frontier model may paraphrase **free-text surface fields only** — descriptions, merchant-style
names. Never a label, a number, a reference, or a correspondence decision
([#19](https://github.com/raheebwa/consylr/issues/19)).

Every paraphrased case is **deterministically re-validated** afterwards: schema, arithmetic, and
family assignment. A paraphrase that changes any of the three is **discarded, not corrected** —
correcting it means a human deciding what the case now is, which is exactly the inferred ground
truth this design exists to avoid.

**A paraphrased corpus is not reproducible, and pretending otherwise would be the more expensive
mistake.** A frontier-model call is neither deterministic nor offline, so the moment paraphrase is
on, "same config, same seed, same corpus" stops being true. The honest consequence:

- A paraphrased corpus is a **derived artefact that must be preserved, not re-derived.** It is
  kept, not regenerated, and any published number measured on it **binds to the preserved
  artefact**.
- `meta.json` records, per case, whether it was paraphrased and by what — enough to prove which
  cases were touched, so the deterministic subset remains separable and independently checkable.
- The deterministic layer beneath it stays regenerable, and that is what the reproducibility claim
  refers to.

**The sealed evaluation set is never paraphrased. That is a refusal, not a default.** The exam has
to be regenerable by someone holding only the config and the seed, and a preserved-artefact exam is
one nobody else can obtain — corpora are not committed, so a preserved sealed set would exist only
where it was made. Every published accuracy figure comes from the sealed set, so this keeps the
figures that matter attached to something reproducible.

For the training corpus, paraphrase remains permitted and **off by default**. The tension is worth
stating plainly: it exists only to stop surface text being uniform enough that the model learns the
generator rather than the task, and it is paid for in a corpus that must be stored forever and
cannot be handed to anyone as a recipe. If that price ever looks worse than the uniformity it
buys, the right answer is to leave it off — and a corpus where some cases passed through another
model and some did not is two corpora unless the record says which.

### Audit depth

`audit` must be able to fail a corpus **it did not generate** — otherwise an externally-supplied
corpus is checkable only on trust. But a foreign corpus is exactly the one whose `meta.json`
cannot be believed: trusting a recorded `prompt_tokens` on a corpus from elsewhere makes the audit
a formality that restates whatever the file claims.

So there are two depths, and the difference is what they are allowed to trust:

| Mode | Trusts `meta.json` | Use |
|---|---|---|
| fast (default) | yes | Local iteration only, where the corpus was just built here |
| **`--deep`** | **no** — re-tokenises every prompt and re-validates every expected output from scratch | Any corpus whose provenance is not this machine, and every CI run |

CI runs **deep on the whole sealed set** — 200 packets, cheap enough that there is no reason not
to — and **deep on a sample of the training corpus**, because 8,000–15,000 cases is not cheap and
a sampled deep check still catches a systematic fault.

**The fast path is a local convenience and is never the basis for a published claim.** Any figure
that reaches a document comes from a deep audit.

### Scale

Roughly **300–500 gold scenario templates**, randomised into **8,000–15,000** training examples,
and a separately-frozen sealed set of ~200 packets
([#15](https://github.com/raheebwa/consylr/issues/15)).

## What it must refuse to do

- **Emit an over-budget case.** The failure it prevents is invisible downstream.
- **Emit a corpus that misses its quota.** Fail loudly instead.
- **Let a template cross the split boundary.**
- **Emit a case assignable to two families.** That is a taxonomy defect, and the generator
  surfaces it rather than picking one.
- **Emit an out-of-scope shape** — unconstrained many-to-many at scale, fraud attribution, or
  anything requiring evidence outside the packet.
- **Touch real data.** No real business, person, account, reference or ledger entry, from any
  source. The pattern configuration carries **aggregate patterns only**, and it is swept like
  every other committed file.
- **Depend on anything unavailable to a stranger.** No network **at build time**, no private
  dataset, no credential. Setup may fetch the tokeniser; the build may not.
- **Repair a failed paraphrase.**
- **Paraphrase the sealed set.** The exam stays regenerable from a config and a seed.
- **Publish a figure from a fast audit.** Deep or it does not count.

## Verification

Test-driven, per `CONTRIBUTING.md`: the failing test first, then the code.

### Property tests — the invariants that must hold for every corpus

| Invariant | Why it matters |
|---|---|
| Same config + seed → identical corpus **at the deterministic layer** | Reproducibility is the provenance story, and the layer is named because paraphrase breaks it |
| Every case's expected output validates against RFC-0001, **using the validator that ships in the product** | A second validator written for the corpus tests the second validator |
| Every rendered prompt is inside budget | The silent-truncation failure |
| Every case belongs to exactly one family | Grouped split is otherwise undefined |
| No template appears in both roles | Otherwise the split separates nothing |
| Quota plan satisfied on both constraints | Otherwise the score is unearned |
| Every ID referenced in `expected.json` resolves in `packet.json` | Ground truth must be self-consistent |
| Arithmetic in every case is consistent with its construction | The deformation and the numbers must agree |

### Corpus-level audits, run by `audit` and by CI

- **Near-duplicate detection** across cases, so randomisation is not producing the same case twice
  under different ids.
- **Per-family quota audit**, failing below a family's floor.
- **Certainty-band audit**, asserting the 40–50% supported floor and the current
  `cause_not_established` ratio.
- **A human spot-check of roughly 100 examples**, spanning every family. It is the only check that
  catches a family whose definition is coherent and wrong, and it is not automatable — so it is
  scheduled rather than hoped for.

### What the tests must not do

Assert the shape of the implementation. The check is whether a test would survive rewriting the
generator while keeping its output contract; if changing *how* a case is built forces a test to
change, the test describes the code rather than constraining it.

## Open questions

All four questions this RFC opened have been settled and are written into the sections above:
the tokeniser's provenance (§The token-budget assertion), the separate `seal` command
(§Command surface), templates as data (§A template is a data file), and the two audit depths
(§Audit depth). What remains open is narrower:

1. How many templates per family make the grouped split meaningful? Too few and it separates
   almost nothing — carried from [RFC-0002](0002-case-taxonomy.md).
2. What sample size makes deep-on-sample a real check rather than a gesture, and is the sample
   drawn per family or across the corpus?
3. Should a paraphrased training corpus be given a content hash that a run record cites, so a
   published number names the exact preserved artefact rather than a directory?
