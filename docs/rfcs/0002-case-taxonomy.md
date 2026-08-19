# RFC-0002 — the case taxonomy

- **Status:** draft
- **Date:** 2026-08-18
- **Depends on:** [RFC-0001](0001-output-schema.md) (the exception-kind enum this expands),
  [ADR-0003](../adrs/0003-freeze-base-model-and-training-backend.md) (the frozen model)
- **Amends:** [RFC-0001](0001-output-schema.md) — removes `missing_record` from the exception-kind
  enum. Writing the correctness definitions exposed that a missing counterpart was expressible two
  ways, and two ways to state one fact produces inconsistent ground truth.

## Summary

Names the case families once, so the generator, the training mix, the metric table and the report
all mean the same thing by the same word. Defines what a **correct answer** looks like for each —
including the families whose correct answer is a refusal — and fixes the quotas the corpus is
built to.

Freezing this is what makes the grouped split possible. The sealed evaluation splits **by
perturbation family, never by random rows**, so a family that is loosely defined leaks across the
split boundary and reports a score the model did not earn.

## Interface

### Two axes, deliberately not one

The single most confusing thing here is that "family" is used for two different ideas in the
surrounding documents. They are separated permanently:

| Axis | What it is | Where it lives |
|---|---|---|
| **Perturbation family** | *How a case was constructed* — the deformation applied to a clean pair. **This is the split key.** | this RFC, the generator |
| **Exception kind** | *What the model emits* in `exceptions[].kind` | [RFC-0001](0001-output-schema.md) |

They overlap but are not the same set. Some perturbation families have no exception at all
(`clean_match`), and some produce an exception kind that names the absence of a cause
(`cause_not_established`). **A case belongs to exactly one perturbation family**, by construction,
which is what a grouped split requires.

### The families

| Perturbation family | Construction | Correct answer | Exception kind emitted |
|---|---|---|---|
| `clean_match` | A pair that corresponds with no deformation | `supported` match, no exception | — |
| `fee_at_source` | Amount reduced by a fee described in policy | `supported` match + `supported` exception | `fee_at_source` |
| `withholding` | Amount reduced by a withholding described in policy | `supported` match + `supported` exception | `withholding` |
| `timing_cutoff` | Same event, dates either side of a cut-off | `supported` match + `supported` exception | `timing_cutoff` |
| `reference_mangled` | Reference corrupted — truncated, transposed, padded | `supported` match, correspondence carried by other evidence | `reference_mangled` |
| `name_variant` | Counterparty name misspelled, abbreviated, or aliased | `supported` match | `name_variant` |
| `partial_payment` | One obligation settled by several transfers | `supported` many-side match | `partial_payment` |
| `duplicate` | The same event recorded twice on one side | `supported` match + duplicate flagged, and the duplicate is **not** matched twice | `duplicate` |
| `reversal` | A posting and its reversal | `supported` match spanning both | `reversal` |
| `batched_vs_itemised` | One side batched, the other itemised | `supported` many-side match | `batched_vs_itemised` |
| `missing_record` | A record with no counterpart, and nothing explaining it | `open` entry + the record in `residue` | — |
| `cause_not_established` | A real difference the packet does **not** explain | `ambiguous`/`unsupported`, `open` entry, and the exception naming the absence | `cause_not_established` |
| `decoy` | Two records that look alike — often identical amounts — and are **not** the same event | `unsupported` match, **and both records in `residue`** | — |
| `ambiguous_pair` | One record with two equally good counterparts | one `ambiguous` match naming both candidates, never two `supported` ones | — |

The last three carry no exception kind because their correct answer is not an exception. They are
still perturbation families: they are constructed deliberately, and they are split on.

### What "correct" means where the answer is a refusal

Four families have a refusal as the right answer, and each fails differently:

- **`missing_record`** — correct is an `open` entry *and* residue. Producing only one of the two is
  wrong: an unmatched record that is never listed in `residue` is the silent-residue failure the
  schema exists to prevent.
- **`cause_not_established`** — correct is naming the difference while declining its cause.
  Emitting a plausible cause is a **hallucination**, and emitting no exception at all is a
  **miss**. Both are failures and they are counted separately.
- **`decoy`** — correct is an explicit `unsupported` match plus residue for both records. Silence
  scores as a miss, because silence cannot be distinguished from never having looked.
- **`ambiguous_pair`** — correct is one `ambiguous` entry naming both candidates. Two `supported`
  entries is a schema-level contradiction; picking one arbitrarily is a false match.

## Behaviour

### Quotas are two constraints, not one

They are frequently conflated, and conflating them double-counts. A `fee_at_source` case with a
supporting policy line **is** a clearly-supported case — so certainty is a property of a case, not
a family.

**Constraint A — certainty allocation (the mix).** Governs what the model learns to do.

| Band | Share of the SFT mix |
|---|---|
| Clearly supported | **65–75%**, target 70% — a deployment prior, see §The supported band |
| `cause_not_established` cases | **10–15%** — opening value, see §Tuning |
| Remaining ambiguous / unsupported / residue-bearing | the balance |

### The supported band, and why it moved

**The 40–50% band was a training-signal-density choice.** Eleven of the fourteen families
produce a clearly-supported answer, so an equal template split gives roughly 80% supported and
the hard cases arrive too rarely to be learned. Holding supported down to half forced mass onto
the families the model finds difficult. That reasoning was sound for what it was solving.

**65–75% is a deployment-prior choice, and it is a different question.** The product is an
exception analyst reading reconciliation packets that have already passed through an upstream
filter. In the work it is built for, most packets it is shown *are* settleable from the evidence
inside them — the ledger rows and the remittance data are present, and the analyst's job is to
close them and say why. The cases it cannot settle — a document that is not there, a difference
whose cause nothing states, two counterparts equally consistent with one record — are the
minority that gets escalated to a person. Seven in ten closeable and three in ten escalated is
the operating shape being claimed, so it is the shape the training mix should carry.

**The exam's own 78.9% supported is not the justification and must never be cited as one.**
sealed-v4 is near-uniform across families because it was built to measure every family, not to
model deployment; that its supported share lands near this band is a coincidence of arithmetic,
and tuning a training mix toward a holdout's composition is optimising the test — the failure
rule 4 below exists to prevent. If the deployment claim above is wrong, this band is wrong, and
the exam has nothing to say about it either way.

**Density has not stopped mattering.** Constraint B is unchanged and every family still clears
its floor. A supported share this high is only safe while the hard families remain individually
measurable, which is why the two constraints are still asserted jointly rather than traded.

**Constraint B — family coverage.** Every family in the table above is represented in sufficient
number to be measured *on its own*, because per-family metrics are reported and a family with a
handful of cases produces a number with no meaning.

**The two must be jointly satisfiable, and the generator asserts both.** A quota plan that
satisfies one while violating the other is a defect the generator refuses to emit, not a
compromise it silently makes.

### Tuning the `cause_not_established` ratio

The opening value is **10–15% of the total mix** — large enough that the model learns the family
as a real answer, small enough that abstention stays expensive.

**That is a starting point, recorded as one. It is not a decision.** The ratio is a *measured*
quantity, and these four rules are what stop it degrading back into a preference:

1. **Tune only between training runs, and only on sealed-set measurements.** Never mid-run, never
   on intuition about the outputs.
2. **One knob, two gauges** ([#16](https://github.com/raheebwa/consylr/issues/16)):
   - false-abstention rate on clearly-supported cases drifting toward **5%** → the ratio **comes
     down**;
   - correct-abstention rate on unsupported cases sitting under **90%** → the ratio **goes up**.
   These pull in opposite directions on purpose. If both fire at once, the problem is not the
   ratio and turning the knob will not fix it.
3. **Every change is recorded with the measurement that drove it** — a tuning-log line carrying
   the date, the old and new ratio, and both gauge readings. **Silent retuning is how a measured
   quantity degrades into a vibe.**
4. **The sealed set's family distribution is frozen independently and never moves with the
   training mix.** *Tune the mix; never the exam.*

### Tuning log

Every change to a mix ratio, with the measurement that drove it. Rule 3 above requires the line;
this is where it goes. A ratio with no line here was changed silently, which is the failure the
rule names.

| Date | Ratio | From | To | Measurement that drove it |
|---|---|---|---|---|
| 2026-08-19 | clearly supported | 40–50% | 65–75%, target 70% | Not a gauge reading. The band was re-derived from the deployment claim above after the gauges were found to be uninformative about it: on run 4's checkpoints **both** fire at once — false abstention 38.8% and correct abstention 73.7% at 6,000 iterations, 8.8% and 35.1% at 4,000 — which rule 2 states means the ratio is not the cause. The evidence for what *is* the cause is recorded against the decoupling change in RFC-0003: certainty is currently a deterministic function of family in every corpus this project has built, so a model can score certainty perfectly by recognising the family and never reading a policy line. The mix moves here because the deployment claim says it should, not because a gauge asked for it. |

Rule 4 is what makes the other three safe. Without it, tuning a training ratio against a threshold
measured on the sealed set is optimising the test — the ratio would converge on whatever flatters
the score, and the score would stop meaning anything. **The sealed distribution is set once, from
what the product must handle, and a change to it invalidates every prior comparison** and must be
recorded as a new evaluation rather than an adjustment to the old one.

### The grouped split

Cases are split into training and sealed roles **by perturbation family**. A random split puts
near-identical constructions on both sides of the boundary — same seed lineage, same template,
same deformation — and the model scores well by recognising cases it has effectively seen.

Consequences the generator must honour:

- A family present in the sealed set may still appear in training, but **no scenario template may
  cross the boundary**. The template is the unit of separation, not the row.
- Per-family metrics are reported **and** pooled, because a collapse usually starts in one family
  and a pooled number hides it.
- Seeds are recorded so the split is reproducible but never accidentally re-drawn.

## What it must refuse to do

- **No case in two families.** Assignment is by construction and is exactly one. A case that could
  be argued into two families is a definition defect, and the fix is to sharpen the definitions —
  not to pick one.
- **No family without a correctness definition.** A family that cannot say what a right answer
  looks like cannot be scored, so it cannot be generated.
- **No out-of-scope shapes.** The generator cannot emit what the PRD rules out: unconstrained
  many-to-many at scale, fraud attribution, or anything requiring evidence outside the packet.
- **No tuning the sealed distribution.** See rule 4. This is the one that will be tempting.
- **No real records.** Every case is procedurally generated, so ground truth is known by
  construction rather than inferred.

## Verification

- **Per-family quota audit** on every generated corpus, failing the build when a family falls
  below its floor.
- **Certainty-band audit**, asserting the 40–50% supported floor and the current
  `cause_not_established` ratio.
- **Template-crossing check**: no scenario template contributes to both roles.
- **Every case validates against [RFC-0001](0001-output-schema.md)**, using the validator that
  ships in the product.
- **Ground-truth agreement**: the expected output stored with a case is exactly what a correct
  model would emit, checked mechanically rather than by eye.
- **A human spot-check of roughly 100 examples**, spanning every family — the one check that
  catches a family whose definition is coherent and wrong.

## Open questions

1. How many templates per family are enough for the grouped split to be meaningful? Too few and
   the split separates almost nothing.
2. Should `decoy` be split by *why* the records look alike — identical amount, near-identical
   name, adjacent reference? Each is a different discrimination and may deserve its own family.
3. Does `duplicate` need a variant where the duplicate is on the *other* side, and is that a
   different family or the same one?
4. The `open[].need` field is free text ([RFC-0001](0001-output-schema.md) open question 1). Once
   the corpus exists, does the set of distinct needs collapse to something small enough to be an
   enum?
