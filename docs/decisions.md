# Decisions

What has been settled, what has not, and where each was argued. This is the index; the
authoritative record for anything carrying an ADR number is the ADR itself, in
[`adrs/`](adrs/).

A fact lives in exactly one place. Where a row below names a research section, the reasoning is
in [`research/2026-08-18-entry-decision-research.md`](research/2026-08-18-entry-decision-research.md)
— read it before changing the decision. Where a row names an ADR, the ADR is current: if it and
a research document disagree, the ADR wins and should say what it overrode.

**Consylr is pre-code.** The positioning is decided and evidenced; nothing is built yet. What is
being built, and in what order, is tracked in
[issues](https://github.com/raheebwa/consylr/issues), grouped under epics.

## What is decided

| Decision | Call | Where argued |
|---|---|---|
| Positioning | **Offline Enterprise Exception Analyst**, flagship = SLM-led small-packet reconciliation (hybrid of the two candidate positions, scored 9.2/10 vs 8.5 and 7.5) | Research §Executive summary |
| Correspondence | **The model decides correspondence.** No external deterministic matcher in the runtime | Research §Recommended architecture |
| `joinless` | **Prior-work evidence only.** Not a runtime dependency | Research §`joinless` belongs in the founder evidence |
| Arithmetic | Deterministic. Generation is never the authority for a number | Research §What the numerical-reasoning research really says |
| Abstention | First-class trained behaviour, not a prompt instruction | Research §Grounding and abstention |
| Model band | **3.8–4B**, chosen by bake-off, frozen on the *quantised GGUF* never the BF16 checkpoint | Research §Bake-off sequence |
| Base model | **`Qwen3-4B-Instruct-2507`**, frozen on its Q4_K_M GGUF after the whole chain ran end to end. Qwen3.5-4B killed **on the local path only** — it converts correctly from a standard HF layout, so it re-enters only together with a backend that produces one | [ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md) |
| Training backend | **Local Apple Silicon path** — `mlx_lm.lora` → `mlx_lm.fuse` → `convert_hf_to_gguf.py` → `llama-quantize`, converter pinned to the same `llama.cpp` tag as the binaries. A decision in its own right, revisitable without reopening the model | [ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md) |
| Quantisation | **Q4_K_M baseline.** **Q5 is now effectively off the table** — the frozen model already clears the hard memory target by only 80 MB | [ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md) |
| Memory | **≤4 GB preferred is now the working target**, not ≤5 GB. Measured 4.90 GB on the frozen model — 80 MB inside the hard target, which is not margin. *[competition constraint — ADTC audit profile]* evaluation runs on 4 vCPU / 8 GB with the OS and runtime on top, and an out-of-memory there is **automatic disqualification**, not a low score | [ADR-0003](adrs/0003-freeze-base-model-and-training-backend.md) |
| Throughput | Fast enough that a local session feels responsive, and optimised past that. The harness's 15 TPS cap is an implementation detail, not the goal | Research §Contradiction matrix |
| App scope | **CLI is the only surface for now.** What is being proved is the model's judgement, and a richer surface would not prove it sooner | Research §Minimal CLI |
| Language | **Swahili is off the critical path.** The African-use-case bonus does not require it | Research §Contradiction matrix |
| Licence | **MIT**, `Copyright (c) 2026 Aheebwa Ramadhan`. The ADTC template's GPL-3.0 governs the submission fork, not this repo | [ADR-0001](adrs/0001-mit-licence-and-public-repository.md) |
| Publication | **This repo is public.** The research document was redacted first. Does *not* resolve the Participation Agreement | [ADR-0001](adrs/0001-mit-licence-and-public-repository.md) |
| Name | **Keep "Consylr".** Knock-out search only — no registry clearance, and the residual risk is recorded | [ADR-0002](adrs/0002-keep-the-name-consylr.md) |

## What is explicitly not decided

- **The ADTC Participation Agreement.** Still a pre-submission blocker, now with a partial
  answer rather than none. A **preliminary working read on 2026-08-18** indicated that
  participants retain ownership of IP created for the contest, and grant the organisers and
  their partners a non-exclusive, royalty-free promotional and marketing licence over
  submissions. It also indicated that **the terms themselves may change.**
  That read is a working interpretation, not legal advice, and **not a substitute for the
  owner reading the agreement in full** — which is still required before the box is ticked.
  Because the agreement expressly permits changes and the competition infrastructure is
  live, **all official sources are re-checked at submission time**, not once.
  **Going public did not resolve this.** Licensing this repository MIT waives nothing under
  that agreement and pre-commits nothing to it.


## Where the rest of it lives

| Looking for | Go to |
|---|---|
| What is being worked on, and next | [Issues](https://github.com/raheebwa/consylr/issues) and the epics that group them |
| Why a decision was made, and its cost | [`adrs/`](adrs/) |
| How a component works | [`rfcs/`](rfcs/) |
| The evidence under all of it | [`research/`](research/) |
| Scope, and what is never claimed | [`prd/prd.md`](prd/prd.md) |
| Conventions, commits, hooks, how changes land | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Competition dates and what the harness imposes | [`../README.md`](../README.md) §The immediate vehicle |
