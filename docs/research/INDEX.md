# Research index

The evidence layer. These documents are captured as delivered and **not edited as
understanding improves** — that is what ADRs are for. If a research document and an ADR
disagree, the ADR is current.

| Document | Date | What it settles | Status |
|---|---|---|---|
| [2026-08-18-entry-decision-research.md](2026-08-18-entry-decision-research.md) | 2026-08-18 | The entry thesis: Offline Enterprise Exception Analyst with SLM-led bounded reconciliation. Model shortlist, quantisation economics, sealed-test design, gate plan, risk register, legal dependencies. | **Current — governs the build** |

## Lineage — superseded material held elsewhere

This entry began as an offline-education thesis under the [[somedser]] product line. Those
documents remain in the life-os vault at `sources/product-research/` and are **superseded on
positioning** by the 2026-08-18 report, though their decode of the competition's scoring
mechanics remains useful history:

- `2026-06-28-somedser-offline-education-memo.md` — the canonical June decision:
  education-as-task framing, Gemma-3-4B/1B, Swahili, grand-prize target. **Positioning
  superseded**; bare-GGUF judging decode still sound.
- `2026-06-28-somedser-offline-execution-dossier.md` — synthetic-data recipe, Unsloth QLoRA
  → GGUF spike, 1B-vs-4B score model, week-by-week plan. **Partially reusable**: the
  training mechanics survive, the task families do not.
- `2026-06-28-somedser-offline-white-paper.md` — agriculture-leaning first pass, already
  marked SUPERSEDED in June.

What changed, in one line: the June plan's differentiator (a Socratic understanding probe)
was ranked **7th of 9** by the August review as structurally mismatched to single-shot
evaluation, and education-as-task **3rd** as insufficiently differentiated.

## What is missing and known to be missing

- **The ADTC Participation Agreement.** Its full text could not be retrieved. Unresolved
  legal dependency; IP ownership of the fine-tuned weights is unread.
- **The two charts** referenced in the 2026-08-18 report (`adtc_model_tradeoff.png`,
  `adtc_memory_score_sensitivity.png`) did not survive capture.
- **Independent verification** of the vendor benchmark figures quoted throughout (Gemma 3/4,
  Qwen3/3.5, Phi-4-mini model cards; BlackLine and Duco product documentation). They are
  second-hand via the report and its citation markers were lost in export.
