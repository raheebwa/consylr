#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Checks applied to staged content by the pre-commit hook.
# Usage: checks.sh <check-name|all> <path>...
#
# Each check is a pure function of the paths it is given, so it can be tested
# against fixtures without a repository. Tests live in tests/hooks/.
set -uo pipefail

note() { printf '  %s\n' "$1" >&2; }

# Every source file carries its licence identifier, so the file survives being
# copied out of the tree.
#
# Shell is source too, and .githooks/ is precisely the kind of directory people
# copy between repositories — these hooks descend from another repo's — so the
# rule applies there at least as much as to product code. Scoping it to "product
# source only" would be an undocumented exception with a label on it.
check_spdx() {
  local rc=0 f
  for f in "$@"; do
    case "$f" in *.py|*.sh|.githooks/*) ;; *) continue ;; esac
    [ -f "$f" ] || continue
    head -n 5 "$f" | grep -qxF '# SPDX-License-Identifier: MIT' \
      || { note "$f: no '# SPDX-License-Identifier: MIT' in the first five lines"; rc=1; }
  done
  return $rc
}

# PEP 639: the licence is an SPDX expression. A trove classifier alongside one
# is deprecated, and build tools may error on the combination.
check_license_classifier() {
  local rc=0 f
  for f in "$@"; do
    case "$f" in *pyproject.toml) ;; *) continue ;; esac
    [ -f "$f" ] || continue
    grep -q 'License ::' "$f" \
      && { note "$f: a 'License ::' classifier contradicts the PEP 639 licence expression"; rc=1; }
  done
  return $rc
}

# A workflow declares its scope, and pins every action to an immutable SHA.
# A tag is mutable, so pinning to a tag is pinning to nothing.
check_workflow() {
  local rc=0 f line
  for f in "$@"; do
    case "$f" in .github/workflows/*.yml|.github/workflows/*.yaml) ;; *) continue ;; esac
    [ -f "$f" ] || continue
    grep -qE '^[[:space:]]*permissions:' "$f" \
      || { note "$f: no 'permissions:' block; a workflow must declare its scope"; rc=1; }
    while IFS= read -r line; do
      printf '%s' "$line" | grep -qE 'uses:[[:space:]]*[^@[:space:]]+@[0-9a-f]{40}([[:space:]]|$)' \
        || { note "$f: action not pinned to a 40-character SHA -> ${line#*:}"; rc=1; }
    done < <(grep -E '^[[:space:]]*-?[[:space:]]*uses:' "$f")
  done
  return $rc
}

# Keep a Changelog: version headings are '## [x.y.z] - YYYY-MM-DD', ISO only.
# '## [Unreleased]' is not a version heading and is not matched.
check_changelog() {
  local rc=0 f line
  for f in "$@"; do
    case "$f" in *CHANGELOG.md) ;; *) continue ;; esac
    [ -f "$f" ] || continue
    while IFS= read -r line; do
      printf '%s' "$line" | grep -qE '^## \[[0-9]+\.[0-9]+\.[0-9]+\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$' \
        || { note "$f: version heading must be '## [x.y.z] - YYYY-MM-DD' -> $line"; rc=1; }
    done < <(grep -E '^## \[[0-9]' "$f")
  done
  return $rc
}

# Weights, adapters, corpora and run output are regenerated or fetched, never
# committed. .gitignore already refuses these; this check covers the one path
# .gitignore cannot — a rushed `git add -f`.
#
# Matched on whole path segments, so ordinary prose like docs/modelling.md is
# not caught by the 'model' family.
check_no_artifacts() {
  local rc=0 f
  for f in "$@"; do
    case "$f" in .gitkeep|*/.gitkeep) continue ;; esac
    case "$f" in
      *.gguf|*.safetensors|*.bin)
        note "$f: model weights are fetched at setup, never committed"; rc=1 ;;
      model/*|*/model/*|models/*|*/models/*|checkpoints/*|*/checkpoints/*|adapters/*|*/adapters/*)
        note "$f: model and adapter directories are not tracked"; rc=1 ;;
      data/generated/*|*/data/generated/*|data/sealed/*|*/data/sealed/*)
        note "$f: corpora are regenerated from the generator and its seed, never committed"; rc=1 ;;
      runs/*|*/runs/*)
        note "$f: run output is written per run, never committed"; rc=1 ;;
    esac
  done
  return $rc
}

# Many countries reserve no range for fictional use, so a locale-plausible
# number can route to a real person. The documented placeholder forms are
# '+<country-code> 000 000 000' and an all-zero number.
check_pii() {
  local rc=0 f hits
  for f in "$@"; do
    case "$f" in *.gguf|*.safetensors|*.bin|*.png|*.jpg|*.jpeg|*.pdf|*.svg) continue ;; esac
    [ -f "$f" ] || continue
    hits="$(grep -oE '\+[0-9][0-9 ()-]{7,}[0-9]' "$f" 2>/dev/null | grep -v '^+000' || true)"
    if [ -n "$hits" ]; then
      note "$f: use the +<country-code> 000 000 000 placeholder; a plausible number can route to a real person -> $(printf '%s' "$hits" | head -n1)"
      rc=1
    fi
  done
  return $rc
}

ALL='check_spdx check_license_classifier check_workflow check_changelog check_no_artifacts check_pii'

cmd="${1:-}"; shift || true
case "$cmd" in
  all) rc=0; for c in $ALL; do "$c" "$@" || rc=1; done; exit $rc ;;
  check_*) case " $ALL " in *" $cmd "*) "$cmd" "$@"; exit $? ;; esac
           printf 'unknown check: %s\n' "$cmd" >&2; exit 2 ;;
  *) printf 'usage: checks.sh <all|%s> <path>...\n' "${ALL// /|}" >&2; exit 2 ;;
esac
