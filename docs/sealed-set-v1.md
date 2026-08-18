# The sealed evaluation set, v1

Frozen 2026-08-18. This is the record that lets the set be rebuilt and stops it
being re-drawn into training by accident. The corpus itself is not committed —
RFC-0003 keeps corpora out of the repository and makes them reproducible from a
configuration and a seed instead.

## How to rebuild it

```sh
CONSYLR_TOKENISER=/path/to/tokenizer.json \
  mise exec -- python -c "
from pathlib import Path
from consylr.sealed import Sealed, seal
from consylr.templates import load
seal(load(Path('templates')), Sealed(seed=20260818), Path('out/sealed-v1'), tokeniser=...)
"
```

The tokeniser is the frozen model's, per
[ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md). A different one
produces different token counts and therefore a different budget verdict, which
is why it is named here rather than assumed.

## What it is

| | |
|---|---|
| Seed | `20260818` — **reserved; never a training seed** |
| Templates | 70 authored, 28 sealed (two of five per family) |
| Packets | 196 |
| Families | 14, exactly 14 packets each |
| Role | `holdout`, and nothing in the configuration can say otherwise |
| Prompt template digest | `fad3f8691f8e606d…` — the authoritative value is `consylr.prompt.DIGEST`, computed from the artefact rather than transcribed |
| Worst rendered prompt | 928 tokens against a 1,448 cap |

Certainty across the set: 154 supported, 28 ambiguous, 14 unsupported. The
abstention families — `cause_not_established` and `missing_record` — hold 28
packets between them, which is enough to *measure* a refusal rate rather than
merely demonstrate that refusal happens ([#16](https://github.com/raheebwa/consylr/issues/16)).

## What binds it

The set is bound to the prompt template by digest. **Changing that template
invalidates this set**: budgets re-assert over every case and the exam is
rebuilt. The model was trained against one interface and a changed interface is
a different one, whatever the diff looks like.

It is also bound to the templates in `templates/`. Re-authoring them changes
what the exam asks.

## What was checked before it was written

Nothing here was audited afterwards. `consylr.corpus.write` refuses to write a
corpus that fails, so a set that reached disk passed:

- every case validated against the validator that ships in the product;
- every packet inside the token budget, measured with the frozen tokeniser;
- **no two packets identical under different answers** — contradictory ground
  truth, which would train the model on one answer and examine it on the other;
- **no packet in both roles** — the leak that raises measured accuracy rather
  than lowering it.

The last two are exhaustive over the whole corpus rather than sampled. An
earlier design sampled three probe cases per template and could be walked past
by a difference sitting on an unsampled pair.

## Positioning

RFC-0002 makes this the set that decides positioning. After it is frozen the
argument about positioning is over — which is the point of freezing it.
