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

**Which keys a row carries decides which dataset class the backend picks, and
that decides the interface the model is trained against.** A `prompt`/
`completion` pair selects the class that wraps them in the model's *chat
template*, so the model would learn to answer after an assistant marker while
the profiler sends a bare prompt with none. The interfaces would differ by a few
tokens nobody looks at, the loss would fall, the eval would be poor, and nothing
would name the cause.

By default the row is `text`, tokenised verbatim, so the answer begins exactly
where generation begins. The cost is that the loss covers the prompt as well as
the answer, because masking is not offered for that shape — and that cost is
visible in the first tuned model, which learned the shape of an answer rather
than how to read a packet.

`masked=True` takes the other route and removes the cost rather than accepting
it: `prompt`/`completion` rows against a **passthrough model**, whose chat
template emits its messages' contents and nothing else. The wrap becomes a no-op,
the tokens are identical to the `text` row's, and the mask offset falls exactly
on the boundary between prompt and answer. That model must be named — see
`consylr.passthrough` — because these rows are correct or catastrophic depending
on which model they meet, and a file that cannot say which is a trap.

It reads a corpus from disk rather than taking cases in memory, deliberately.
The artefacts on disk are what passed the audit; anything held in memory is
something that might not have.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from consylr.passthrough import CHAT_TEMPLATE, TEMPLATE_FILE
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
    masked: bool = False,
    model: Path | None = None,
) -> int:
    """Write one JSON line per case, and return how many.

    The shape is `{"text": ...}`, deliberately — see the module docstring. The
    template id rides along so a split can be checked after the fact; it is not
    a key the backend selects on.

    A validation slice is split **by template**, never by row — the same rule
    the exam is held to. Drawn at random it would share templates with training,
    so the model would be validated on scenarios it had already been fitted to
    and the validation loss would report memorisation as learning.
    """
    if masked:
        # The invariant was never "use `text`" — it is that the tokens the
        # trainer sees are the tokens the profiler sends. `text` rows guarantee
        # that by being tokenised verbatim, and pay for it by spreading the loss
        # over the prompt. Masking needs the `prompt`/`completion` shape, which
        # routes through `apply_chat_template` and is safe only against a model
        # whose template passes through.
        #
        # So the model is named here rather than assumed. Emitting these rows
        # without it produces a file that is correct or catastrophic depending
        # on a flag set somewhere else later, with nothing recording which.
        if model is None:
            raise ValueError(
                "masked rows need the passthrough model they will be trained against; "
                "build it first and name it here"
            )
        found = (
            (model / TEMPLATE_FILE).read_text(encoding="utf-8")
            if (model / TEMPLATE_FILE).exists()
            else ""
        )
        if found.strip() != CHAT_TEMPLATE:
            raise ValueError(
                f"{model} is not a passthrough model: its chat template would put markers "
                "between the prompt and the answer that the profiler never sends"
            )

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
        # The answer follows the prompt with nothing between them, because
        # nothing is between them at inference either. Separators match the
        # packet's own serialisation, so the model is trained to produce the
        # shape the validator reads.
        answer = json.dumps(expected, sort_keys=True, separators=(",", ":"))
        rendered = render(packet)
        body = {"prompt": rendered, "completion": answer} if masked else {"text": rendered + answer}
        row = json.dumps({**body, "template_id": template_id})
        (held if validation(template_id) else lines).append(row)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if valid_out is not None:
        valid_out.parent.mkdir(parents=True, exist_ok=True)
        valid_out.write_text("\n".join(held) + "\n", encoding="utf-8")
    return len(lines)
