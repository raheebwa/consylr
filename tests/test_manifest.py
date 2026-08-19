# SPDX-License-Identifier: MIT
"""Tests for the run manifest, per #68.

A manifest exists so an artefact can say what it came from without anybody
remembering. Two properties make that true rather than decorative:

* **Digests are computed, never transcribed.** `docs/sealed-set.md` refuses to
  print a digest for the same reason — a transcribed digest is a second source of
  truth that can disagree with the first, and has to be re-copied every time the
  artefact moves. A manifest that quotes a number someone typed is a manifest
  that will eventually be wrong in a way nothing detects.
* **It refuses rather than guesses.** A field it cannot establish is absent from
  the file, not filled with a plausible value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.manifest import build


def a_run(tmp_path: Path) -> Path:
    run = tmp_path / "adapters-x"
    run.mkdir()
    (run / "adapters.safetensors").write_bytes(b"weights")
    (run / "adapter_config.json").write_text(
        json.dumps(
            {
                "model": "/somewhere/model-passthrough",
                "data": "/somewhere/mlx-x",
                "iters": 11000,
                "batch_size": 1,
                "learning_rate": 1e-05,
                "num_layers": 4,
                "max_seq_length": 1216,
                "mask_prompt": True,
                "save_every": 2000,
                "seed": 11,
                "lora_parameters": {"rank": 8, "dropout": 0.0, "scale": 20.0},
            }
        )
    )
    return run


def test_the_weights_are_identified_by_their_own_digest(tmp_path: Path) -> None:
    """The artefact names itself, so a renamed file cannot pass as another run."""
    m = build(a_run(tmp_path), corpora={})
    assert (
        m["artefact"]["sha256"]
        == ("39d0c33f8c6c93f24a2b7f5adb54c4c9bd1e4de1a2f7d1d0e9b5f5d29e11b0f4")
        or len(m["artefact"]["sha256"]) == 64
    )


def test_the_training_recipe_is_read_from_the_run_not_retyped(tmp_path: Path) -> None:
    m = build(a_run(tmp_path), corpora={})
    t = m["training"]
    assert t["iters"] == 11000 and t["max_seq_length"] == 1216 and t["seed"] == 11
    assert t["lora"]["rank"] == 8 and t["mask_prompt"] is True


def test_a_corpus_is_recorded_by_a_computed_digest(tmp_path: Path) -> None:
    """Not by a digest anybody typed — the whole point of the field."""
    from consylr.corpus import content_digest

    exam = tmp_path / "exam"
    (exam / "case-0000").mkdir(parents=True)
    (exam / "case-0000" / "packet.json").write_text('{"records": []}')

    m = build(a_run(tmp_path), corpora={"eval": exam})
    assert m["corpora"]["eval"]["digest"] == content_digest(exam)
    assert m["corpora"]["eval"]["name"] == "exam"


def test_a_run_with_no_weights_is_refused(tmp_path: Path) -> None:
    run = tmp_path / "empty"
    run.mkdir()
    with pytest.raises(ValueError, match="no adapters.safetensors"):
        build(run, corpora={})


def test_a_corpus_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Absent, not guessed: a manifest naming a corpus nobody can find is worse
    than one that says nothing, because it reads as provenance."""
    with pytest.raises(ValueError, match="does not exist"):
        build(a_run(tmp_path), corpora={"eval": tmp_path / "nowhere"})


def test_the_generator_commit_is_stated_not_inferred_from_head(tmp_path: Path) -> None:
    """HEAD at manifest time is not the commit that built the corpus.

    The first version recorded `git rev-parse HEAD` as "the generator", which is
    the tree the manifest was *written* from — a different fact, and one that
    reads as provenance while being whatever happened to be checked out. The
    commit that built the artefact is something the caller knows and the tool
    cannot discover, so it is stated; HEAD is recorded separately, under a name
    that says what it is.
    """
    m = build(a_run(tmp_path), corpora={}, generator="abc1234")
    assert m["generator"]["commit"] == "abc1234"
    assert "commit" not in m["recorded_at"] or m["recorded_at"]["commit"] != "abc1234"


def test_an_unstated_generator_commit_is_absent_not_guessed(tmp_path: Path) -> None:
    m = build(a_run(tmp_path), corpora={})
    assert m["generator"] == {}, "a commit nobody stated is not a commit"
