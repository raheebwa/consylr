# SPDX-License-Identifier: MIT
"""Run a model against a sealed set and report every metric RFC-0001 names.

It asserts the exam's content digest before it generates anything. An exam that
can silently change between runs is not an exam, and the seed alone does not
establish that the set on disk is the set a number was computed on — a file
edited afterwards still carries the seed in its metadata.

It renders through `consylr.prompt`, the same artefact the corpus was built
against, and refuses a case whose recorded digest is not that template's. The
profiler applies no chat template of its own, so this is the model's whole
interface and evaluating through a different one measures a different system.

**`--scaffold` is a reference measurement and never the headline.** It forces
the answer to begin with an open brace, which tells us what a model could do if
it could produce the format at all. A base model with no fine-tuning generates
raw continuations — the profiler applies no chat template, so that is the mode
being measured — and may score near zero on parse rate for reasons of format
rather than reasoning.

Reporting only the profiler-mode number invites the question "did you just teach
it JSON?", and reporting only the scaffolded one would measure a system nobody
runs. Both, labelled, separate the two gains: what the base cannot format, what
it cannot reason about given the format, and what the fine-tune does in the mode
that counts.

Usage:

    mise exec -- python tools/evaluate.py <exam-dir> <model> [expected-digest] [--scaffold]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from consylr import prompt
from consylr.corpus import content_digest
from consylr.score import Answer, positional, record, score

#: RFC-0001 sizes the answer at well inside the harness's 256-token default
#: reservation. Generating far beyond it would measure a model rambling rather
#: than a model answering.
MAX_TOKENS = 320

#: What `--scaffold` forces the answer to start with. The smallest thing that
#: makes the format available without supplying any of the content.
SCAFFOLD = '\n{"matches"'


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    exam = Path(sys.argv[1])
    model_name = sys.argv[2]
    scaffold = "--scaffold" in sys.argv
    # `--adapter=<path>` rather than `--adapter <path>`: the positional argument
    # after the model is the expected digest, and a two-token flag would put an
    # adapter path there — where it would be compared against the exam's digest
    # and refuse the run with a message about the wrong thing entirely.
    adapter = next((a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--adapter=")), "")
    rest = [a for a in sys.argv[3:] if not a.startswith("--")]
    expected_digest = rest[0] if rest else ""

    digest = content_digest(exam)
    if expected_digest and digest != expected_digest:
        print(f"REFUSED: {exam} digests {digest}, not the {expected_digest} this run expects")
        return 1
    print(f"exam {exam.name}: digest {digest}")

    import mlx_lm  # imported late so a digest mismatch costs no model load

    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    print(f"{len(cases)} packets, model {model_name}")

    # The tuned model is the base plus an adapter, and loading the base alone
    # would score the wrong system while reporting the right name.
    model, tokeniser = (
        mlx_lm.load(model_name, adapter_path=adapter) if adapter else mlx_lm.load(model_name)
    )
    answers, started = [], time.time()
    for n, case in enumerate(cases, start=1):
        meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        if meta.get("prompt_digest") != prompt.DIGEST:
            print(f"REFUSED: {case.name} was rendered against another prompt template")
            return 1
        packet = json.loads((case / "packet.json").read_text(encoding="utf-8"))
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        rendered = prompt.render(packet)
        # The scaffold is part of the answer, not of the question: the model
        # continues from an open brace, and the brace is prepended to what it
        # produced so the scorer reads one JSON document.
        produced = mlx_lm.generate(
            model,
            tokeniser,
            prompt=rendered + (SCAFFOLD if scaffold else ""),
            max_tokens=MAX_TOKENS,
            verbose=False,
        )
        if scaffold:
            produced = SCAFFOLD.strip() + produced
        answers.append(
            Answer(packet=packet, expected=expected, produced=produced, family=meta["family"])
        )
        if n % 25 == 0:
            rate = (time.time() - started) / n
            print(f"  {n}/{len(cases)}  {rate:.1f}s/case  eta {rate * (len(cases) - n) / 60:.1f}m")

    report = score(answers)
    # Scored on the same packets, every run, and printed on the same line as the
    # figure it qualifies. Correspondence F1 is nearly saturated on a
    # position-regular exam by a model that reads nothing, so the raw number
    # invites exactly the wrong reading — and a control kept in a separate script
    # is one nobody runs.
    null = score(
        [
            Answer(
                packet=a.packet, expected=a.expected, produced=positional(a.packet), family=a.family
            )
            for a in answers
        ]
    )
    mode = "SCAFFOLDED reference (not profiler mode)" if scaffold else "profiler mode"
    print(f"\n=== {model_name}{' + ' + adapter if adapter else ''} on {exam.name} — {mode} ===")
    print(f"parse rate            {report.parse_rate:.1%}")
    print(f"schema valid          {report.schema_valid:.1%}")
    print(
        f"exact match           {report.exact_match:.1%}"
        f"   (null {null.exact_match:.1%}, margin "
        f"{report.exact_match - null.exact_match:+.1%})"
    )
    print(
        f"correspondence F1     {report.correspondence_f1:.3f}"
        f"   (null {null.correspondence_f1:.3f}, margin "
        f"{report.correspondence_f1 - null.correspondence_f1:+.3f})"
    )
    print(f"citation resolution   {report.citation_resolution:.1%}")
    print(f"correct abstention    {report.correct_abstention:.1%}  (target >= 90%)")
    print(f"false abstention      {report.false_abstention:.1%}  (target < 5%)")
    print("\nper family (exact / F1 / n):")
    for family in sorted(report.per_family):
        t = report.per_family[family]
        print(f"  {family:24s} {t.exact_match:6.1%} {t.correspondence_f1:6.3f} {t.asked:4d}")

    suffix = ("-tuned" if adapter else "") + ("-scaffolded" if scaffold else "")
    out = exam.parent / f"eval-{exam.name}-{model_name.split('/')[-1]}{suffix}.json"
    out.write_text(
        json.dumps(
            record(
                answers,
                report,
                exam=exam.name,
                model=model_name,
                mode="scaffolded-reference" if scaffold else "profiler",
                adapter=adapter,
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
