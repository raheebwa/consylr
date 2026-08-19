# SPDX-License-Identifier: MIT
"""Tests for emitting training data, per issue #21.

A thin transform with one way to be badly wrong: rendering the prompt any way
other than through the frozen artefact. The model would then be trained against
one interface and examined through another, and nothing downstream would say so
— the loss would fall, the eval would be poor, and the cause would be invisible.
"""

import json
from pathlib import Path

import pytest

from consylr.corpus import write
from consylr.emit import emit
from consylr.passthrough import CHAT_TEMPLATE, TEMPLATE_FILE
from consylr.prompt import DIGEST, TEMPLATE, render
from tests.support import a_template, built


def a_corpus(tmp_path: Path, n: int = 3) -> Path:
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + i}.00") for i in range(n)]
    write(tmp_path, [built(t, case_index=0, role="train") for t in templates], templates=templates)
    return tmp_path


def test_every_case_becomes_one_line(tmp_path: Path) -> None:
    corpus = a_corpus(tmp_path / "corpus")
    out = tmp_path / "train.jsonl"
    assert emit(corpus, out) == 3
    assert len(out.read_text().splitlines()) == 3


def test_a_row_is_the_rendered_prompt_followed_by_the_answer(tmp_path: Path) -> None:
    """The transition the model must learn is the one the profiler exercises.

    `mlx_lm` wraps a `{prompt, completion}` pair in the model's **chat
    template** — the model would learn to answer after an assistant marker while
    the profiler sends a bare prompt with no marker at all. That is the
    four-mode trap on the training side: the loss would fall, the eval would be
    poor, and nothing would name the cause.

    A `text` row is tokenised verbatim, so the answer begins at exactly the
    character position generation begins at.
    """
    corpus = a_corpus(tmp_path / "corpus", n=1)
    out = tmp_path / "train.jsonl"
    emit(corpus, out)
    row = json.loads(out.read_text().splitlines()[0])

    case = next(corpus.iterdir())
    packet = json.loads((case / "packet.json").read_text())
    expected = json.loads((case / "expected.json").read_text())
    rendered = render(packet)

    assert row["text"].startswith(rendered)
    assert json.loads(row["text"][len(rendered) :]) == expected
    # And it is the artefact, not a copy that happens to match today.
    assert TEMPLATE.split("{packet}")[1].strip() in row["text"]


def test_a_row_carries_no_chat_markers(tmp_path: Path) -> None:
    # The profiler applies no chat template. A marker here would train the model
    # to expect one.
    corpus = a_corpus(tmp_path / "corpus", n=1)
    out = tmp_path / "train.jsonl"
    emit(corpus, out)
    text = json.loads(out.read_text().splitlines()[0])["text"]
    for marker in ("<|im_start|>", "<|im_end|>", "<|endoftext|>", "assistant"):
        assert marker not in text


def a_passthrough(where: Path) -> Path:
    """A directory carrying the passthrough template, as `build` leaves it."""
    where.mkdir(parents=True, exist_ok=True)
    (where / TEMPLATE_FILE).write_text(CHAT_TEMPLATE, encoding="utf-8")
    return where


def test_a_row_uses_the_key_that_avoids_the_chat_template(tmp_path: Path) -> None:
    """`mlx_lm` picks its dataset class by which keys are present.

    `prompt` and `completion` together select the class that applies the chat
    template, whatever else the row carries — so by default those keys must be
    absent, not merely accompanied by a `text` field.
    """
    corpus = a_corpus(tmp_path / "corpus", n=1)
    out = tmp_path / "train.jsonl"
    emit(corpus, out)
    row = json.loads(out.read_text().splitlines()[0])
    assert "text" in row
    assert "prompt" not in row and "completion" not in row


def test_masked_rows_are_refused_without_a_model_to_check(tmp_path: Path) -> None:
    """The invariant was never "use `text`". It was that the interface the
    trainer sees is the interface the profiler sends.

    `text` rows guaranteed that by being tokenised verbatim, at the cost of the
    prompt sharing the loss. Masking needs the `prompt`/`completion` shape, which
    routes through the chat template — safe only against a model whose template
    passes through. Emitting those rows without naming that model would produce
    a file that is correct or catastrophic depending on a flag somebody sets
    later, with nothing to say which.
    """
    corpus = a_corpus(tmp_path / "corpus", n=1)

    with pytest.raises(ValueError, match="passthrough"):
        emit(corpus, tmp_path / "train.jsonl", masked=True)


def test_masked_rows_split_the_prompt_from_the_answer(tmp_path: Path) -> None:
    """Concatenated they must equal the unmasked row exactly, because that is
    the string the profiler sends. The split is where the loss boundary goes,
    not a change to what the model reads."""
    corpus = a_corpus(tmp_path / "corpus", n=1)
    plain, split = tmp_path / "plain.jsonl", tmp_path / "split.jsonl"
    emit(corpus, plain)
    emit(corpus, split, masked=True, model=a_passthrough(tmp_path / "model"))

    row = json.loads(split.read_text().splitlines()[0])
    assert (
        row["prompt"] + row["completion"] == json.loads(plain.read_text().splitlines()[0])["text"]
    )
    assert "text" not in row


def test_a_corpus_rendered_against_another_template_is_refused(tmp_path: Path) -> None:
    # Every case records the interface it was built against. Emitting a corpus
    # whose digest does not match this template would train the model on prompts
    # nobody can reproduce.
    corpus = a_corpus(tmp_path / "corpus", n=1)
    meta_path = next(corpus.iterdir()) / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["prompt_digest"] = "0" * 64
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    out = tmp_path / "train.jsonl"
    try:
        emit(corpus, out)
    except ValueError as e:
        assert DIGEST[:12] in str(e)
    else:
        raise AssertionError("a corpus built against another interface was emitted")


def test_an_empty_corpus_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    try:
        emit(empty, tmp_path / "train.jsonl")
    except ValueError:
        return
    raise AssertionError("an empty corpus produced a training file")


def test_the_validation_slice_is_split_by_template(tmp_path: Path) -> None:
    """Grouped, never by row — the same rule the exam is held to.

    A validation set drawn at random shares templates with training, so the
    model is validated on scenarios it has already been fitted to and the
    validation loss reports memorisation as learning. Splitting by template is
    the whole of the defence, and doing it ad hoc at a call site is how it stops
    being done.
    """
    corpus = a_corpus(tmp_path / "corpus", n=10)
    train, valid = tmp_path / "train.jsonl", tmp_path / "valid.jsonl"
    emit(corpus, train, valid_out=valid, valid_share=0.3)

    def templates_in(path: Path) -> set[str]:
        return {json.loads(line)["template_id"] for line in path.read_text().splitlines()}

    assert templates_in(train) and templates_in(valid)
    assert not (templates_in(train) & templates_in(valid))


def test_the_validation_split_is_the_same_every_time(tmp_path: Path) -> None:
    corpus = a_corpus(tmp_path / "corpus", n=10)
    first = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    emit(corpus, tmp_path / "t1.jsonl", valid_out=first, valid_share=0.3)
    emit(corpus, tmp_path / "t2.jsonl", valid_out=second, valid_share=0.3)
    assert first.read_text() == second.read_text()


def test_a_model_whose_template_is_not_the_passthrough_is_refused(tmp_path: Path) -> None:
    """The directory has to be the artefact `build` verified, not merely a path.

    Naming any directory would make the guard a formality — and the failure it
    guards against is a training run against the model's real chat markers,
    which produces a falling loss and a poor score with nothing naming the
    cause.
    """
    corpus = a_corpus(tmp_path / "corpus", n=1)
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / TEMPLATE_FILE).write_text("{% for m in messages %}<|im_start|>{{ m }}{% endfor %}")

    with pytest.raises(ValueError, match="passthrough"):
        emit(corpus, tmp_path / "train.jsonl", masked=True, model=wrong)


def test_the_emitted_answer_carries_a_canonical_list_order(tmp_path: Path) -> None:
    """The target's list order is arbitrary, so it must not be part of the target.

    A case's `expected.json` lists its matches in whatever order the generator
    produced them — 3.6% of the training corpus in packet order, so effectively
    none. A model cannot derive that order from the packet, which makes it noise
    the training signal carries and the model has to memorise. Emitting a
    canonical order removes the noise, and it makes the emitted answer agree with
    the way the scorer now compares one.

    The corpus on disk is left exactly as written. It is the audited artefact,
    and the exam's provenance rests on regenerating it byte for byte.
    """
    from consylr.canonical import ordered

    corpus = a_corpus(tmp_path / "corpus", n=1)
    out = tmp_path / "train.jsonl"
    emit(corpus, out)

    case = next(p for p in sorted(corpus.iterdir()) if (p / "packet.json").exists())
    packet = json.loads((case / "packet.json").read_text())
    expected = json.loads((case / "expected.json").read_text())
    text = json.loads(out.read_text().splitlines()[0])["text"]
    answer = json.loads(text[len(render(packet)) :])

    assert answer == expected, "canonical order reorders an answer; it never changes one"
    assert json.dumps(answer, sort_keys=True, separators=(",", ":")) == json.dumps(
        ordered(expected), sort_keys=True, separators=(",", ":")
    )
    assert json.loads((case / "expected.json").read_text()) == expected
