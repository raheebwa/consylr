# SPDX-License-Identifier: MIT
"""A model directory whose chat template is a no-op, per issue #21.

The training backend picks its dataset class by which keys a row carries, and
only the `prompt`/`completion` shape supports masking the prompt out of the
loss. That shape routes through `apply_chat_template`, which wraps the pair in
the model's chat markers — while the profiler sends a bare prompt with none. So
the first run took the other trade: `text` rows, verbatim tokenisation, correct
interface, and **no masking**, with the loss spread across prompt and answer
alike.

That trade is what the first tuned model's numbers look like. It learned the
shape of an answer rather than how to read a packet: 204 packets produced 65
distinct outputs, abstention collapsed to 5.3%, and exceptions were invented on
clean packets. The excellent validation loss was largely measuring prompt tokens
the model could copy.

**This removes the trade rather than choosing a side of it.** A model directory
is assembled whose every file is the frozen model's, except a chat template
that emits its messages' contents and nothing else:

    {% for m in messages %}{{ m["content"] }}{% endfor %}

Under it, `apply_chat_template([user, assistant])` tokenises to exactly
`prompt + completion`, and `apply_chat_template([user], add_generation_prompt=
True)` to exactly `prompt` — so the mask offset falls precisely on the boundary
between them. Masking is recovered and the interface is unchanged.

**The claim is checked rather than asserted.** `build` verifies the property
against the real tokeniser after writing, and removes the directory if it does
not hold. A passthrough that quietly stopped passing through would train the
model against an interface the evaluation does not use, which is the one failure
this whole module exists to prevent — and nothing downstream would report it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: Emits each message's content and nothing else: no role markers, no
#: separators, no generation prompt. Kept on one line because a Jinja template
#: emits its own whitespace, and a newline here would become a token there.
CHAT_TEMPLATE = (
    '{% for m in messages %}{{ m["content"] }}{% endfor %}'
    "{% if not add_generation_prompt %}{{ eos_token }}{% endif %}"
)

#: The file transformers reads a chat template from when it sits beside the
#: tokeniser rather than inside `tokenizer_config.json`. The frozen model ships
#: it this way, and writing the key into the config instead would leave the
#: original file in place and silently win.
TEMPLATE_FILE = "chat_template.jinja"

PROMPT = "PROMPT-SIDE-PROBE"
COMPLETION = '{"probe":"completion-side"}'


def build(source: Path, dest: Path) -> Path:
    """Assemble the passthrough model directory, or leave nothing behind.

    Every file is linked rather than copied — the weights are gigabytes and a
    second copy is a second thing that can drift from the frozen artefact.
    """
    if not (source / TEMPLATE_FILE).exists() and not (source / "tokenizer_config.json").exists():
        raise ValueError(f"{source} does not look like a model directory")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for entry in sorted(source.iterdir()):
        if entry.name == TEMPLATE_FILE:
            continue
        (dest / entry.name).symlink_to(entry.resolve())
    (dest / TEMPLATE_FILE).write_text(CHAT_TEMPLATE, encoding="utf-8")

    try:
        verify(dest)
    except Exception:
        # A directory that failed its check must not be left where a training
        # run could pick it up. The failure is the useful artefact, not the
        # directory.
        shutil.rmtree(dest)
        raise
    return dest


def verify(model: Path) -> tuple[int, int]:
    """Assert the template passes through, and return (prompt tokens, total).

    Raises rather than reports. There is no partial credit here: an interface
    that differs from the evaluation's by a few markers produces a falling loss,
    a poor score, and no diagnostic.
    """
    # Imported here and typed as absent: `transformers` belongs to the training
    # environment, not to this package. Verifying against the real tokeniser is
    # the point — a stub would check nothing.
    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    tok = AutoTokenizer.from_pretrained(str(model))
    messages = [
        {"role": "user", "content": PROMPT},
        {"role": "assistant", "content": COMPLETION},
    ]
    whole = tok.apply_chat_template(messages, return_dict=False)
    prefix = tok.apply_chat_template(messages[:-1], add_generation_prompt=True, return_dict=False)

    body = tok.encode(PROMPT + COMPLETION)
    if whole[:-1] != body:
        raise ValueError(
            "the chat template does not pass through: training would see tokens the "
            "profiler never sends"
        )
    # The stop token is the whole reason this is `whole[:-1]` above. A template
    # emitting only its messages' contents drops it, and the backend does not put
    # it back: `TextDataset` appends `eos_token_id` when it is missing and
    # `CompletionsDataset` does not. A model trained without it never learns to
    # stop — it generates to the cap and its JSON is truncated mid-structure, so
    # every answer is well-formed for three hundred tokens and parses as none.
    #
    # The first version of this check asserted `whole == body` and passed. It was
    # not a weak check; it was an exact assertion of the wrong property — it
    # confirmed the terminator's absence.
    if whole[-1] != tok.eos_token_id:
        raise ValueError(
            "the chat template does not end the answer with the stop token: the model "
            "would never learn to stop and every answer would truncate at the cap"
        )
    if prefix != tok.encode(PROMPT):
        raise ValueError(
            "the masked prefix is not the prompt: the loss boundary would fall in the "
            "wrong place and the answer would be partly masked out"
        )
    return len(prefix), len(whole)
