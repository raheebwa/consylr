# SPDX-License-Identifier: MIT
"""Run a sealed set against the shipped GGUF, in each interface it can meet.

Every metric this project has reported came out of MLX. The judged artefact is
a GGUF in llama.cpp, and issue #23 exists because a result in one runtime is
not evidence about another: the official profiler calls raw `create_completion`
at temperature zero with a 2,048-token window and applies **no chat template**,
so a model that only performs inside its vendor's markers looks fine locally
and underperforms where it is judged.

Three of the four modes run here; the fourth is this project's own CLI.

    profiler    llama-cpp-python `create_completion`, the call
                `adtc_profiler.accuracy.generate_until` makes, with its window.
    completion  `llama-completion`, conversation refused.
    chat        `llama-completion`, conversation allowed — which is where the
                GGUF's own chat template gets applied to a prompt that was
                never meant to pass through one.

Two settings are declared once and consumed by both backends. The window is the
harness's 2,048 and not the model's declared 262,144, because llama.cpp's `-c`
defaults to the model's and a KV cache that size is not a slow run but a dead
one. The layers stay on the CPU because `-ngl` defaults to `auto`, which
offloads to Metal here and to nothing on the audit VM — and the offloaded
reading is 2.4 GB lighter, which is the direction that hides a memory failure.

Usage:

    python tools/evaluate_gguf.py <exam-dir> <gguf> --mode=<mode> \
        [--limit=N] [--bin=<llama.cpp bin dir>] [expected-digest]
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from consylr import prompt
from consylr.corpus import content_digest
from consylr.score import Answer, positional, record, score

#: RFC-0001 sizes the answer well inside the harness's reservation; the same
#: cap `tools/evaluate.py` generates under, so the two runtimes are asked the
#: same question.
MAX_TOKENS = 320

#: Not a default anyone can fall through. See the module docstring.
WINDOW = prompt.BUDGET.context
GPU_LAYERS = 0
SEED = 42

#: A ceiling on one packet, not on the run. Chat mode deliberately leaves
#: llama.cpp's interactive loop enabled, so the child reads its next turn from
#: the terminal this process inherited — `capture_output` redirects stdout and
#: stderr only — and never returns. Generous enough that a slow CPU rung is
#: never mistaken for a hang: the slowest measured case was ~60 s.
RUN_TIMEOUT_S = 900


@dataclass(frozen=True)
class Mode:
    """One interface the artefact can be met through."""

    label: str
    #: None marks the in-process backend, which has no command line at all.
    conversation: bool | None


MODES: dict[str, Mode] = {
    "profiler": Mode("profiler (llama-cpp-python create_completion)", None),
    "completion": Mode("completion (llama-completion, -no-cnv)", False),
    "chat": Mode("chat (llama-completion, conversation mode)", True),
}

#: The modes that run a binary. Named rather than derived at the call site, so
#: a fourth mode cannot be added and silently skipped by the gates.
SUBPROCESS_MODES: tuple[str, ...] = tuple(
    name for name, mode in MODES.items() if mode.conversation is not None
)


def llama_kwargs(model: str, *, gpu_layers: int = GPU_LAYERS) -> dict[str, Any]:
    """What the in-process backend constructs and generates with.

    Returned as data rather than applied inline so the window and the offload
    can be asserted without a model file present.
    """
    return {
        "model_path": str(model),
        "n_ctx": WINDOW,
        "n_gpu_layers": gpu_layers,
        "temperature": 0.0,
        "max_tokens": MAX_TOKENS,
        "seed": SEED,
    }


def command(
    mode: str,
    *,
    model: str,
    prompt_file: str,
    binary: str = "llama-completion",
    gpu_layers: int = GPU_LAYERS,
) -> list[str]:
    """The argv for a subprocess mode. Raises for a mode that has no argv."""
    conversation = MODES[mode].conversation
    if conversation is None:
        raise ValueError(f"{mode} runs in process and has no command line")
    argv = [
        binary,
        "-m",
        str(model),
        "-c",
        str(WINDOW),
        "-n",
        str(MAX_TOKENS),
        "-ngl",
        str(gpu_layers),
        "--temp",
        "0",
        "-s",
        str(SEED),
        "-f",
        str(prompt_file),
        # The binary echoes the prompt before continuing it, and the echo is not
        # byte-identical to what was sent -- so stripping it by prefix match
        # leaves the whole packet in front of the answer and every case scores
        # unparseable. Suppressing it at the source removes the guess.
        "--no-display-prompt",
    ]
    if not conversation:
        # Conversation mode is auto-enabled whenever the GGUF carries a chat
        # template, and this one does. Refusing it is what makes mode 2 the
        # interface the profiler actually sends.
        argv.append("-no-cnv")
    return argv


#: Stated in the result file, because a subset whose rule is not recorded is a
#: number nobody can reproduce or argue with.
SUBSET_RULE = (
    "round-robin across families in sorted order, cases within a family in "
    "sorted order, until the requested count is reached"
)


def result_name(exam: str, model: str, mode: str, subset: int, gpu_layers: int) -> str:
    """The result file's name, carrying everything that makes it a different run.

    Keyed on exam, model and mode alone, a `--stratified` or `--gpu-layers`
    diagnostic wrote over the full CPU audit result and every raw answer
    retained in it. `evaluate.py` fixed exactly this once already — "a filename
    that cannot distinguish two artefacts is a filename that overwrites one of
    them" — and the fix did not travel because this tool was forked rather than
    parameterised.

    An audit-shaped run keeps the plain name, so the ladder's existing results
    stay findable by the tools that read them.
    """
    marks = ""
    if subset:
        marks += f"-n{subset}"
    if gpu_layers != GPU_LAYERS:
        marks += f"-ngl{gpu_layers}"
    return f"eval-{exam}-{Path(model).stem}-{mode}{marks}.json"


def stratified(cases: Sequence[tuple[str, str]], n: int) -> list[tuple[str, str]]:
    """`n` cases spread evenly over the families present.

    Taking the first `n` by file order would over-sample whichever families
    sort early and miss others entirely — and a divergence confined to a family
    the subset never asked about reads as agreement.
    """
    by_family: dict[str, list[tuple[str, str]]] = {}
    for case in sorted(cases):
        by_family.setdefault(case[1], []).append(case)
    picked: list[tuple[str, str]] = []
    families = sorted(by_family)
    depth = 0
    while len(picked) < n and any(len(v) > depth for v in by_family.values()):
        for family in families:
            if len(by_family[family]) > depth and len(picked) < n:
                picked.append(by_family[family][depth])
        depth += 1
    return picked


#: How the binary announces that generation terminated. It is not part of the
#: answer, and a run that hit the token cap never prints it -- so it is trimmed
#: only when present, and a truncated answer stays truncated as evidence.
END_MARKER = "[end of text]"


def said(stdout: str) -> str:
    """The answer, out of what the binary wrote."""
    return stdout.strip().removesuffix(END_MARKER).strip()


def _in_process(model: str, rendered: list[str], gpu_layers: int = GPU_LAYERS) -> list[str]:
    """Generate every answer through the profiler's own call."""
    from llama_cpp import Llama  # type: ignore[import-not-found]

    kwargs = llama_kwargs(model, gpu_layers=gpu_layers)
    llm = Llama(
        model_path=kwargs["model_path"],
        n_ctx=kwargs["n_ctx"],
        n_gpu_layers=kwargs["n_gpu_layers"],
        seed=kwargs["seed"],
        verbose=False,
    )
    out = []
    for n, text in enumerate(rendered, start=1):
        # Read from the same dict the tests assert against. Re-specifying these
        # as literals meant the declaration and the run could drift apart in
        # silence: the tests kept passing, the record kept describing the
        # declared configuration, and llama-cpp-python's create_completion
        # defaults max_tokens to 16 — which would truncate every answer while
        # the dict still said 320, and the divergence would be blamed on the
        # interface this tool exists to compare.
        completion = llm.create_completion(
            prompt=text,
            max_tokens=kwargs["max_tokens"],
            temperature=kwargs["temperature"],
        )
        out.append(completion["choices"][0]["text"])
        if n % 25 == 0:
            print(f"  {n}/{len(rendered)}", flush=True)
    return out


def _subprocess(
    mode: str, model: str, rendered: list[str], binary: str, gpu_layers: int = GPU_LAYERS
) -> list[str]:
    """Generate every answer by running the binary once per packet.

    The prompt goes through a file rather than `-p`: a rendered packet is
    thousands of characters of JSON and braces, and an argv round trip through
    a shell is a way for the string the model sees to stop being the string
    that was budgeted.
    """
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prompt.txt"
        for n, text in enumerate(rendered, start=1):
            path.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                command(
                    mode,
                    model=model,
                    prompt_file=str(path),
                    binary=binary,
                    gpu_layers=gpu_layers,
                ),
                capture_output=True,
                text=True,
                check=False,
                timeout=RUN_TIMEOUT_S,
                # Interactive modes otherwise read the operator's terminal.
                stdin=subprocess.DEVNULL,
            )
            if proc.returncode != 0:
                # The failure is the result in chat mode. Recording it as an
                # empty answer would score it as a model that said nothing,
                # which is a different and much milder finding than a runtime
                # that died.
                out.append(f"__RUNTIME_FAILED__ rc={proc.returncode}\n{proc.stderr[-2000:]}")
            else:
                out.append(said(proc.stdout))
            if n % 25 == 0:
                print(f"  {n}/{len(rendered)}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print(__doc__)
        return 2
    exam, model = Path(args[0]), args[1]
    flags = {
        a.split("=", 1)[0]: a.split("=", 1)[1] for a in args[2:] if a.startswith("--") and "=" in a
    }
    mode = flags.get("--mode", "profiler")
    if mode not in MODES:
        print(f"REFUSED: unknown mode {mode!r}; known: {', '.join(MODES)}")
        return 2
    limit = int(flags.get("--limit", "0"))
    subset = int(flags.get("--stratified", "0"))
    # Diagnostic only. Comparing two quantisations of the same weights is about
    # the quantisation, and an hour per arm on the CPU buys nothing -- but an
    # offloaded reading is not the audit's system, so it travels in the record.
    gpu_layers = int(flags.get("--gpu-layers", str(GPU_LAYERS)))
    bindir = flags.get("--bin", "")
    rest = [a for a in args[2:] if not a.startswith("--")]

    digest = content_digest(exam)
    if rest and digest != rest[0]:
        print(f"REFUSED: {exam} digests {digest}, not the {rest[0]} this run expects")
        return 1
    print(f"exam {exam.name}: digest {digest}")

    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    if subset:
        # Chosen across families rather than by file order, so a divergence
        # confined to one family cannot hide behind a subset that never asked
        # about it. The rule travels in the result file.
        family_of = {
            c.name: json.loads((c / "meta.json").read_text(encoding="utf-8"))["family"]
            for c in cases
        }
        keep = {
            name for name, _ in stratified([(c.name, family_of[c.name]) for c in cases], subset)
        }
        cases = [c for c in cases if c.name in keep]
    elif limit:
        cases = cases[:limit]
    if not cases:
        # A mistyped path digests the empty set without complaint and would
        # report 0.0% on every metric — which reads as total model failure
        # rather than a wrong argument — then write that over the real result.
        print(f"REFUSED: {exam} holds no cases; nothing to evaluate")
        return 1
    print(f"{len(cases)} packets, {Path(model).name}, mode {mode}")

    packets, expected, families, rendered = [], [], [], []
    unestablished: list[bool | None] = []
    for case in cases:
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        if meta.get("prompt_digest") != prompt.DIGEST:
            print(f"REFUSED: {case.name} was rendered against another prompt template")
            return 1
        packet = json.loads((case / "packet.json").read_text(encoding="utf-8"))
        packets.append(packet)
        expected.append(json.loads((case / "expected.json").read_text(encoding="utf-8")))
        families.append(meta["family"])
        unestablished.append(meta.get("unestablished"))
        rendered.append(prompt.render(packet))

    started = time.time()
    if MODES[mode].conversation is None:
        produced = _in_process(model, rendered, gpu_layers)
    else:
        binary = str(Path(bindir) / "llama-completion") if bindir else "llama-completion"
        produced = _subprocess(mode, model, rendered, binary, gpu_layers)
    elapsed = time.time() - started

    answers = [
        Answer(packet=p, expected=e, produced=s, family=f, unestablished=u)
        for p, e, s, f, u in zip(packets, expected, produced, families, unestablished, strict=True)
    ]
    report = score(answers)
    null = score(
        [
            Answer(
                packet=a.packet, expected=a.expected, produced=positional(a.packet), family=a.family
            )
            for a in answers
        ]
    )
    print(f"\n=== {Path(model).name} on {exam.name} — mode {MODES[mode].label} ===")
    print(f"packets               {len(answers)}   ({elapsed / max(len(answers), 1):.1f}s/case)")
    print(f"parse rate            {report.parse_rate:.1%}")
    print(f"schema valid          {report.schema_valid:.1%}")
    print(
        f"exact match           {report.exact_match:.1%}"
        f"   (null {null.exact_match:.1%}, margin {report.exact_match - null.exact_match:+.1%})"
    )
    print(
        f"correspondence F1     {report.correspondence_f1:.3f}"
        f"   (null {null.correspondence_f1:.3f}, margin "
        f"{report.correspondence_f1 - null.correspondence_f1:+.3f})"
    )
    print(f"citation resolution   {report.citation_resolution:.1%}")
    print(f"correct abstention    {report.correct_abstention:.1%}  (target >= 90%)")
    print(f"false abstention      {report.false_abstention:.1%}  (target < 5%)")

    out = exam.parent / result_name(exam.name, model, mode, subset, gpu_layers)
    out.write_text(
        json.dumps(
            record(
                answers,
                report,
                exam=exam.name,
                model=Path(model).name,
                mode=MODES[mode].label,
                runtime="llama.cpp",
                window=WINDOW,
                subset_rule=SUBSET_RULE if subset else "",
                gpu_layers=gpu_layers,
                seconds_per_case=round(elapsed / max(len(answers), 1), 2),
                null_correspondence_f1=null.correspondence_f1,
                null_exact_match=null.exact_match,
                exam_digest=digest,
                prompt_digest=prompt.DIGEST,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
