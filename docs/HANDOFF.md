# HANDOFF — start here

Last updated: 2026-08-18

## Where this stands

**Pre-code.** The entry thesis is decided and evidenced; nothing is built. The binding
constraint is that **Gate 1 closes 2026-08-24 23:45 PDT (≈ 2026-08-25 09:45 EAT)** and the
research plan budgets ~55–70 focused engineering hours to reach it.

The full reasoning is in
[docs/research/2026-08-18-entry-decision-research.md](research/2026-08-18-entry-decision-research.md).
Read it before changing any decision below.

## What is decided

| Decision | Call | Where argued |
|---|---|---|
| Positioning | **Offline Enterprise Exception Analyst**, flagship = SLM-led small-packet reconciliation (hybrid of the two candidate positions, scored 9.2/10 vs 8.5 and 7.5) | Research §Executive summary |
| Correspondence | **The model decides correspondence.** No external deterministic matcher in the runtime | Research §Recommended architecture |
| `joinless` | **Prior-work evidence only.** Not a runtime dependency | Research §`joinless` belongs in the founder evidence |
| Arithmetic | Deterministic. Generation is never the authority for a number | Research §What the numerical-reasoning research really says |
| Abstention | First-class trained behaviour, not a prompt instruction | Research §Grounding and abstention |
| Model band | **3.8–4B**, chosen by bake-off, frozen on the *quantised GGUF* never the BF16 checkpoint | Research §Bake-off sequence |
| Quantisation | **Q4_K_M baseline.** Q5 only if sealed evaluation pays for its RAM/TPS cost | Research §Size and quantisation |
| Memory | **≤5 GB peak RSS hard internal, ≤4 GB preferred** (ceiling is 7 GB; each extra GB costs ~2.86 total points) | Research §Hard memory target |
| Throughput | Optimise past 15 TPS — the profiler cap is an implementation detail, not the goal | Research §Contradiction matrix |
| App scope | **CLI only** before Gate 1. Round one tests the model | Research §Minimal CLI |
| Language | **Swahili is off the critical path.** The African-use-case bonus does not require it | Research §Contradiction matrix |
| Licence | **MIT**, `Copyright (c) 2026 Aheebwa Ramadhan`. The ADTC template's GPL-3.0 governs the submission fork, not this repo | [ADR-0001](adrs/0001-mit-licence-and-public-repository.md) |
| Publication | **This repo is public.** The research document was redacted first. Does *not* resolve trademark or the Participation Agreement | [ADR-0001](adrs/0001-mit-licence-and-public-repository.md) |

## What is explicitly NOT decided

- **Base model.** Bake-off order: Qwen3.5-4B (mandatory 2-hour conversion spike first) →
  Qwen3-4B → Gemma 3 4B → Phi-4-mini → 1–2B efficiency baseline.
- **Trademark clearance for the name "Consylr".** No knock-out search has been run.
  Publishing under a working name does not clear it — it raises the cost of changing it.
- **The ADTC Participation Agreement** — its IP terms are unread. This is a
  pre-submission blocker, not a formality. Do not tick the box before reading it.
  **Going public did not resolve this.** Licensing this repository MIT waives nothing
  under that agreement and pre-commits nothing to it.

## Next actions, in order

1. **Qwen3.5-4B compatibility spike (2 hours, hard timebox).**
   Tiny LoRA → merge → GGUF → Q4_K_M → run the official profiler. There is an open
   `llama.cpp` issue reporting a 33-vs-32 block mismatch on exactly this path. If it does
   not pass repeatedly on a fresh environment, drop Qwen3.5 immediately and move to
   Qwen3-4B. Do not attempt to fix `llama.cpp`.
2. **Freeze primary + fallback base model.** (Research plan puts this on 2026-08-18.)
3. **Freeze the output schema, training taxonomy and sealed-test generator.**
   Once frozen, stop debating positioning — the sealed evaluation decides it.
4. **Build ~200 sealed reconciliation packets before any fine-tuning**, spanning direct,
   fuzzy, split, batched, ambiguous and unsupported cases. Grouped split by perturbation
   family, never random rows.
5. **Create `DATA_PROVENANCE.md` before the first training run.**

## Traps already identified

- **The profiler does not apply a chat template.** Current `accuracy.py` calls raw
  `create_completion()` at `temperature=0.0` with a fixed 2,048-token context. A model that
  only performs well inside its vendor's chat template will underperform in judging.
  **Test the final GGUF in four modes:** official profiler, raw `llama-cli` completion,
  chat-template interaction, and the CLI.
- **2,048-token context** invalidates any model choice argued on 128K/262K context.
- **The submission repo is not this repo.** Gate 1 needs a public repo generated from the
  official ADTC template, with an idempotent `download_model.sh`, two participant prompts in
  metadata, no credentials required to fetch the model, and **no weights committed**.
- **Never train on real confidential material** — no employer production data, no member or
  customer ledgers, no client records, however much more realistic it would make the cases.
  Procedurally generated cases are both safer *and* better, because the ground truth is
  known by construction rather than inferred.
- **Do not design to 6.8 GB.** The profiler anticipates audit variance between local and
  official environments.

## Repo conventions

- `scratchpad/` is gitignored — non-committed working material lives there.
- No model weights, adapters, datasets or run outputs in git (see `.gitignore`).
- Conventional commits, lowercase scope, no attribution trailers.
- ADRs record decisions; RFCs record designs; research holds the evidence. A fact lives in
  exactly one of them, and the others link to it.
