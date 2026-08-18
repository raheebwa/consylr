# SPDX-License-Identifier: MIT
"""Tests for sealing the evaluation set, per RFC-0003 and issue #15.

Sealed means sealed: no packet here is ever seen by a training run, and the
seed that produced it is recorded so the set can be rebuilt but not accidentally
re-drawn into training.
"""

import os
from pathlib import Path

import pytest

from consylr.cases import DEFORMATIONS
from consylr.sealed import Sealed, seal, sealed_templates
from consylr.split import HOLDOUT, TRAIN
from consylr.templates import Template, load
from tests.support import PerFourCharacters

CONFIG = Sealed(seed=20260818)


def all_templates() -> list[Template]:
    return load(Path(__file__).resolve().parent.parent / "templates")


def test_every_family_is_represented_in_the_sealed_set() -> None:
    """Per-family metrics are reported, so a family absent from the exam is a
    metric that cannot be computed — and a refusal rate needs the abstention
    families present in numbers, not merely present."""
    chosen = sealed_templates(all_templates(), CONFIG)
    families = {t.family for t in chosen}
    assert families == set(DEFORMATIONS)


def test_the_sealed_choice_is_the_same_every_time() -> None:
    templates = all_templates()
    first = [t.id for t in sealed_templates(templates, CONFIG)]
    second = [t.id for t in sealed_templates(list(reversed(templates)), CONFIG)]
    assert first == second


def test_a_different_seed_seals_a_different_set() -> None:
    templates = all_templates()
    a = {t.id for t in sealed_templates(templates, CONFIG)}
    b = {t.id for t in sealed_templates(templates, Sealed(seed=CONFIG.seed + 1))}
    assert a != b


def test_no_sealed_template_is_also_a_training_template() -> None:
    # The whole property. A template in both roles means the exam asks what the
    # training set already answered.
    templates = all_templates()
    chosen = {t.id for t in sealed_templates(templates, CONFIG)}
    training = {t.id for t in templates} - chosen
    assert chosen and training
    assert not (chosen & training)


def test_sealing_writes_roughly_two_hundred_packets(tmp_path: Path) -> None:
    written = seal(all_templates(), CONFIG, tmp_path, tokeniser=PerFourCharacters())
    assert 150 <= len(written) <= 260, f"{len(written)} packets"


def test_every_sealed_case_is_recorded_as_holdout(tmp_path: Path) -> None:
    import json

    seal(all_templates(), CONFIG, tmp_path, tokeniser=PerFourCharacters())
    roles = {json.loads((d / "meta.json").read_text())["role"] for d in tmp_path.iterdir()}
    assert roles == {HOLDOUT}


def test_the_seed_that_produced_the_set_is_recorded(tmp_path: Path) -> None:
    # So the set can be rebuilt, and so nobody re-draws it into training by
    # reaching for a seed they thought was unused.
    import json

    seal(all_templates(), CONFIG, tmp_path, tokeniser=PerFourCharacters())
    metas = [json.loads((d / "meta.json").read_text()) for d in tmp_path.iterdir()]
    assert all(m["sealed_seed"] == CONFIG.seed for m in metas)


def test_a_training_role_cannot_be_sealed() -> None:
    """RFC-0003 wants `seal` to reject a training configuration structurally.

    A single command taking a role argument can be pointed at the wrong one by a
    typo, and the resulting corpus looks correct.
    """
    with pytest.raises((TypeError, ValueError)):
        Sealed(seed=1, role=TRAIN)  # type: ignore[call-arg]


TOKENISER = os.environ.get("CONSYLR_TOKENISER", "")


@pytest.mark.skipif(not TOKENISER, reason="CONSYLR_TOKENISER not set")
def test_the_whole_sealed_set_fits_the_frozen_budget(tmp_path: Path) -> None:
    """The measurement that decides whether the exam is usable at all.

    Every other test here is about structure and uses an approximate tokeniser
    so that it does not become a budget test by accident. This one is the budget
    test, and it uses the frozen model's tokeniser — because an over-budget
    packet is left-truncated by the harness, which produces well-formed JSON
    about evidence the model was never shown.
    """
    tokenizers = pytest.importorskip("tokenizers")
    tok = tokenizers.Tokenizer.from_file(TOKENISER)

    class Frozen:
        def encode(self, text: str) -> list[int]:
            return list(tok.encode(text).ids)

    written = seal(all_templates(), CONFIG, tmp_path, tokeniser=Frozen())
    assert written, "the sealed set was refused by its own audit"
