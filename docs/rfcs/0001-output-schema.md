# RFC-0001 — the output schema

- **Status:** draft
- **Date:** 2026-08-18
- **Depends on:** [ADR-0003](../adrs/0003-freeze-base-model-and-training-backend.md) (the frozen
  model, and therefore the tokeniser these budgets are measured in)

## Summary

The contract for one analysis: a bounded evidence packet goes in, and a single JSON object comes
out describing which records correspond, which exceptions the evidence supports, what is missing,
what is left over, and what a human is being asked to authorise.

Everything downstream codes against this: the packet generator, the validator, the training
targets, the CLI, and the two public test prompts. **Freezing it is the point** — once frozen,
the sealed evaluation decides the product's positioning, and a schema that keeps moving means a
score that means nothing.

The boundary this document draws is not between fields. It is between **what the model is
allowed to author** and **what only the deterministic layer may author**. That line is the
product.

## Interface

### Two documents, not one

| Document | Authored by | Contains |
|---|---|---|
| **Model output** | the model, alone | correspondence, exception classification, certainty, citations, residue |
| **Report** | the deterministic layer | the model output, plus verification outcomes and every computed number |

The model emits the first. The validator reads it, checks it, computes what only it may compute,
and emits the second. **A consumer never sees model output directly** — it sees a report, in
which every number is either quoted from a source record with its record ID, or computed by the
validator and marked as such.

This is how "generation is never the authority for a number" becomes structural instead of
aspirational. There is no field in the model output whose value is a computed figure, so there
is nothing for the model to get wrong arithmetically. It cites; the validator calculates.

### Model output

```json
{
  "matches": [
    {"l": ["A-017"], "r": ["B-004"], "c": "supported", "why": ["A-017", "B-004", "P-02:L7"]}
  ],
  "exceptions": [
    {"on": ["A-017", "B-004"], "kind": "fee_at_source", "c": "supported", "why": ["P-02:L7"]}
  ],
  "open": [
    {"on": ["A-019"], "need": "settlement breakdown", "why": ["P-02:L11"]}
  ],
  "residue": {"l": ["A-019"], "r": ["B-011"]},
  "do": [
    {"act": "accept", "on": ["A-017", "B-004"]},
    {"act": "hold", "on": ["A-019"]}
  ]
}
```

Field by field. Every one has to justify its tokens; the rationale column is why it survived.

| Field | Type | Required | Why it exists |
|---|---|---|---|
| `matches[].l` / `.r` | array of record IDs | yes | The correspondence claim. Two sides, so one-to-many and many-to-one are the same shape as one-to-one — no separate field, no separate code path. |
| `matches[].c` | `supported` \| `ambiguous` \| `unsupported` | yes | Certainty, categorical. See §What it must refuse, and §Residue for what `unsupported` means for a record's status. |
| `matches[].why` | array of evidence IDs | yes | The citation. Empty is invalid on a `supported` claim. |
| `exceptions[].on` | array of record IDs | yes | Which records the difference is between. |
| `exceptions[].kind` | family identifier | yes | From the frozen family list below. |
| `exceptions[].c` | certainty | yes | An exception can be observed but its cause unsupported. |
| `exceptions[].why` | array of evidence IDs | yes | Usually a policy line. Empty forces `kind: cause_not_established`. |
| `open[].on` | array of record IDs | yes | What could not be concluded. |
| `open[].need` | short string | yes | The evidence that would close it. The one free-text field, and §Verification prices it. |
| `open[].why` | array of evidence IDs | **omitted when empty** | The citation establishing that the evidence is *required* — typically the policy line demanding it. This is the control on `need`: with a citation, the requirement comes from the packet; without one, `need` is the model's own reading. Omitted rather than sent empty, so it costs nothing on the entries that have no grounding. |
| `residue.l` / `.r` | array of record IDs | yes | Records matched to nothing, by the rule in §Residue. **Required even when empty**, so "everything matched" is always an assertion and never a silence. |
| `do[].act` | `accept` \| `hold` \| `escalate` \| `request` | yes | The disposition a human authorises. |
| `do[].on` | array of record IDs | yes | What the act applies to. |

**Keys are short but pronounceable.** `l`, `r`, `c`, `why`, `on`, `do` are read hundreds of times
by a judge and thousands of times by a training run; the tokens are real. Single-letter keys were
rejected for the fields a reader has to interpret — `kind`, `need`, `residue`, `act` stay spelled
out. The rule: abbreviate structure, spell out meaning.

**Evidence IDs** are the packet's immutable identifiers: `A-nnn`/`B-nnn` for records on either
side, `D-nn` for documents, `P-nn` for policy, with an optional `:Lnn` or `:Lnn-Lnn` line span on
policy. A reference that does not resolve in the supplied packet is a validation failure, not a
stylistic problem.

### Residue, and what an `unsupported` match means

`c: unsupported` is not a wasted entry. It is how the model says **"I considered these and the
evidence does not support the correspondence"** — a decoy rejected on the record, which is a
different and more useful statement than never mentioning the pair. Two records of identical
amount that are *not* the same event is exactly the case a reconciliation product must get right,
and silence cannot distinguish "considered and rejected" from "never noticed".

Keeping it forces the residue rule to be exact, because the no-silent-residue invariant is
otherwise uncheckable:

> **A record is residue if and only if it appears in no `matches` entry whose `c` is `supported`
> or `ambiguous`.**
>
> **An `unsupported` match does not count as matched.** A record named only in unsupported
> matches is residue, and must appear in `residue`.

So a record can be both cited in a `matches` entry and listed in `residue`, and that is not a
contradiction — it is the schema saying "this was looked at, the match was rejected, and the
record is still unaccounted for". The validator enforces it as a computable rule rather than a
judgement.

### Exception families

The `kind` enum, frozen here because the schema cannot validate without it. **[#12](https://github.com/raheebwa/consylr/issues/12) expands each into its correctness
definition and per-family quotas; this list is the identifiers themselves.**

```
fee_at_source · withholding · timing_cutoff · reference_mangled · name_variant
partial_payment · duplicate · reversal · batched_vs_itemised · cause_not_established
```

`cause_not_established` is a first-class member, not a fallback. It is what the model emits when
a difference is real but the packet does not explain it.

**There is deliberately no `missing_record` kind.** A record with no counterpart is already said
twice — by `residue`, which is required on every output, and by an `open` entry naming what would
close it. A third way to say it would let the same fact be labelled two ways in the training
corpus, and inconsistent ground truth is worse than a missing convenience. An exception describes
a difference *between corresponding records*; where nothing corresponds, there is no exception to
describe.

### Report additions

The validator adds, and the model may never author:

| Field | Meaning |
|---|---|
| `verified[]` | Per claim: did every cited ID resolve, and did every quoted figure match its source? |
| `computed[]` | Deltas, sums, and fee reconciliations, each with the record IDs they derive from. |
| `arithmetic_ok` | Whether the computed figures are consistent with the model's classification. |
| `disagreements[]` | Where a model claim and a computed figure conflict. **Reported, not resolved, and never silently corrected** — the disagreement is the signal. |
| `budget` | Prompt tokens, reserved generation tokens, and the limit they were checked against. |

## Behaviour

The cases worth specifying are the ones where a plausible-looking answer is the wrong answer.

**Empty packet, or one side empty.** Not an error and not an abstention. `matches` empty,
`exceptions` empty, `residue` listing every supplied record on its side, and `do` a single
`request`. A packet with nothing to reconcile has a correct answer, and it is not silence.

**Everything ambiguous.** Every `matches[].c` is `ambiguous`, every `do[].act` is `hold`. The
schema must not require at least one `supported` claim — a packet can legitimately support no
conclusion, and a schema that cannot say so trains the model to invent one.

**Contradictory evidence.** Both conflicting IDs are cited in the same `why`, and certainty drops
to `ambiguous` or `unsupported`. The model does not pick a side and must not omit the losing
citation — an omitted contradiction is indistinguishable from evidence that was never there.

**One record, two equally good counterparts.** A single `matches` entry with both candidates on
one side and `c: ambiguous` — *not* two competing `supported` entries. Two confident claims about
the same record is a schema-level contradiction, and the validator rejects it.

**Over-budget packet — rejected at the boundary, before generation.**

This is the case the schema exists to prevent, and it is not intuitive. The harness does **not**
truncate output when the window is exceeded. It reserves the generation budget first, then
**left-truncates the prompt**:

```python
budget = _N_CTX - max_gen - 1
if len(tokens) > budget:
    tokens = tokens[-budget:]  # left-truncate, keep recent context
```

So an over-budget packet still produces well-formed JSON and a healthy parse rate, while the
model has **silently lost the beginning of its input** — the earliest records, and whatever
instructions or schema description sat at the top of the prompt. It then answers confidently
about evidence it was never shown.

**Nothing downstream can detect this.** The output is valid, the citations resolve against the
records it did see, and the score is simply wrong. Therefore the budget is enforced *before* a
token is generated: an over-budget packet is refused, loudly, with the measured count and the
limit. Rejection at generation time is the only point at which this failure is visible.

**Malformed model output.** A reportable event carrying the raw text, not an empty result and not
a repair attempt. A schema violation is evidence about the model, and silently fixing it destroys
the measurement the sealed evaluation depends on.

## What it must refuse to do

- **No numeric confidence.** Never `"confidence": 0.87`. Categorical states only. A number that
  looks calibrated and is not is worse than no number, because a reader will act on it. If
  calibration is ever established, that is a new RFC with the calibration evidence attached.
- **No claim without a citation.** `why: []` on a `supported` claim is invalid.
- **No cause asserted beyond the packet.** If the policy does not cover it, the family is
  `cause_not_established` — not the nearest plausible cause.
- **No computed number authored by the model.** There is no field for one. Deltas and sums are
  the validator's.
- **No autonomous action.** `do` is a request for authorisation. `accept` means *recommend
  accepting*; nothing in this schema posts anything.
- **No silent residue.** `residue` is required even when both sides are empty.
- **No invented identifiers.** Every ID must resolve in the supplied packet.
- **No prose where an ID would do.** `need` is the single free-text field, and it is capped.

## Verification

### Every field earns its tokens, and the budget is measured

At `n_ctx = 2048` with the harness defaulting `max_gen_toks` to **256**, the schema's own weight
is a scored constraint, not a matter of taste. Budget:

| Component | Limit |
|---|---|
| Rendered prompt, including the packet | **≤ ~1,200 tokens** |
| Reserved generation headroom | **≥ ~600 tokens** |
| Gate 1 packet size | **5–10 records** *[competition constraint — ADTC profiler]* |

Output must fit comfortably inside **256 tokens** for a 5–10 record packet, because that is what
the harness reserves unless a task overrides it. Reserving more than the harness does is safe;
assuming it reserves ours is not.

**These are measured with the frozen model's tokeniser, not estimated.** Measurements for each
worked example below are recorded with it, and the generator asserts the budget on the rendered
prompt using the same tokeniser — a character or word heuristic is wrong by exactly the amount
that matters at the boundary ([#14](https://github.com/raheebwa/consylr/issues/14)).

### Test families

| Family | Threshold |
|---|---|
| Structured-output parse rate | ≥ 99% |
| Every cited ID resolves | 100% — a failure here is a defect, not a score |
| Amount, reference and date exact-copy rate | ≥ 99.5% |
| Evidence citation precision | ≥ 98% |
| Correct abstention on unsupported cases | ≥ 90% |
| **False abstention on clearly-supported cases** | **< 5%** |

The last row is not symmetry for its own sake. A schema that makes abstention cheap and rewards
it will produce a model that abstains on everything and scores well on the row above it
([#16](https://github.com/raheebwa/consylr/issues/16)).

### Measured output cost

Measured with the **frozen model's own tokeniser**, on the compact JSON each example below
serialises to. Not estimated, and not counted in characters.

| Example | Tokens |
|---|---|
| 1 — clean one-to-one | **75** |
| 2 — split payment | **130** |
| 3 — abstention with reason | **141** |
| 4 — residue declared | **127** |
| 5 — decoy rejected | **93** |

**Worst case 141 tokens against the harness's 256-token default reservation — 45% spare.** That
margin is the room a 10-record packet needs, and it is the reason single-letter keys were not
necessary: the schema is already comfortably inside the budget at readable key names, so the
tokens saved by making `kind` into `k` would buy nothing and cost a judge's patience.

Re-measure whenever the schema or the frozen model changes. Both invalidate the table.

### Worked examples

Each is valid against the schema and its cost is in the table above.

**1 — clean one-to-one match.**

```json
{"matches":[{"l":["A-017"],"r":["B-004"],"c":"supported","why":["A-017","B-004"]}],
 "exceptions":[],"open":[],"residue":{"l":[],"r":[]},
 "do":[{"act":"accept","on":["A-017","B-004"]}]}
```

**2 — split payment, one invoice settled by two transfers.**

```json
{"matches":[{"l":["A-021"],"r":["B-008","B-009"],"c":"supported","why":["A-021","B-008","B-009"]}],
 "exceptions":[{"on":["A-021","B-008","B-009"],"kind":"partial_payment","c":"supported","why":["A-021"]}],
 "open":[],"residue":{"l":[],"r":[]},
 "do":[{"act":"accept","on":["A-021","B-008","B-009"]}]}
```

**3 — abstention with a reason.**

```json
{"matches":[{"l":["A-019"],"r":["B-012"],"c":"ambiguous","why":["A-019","B-012"]}],
 "exceptions":[{"on":["A-019","B-012"],"kind":"cause_not_established","c":"unsupported","why":[]}],
 "open":[{"on":["A-019"],"need":"processor settlement breakdown","why":["P-02:L11"]}],
 "residue":{"l":[],"r":[]},
 "do":[{"act":"hold","on":["A-019","B-012"]},{"act":"request","on":["A-019"]}]}
```

Two things to read here. `exceptions[].why` is empty and that is **valid**, because the family is
`cause_not_established` — the absence of support is the claim. And `open[].why` cites `P-02:L11`,
the policy line that makes the settlement breakdown *required*: the need comes from the packet
rather than from the model's imagination. The `request` disposition is what the new invariant
demands — an `open` entry and a request for it are the same statement made twice, to a validator
and to a human.

**4 — residue declared.**

```json
{"matches":[{"l":["A-031"],"r":["B-020"],"c":"supported","why":["A-031","B-020"]}],
 "exceptions":[],"open":[{"on":["B-021"],"need":"counterparty ledger entry"}],
 "residue":{"l":["A-032"],"r":["B-021"]},
 "do":[{"act":"accept","on":["A-031","B-020"]},{"act":"request","on":["B-021"]},
       {"act":"escalate","on":["A-032"]}]}
```

**5 — decoy rejected, and the record still counted as residue.**

Two records of identical amount that are not the same event. The pair is named and rejected, and
`A-044` appears in **both** `matches` and `residue` — which the rule in §Residue makes correct
rather than contradictory.

```json
{"matches":[{"l":["A-044"],"r":["B-030"],"c":"unsupported","why":["A-044","B-030","P-05:L3"]}],
 "exceptions":[],"open":[],
 "residue":{"l":["A-044"],"r":["B-030"]},
 "do":[{"act":"escalate","on":["A-044","B-030"]}]}
```

Without this example the residue rule reads as a technicality. With it, the reason for keeping
`unsupported` in the enum is visible: silence here would have been indistinguishable from not
having looked.

### How the schema itself is tested

- A JSON Schema document, and **the same validator ships in the product and validates the
  training corpus**. A second validator written for the corpus tests the second validator.
- Property tests over the invariants:
  - no `supported` claim without a citation;
  - no record in two `supported` matches;
  - `residue` present on every output, and **exactly** the records satisfying the rule in
    §Residue — neither more nor fewer;
  - every referenced ID resolvable in the supplied packet;
  - **every `do[].act: "request"` is covered by an `open[]` entry naming the same records.** A
    request for evidence with nothing recorded as needed is a dangling disposition: it asks a
    human for something the output never said was missing;
  - **every ID in `do[].on` appears somewhere in `matches`, `exceptions`, `open` or `residue`.**
    Resolvability against the packet is a different check from internal coherence, and an output
    can pass the first while disposing of a record it never reasoned about.
- Round-trip on all four examples, in all four testing modes, since the profiler applies no chat
  template and a schema that only survives inside one is not frozen.

## Open questions

1. Should `open[].need` be a closed enum rather than free text? It is the only field a model can
   pad, and an enum would make it cheaper and machine-checkable — at the cost of expressiveness
   on evidence types nobody enumerated yet. Deferred until the taxonomy in
   [#12](https://github.com/raheebwa/consylr/issues/12) shows how many distinct needs actually
   occur.
2. Does `do` need an ordering guarantee? Currently a set. If a disposition ever depends on
   another, this becomes a sequence and the schema changes.
3. Should the report expose the model's raw text alongside the parsed object on every run, or
   only on failure? Always would help debugging and cost storage.
4. Is one `matches` entry with several IDs on one side sufficient for many-to-many, or does that
   case need refusing outright as out of scope? The PRD rules out unconstrained many-to-many at
   scale but does not settle the bounded case.
