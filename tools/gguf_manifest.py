# SPDX-License-Identifier: MIT
"""What a quantised artefact came from, per #68 and #70.

    python -m tools.gguf_manifest <artefact.gguf> --parent=<f16.gguf> \
        --recipe="Q6_K --imatrix" [--calibration=<file>] [--parent-manifest=<json>]

`tools/manifest.py` describes a training run — weights and the config that
produced them. A quantised GGUF is a different shape: one file derived from
another by one command, with a calibration set that changed what that command
did. It **inherits** provenance rather than owning it, so the chain back to the
corpus has to be walkable from this file alone.

Written *before* anything describes the artefact — result files, a model card, a
submission — because a provenance record written afterwards is a record of what
someone remembered rather than of what happened.

The parent's rules apply for the parent's reasons. **Every digest is computed
here, never transcribed**: a copied digest is a second source of truth that can
disagree with the first, and it reads as provenance while being wrong. **A
missing input is refused, not omitted**: an absent field with a plausible name
says "this had no calibration" when the truth is "nobody checked".

The recipe is recorded because the file cannot state it. Two GGUFs of the same
parent differ only by the command that made them, and the command leaves no
trace inside either one — as this project found by shipping a Q4_K_M that had
silently lost a capability its f16 parent still had.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _described(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is not on disk; provenance is refused rather than guessed")
    return {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}


def build(
    artefact: Path,
    *,
    parent: Path,
    calibration: Path | None,
    recipe: str,
    parent_manifest: Path | None = None,
) -> dict[str, Any]:
    """The record, computed. Raises if anything it must describe is absent."""
    out: dict[str, Any] = {
        "artefact": _described(Path(artefact)),
        "derived_from": _described(Path(parent)),
        # Not a free-text note: the exact argument string, because "Q6_K" and
        # "Q6_K --imatrix" produce files that differ in what they can do and in
        # nothing a reader can see.
        "recipe": recipe,
        # `"none"` is a claim, and it has to be distinguishable from a
        # calibration set nobody recorded.
        "calibration": _described(Path(calibration)) if calibration is not None else "none",
    }
    if parent_manifest is not None:
        out["inherits"] = json.loads(Path(parent_manifest).read_text(encoding="utf-8"))
    out["recorded_at"] = _head()
    return out


def _head() -> dict[str, Any]:
    """The tree this record was written from — not the one that quantised
    anything. See the manifest tool's own note on that distinction.

    **A dirty tree is recorded, not refused**: a clean-looking record of a dirty
    tree claims a reproducibility that did not exist. And an unavailable commit
    is an absent field rather than an empty string — `{"commit": ""}` is a
    present field with a plausible name asserting nothing, which is exactly the
    failure this module's own docstring forbids.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    return {"commit": commit, "tree_dirty": bool(dirty)}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    # A flag carried past the shell without an `=` is a flag the shell split off
    # something else — `--recipe=Q6_K --imatrix` unquoted arrives as two tokens
    # and quietly records an uncalibrated recipe for a calibrated file.
    stray = [a for a in args[1:] if a.startswith("--") and "=" not in a]
    if stray:
        print(f"{' '.join(stray)} arrived without a value; quote the whole flag")
        return 2
    flags = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in args[1:] if "=" in a}
    # Emptiness is checked, not just presence. `--recipe=` satisfies `in flags`
    # and records the empty string; `--calibration=` is falsy and used to record
    # the affirmative claim "none" on nobody's behalf.
    for required in ("--parent", "--recipe"):
        if not flags.get(required, "").strip():
            print(f"{required}=<value> is required and must not be empty")
            return 2
    if "--calibration" in flags and not flags["--calibration"].strip():
        print("--calibration was given with no value; omit it to record no calibration")
        return 2
    artefact = Path(args[0])
    calib = flags.get("--calibration")
    pm = flags.get("--parent-manifest")
    record = build(
        artefact,
        parent=Path(flags["--parent"]),
        calibration=Path(calib) if calib else None,
        recipe=flags["--recipe"],
        parent_manifest=Path(pm) if pm else None,
    )
    out = artefact.with_suffix(".manifest.json")
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
