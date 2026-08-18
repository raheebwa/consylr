# SPDX-License-Identifier: MIT
"""Build the training corpus from the pattern templates, per RFC-0003 and #20.

A tool rather than an ad-hoc invocation, because a corpus produced by a command
nobody can re-run is a corpus whose provenance rests on someone's shell history.
The first training corpus was built that way, and reconstructing how took longer
than writing this did.

**It writes nothing that has not passed the audit.** `corpus.write` runs every
check before a byte reaches disk and raises otherwise, so a corpus on disk is
one that passed. That includes the check which is the whole boundary between
this set and the exam: **every packet here is compared byte for byte against all
of the sealed set's**, and a collision refuses the corpus rather than warning
about it. The pattern templates are training-only and the exam is built from a
different directory, but the guarantee does not rest on that — it rests on the
comparison.

Usage:

    CONSYLR_TOKENISER=/path/to/tokenizer.json \\
      python -m tools.build_train_corpus <sealed-dir> <out-dir> [--limit=N] [--seed=N]

The tokeniser is required and never guessed. RFC-0003 budgets in the frozen
model's tokeniser because a character or word heuristic is wrong by exactly the
amount that matters at the boundary, and an over-budget packet is left-truncated
by the harness into a well-formed answer about evidence the model never saw.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from consylr import corpus, generate
from consylr.quota import Plan
from consylr.templates import load

TEMPLATES = Path(__file__).resolve().parent.parent / "templates-train"

#: A ceiling rather than a target. `cases_for` stops early when a template has
#: nothing else distinct to give, so asking for more than a template holds costs
#: nothing and hides nothing — the yield reports what was asked and what was
#: refused as a duplicate.
LIMIT = 30

#: Never the sealed set's `20260818`, which is reserved. Recorded here rather
#: than passed by habit, so a corpus can be rebuilt by reading this file.
SEED = 7


class _Frozen:
    """The frozen model's tokeniser, wrapped to the protocol `budget` expects."""

    def __init__(self, path: str) -> None:
        import tokenizers

        self._tok = tokenizers.Tokenizer.from_file(path)

    def encode(self, text: str) -> list[int]:
        return list(self._tok.encode(text).ids)


def _tokeniser() -> _Frozen:
    path = os.environ.get("CONSYLR_TOKENISER", "")
    if not path or not Path(path).is_file():
        raise SystemExit(
            "CONSYLR_TOKENISER is not set to a readable tokenizer.json.\n"
            "The build makes no network calls; fetch the frozen model once, then:\n"
            "  export CONSYLR_TOKENISER=<hf cache>/models--mlx-community--"
            "Qwen3-4B-Instruct-2507-4bit/snapshots/<snapshot>/tokenizer.json"
        )
    return _Frozen(path)


def _exam_packets(sealed: Path) -> list[dict[str, Any]]:
    """Every packet the exam asks, for the byte comparison that is the boundary."""
    packets = [
        json.loads((case / "packet.json").read_text(encoding="utf-8"))
        for case in sorted(sealed.iterdir())
        if (case / "packet.json").exists()
    ]
    if not packets:
        # Silence here would be the expensive kind: an empty held-out set makes
        # the comparison vacuous, and the corpus would be written having been
        # checked against nothing.
        raise SystemExit(f"{sealed} holds no packets; the exam comparison would check nothing")
    return packets


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    sealed = Path(sys.argv[1])
    out = Path(sys.argv[2])
    limit = next((int(a.split("=", 1)[1]) for a in sys.argv[3:] if a.startswith("--limit=")), LIMIT)
    seed = next((int(a.split("=", 1)[1]) for a in sys.argv[3:] if a.startswith("--seed=")), SEED)

    tokeniser = _tokeniser()
    templates = load(TEMPLATES)
    held_out = _exam_packets(sealed)
    print(f"{len(templates)} pattern templates, {len(held_out)} exam packets held out")

    produced = generate.corpus_for(
        templates,
        seed=seed,
        role="train",
        limit=limit,
        tokeniser=tokeniser,
        extra={"corpus_seed": seed, "permuted": True},
        # Training packets are permuted; the exam is not. score.positional scores
        # 0.809 against an unpermuted corpus built from these templates and 0.273
        # against a permuted one, so pairing by list position stops being a
        # winning policy and a model has to read the records to pair them.
        permute=True,
    )
    print(
        f"asked {produced.asked}, distinct {produced.distinct}, "
        f"refused as duplicates {produced.duplicates}"
    )

    written = corpus.write(
        out,
        produced.cases,
        templates=templates,
        plan=Plan(families=frozenset(t.family for t in templates)),
        held_out=held_out,
    )
    print(f"{len(written)} cases written to {out}")
    print(f"corpus digest {corpus.content_digest(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
