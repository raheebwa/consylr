# SPDX-License-Identifier: MIT
"""Tests for staging a training checkpoint so it can be evaluated, per #21.

`--save-every` writes `0002000_adapters.safetensors` **beside** the final
`adapters.safetensors`, and the loader reads a *fixed filename* from a directory
(`mlx_lm/tuner/utils.py`). So pointing `--adapter` at the training directory
loads the final weights whatever rung you meant — silently. A checkpoint ladder
built that way scores one artefact repeatedly and produces a flat curve with no
error and no clue.

Staging is therefore not a convenience. It is the difference between measuring
how many epochs the task needs and measuring the same adapter five times.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consylr.checkpoints import rungs, stage


def a_run(where: Path, iters: tuple[int, ...] = (2000, 4000)) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    (where / "adapter_config.json").write_text(json.dumps({"num_layers": 4}), encoding="utf-8")
    (where / "adapters.safetensors").write_text("final", encoding="utf-8")
    for it in iters:
        (where / f"{it:07d}_adapters.safetensors").write_text(f"weights-{it}", encoding="utf-8")
    return where


def test_a_staged_rung_carries_that_checkpoint_not_the_final_weights(tmp_path: Path) -> None:
    """The whole point. The staged directory must hold the rung's own weights
    under the name the loader reads, or the ladder measures the last adapter
    every time."""
    run = a_run(tmp_path / "run")
    out = stage(run, 2000, tmp_path / "rung-2000")

    assert (out / "adapters.safetensors").read_text() == "weights-2000"
    assert (out / "adapter_config.json").exists(), "the loader reads this before the weights"


def test_the_rungs_are_discovered_rather_than_assumed(tmp_path: Path) -> None:
    """A caller naming rungs by hand names the ones it expects, and a run that
    saved different ones is then evaluated at the wrong places or not at all."""
    run = a_run(tmp_path / "discover", iters=(2000, 4000, 6000))

    assert rungs(run) == [2000, 4000, 6000]


def test_a_rung_that_was_never_saved_is_refused(tmp_path: Path) -> None:
    """Silence here would stage the config with no weights beside it, and the
    loader would fail later with a message about a missing file rather than
    about a checkpoint that does not exist."""
    run = a_run(tmp_path / "missing")

    with pytest.raises(ValueError, match="9000"):
        stage(run, 9000, tmp_path / "rung-9000")
