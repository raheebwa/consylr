# SPDX-License-Identifier: MIT
"""Tests for running the shipped GGUF, per #23's four modes.

Every number this project has reported so far came out of MLX. The artefact
that gets judged is a GGUF in llama.cpp, and a result in one runtime is not
evidence about the other. These tests defend the three things that make a
cross-mode comparison mean anything: that the window is the harness's rather
than the model's, that the layers stay where the audit box can run them, and
that a mode can never be reported under another mode's name.
"""

import pytest

from consylr import prompt
from tools.evaluate_gguf import (
    MODES,
    RUN_TIMEOUT_S,
    SUBPROCESS_MODES,
    command,
    llama_kwargs,
    main,
    result_name,
    said,
    stratified,
)


def test_the_window_is_the_harness_s_and_never_the_model_s() -> None:
    """The GGUF declares a 262,144-token context and llama.cpp's `-c` defaults
    to "loaded from model". An omitted `-c` therefore does not fall back to
    something small — it asks for a KV cache orders of magnitude past the
    memory ceiling, on a box where exceeding the ceiling is disqualification.

    Both backends are checked, because the window has to be declared twice and
    a tool that got it right in one place would still report the other."""
    for mode in SUBPROCESS_MODES:
        argv = command(mode, model="m.gguf", prompt_file="p.txt")
        assert "-c" in argv, f"{mode} would take the model's own context"
        assert argv[argv.index("-c") + 1] == str(prompt.BUDGET.context)
    assert llama_kwargs("m.gguf")["n_ctx"] == prompt.BUDGET.context


def test_the_audit_box_has_no_gpu_so_the_layers_stay_on_the_cpu() -> None:
    """`-ngl` defaults to `auto`, which offloads to Metal here and to nothing on
    the audit VM. The offloaded configuration reads 2.4 GB lighter — the
    direction that hides a memory failure rather than causing one — and it is
    not the system the judges run."""
    for mode in SUBPROCESS_MODES:
        argv = command(mode, model="m.gguf", prompt_file="p.txt")
        assert argv[argv.index("-ngl") + 1] == "0"
    assert llama_kwargs("m.gguf")["n_gpu_layers"] == 0


def test_completion_mode_refuses_conversation_and_chat_mode_does_not() -> None:
    """The whole difference between mode 2 and mode 3 is whether llama.cpp
    applies the GGUF's chat template. Conversation mode is auto-enabled when a
    template is present, and this artefact carries one — so mode 2 has to say
    no explicitly, and mode 3 exists precisely to let it happen."""
    assert "-no-cnv" in command("completion", model="m.gguf", prompt_file="p.txt")
    assert "-no-cnv" not in command("chat", model="m.gguf", prompt_file="p.txt")


def test_generation_is_deterministic_in_every_mode() -> None:
    """The harness reads at temperature zero. A sampled run would make a
    divergence between modes unattributable to the interface."""
    for mode in SUBPROCESS_MODES:
        argv = command(mode, model="m.gguf", prompt_file="p.txt")
        assert argv[argv.index("--temp") + 1] == "0"
    assert llama_kwargs("m.gguf")["temperature"] == 0.0


def test_each_mode_records_under_its_own_name() -> None:
    """A chat-mode number reported as a profiler-mode number is the one error
    this issue exists to prevent."""
    assert len({MODES[m].label for m in MODES}) == len(MODES)
    for name in MODES:
        assert name in MODES[name].label


def test_an_unknown_mode_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(KeyError):
        command("scaffolded", model="m.gguf", prompt_file="p.txt")


def test_the_binary_is_told_not_to_echo_the_prompt() -> None:
    """llama-completion prints the prompt before continuing it, and the echo is
    not byte-identical to what was sent — so stripping it by prefix match
    silently leaves the whole packet in front of the answer, and every case
    scores as unparseable. Suppressing the echo at the source removes the guess
    rather than improving it."""
    for mode in SUBPROCESS_MODES:
        assert "--no-display-prompt" in command(mode, model="m.gguf", prompt_file="p.txt")


def test_the_end_of_text_marker_is_not_part_of_the_answer() -> None:
    """The binary announces termination in the output stream. Left in place it
    turns a complete answer into trailing garbage after the closing brace."""
    assert said('{"matches":[]} [end of text]\n\n') == '{"matches":[]}'
    assert said('  {"matches":[]}  ') == '{"matches":[]}'


def test_an_answer_without_the_marker_survives_intact() -> None:
    """A run that hit the token cap never prints the marker, and its truncated
    answer is evidence — trimming something that is not there must not trim
    anything that is."""
    assert said('{"matches":[{"l":["A-1"]') == '{"matches":[{"l":["A-1"]'


def test_a_subset_covers_every_family_before_it_doubles_up() -> None:
    """A 50-of-204 subset drawn by file order would over-sample whichever
    families sort early and miss others entirely, and a divergence confined to
    an absent family would read as agreement."""
    cases = [(f"c{i:03d}", f"fam{i % 14}") for i in range(204)]
    picked = stratified(cases, 50)
    families = {f for _, f in picked}
    assert len(picked) == 50
    assert families == {f"fam{i}" for i in range(14)}
    counts = [sum(1 for _, f in picked if f == fam) for fam in sorted(families)]
    assert max(counts) - min(counts) <= 1


def test_the_subset_is_the_same_subset_every_time() -> None:
    """A subset that moves between runs cannot be compared with itself."""
    cases = [(f"c{i:03d}", f"fam{i % 14}") for i in range(204)]
    assert stratified(cases, 50) == stratified(cases, 50)


def test_asking_for_more_than_there_is_returns_everything() -> None:
    cases = [(f"c{i:03d}", "fam") for i in range(5)]
    assert len(stratified(cases, 50)) == 5


def test_the_offload_default_survives_the_override_existing() -> None:
    """A diagnostic sometimes needs the GPU — comparing two quantisations of the
    same weights is about the quantisation, and waiting an hour per arm on the
    CPU buys nothing. The override must not become the default: an offloaded
    reading is 2.4 GB lighter and is not the audit's system."""
    assert llama_kwargs("m.gguf")["n_gpu_layers"] == 0
    assert llama_kwargs("m.gguf", gpu_layers=99)["n_gpu_layers"] == 99
    for mode in SUBPROCESS_MODES:
        argv = command(mode, model="m.gguf", prompt_file="p.txt", gpu_layers=99)
        assert argv[argv.index("-ngl") + 1] == "99"


def test_a_diagnostic_run_cannot_overwrite_an_audit_run() -> None:
    """The filename keyed only on exam/model/mode, so a --stratified or
    --gpu-layers diagnostic wrote over the full CPU audit result and every raw
    answer retained in it. This is verbatim the incident evaluate.py:148-153
    documents and already fixed -- 'a filename that cannot distinguish two
    artefacts is a filename that overwrites one of them' -- which did not travel
    because this tool was forked rather than parameterised."""
    audit = result_name("sealed-v4", "m.gguf", "profiler", subset=0, gpu_layers=0)
    for diagnostic in (
        result_name("sealed-v4", "m.gguf", "profiler", subset=50, gpu_layers=0),
        result_name("sealed-v4", "m.gguf", "profiler", subset=0, gpu_layers=99),
        result_name("sealed-v4", "m.gguf", "profiler", subset=50, gpu_layers=99),
    ):
        assert diagnostic != audit


def test_the_audit_shaped_run_keeps_the_plain_name() -> None:
    """The name every earlier result already carries. A rename would orphan the
    ladder's results from the tools that read them."""
    assert result_name("probe-v1", "consylr-v5-Q6_K-imat.gguf", "profiler", 0, 0) == (
        "eval-probe-v1-consylr-v5-Q6_K-imat-profiler.json"
    )


def test_a_wedged_child_is_killed_rather_than_waited_on_forever() -> None:
    """Chat mode deliberately leaves llama.cpp's interactive loop enabled, so
    the child reads its next turn from the inherited terminal and never returns.
    capture_output redirects stdout and stderr only. Without a timeout, case 1
    of 204 hangs silently and the operator's keystrokes are eaten by the child."""
    assert RUN_TIMEOUT_S > 0


def test_an_exam_with_no_cases_is_refused() -> None:
    """A mistyped path digests the empty set without complaint, loads the whole
    model, and reports 'parse rate 0.0% / correct abstention 0.0%' -- which reads
    as total model failure rather than a wrong argument -- then writes a record
    attesting an empty exam over the real one and exits 0."""
    import tempfile

    with tempfile.TemporaryDirectory() as empty:
        assert main([empty, "m.gguf", "--mode=profiler"]) == 1


def test_every_declared_generation_setting_has_a_reader() -> None:
    """llama_kwargs is documented and tested as the single declaration of what
    the in-process backend generates with, but two of its six keys were
    re-specified as literals at the call site with no reader anywhere. Change
    one for a diagnostic and the tests keep passing, the record keeps describing
    the declared configuration, and the run uses the old one."""
    import inspect

    from tools import evaluate_gguf

    body = inspect.getsource(evaluate_gguf._in_process)
    for key in llama_kwargs("m.gguf"):
        assert f'kwargs["{key}"]' in body, f"{key} is declared but never read"
