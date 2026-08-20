# SPDX-License-Identifier: MIT
"""Tests for a quantised artefact's provenance, per #68 and #70.

`tools/manifest.py` describes a *training run* — weights plus the config that
produced them. A quantised GGUF is a different shape: one file derived from
another file by one command, with a calibration set that changed what the
command did. It inherits provenance rather than owning it, and the chain back to
the corpus has to be walkable from the file alone.

The rules are the parent's, for the parent's reasons: every digest computed here
and never transcribed, and a missing input refused rather than filled with a
plausible-looking absence.
"""

import json
from pathlib import Path

import pytest

from tools.gguf_manifest import build


def a_file(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_it_computes_every_digest_it_prints(tmp_path: Path) -> None:
    """A transcribed digest is a second source of truth that can disagree with
    the first, and it reads as provenance while being wrong."""
    artefact = a_file(tmp_path / "q.gguf", "quantised bytes")
    parent = a_file(tmp_path / "f16.gguf", "f16 bytes")
    calib = a_file(tmp_path / "calib.txt", "calibration text")
    m = build(artefact, parent=parent, calibration=calib, recipe="Q6_K --imatrix")
    import hashlib

    assert m["artefact"]["sha256"] == hashlib.sha256(b"quantised bytes").hexdigest()
    assert m["derived_from"]["sha256"] == hashlib.sha256(b"f16 bytes").hexdigest()
    assert m["calibration"]["sha256"] == hashlib.sha256(b"calibration text").hexdigest()


def test_the_recipe_is_recorded_because_the_file_cannot_say_it(tmp_path: Path) -> None:
    """Two GGUFs of the same parent differ only by the command that made them,
    and the command leaves no trace inside the file."""
    m = build(
        a_file(tmp_path / "q.gguf", "x"),
        parent=a_file(tmp_path / "p.gguf", "y"),
        calibration=a_file(tmp_path / "c.txt", "z"),
        recipe="Q6_K --imatrix",
    )
    assert m["recipe"] == "Q6_K --imatrix"


def test_a_missing_input_is_refused_not_omitted(tmp_path: Path) -> None:
    """An absent field with a plausible name is worse than an error: it reads
    as 'this artefact had no calibration' rather than 'nobody checked'."""
    with pytest.raises(FileNotFoundError):
        build(
            a_file(tmp_path / "q.gguf", "x"),
            parent=tmp_path / "not-here.gguf",
            calibration=a_file(tmp_path / "c.txt", "z"),
            recipe="Q6_K",
        )


def test_an_uncalibrated_quantisation_says_so_explicitly(tmp_path: Path) -> None:
    """`None` is a claim — that this quantisation used no calibration — and it
    has to be distinguishable from a calibration nobody recorded."""
    m = build(
        a_file(tmp_path / "q.gguf", "x"),
        parent=a_file(tmp_path / "p.gguf", "y"),
        calibration=None,
        recipe="Q6_K",
    )
    assert m["calibration"] == "none"


def test_it_carries_the_parent_manifest_forward(tmp_path: Path) -> None:
    """The chain back to the corpus is the point. A manifest that stops at the
    f16 makes the reader guess which training run it came from."""
    parent_manifest = a_file(tmp_path / "m.json", json.dumps({"corpora": {"train": {"name": "t"}}}))
    m = build(
        a_file(tmp_path / "q.gguf", "x"),
        parent=a_file(tmp_path / "p.gguf", "y"),
        calibration=None,
        recipe="Q6_K",
        parent_manifest=parent_manifest,
    )
    assert m["inherits"]["corpora"]["train"]["name"] == "t"
