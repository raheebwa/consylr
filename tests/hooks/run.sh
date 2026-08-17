#!/usr/bin/env bash
# Runs every hook test. This is the command CONTRIBUTING.md documents and the
# command CI will run; if the two ever diverge, the documented one is correct.
#
# Globbed rather than listed, so adding a test file does not require editing
# this runner, the pre-commit hook, and CONTRIBUTING.md in step.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 1

rc=0 ran=0
for t in tests/hooks/*.test.sh; do
  [ -f "$t" ] || continue
  ran=$((ran + 1))
  printf '== %s\n' "$t"
  bash "$t" || rc=1
done

if [ "$ran" -eq 0 ]; then
  printf 'no test files found in tests/hooks/ — that is a failure, not a pass\n' >&2
  exit 2
fi

printf '\n%d test file(s) run\n' "$ran"
exit $rc
