# SPDX-License-Identifier: MIT
"""The command surface, per #25-#28.

Everything this project claims either holds here at run time or was only ever a
sentence in a document. Three properties are load-bearing:

**The prompt is the frozen one, and that is compared rather than printed.** An
earlier version of this module printed the digest, never checked it, and said in
this docstring that it did — so editing the frozen artefact left every answer
afterwards measuring a system the model was never trained against, byte-
indistinguishable from a correct one. The caller supplies the digest its model
was built against (the artefact's manifest carries it) and a mismatch refuses.

**An over-budget packet is refused, never trimmed.** The harness does not
truncate output when the window is exceeded — it reserves the generation budget
and then left-truncates the *prompt*. The run still produces well-formed JSON
and a healthy parse rate while the model has lost the earliest records and any
instruction above them, and answers confidently about evidence it was never
shown. That failure is invisible downstream, so it is refused here.

**Generation happens inside the offline guard.** Not argument parsing, not
setup — generation, because a model loader reaching the network at load time is
exactly the case a guard placed anywhere else would miss.

Generation is injected rather than imported. The surface is then testable
without weights, and the runtime that supplies it is named by the caller
instead of assumed by this module.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from consylr import prompt
from consylr.budget import Tokeniser, check
from consylr.evidence import unresolved
from consylr.offline import no_network
from consylr.schema import validate

#: What the operator sees before the model has produced anything. Three seconds
#: of silence is a long time for someone holding an exception queue, and what
#: the packet contained is knowable immediately.
PARSED = "packet parsed, {n} records, prompt template {digest}"


class CliRefused(RuntimeError):
    """The run was refused before anything was generated.

    A refusal, not a warning: every condition checked here produces a plausible
    answer if it is allowed through, which is why none of them may be.
    """


def _records(packet: Any) -> list[Any]:
    if not isinstance(packet, dict):
        raise CliRefused("the packet is not a JSON object")
    records = packet.get("records")
    if not isinstance(records, list):
        raise CliRefused("the packet has no `records` list; it is not a reconciliation packet")
    return records


def run(
    packet_path: Path,
    *,
    generate: Callable[[str], str],
    tokeniser: Tokeniser,
    out: Callable[[str], None] = print,
    expect_digest: str = "",
) -> Any:
    """Reconcile one packet and return the parsed answer."""
    if expect_digest and expect_digest != prompt.DIGEST:
        raise CliRefused(
            f"this build renders through prompt template {prompt.DIGEST[:12]}, not the "
            f"{expect_digest[:12]} the model was trained against; the answer would "
            "measure a different system and look no different"
        )
    try:
        packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CliRefused(f"{packet_path} is not valid JSON: {e}") from e

    records = _records(packet)
    rendered = prompt.render(packet)

    # Before the model, not after: a refusal that arrives after generation has
    # already cost the operator the wait is a refusal that will be overridden.
    violations = check(rendered, tokeniser, prompt.BUDGET)
    if violations:
        raise CliRefused(
            "; ".join(f"{v.code}: {v.detail}" for v in violations)
            + " — refused rather than trimmed, because the harness would truncate "
            "the prompt and answer confidently about records it never saw"
        )

    out(PARSED.format(n=len(records), digest=prompt.DIGEST[:12]))

    with no_network():
        said = generate(rendered)

    try:
        answer = json.loads(said)
    except json.JSONDecodeError as e:
        raise CliRefused(f"the model did not produce one JSON object: {e}") from e
    # `[]` and `[{...}]` parse as JSON and are routine shape slips. Reaching the
    # reference checker with one produced a raw traceback out of a function whose
    # whole contract is refusing with a named reason.
    if not isinstance(answer, dict):
        raise CliRefused(f"the model produced a {type(answer).__name__}, not one JSON object")

    # Shape is the schema's authority, not this module's and not the reference
    # checker's. Every defect it exists to catch used to reach the operator in
    # silence while the scorer counted the same answer invalid.
    for violation in validate(answer, packet):
        out(f"{violation.code}: {violation.detail}")

    # Reported, never silently corrected and never discarded. A model that
    # cited evidence the packet did not contain has told the operator something
    # a tidied answer would not, and the disagreement is the useful signal.
    # Nothing is printed when there is nothing wrong: a tool that reassures on
    # every run trains its operator to stop reading.
    for violation in unresolved(answer, packet):
        out(f"{violation.code}: {violation.detail}")
    return answer


def lazily(load: Callable[[], Any]) -> Callable[[str], str]:
    """Defer the model load to the first generation, so it happens inside the guard.

    Handing `run` an already-constructed model puts the load in the caller,
    before `no_network()` is entered — which is precisely the case this module's
    docstring says the guard is positioned to catch. A loader that runs on first
    use runs where the guard is up.
    """
    held: list[Any] = []

    def generate(rendered: str) -> str:
        if not held:
            held.append(load())
        completion = held[0].create_completion(
            prompt=rendered, max_tokens=MAX_TOKENS, temperature=0.0
        )
        return str(completion["choices"][0]["text"])

    return generate


#: The answer's whole allowance, matching what the evaluation generates under.
MAX_TOKENS = 320


def main(argv: list[str] | None = None) -> int:
    """`consylr <packet.json> --model=<gguf> [--expect-prompt=<digest>]`"""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(main.__doc__)
        return 2
    flags = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in args[1:] if "=" in a}
    model = flags.get("--model", "")
    if not model:
        print("--model=<gguf> is required")
        return 2

    def load() -> Any:
        from llama_cpp import Llama  # type: ignore[import-not-found]

        return Llama(model_path=model, n_ctx=prompt.BUDGET.context, n_gpu_layers=0, verbose=False)

    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    tokeniser = (
        AutoTokenizer.from_pretrained(flags["--tokeniser"]) if "--tokeniser" in flags else None
    )
    if tokeniser is None:
        print("--tokeniser=<dir> is required: the budget is asserted with the real one")
        return 2
    try:
        answer = run(
            Path(args[0]),
            generate=lazily(load),
            tokeniser=tokeniser,
            expect_digest=flags.get("--expect-prompt", ""),
        )
    except CliRefused as refused:
        print(f"REFUSED: {refused}")
        return 1
    print(json.dumps(answer, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
