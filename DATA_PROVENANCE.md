# Data provenance

Where Consylr's training and evaluation data comes from, what it is not, and how
a reader who has none of it can obtain the same thing.

This exists because the central claim of the evaluation is that the ground truth
is known rather than inferred. That claim is worth exactly as much as this
document's ability to be checked.

## The short version

**Every case is procedurally generated. No real business, person, account,
reference, invoice or ledger entry appears in any corpus, at any point.** There
is no dataset behind this that was cleaned, anonymised or sampled — there is a
generator, a committed configuration, and a seed.

## Ground truth is a by-product of construction

A case is built by applying a **named deformation** to a clean corresponding
pair: a fee deducted at source, a reference transposed, one obligation settled by
two transfers, a record with no counterpart, two records that look alike and are
not the same event.

The correct answer therefore falls out of *how the case was built*, rather than
being a judgement made afterwards by a person or a model. Nothing labels this
data, because nothing needs to.

Two refusals hold that up, and both are code rather than intention:

- a family with no deformation is refused rather than approximated, because
  emitting the nearest case the builder can manage would produce ground truth
  that is a guess wearing the shape of a construction;
- **every case is put to the validator that ships in the product** before it may
  be written. "Correct by construction" is a claim about the builder, and a
  claim needs something able to contradict it.

## Reproducibility, and exactly how far it reaches

**The corpora are not committed.** They are reproducible from a committed
configuration and a seed, which is a stronger provenance story than shipping the
files: a reader regenerates them rather than trusting them.

Every random draw is derived from `(root seed, template id, case index)` rather
than from one shared stream. A shared stream would make case *n* depend on how
many draws preceded it, so adding a family at the front would silently change
every case behind it, and a corpus regenerated after an unrelated edit would no
longer be the one the published numbers came from.

The build makes **no network call**. Setup fetches the tokeniser once; the build
does not, and says exactly what to fetch if it is absent.

## What is calibrated against reality, and what is not

The generator's formatting conventions — reference shapes, amount and date
distributions, the ways a reference gets mangled, the sector vocabulary — are
informed by the *shapes* of real-world public records.

**What is committed is aggregate patterns only.** No record, no identifier, no
counterparty name and no amount is carried across from any real source. The
counterparties are invented; the references follow a documented shape; the
amounts are chosen to span three orders of magnitude so that a proportional
deduction is observable at the small end and a batched total is plausible at the
large.

This is a deliberate limit rather than a shortcut. Procedurally generated cases
are both safer **and better evidence**, because the ground truth is known by
construction rather than inferred — and a corpus calibrated on real records is
one nobody else can regenerate.

## Paraphrase: available, off, and never used

The design permits a frontier model to paraphrase free-text surface fields only
— never a label, a number, a reference, or a correspondence decision.

**It has never been used. Every corpus to date is fully deterministic.**

The reason it is recorded here rather than omitted is that turning it on has a
permanent consequence: a paraphrased corpus is **not reproducible**, because a
frontier-model call is neither deterministic nor offline. Such a corpus becomes a
*preserved derived artefact* that must be kept rather than regenerated, and any
number measured on it binds to the preserved copy. The sealed evaluation set may
never be paraphrased at all, so that every published accuracy figure stays
attached to something a stranger can rebuild.

## The pin chain

A number is only as reproducible as the artefacts it was measured against, so
each is pinned and each is checkable:

| Artefact | How it is pinned |
|---|---|
| Prompt template | SHA-256 recorded on **every case**, and re-asserted when the corpus is read |
| Tokeniser | the frozen model's own, resolved from an explicit path; budgets are measured with it and never estimated |
| Exam | content digest over its packets, asserted by a scoring run **before** it scores |
| Training corpus | content digest, recorded when written |
| Templates | per-template digest recorded on every case that came from one |

No digest is transcribed into prose anywhere in this repository. A transcribed
digest is a second source of truth that can disagree with the first and has to be
re-copied whenever the artefact moves, so the documentation names the function
that computes it and a run asserts the value it computes.

## Separation of training from evaluation

The evaluation set is held out by **scenario template**, never by row: a random
split would put near-identical constructions on both sides, and the model would
score well by recognising cases it had effectively already seen.

That separation is enforced by comparison rather than by argument. **Every
training packet is compared byte for byte against every packet in the evaluation
set**, and a single collision refuses the entire corpus — nothing is written.
The same audit refuses a corpus containing the same packet twice, or one packet
under two different answers.

The training corpus additionally **shuffles record order per case before
identifiers are assigned**, so correspondence cannot be recovered from position.
The evaluation set does not, which is recorded here because it matters for how
its numbers are read: a model that pairs record *n* with record *n* and consults
nothing else scores **0.839** correspondence F1 on that exam. Every reported F1
is published beside that control.

## What this data cannot support

- It is not evidence about real ledgers, real reconciliation workloads, or any
  particular organisation's records.
- Distributional realism is calibrated on shapes, not on measured frequencies
  from a real population, so it should not be read as one.
- The evaluation set is deliberately narrower in surface than the training
  corpus. Training broad and examining narrow understates rather than overstates
  what the model can do, and it is stated so that nobody has to infer it.
