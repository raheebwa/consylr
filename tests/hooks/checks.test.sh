#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Tests for the staged-content checks the pre-commit hook applies.
#
# Each check is a pure function of the paths it is given, so it is tested against
# fixtures in a temporary directory rather than against a repository. A check
# nobody tested enforces nothing.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 1
LIB=.githooks/checks.sh
pass=0; fail=0
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# try <ok|bad> <check-fn> <label> <path> ; fixture content arrives on stdin.
try() {
  local want="$1" fn="$2" label="$3" path="$4" got
  mkdir -p "$tmp/$(dirname "$path")"; cat > "$tmp/$path"
  if ( cd "$tmp" && bash "$OLDPWD/$LIB" "$fn" "$path" ) >/dev/null 2>&1; then got=ok; else got=bad; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); else
    fail=$((fail+1)); printf '  FAIL  %s [%s]: wanted %s got %s\n' "$label" "$fn" "$want" "$got"; fi
}

# --- check_spdx: a no-op on a docs-only tree, in place before the first .py ---
try ok  check_spdx "py with spdx first" "a.py" <<<'# SPDX-License-Identifier: MIT
x = 1'
try bad check_spdx "py without spdx" "b.py" <<<'x = 1'
try bad check_spdx "spdx below line five" "c.py" <<<'1
2
3
4
5
# SPDX-License-Identifier: MIT'
try ok  check_spdx "prose is not source" "notes.md" <<<'no spdx here'

# Shell counts as source. .githooks/ is exactly the kind of directory people copy
# between repositories — these hooks descend from another repo's — so the one
# machine-readable line that survives the copy matters here more than most places.
try ok  check_spdx "sh with spdx after the shebang" "s.sh" <<<'#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
echo hi'
try bad check_spdx "sh without spdx" "t.sh" <<<'#!/usr/bin/env bash
echo hi'
try ok  check_spdx "un-suffixed hook with spdx" ".githooks/commit-msg" <<<'#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
exit 0'
try bad check_spdx "un-suffixed hook without spdx" ".githooks/pre-push" <<<'#!/usr/bin/env bash
exit 0'

# --- check_license_classifier: path-scoped, free, and waiting for a manifest ---
try ok  check_license_classifier "expression only" "pyproject.toml" <<<'license = "MIT"'
try bad check_license_classifier "trove classifier present" "pyproject.toml" <<<'classifiers = ["License :: OSI Approved :: MIT License"]'

# --- check_workflow: permissions block, and 40-char SHA pinning ---
try ok  check_workflow "pinned and scoped" ".github/workflows/ok.yml" <<<'permissions:
  contents: read
jobs:
  a:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683'
try bad check_workflow "action pinned to a tag" ".github/workflows/tag.yml" <<<'permissions:
  contents: read
jobs:
  a:
    steps:
      - uses: actions/checkout@v4'
try bad check_workflow "no permissions block" ".github/workflows/np.yml" <<<'jobs:
  a:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683'

# --- check_changelog: Keep a Changelog heading format ---
try ok  check_changelog "iso date" "CHANGELOG.md" <<<'## [0.1.0] - 2026-08-18'
try bad check_changelog "non-iso date" "CHANGELOG.md" <<<'## [0.1.0] - 18/08/2026'
try ok  check_changelog "unreleased alone is valid" "CHANGELOG.md" <<<'## [Unreleased]'

# --- check_no_artifacts: expanded to this repository's families ---
# The .gitignore already refuses these. The hook exists for the path .gitignore
# cannot cover: a rushed `git add -f`.
try bad check_no_artifacts "gguf weights"        "model.gguf"                  <<<'binary'
try bad check_no_artifacts "safetensors weights" "adapter.safetensors"         <<<'binary'
try bad check_no_artifacts "raw bin weights"     "pytorch_model.bin"           <<<'binary'
try bad check_no_artifacts "model dir"           "model/weights.q4.gguf"       <<<'binary'
try bad check_no_artifacts "models dir"          "models/a/b.txt"              <<<'text'
try bad check_no_artifacts "checkpoints dir"     "checkpoints/step-500/x"      <<<'text'
try bad check_no_artifacts "adapters dir"        "adapters/lora/x"             <<<'text'
try bad check_no_artifacts "generated corpus"    "data/generated/packets.jsonl" <<<'{}'
try bad check_no_artifacts "sealed corpus"       "data/sealed/packets.jsonl"    <<<'{}'
try bad check_no_artifacts "run output"          "runs/2026-08-18/result.json"  <<<'{}'
try bad check_no_artifacts "nested model dir"    "spikes/model/x.gguf"          <<<'binary'
try ok  check_no_artifacts "gitkeep is allowed"  "model/.gitkeep"               <<<''
try ok  check_no_artifacts "ordinary document"   "docs/notes.md"                <<<'text'
try ok  check_no_artifacts "modelling prose"     "docs/modelling.md"            <<<'text'

# --- check_pii: the placeholder rule ---
try ok  check_pii "documented placeholder form" "d.md" <<<'Call +<country-code> 000 000 000 for support.'
try ok  check_pii "zeroed placeholder" "d2.md" <<<'Call +000 000 000 000 for support.'
# Assembled at runtime: writing a locale-plausible number as a literal would put
# one in a tracked file, which is the very thing check_pii exists to prevent.
cc="+"; plausible="${cc}256 772 123 456"
try bad check_pii "locale-plausible number" "e.md" <<<"Call $plausible for support."
try ok  check_pii "binary skipped" "f.gguf" <<<'anything'

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
