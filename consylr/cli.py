# SPDX-License-Identifier: MIT
"""The command surface, per #25-#28.

Everything this project claims either holds here at run time or was only ever a
sentence in a document. Three properties are load-bearing:

**The prompt is the frozen one.** `consylr.prompt` is the whole interface the
model was trained against and the whole interface the harness sends. Rendering
an operator's packet through anything else measures a different system, so the
template's digest travels with the answer rather than being assumed.

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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from consylr import prompt
from consylr.budget import Tokeniser, check
from consylr.evidence import unresolved
from consylr.offline import no_network

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
) -> Any:
    """Reconcile one packet and return the parsed answer."""
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

    # Reported, never silently corrected and never discarded. A model that
    # cited evidence the packet did not contain has told the operator something
    # a tidied answer would not, and the disagreement is the useful signal.
    # Nothing is printed when there is nothing wrong: a tool that reassures on
    # every run trains its operator to stop reading.
    for violation in unresolved(answer, packet):
        out(f"{violation.code}: {violation.detail}")
    return answer
