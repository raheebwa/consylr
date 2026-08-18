# SPDX-License-Identifier: MIT
"""Staging a training checkpoint so it can be evaluated, per issue #21.

`--save-every` writes each checkpoint as `0002000_adapters.safetensors` **into
the same directory** as the final `adapters.safetensors`. The loader takes a
*directory* and reads a fixed filename from it:

    mlx_lm/tuner/utils.py
    model.load_weights(str(adapter_path / "adapters.safetensors"), strict=False)

So pointing an evaluation at the training directory loads the **final** weights
whichever rung was meant. A checkpoint ladder built that way scores one adapter
repeatedly and returns a flat curve — with no error, no warning, and nothing in
the result files to say the rungs were identical. The conclusion drawn from it
would be that more training changes nothing.

Staging is therefore not tidiness. It is the difference between measuring how
many epochs the task needs and measuring the same adapter five times.

The weights are copied rather than linked: a rung is evaluated once and then
kept as the provenance of whatever number it produced, and a symlink into a
training directory that a later run overwrites is a number whose artefact
quietly changed underneath it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

#: What the loader reads, and what a checkpoint is not called.
WEIGHTS = "adapters.safetensors"

#: Read before the weights are, for the layer count and LoRA parameters. A rung
#: staged without it fails at load with a message about a missing file rather
#: than about the checkpoint.
CONFIG = "adapter_config.json"

_CHECKPOINT = re.compile(r"^(\d+)_adapters\.safetensors$")


def rungs(run: Path) -> list[int]:
    """Every checkpoint iteration this run actually saved, ascending.

    Discovered rather than assumed. A caller naming rungs by hand names the ones
    it expected, and a run that saved different ones is then evaluated at the
    wrong places or silently not at all.
    """
    found = [
        int(match.group(1))
        for entry in run.iterdir()
        if (match := _CHECKPOINT.match(entry.name)) is not None
    ]
    return sorted(found)


def stage(run: Path, iteration: int, dest: Path) -> Path:
    """Put one checkpoint where an evaluation can load it, under its own name."""
    weights = run / f"{iteration:07d}_adapters.safetensors"
    if not weights.exists():
        raise ValueError(
            f"{run} holds no checkpoint at {iteration}; it saved {rungs(run)}. "
            "Staging the config alone would fail later with a message about a "
            "missing file rather than about a checkpoint that does not exist."
        )
    if not (run / CONFIG).exists():
        raise ValueError(f"{run} has no {CONFIG}; the loader reads it before the weights")

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run / CONFIG, dest / CONFIG)
    shutil.copy2(weights, dest / WEIGHTS)
    return dest
