# SPDX-License-Identifier: MIT
"""Assemble the passthrough model directory used for masked training, per #21.

Usage:

    uv run --with transformers --with jinja2 --with-editable . \
      python -m tools.build_passthrough_model <frozen-model-dir> <dest>

The verification needs `transformers`, which is not a package dependency — it is
the training environment's. That is why this is a tool: the check runs where the
training runs, against the tokeniser the training will use, rather than against
whatever a test environment happens to have.
"""

from __future__ import annotations

import sys
from pathlib import Path

from consylr.passthrough import build, verify


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dest = build(Path(sys.argv[1]), Path(sys.argv[2]))
    prompt_tokens, whole = verify(dest)
    print(f"passthrough model at {dest}")
    print(
        f"probe: {prompt_tokens} prompt tokens of {whole}; loss would cover the remaining "
        f"{whole - prompt_tokens}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
