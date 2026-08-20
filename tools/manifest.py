# SPDX-License-Identifier: MIT
"""What a trained artefact came from, in a form nobody has to remember.

    python -m tools.manifest <run dir> [--corpus name=<dir> ...] \
        [--templates name=<dir> ...] [--note k=v ...]

Written beside the weights, and written *before* anything is derived from them,
so a converted or quantised artefact inherits its provenance from a file rather
than from someone's recollection of the evening.

**Every digest is computed here, never transcribed.** `docs/sealed-set.md`
refuses to print one for the same reason: a transcribed digest is a second source
of truth that can disagree with the first, and it has to be re-copied every time
the artefact moves. A manifest quoting a number someone typed is a manifest that
will eventually be wrong in a way nothing detects — which is worse than no
manifest, because it reads as provenance.

**It refuses rather than guesses.** A corpus that is not on disk is an error, not
an absent field with a plausible name in it. The recipe is read out of the run's
own `adapter_config.json` rather than retyped from the command that produced it,
because the command is what someone *meant* to run and the config is what ran.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from consylr.corpus import content_digest, template_digest

WEIGHTS = "adapters.safetensors"
CONFIG = "adapter_config.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _head() -> dict[str, Any]:
    """The tree the manifest was written from — which is NOT the generator.

    The first version of this recorded `git rev-parse HEAD` under "generator",
    and it was wrong in the way that matters: HEAD at manifest time is whatever
    happens to be checked out, while the commit that built the artefact is
    earlier and often unreachable from here. Both are facts; only one is
    provenance, and conflating them produced a manifest that read as authoritative
    about something it had never seen.

    A dirty tree is recorded rather than refused. The run happened; the manifest's
    job is to say what it happened from, and a clean-looking record of a dirty
    tree claims a reproducibility that did not exist.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
            ).stdout.strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    return {"commit": sha, "tree_dirty": dirty}


def build(
    run: Path,
    *,
    corpora: dict[str, Path],
    templates: dict[str, Path] | None = None,
    generator: str = "",
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The manifest for one trained artefact."""
    weights = run / WEIGHTS
    if not weights.is_file():
        raise ValueError(f"{run} holds no {WEIGHTS}; there is no artefact to describe")

    config: dict[str, Any] = {}
    if (run / CONFIG).is_file():
        config = json.loads((run / CONFIG).read_text(encoding="utf-8"))

    recorded: dict[str, Any] = {}
    for label, where in corpora.items():
        if not where.is_dir():
            raise ValueError(f"{label} corpus {where} does not exist; it cannot be recorded")
        recorded[label] = {"name": where.name, "digest": content_digest(where)}

    lora = config.get("lora_parameters", {}) or {}
    return {
        "artefact": {"path": str(run), "weights": WEIGHTS, "sha256": _sha256(weights)},
        "base_model": config.get("model", ""),
        "data": config.get("data", ""),
        "corpora": recorded,
        # The set a corpus was drawn from, not only the corpus. A case records
        # the templates it used, so a template no case referenced leaves every
        # per-case fingerprint matching while the directory has changed.
        "templates": {
            label: {"name": where.name, "digest": template_digest(where)}
            for label, where in sorted((templates or {}).items())
        },
        # Stated by the caller, because the tool cannot discover it: the commit
        # that built the corpus is earlier than this one and may not be reachable
        # from the branch a manifest is written on. Absent when unstated.
        "generator": {"commit": generator} if generator else {},
        "recorded_at": _head(),
        "training": {
            "iters": config.get("iters"),
            "batch_size": config.get("batch_size"),
            "learning_rate": config.get("learning_rate"),
            "num_layers": config.get("num_layers"),
            "max_seq_length": config.get("max_seq_length"),
            "mask_prompt": config.get("mask_prompt"),
            "save_every": config.get("save_every"),
            "seed": config.get("seed"),
            "lora": {
                "rank": lora.get("rank"),
                "dropout": lora.get("dropout"),
                "scale": lora.get("scale"),
            },
        },
        "notes": dict(notes or {}),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    run = Path(sys.argv[1])
    corpora: dict[str, Path] = {}
    templates: dict[str, Path] = {}
    notes: dict[str, str] = {}
    generator = ""
    for arg in sys.argv[2:]:
        if arg.startswith("--templates="):
            label, _, where = arg[len("--templates=") :].partition("=")
            templates[label] = Path(where)
            continue
        if arg.startswith("--corpus="):
            label, _, where = arg.split("=", 1)[1].partition(":")
            corpora[label] = Path(where)
        elif arg.startswith("--generator="):
            generator = arg.split("=", 1)[1]
        elif arg.startswith("--note="):
            key, _, value = arg.split("=", 1)[1].partition(":")
            notes[key] = value

    body = build(run, corpora=corpora, templates=templates, generator=generator, notes=notes)
    out = run / "manifest.json"
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(body, indent=2, sort_keys=True))
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
