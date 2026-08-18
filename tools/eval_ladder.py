# SPDX-License-Identifier: MIT
"""Evaluate every checkpoint of a training run, per issue #21.

The point is a *curve* rather than a score: how many epochs the task needs is a
measured quantity, and a single run at one budget cannot report it. It also
yields the best checkpoint rather than the last one, which are not reliably the
same adapter.

Each rung is staged into its own directory first — see `consylr.checkpoints` for
why that is load-bearing rather than tidy. Rungs are evaluated one at a time,
never concurrently: two jobs on one GPU starve each other badly enough to have
cost an hour once already.

Usage:

    uv run --with mlx-lm --with-editable . python -m tools.eval_ladder \
      <run-dir> <exam> <model> [--staging=<dir>] [--rungs=2000,6000]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from consylr.checkpoints import rungs, stage


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    run, exam, model = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    staging = next(
        (Path(a.split("=", 1)[1]) for a in sys.argv[4:] if a.startswith("--staging=")),
        run.parent / f"{run.name}-rungs",
    )
    chosen = next(
        (
            [int(n) for n in a.split("=", 1)[1].split(",")]
            for a in sys.argv[4:]
            if a.startswith("--rungs=")
        ),
        rungs(run),
    )
    if not chosen:
        raise SystemExit(f"{run} holds no checkpoints; nothing to ladder")

    print(f"{len(chosen)} rungs: {chosen}")
    for iteration in chosen:
        where = stage(run, iteration, staging / f"{run.name}-{iteration:07d}")
        print(f"\n=== rung {iteration} ===", flush=True)
        # Serial by construction. Nothing here runs two evaluations at once.
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "evaluate.py"),
                str(exam),
                model,
                f"--adapter={where}",
            ],
            check=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
