# ADR-0003 — freeze the base model, and the training backend, separately

- **Status:** accepted
- **Date:** 2026-08-18
- **Deciders:** Aheebwa Ramadhan

## Context

The base model was the largest open question, and everything downstream was blocked on it: the
sealed evaluation, the training runs, the conversion, the submission metadata.

The plan was a bake-off in a fixed order — Qwen3.5-4B first, behind a mandatory conversion
spike, then Qwen3-4B, Gemma 3 4B, Phi-4-mini, and a 1–2B efficiency control. Qwen3.5 went first
because it was the most capable candidate and because a specific risk was already on record: an
open `llama.cpp` issue reporting a 33-versus-32 block mismatch on exactly the fine-tune-to-GGUF
path this project depends on. The spike carried a two-hour hard timebox and a kill criterion
agreed in advance, precisely so that a promising model could not absorb unbounded time.

**Two things were being decided, not one.** The model is one axis; the toolchain that turns a
fine-tune into a quantised GGUF is another. The research plan assumed Unsloth QLoRA, which is
CUDA-only and cannot run on the Apple Silicon machine this is built on — so the backend was
never settled either, and a failure in one axis must not be recorded as a failure in the other.

## Decision

Two decisions, deliberately recorded as two, so that either can be revisited without reopening
the other.

**(a) The primary base model is `Qwen3-4B-Instruct-2507`.** `Qwen3ForCausalLM`, 36 layers,
conventional attention, no multi-token-prediction head. Frozen on the **quantised Q4_K_M GGUF**,
not the checkpoint, consistent with the standing decision that the artefact which ships is the
artefact a decision may be taken on.

**(b) The training backend is the local Apple Silicon path:**
`mlx_lm.lora` → `mlx_lm.fuse` → `convert_hf_to_gguf.py` → `llama-quantize … Q4_K_M`, with the
converter pinned to the same `llama.cpp` tag as the binaries it feeds. No rented GPU, no upload,
no cost.

Both were decided by running the whole chain end to end, not by reading model cards.

### The toolchain that produced these results

Pinned rather than latest, because a spike verdict that cannot be attributed to a specific
toolchain is not a verdict.

| Component | Pin | Why it matters |
|---|---|---|
| `llama.cpp` binaries | **b10453**, commit `3cb7ffb1a` | The runtime under test |
| `convert_hf_to_gguf.py` | **same tag, b10453** | Converter and binaries must not drift; a release tarball ships binaries only, so the converter comes from the source repo and is pinned to the tag it feeds |
| `adtc-profiler` | **0.1.0** | Competition infrastructure, actively changing — re-check before submission |
| `llama-cpp-python` | **0.3.35** | Not a preference: the harness's `accuracy.py` errors out demanding `0.3.x` |
| `mlx-lm` | **0.31.3** | The training backend |
| `torch` / `transformers` | **2.13.0** / **5.15.0** | Converter dependencies |
| Python / `uv` | **3.13.11** / **0.12.5** | |

The full link-by-link spike record — every command, timing, and intermediate artefact size —
is kept with the spike artefacts outside this repository. It **extends** the table above rather
than replacing it: nothing needed to interpret or reproduce a figure in this ADR is only there.

## Consequences

**Made easy.** Everything downstream unblocks. The pipeline is local, free, reproducible from a
pinned toolchain, and fast enough that a full retrain-to-GGUF cycle is minutes rather than
hours.

**Measured baseline, on the participant machine** — a 4B Q4_K_M produced from this exact path:

| Metric | Value |
|---|---|
| Peak RSS | **5020.67 MB (4.90 GB)** |
| Steady-state RSS | 4816.81 MB (4.70 GB) |
| Generation throughput | **39.01 t/s** |
| First-token latency | **2960 ms** |
| Quantised artefact | 2375.91 MiB (4.95 BPW) |
| Thermal | not throttled |

**These are development-machine figures and the audit numbers will be worse.** The evaluation
profile is 4 vCPU / 8 GB RAM / integrated GPU; these were taken on a 32 GB machine.

**The consequence that follows, stated rather than left implied:** peak RSS clears the ≤5 GB
hard target **by 80 MB**. Against an 8 GB audit box, where the operating system and the runtime
sit on top of model peak RSS, and where an out-of-memory is an **automatic disqualification**
rather than a low score, 80 MB is not margin.

Therefore:

- **≤4 GB preferred becomes the working target**, not an aspiration.
- **Q5 is off the table** absent a substantial reduction elsewhere. It was already conditional
  on the sealed evaluation paying for its cost; that condition is now much harder to meet.
- **Memory reduction is explicit, in-scope work**, not an optimisation to consider later:
  comparing quantisation variants (the Q4_K_S and IQ4 families) and whatever KV-cache options
  the profiler permits — **measured, never assumed**.

**Made hard, and the honest costs:**

- The chosen model is not the most capable candidate. Qwen3.5-4B was, and it is being set aside
  for a toolchain reason rather than a capability one. That is a real cost, and the revisit
  condition below is how it stays visible.
- 2960 ms to first token is slow for an interactive session. It is not a competition problem —
  the harness measures generation throughput — but it is a product problem, tracked against the
  CLI work.
- The local backend has now demonstrated one silent failure mode on a hybrid architecture. It is
  trusted on the frozen model because it was verified there, and not trusted in general.

## The kill, recorded precisely

**Qwen3.5-4B is killed on the local path only.** It is not disqualified as a model, and the
record should not be read that way.

The evidence separates cleanly:

| What was tested | Result |
|---|---|
| Untouched official checkpoint → GGUF → Q4_K_M → `llama-cli` | **Works.** 441 tensors, 33 blocks consistent, 2644 MiB, coherent output at 67.1 t/s |
| Fine-tuned via the local MLX path → GGUF → Q4_K_M | **Broken.** Loads only with `--no-mtp`, then emits garbage |

The reported trap reproduced exactly — `check_tensor_dims: tensor 'blk.32.attn_norm.weight' not
found`, with the GGUF declaring `block_count = 33` while carrying `blk.0…blk.31`. The cause is
a config-versus-tensor mismatch: the official checkpoint carries 426 text tensors, a 297-tensor
vision tower and a 15-tensor multi-token-prediction head; `mlx_lm.fuse` keeps the text tensors,
which is correct for a text fine-tune, but the converter reads `mtp_num_hidden_layers: 1` from
the copied config and extends `block_count` for a block whose weights are gone.

`--no-mtp` is a supported converter flag and corrects the count honestly. The model then loads —
and produces gibberish. Three-way isolation placed the fault:

| Stage | Output |
|---|---|
| base + adapter, inside MLX | coherent |
| fused model, inside MLX | coherent, identical text |
| fused → GGUF → Q4_K_M, in `llama.cpp` | **garbage** |

So the fuse step is sound, and the converter mis-maps the MLX-fused layout of Qwen3.5's
**hybrid linear-attention** architecture — `layer_types` alternating `linear_attention` and
`full_attention`, carrying `linear_attn.A_log` and `conv1d` tensors. It handles the official HF
layout correctly and the MLX-fused layout incorrectly.

**The failure is silent**, which is the whole point of recording it here: convert succeeds,
quantise succeeds, load succeeds, and only reading the generated text reveals that the artefact
is worthless. A green pipeline is not evidence of a working model. This is the strongest
available argument for the standing four-mode testing rule.

No attempt was made to fix `llama.cpp`, as the kill criterion required. The verdict was reached
in 24 minutes of the two-hour timebox.

### Revisit condition, and it is a joint one

**Qwen3.5-4B re-enters if and only if a training backend producing standard HF-layout merged
weights enters** — a rented GPU running Unsloth or PEFT. The evidence for that pairing already
exists: the official checkpoint converts and runs correctly, so the layout is the variable.

**Neither reopens without the other.** Qwen3.5 on the local path is settled. A cloud backend
without Qwen3.5 to justify its cost is a decision with no benefit attached.

## The overhead curve, replacing a dead projection

Non-weight overhead — peak RSS minus quantised weight size — was extrapolated from a single
0.6B measurement to predict ~3.1 GB for a 4B. **The actual figure was 4.90 GB**, wrong by
1.8 GB.

| Model | Weights | Peak RSS | Non-weight overhead |
|---|---|---|---|
| 0.6B Q4_K_M | 372.65 MiB | 958.42 MB | **~0.59 GB** |
| 4B Q4_K_M | 2375.91 MiB | 5020.67 MB | **~2.58 GB** |

Overhead does not hold constant; it scales with the model, because KV cache and context buffers
grow too. Two points are still only two points and this is not a law — but it is the honest
replacement for a one-point ratio that failed, and the direction it establishes is that
overhead cannot be treated as a fixed additive term.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep Qwen3.5-4B and extend the timebox | The kill criterion existed to prevent exactly this. The failure is in a third-party converter's handling of a hybrid architecture; nothing about the next hour makes that shallower. |
| Keep Qwen3.5-4B and patch `llama.cpp` | Explicitly forbidden, and correctly: it makes this project's submission depend on a fork of the runtime the organisers use. |
| Switch to a rented GPU now to keep Qwen3.5 | Buys capability for cost, upload of training data, and a dependency on someone else's hardware inside a six-day window — with the local path already proven on an adequate model. Recorded as the revisit condition instead. |
| Continue down the ladder to Gemma 3 4B or Phi-4-mini | Unnecessary: the ladder exists to find a model that works, and the second rung passed end to end. Gemma 3 would also have dragged in its own licensing regime. Both remain available if the frozen model fails the sealed evaluation. |
| Freeze the model and leave the backend implicit | The backend was an unstated assumption that turned out to be wrong (Unsloth cannot run here). Leaving it implicit is how it stays wrong. |

## Evidence

- The bake-off order, the timebox and the kill criterion as they stood before this ADR:
  [`docs/decisions.md`](../decisions.md), and the spike issue.
- Every figure above was produced by the toolchain tabled under §Decision, and none is
  estimated. The local spike record adds the per-command detail behind them.
- The audit profile and the disqualification consequence: the official submission template.
