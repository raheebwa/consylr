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
regenerated from a seed needs no claims made about where it came from.

It is also the last line before the silent failure this project is most exposed to: an
over-budget packet is **left-truncated by the harness**, producing valid JSON about evidence the
model never saw ([RFC-0001](0001-output-schema.md) §Behaviour). The generator is the only place
that failure is visible, so it refuses to emit one.

## Interface

### Command surface

```
consylr-gen build   --config <path> --seed <int> --out <dir> --role <train|sealed>
consylr-gen audit   --corpus <dir>
consylr-gen inspect --corpus <dir> --case <id>
```

`build` is the only command that writes a corpus. `audit` re-runs every check against a corpus
already on disk and is what CI calls. `inspect` renders one case — its packet, its expected
output, its family, and its template lineage — because a corpus nobody can read case-by-case is a
corpus nobody can check.

### What a case is

```
case/
  packet.json     the evidence packet handed to the model
  expected.json   the correct model output, per RFC-0001
  meta.json       family, template id, seed, role, rendered prompt token count
```

`meta.json` is not decoration. `template_id` is what the grouped split separates on, and
`prompt_tokens` is what the budget audit re-checks without re-tokenising the whole corpus.

### Configuration

One file, versioned with the corpus it produced. It carries the quota plan, the family list, the
budget limits, and a reference to the **pattern configuration** — the committed, aggregate-only
formatting conventions, amount and date distributions, sector vocabulary and mangling patterns
distilled from real-world records ([#20](https://github.com/raheebwa/consylr/issues/20)).

**The generator plus its committed configuration must regenerate the whole corpus anywhere, with
no external data dependency.** That property is not negotiable: it is what lets someone with none
of the source material reproduce the evidence.

## Behaviour

### Determinism

Same config, same seed, same corpus — byte for byte, on any machine.

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

### Optional paraphrase, tightly bounded

A frontier model may paraphrase **free-text surface fields only** — descriptions, merchant-style
names. Never a label, a number, a reference, or a correspondence decision
([#19](https://github.com/raheebwa/consylr/issues/19)).

Every paraphrased case is **deterministically re-validated** afterwards: schema, arithmetic, and
family assignment. A paraphrase that changes any of the three is **discarded, not corrected** —
correcting it means a human deciding what the case now is, which is exactly the inferred ground
truth this design exists to avoid.

Paraphrase is off by default and recorded in `meta.json` when used, because a corpus where some
cases passed through another model and some did not is two corpora unless the record says which.

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
- **Depend on anything unavailable to a stranger.** No network at build time, no private dataset,
  no credential.
- **Repair a failed paraphrase.**

## Verification

Test-driven, per `CONTRIBUTING.md`: the failing test first, then the code.

### Property tests — the invariants that must hold for every corpus

| Invariant | Why it matters |
|---|---|
| Same config + seed → identical corpus | Reproducibility is the provenance story |
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

1. Where does the tokeniser come from at build time? Vendoring it into the repository is
   forbidden; downloading it makes the build network-dependent, which §What it must refuse rules
   out. Most likely a documented local path with a checksum — needs deciding before the first
   corpus is built.
2. Is the sealed set generated by the same command with `--role sealed`, or by a separate command
   that cannot be pointed at the training config by accident? The second is harder to misuse.
3. What is a "template" concretely — a function, a data file, or a parameterised description? It
   is the unit of the split, so this determines whether the split is checkable.
4. Should `audit` be able to fail a corpus it did not generate, purely from its `meta.json`? That
   would make an externally-supplied corpus checkable on the same terms.
