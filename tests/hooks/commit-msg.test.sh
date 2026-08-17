#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Tests for the commit-msg hook. No dependencies beyond bash.
# Run: bash tests/hooks/commit-msg.test.sh
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 1

HOOK=.githooks/commit-msg
pass=0; fail=0
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# expect <accept|reject> <label> <message line...>
expect() {
  local want="$1" label="$2" got
  shift 2
  printf '%s\n' "$@" > "$tmp/msg"
  if bash "$HOOK" "$tmp/msg" >/dev/null 2>&1; then got=accept; else got=reject; fi
  if [ "$got" = "$want" ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); printf '  FAIL  expected %s, got %s: %s\n' "$want" "$got" "$label"; fi
}

SIGN="Signed-off-by: A Name <a@example.com>"

# --- the shape ---
expect accept "conventional with scope" "docs(adrs): record the licence decision" "" "$SIGN"
expect accept "conventional without scope" "docs: state the branching model" "" "$SIGN"
expect reject "unknown type" "wibble(cli): do a thing" "" "$SIGN"
expect reject "uppercase type" "Docs(cli): add a thing" "" "$SIGN"
expect reject "uppercase scope" "docs(CLI): add a thing" "" "$SIGN"
expect reject "no colon separator" "docs cli add a thing" "" "$SIGN"
expect reject "empty subject after colon" "docs(cli):" "" "$SIGN"

# --- the 50-character limit, checked at both sides of the boundary ---
# Built by length rather than typed out, so the two cases cannot silently become
# the same string — which is exactly what happened when they were hand-written.
prefix="docs(evaluation): "                        # 18 characters
at50="$prefix$(printf 'x%.0s' $(seq 1 $((50 - ${#prefix}))))"
at51="$prefix$(printf 'x%.0s' $(seq 1 $((51 - ${#prefix}))))"
[ ${#at50} -eq 50 ] || { printf '  BUG in test: at50 is %d chars\n' "${#at50}"; exit 2; }
[ ${#at51} -eq 51 ] || { printf '  BUG in test: at51 is %d chars\n' "${#at51}"; exit 2; }
expect accept "subject exactly 50 chars" "$at50" "" "$SIGN"
expect reject "subject 51 chars"         "$at51" "" "$SIGN"

# --- the DCO ---
expect reject "missing sign-off" "docs(cli): add a thing"
expect accept "sign-off present" "docs(cli): add a thing" "" "$SIGN"

# --- Signed-off-by is the only permitted trailer ---
# Stated generically rather than as a list of banned trailers: a rule that names
# what it forbids has to be kept in step with it, and publishing the list
# publishes what it guards. Anything trailer-shaped that is not a sign-off is a
# defect, whoever or whatever added it.
expect reject "a second trailer alongside the sign-off" \
  "docs(cli): add a thing" "" "$SIGN" "Reviewed-by: Someone <s@example.com>"
expect reject "an attribution trailer" \
  "docs(cli): add a thing" "" "$SIGN" "Co-Authored-By: Someone <s@example.com>"
expect reject "a trailer with no sign-off at all" \
  "docs(cli): add a thing" "" "Reported-by: Someone <s@example.com>"
expect accept "prose containing a colon is not a trailer" \
  "docs(cli): add a thing" "" "The reason: it was missing." "" "$SIGN"

# Git treats only the LAST paragraph as trailers, and so must this hook. A body
# line that happens to begin with one word and a colon is prose. The test above
# passed for the wrong reason — "The reason:" has a space before the colon and so
# never matched the pattern at all; a single word does match.
expect accept "single-word colon mid-body is prose" \
  "docs(cli): add a thing" "" "measured: 130 tokens against 256 reserved." "" "$SIGN"
expect accept "several such lines across paragraphs" \
  "docs(cli): add a thing" "" "estimated: no." "" "decided: yes." "" "$SIGN"
expect reject "real trailer in the final paragraph still caught" \
  "docs(cli): add a thing" "" "prose here." "" "$SIGN" "Reviewed-by: X <x@y.z>"
expect accept "trailer-shaped prose, sign-off in a later paragraph" \
  "docs(cli): add a thing" "" "Fixes: nothing in particular." "" "$SIGN"

# --- generated subjects git writes itself ---
expect accept "merge subject is exempt" "Merge pull request #12 from raheebwa/docs/thing"
expect accept "revert subject is exempt" 'Revert "docs(cli): add a thing"'

# --- comment lines are stripped before judging ---
expect accept "commented lines ignored" \
  "docs(cli): add a thing" "" "$SIGN" "# Please enter the commit message for your changes."

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
