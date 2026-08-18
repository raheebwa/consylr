# SPDX-License-Identifier: MIT
"""Emit a written corpus as training rows, per issue #21.

Re-runnable rather than ad-hoc, for the same reason the corpus build is: a
training file produced by a shell one-liner has its provenance in somebody's
history, and the file itself cannot say which corpus or which interface it came
from.

Usage:

    python -m tools.emit_training_data <corpus> <out-dir> [--masked=<model>]

`--masked` names the passthrough model the rows will be trained against. `emit`
refuses masked rows without it, because those rows are correct or catastrophic
depending on which model they meet.
"""

from __future__ import annotations

import sys
from pathlib import Path

from consylr.emit import emit

#: A tenth held out, split by template rather than by row — drawn at random the
#: validation slice would share scenarios with training and report memorisation
#: as learning.
VALID_SHARE = 0.1


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    corpus, out = Path(sys.argv[1]), Path(sys.argv[2])
    model = next(
        (Path(a.split("=", 1)[1]) for a in sys.argv[3:] if a.startswith("--masked=")), None
    )

    written = emit(
        corpus,
        out / "train.jsonl",
        valid_out=out / "valid.jsonl",
        valid_share=VALID_SHARE,
        masked=model is not None,
        model=model,
    )
    held = len((out / "valid.jsonl").read_text().strip().splitlines())
    shape = "prompt/completion, masked" if model else "text, unmasked"
    print(f"{written} training rows and {held} validation rows in {out} ({shape})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
