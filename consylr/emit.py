# SPDX-License-Identifier: MIT
"""Turning a written corpus into training data, per issue #21.

A thin transform with one way to be badly wrong: rendering the prompt any way
other than through the frozen artefact. The profiler applies no chat template of
its own, so `consylr.prompt` is the model's entire interface — and a training
file rendered differently trains the model against an interface the evaluation
does not use. Nothing downstream would say so. The loss would fall, the eval
would be poor, and the cause would be invisible.

So it renders through `prompt.render`, and it refuses a corpus whose recorded
prompt digest is not this template's. That check is cheap and it is the only
thing standing between a corpus and a training run nobody can reproduce.

It reads a corpus from disk rather than taking cases in memory, deliberately.
The artefacts on disk are what passed the audit; anything held in memory is
something that might not have.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from consylr.prompt import DIGEST, render

#: Reserved for the validation split, and never a corpus seed — the same reason
#: the exam's seed is reserved.
VALID_SEED = 4242


def emit(
    corpus: Path,
    out: Path,
    *,
    valid_out: Path | None = None,
    valid_share: float = 0.0,
) -> int:
    """Write one JSON line per case, and return how many.

    The shape is `{"prompt": ..., "completion": ...}`, which is what the
    training backend in ADR-0003 reads, plus the template id so a split can be
    checked after the fact.

    A validation slice is split **by template**, never by row — the same rule
    the exam is held to. Drawn at random it would share templates with training,
    so the model would be validated on scenarios it had already been fitted to
    and the validation loss would report memorisation as learning.
    """
    cases = sorted(p for p in corpus.iterdir() if (p / "packet.json").exists())
    if not cases:
        raise ValueError(f"{corpus} holds no cases; there is nothing to train on")

    lines: list[str] = []
    held: list[str] = []

    # Keyed on the template's identity rather than its name, so two ids for one
    # scenario cannot be separated across the boundary.
    def validation(template_id: str) -> bool:
        if valid_share <= 0:
            return False
        draw = hashlib.sha256(f"{VALID_SEED}:{template_id}".encode()).digest()
        return (int.from_bytes(draw[:8], "big") >> 11) / (1 << 53) < valid_share

    for case in cases:
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        recorded = str(meta.get("prompt_digest", ""))
        if recorded != DIGEST:
            raise ValueError(
                f"{case.name} was rendered against prompt template {recorded[:12] or 'none'}, "
                f"not {DIGEST[:12]}. Training on it would fit the model to an interface the "
                "evaluation does not use, and nothing downstream would report it."
            )
        packet = json.loads((case / "packet.json").read_text(encoding="utf-8"))
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        template_id = str(meta.get("template_id", ""))
        row = json.dumps(
            {
                "prompt": render(packet),
                # Separators matched to the packet's own serialisation, so the
                # model is trained to produce the shape the validator reads.
                "completion": json.dumps(expected, sort_keys=True, separators=(",", ":")),
                "template_id": template_id,
            }
        )
        (held if validation(template_id) else lines).append(row)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if valid_out is not None:
        valid_out.parent.mkdir(parents=True, exist_ok=True)
        valid_out.write_text("\n".join(held) + "\n", encoding="utf-8")
    return len(lines)
