# SPDX-License-Identifier: MIT
"""Tests for re-scoring a stored run, per the metric correction on #63.

The tool's whole value is that the two numbers it prints are both real — the one
a run was reported with and the one today's scorer gives. Everything here defends
that: a record re-scored against the wrong exam, or a baseline invented for a
metric the record never carried, produces a number that is wrong in the one way
nobody can see, because a plausible figure in a well-formed table announces
nothing.
"""

import json
from pathlib import Path

import pytest

from consylr.corpus import content_digest, write
from tests.support import a_template, built
from tools.rescore import main, rescore


def an_exam(tmp_path: Path, n: int = 2, offset: int = 0) -> Path:
    """`offset` moves the amounts, so two exams differ in content but not in the
    sequence of families — which is the case the digest check has to catch."""
    templates = [a_template(id=f"t-{i:03d}", amount=f"{100 + offset + i}.00") for i in range(n)]
    write(
        tmp_path, [built(t, case_index=0, role="holdout") for t in templates], templates=templates
    )
    return tmp_path


def a_record(exam: Path, out: Path, **extra: object) -> Path:
    cases = sorted(p for p in exam.iterdir() if (p / "packet.json").exists())
    body = {
        "exam": exam.name,
        "exam_digest": content_digest(exam),
        "parse_rate": 1.0,
        "schema_valid": 1.0,
        "exact_match": 1.0,
        "correspondence_f1": 1.0,
        "correct_abstention": 0.0,
        "false_abstention": 0.0,
        "cases": [
            {
                "family": json.loads((c / "meta.json").read_text())["family"],
                "produced": (c / "expected.json").read_text(),
            }
            for c in cases
        ],
        **extra,
    }
    out.write_text(json.dumps(body), encoding="utf-8")
    return out


def test_a_record_is_rescored_from_its_kept_answers(tmp_path: Path) -> None:
    exam = an_exam(tmp_path / "exam")
    record = a_record(exam, tmp_path / "run.json")
    was, now = rescore(exam, record)
    assert was["exact_match"] == 1.0
    assert now["exact_match"] == 1.0


def test_a_record_from_another_exam_is_refused(tmp_path: Path) -> None:
    """The families can agree while the packets do not.

    Families are quota-balanced and case directories sort by name, so two exams
    sharing a family sequence is the ordinary case rather than a contrived one.
    Re-scoring across them prints a confident table computed against packets the
    model was never shown, and nothing in the output looks wrong.

    `evaluate.py` refuses on the digest before it will score anything. This reads
    the digest that run already wrote down.
    """
    exam = an_exam(tmp_path / "exam")
    other = an_exam(tmp_path / "other", n=2, offset=50)
    record = a_record(exam, tmp_path / "run.json")
    with pytest.raises(ValueError, match="digest"):
        rescore(other, record)


def test_a_metric_the_record_never_carried_is_not_invented(tmp_path: Path) -> None:
    """A missing baseline makes the comparison impossible, not zero.

    Defaulting to 0.0 fabricates exactly the regression the tool exists to
    measure: a record written before a metric existed would report it rising from
    nothing to whatever it is today, and credit the change under review.
    """
    exam = an_exam(tmp_path / "exam")
    record = a_record(exam, tmp_path / "run.json")
    body = json.loads(record.read_text())
    del body["schema_valid"]
    record.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_valid"):
        rescore(exam, record)


def test_one_unreadable_record_does_not_end_the_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The runs that cannot be re-scored are expected input, not an accident.

    Two of this project's own evaluations predate answer retention and hold none.
    A batch that stops at the first of them examines nothing after it, and says so
    with a traceback rather than a refusal.
    """
    exam = an_exam(tmp_path / "exam")
    good = a_record(exam, tmp_path / "good.json")
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"cases": []}), encoding="utf-8")
    later = a_record(exam, tmp_path / "later.json")

    code = main([str(exam), str(empty), str(good), str(later)])
    out = capsys.readouterr().out
    assert code != 0
    assert "REFUSED" in out
    assert "good.json" in out and "later.json" in out
