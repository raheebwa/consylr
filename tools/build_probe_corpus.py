# SPDX-License-Identifier: MIT
"""Build the twin-probe corpus, one case per template, gated like any corpus.

    CONSYLR_TOKENISER=/path/to/tokenizer.json \\
    python -m tools.build_probe_corpus <exam dir> <train corpus dir> <out dir>

**No quota plan, deliberately and not by omission.** A quota governs a training
mix — how much of each answer the model is fed. A probe is an instrument, and its
composition is chosen to make one measurement rather than to teach anything. Every
other gate the writer runs still runs: the shipping validator on each case, the
token budget, the packet-size range, the template shape rules, the duplicate and
contradiction audits, and the held-out comparison.

**Both corpora are held out, byte for byte.** The exam, so the probe cannot ask a
question the sealed set already asks; and the training corpus, so it cannot ask
one the model has already been taught. That is what makes these fresh draws a
fact rather than an intention — the writer refuses the case rather than the
author promising it will not happen.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from consylr import corpus, generate
from consylr.budget import Tokeniser
from consylr.templates import load

TEMPLATES = Path(__file__).resolve().parent.parent / "templates-probe"
SEED = 606


def _tokeniser() -> Tokeniser:
    path = os.environ.get("CONSYLR_TOKENISER", "")
    if not path or not Path(path).is_file():
        raise SystemExit(
            "CONSYLR_TOKENISER is not set to a readable tokenizer.json.\n"
            "  export CONSYLR_TOKENISER=<hf cache>/models--mlx-community--"
            "Qwen3-4B-Instruct-2507-4bit/snapshots/<sha>/tokenizer.json"
        )
    from tokenizers import Tokenizer

    inner = Tokenizer.from_file(path)

    class _Frozen:
        def encode(self, text: str) -> list[int]:
            return list(inner.encode(text, add_special_tokens=False).ids)

    return _Frozen()


def _packets(directory: Path) -> list[dict[str, object]]:
    return [
        json.loads((case / "packet.json").read_text(encoding="utf-8"))
        for case in sorted(directory.iterdir())
        if (case / "packet.json").exists()
    ]


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    exam, train, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

    templates = load(TEMPLATES)
    held_out = _packets(exam) + _packets(train)
    print(f"{len(templates)} probe templates, {len(held_out)} packets held out")

    # One case per template. A pair is a settled case and its twin at the same
    # index, and the twin seeds from the settled one — so more indices would give
    # more pairs of the same scenario rather than more scenarios.
    produced = generate.corpus_for(
        templates,
        seed=SEED,
        role="probe",
        limit=1,
        tokeniser=_tokeniser(),
        extra={"corpus_seed": SEED, "permuted": True, "probe": True},
        permute=True,
    )
    print(f"asked {produced.asked}, distinct {produced.distinct}, refused {produced.duplicates}")

    written = corpus.write(out, produced.cases, templates=templates, held_out=held_out)
    print(f"{len(written)} cases written to {out}")
    print(f"corpus digest {corpus.content_digest(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
