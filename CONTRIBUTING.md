# Contributing to Consylr

Consylr is a compact offline model and the reasoning that constrains it. Both halves have to
hold: the model has to reconcile correctly and abstain honestly, and every claim published
about it has to trace to a run someone else can reproduce.

**Read [`docs/prd/prd.md`](docs/prd/prd.md) and [`README.md`](README.md) §Scope discipline
first.** The out-of-scope list there is load-bearing, not a disclaimer — it is the fastest
way to tell whether an idea belongs here. Then read
[`docs/decisions.md`](docs/decisions.md) for what is decided and what is not, and the
[issues](https://github.com/raheebwa/consylr/issues) for what is being worked on and what is
blocked.

---

## The state of this repository, stated plainly

**There is code now.** This section said there was none, and was written so the change would be
visible rather than silent — this is that change.

| Thing you might look for | Where it stands |
|---|---|
| Test command | **`python -m pytest`** for the package, and **`bash tests/hooks/run.sh`** for the hook rules. CI runs both, plus `ruff check`, `ruff format --check` and `mypy`. |
| CI workflow | **Present** — `.github/workflows/ci.yml`, added with the first module, running the same commands documented here. |
| Package manifest | **Present** — `pyproject.toml`, PEP 639 licence expression, `requires-python` lower bound only. |
| Benchmarks | None published. No figure has been measured yet, and none is quoted anywhere as though it had been. |

Until then, contributions are documents — decision records, designs, corrections to the
evidence layer — plus the hooks that enforce the conventions below. Both have rules, and both
are covered by the test command above.

## Working on the code

From a clone, at the repository root:

```sh
mise trust
mise install
uv pip install -e ".[dev]"
```

[mise](https://mise.jdx.dev) pins the interpreter in `mise.toml`, so a contributor's run and a CI
run are the same run. `mise trust` is required because a project configuration can set environment
variables, and the tool will not read one until you say it may.

Then the commands in the table above. CI runs exactly those.

## Hooks

The rules in this file are enforced locally, not merely documented. Enable them once per
clone:

```sh
git config core.hooksPath .githooks
```

Three hooks then run:

- **`commit-msg`** rejects a subject that is not `<type>(<scope>): <subject>`, a subject over
  50 characters, a missing sign-off, and any trailer other than `Signed-off-by:`. Merge and
  revert subjects, which git writes itself, are exempt.
- **`pre-commit`** refuses a commit on `main` or on a branch not named
  `<type>/<short-description>`, and rejects staged content that breaks a rule stated elsewhere
  in this document: a source file without its SPDX header, a `License ::` classifier, a workflow
  missing `permissions:` or naming an action not pinned to a 40-character commit SHA, a
  changelog heading whose date is not ISO 8601, a committed model artefact or corpus, and a
  phone number that is not the documented placeholder. Once `pyproject.toml` exists it also
  runs `ruff`, `mypy` and the test suite.
- **`pre-push`** refuses a direct push to `main`.

`pre-commit` judges the **staged** content, not the working tree: a partially staged file is
committed as staged, and that is the version the rules have to hold for. The checks themselves
live in `.githooks/checks.sh` as functions of the paths they are given, so they are tested
against fixtures in [`tests/hooks/`](tests/hooks/) — **a hook nobody tested enforces nothing.**

This is work CI cannot do. CI sees a branch only once its history is already written, and a
malformed subject or a missing sign-off cannot be fixed afterwards without rewriting the
branch — cheap before a push, disruptive after one. The moment of the commit is the only point
where the fix is free.

`git config` is per clone, so a fresh clone needs the line again.

### Local extensions

Each of `pre-commit` and `pre-push` will also run
`$(git rev-parse --git-common-dir)/hooks/<name>.local` if you create one and mark it
executable. That is where a personal check belongs: it stays inside the git directory and is
never published, so it may contain things a tracked file must not.

A vocabulary or secret sweep is the clearest example. Such a guard's pattern list *is* the list
it guards, so committing it — or moving it into CI — would publish exactly what it exists to
keep out. The same reasoning applies to ignoring a private path: those entries go in
`.git/info/exclude`, never in the committed `.gitignore`, because **an ignore entry names the
path it ignores and so announces that the path exists.**

If a hook is wrong, fix the hook. `--no-verify` leaves the defect in the history.

## Working material

`scratchpad/` is ignored by git, and that is where working material belongs — session notes,
handoff documents, scratch analysis, anything that records *how* the work is being done rather
than what the work is. Those are not repository artefacts, and `check_no_working_docs` refuses to
let one be committed.

Nothing regenerable is tracked either: no model weights or adapters, no generated or sealed
corpora, no run output. `.gitignore` refuses them and `check_no_artifacts` covers the case
`.gitignore` cannot, which is a deliberate `git add -f`.

## How the documents fit together

Four kinds of document, and **a fact lives in exactly one of them** — the others link to it.
Duplicating a fact means having two of them, and the second one is wrong first.

| Directory | Holds | Changed when |
|---|---|---|
| [`docs/research/`](docs/research/) | The evidence. Captured material, preserved as delivered. | Almost never. It is **not** edited as understanding improves — that is the point of it. A redaction for publication is declared in the document's own header. |
| [`docs/adrs/`](docs/adrs/) | Decisions. What was chosen, and what it cost. | A new ADR supersedes an old one. An accepted ADR is not rewritten to look wiser than it was. |
| [`docs/rfcs/`](docs/rfcs/) | Designs. Interfaces, behaviour, refusals, verification. | Before the thing it describes is built. |
| [`docs/prd/`](docs/prd/) | Scope. What this is and is not. | Rarely, and with an ADR saying why. |

If a research document and an ADR disagree, **the ADR is current**, and it should name what
it overrode. Templates: [`docs/adrs/0000-template.md`](docs/adrs/0000-template.md),
[`docs/rfcs/0000-template.md`](docs/rfcs/0000-template.md). Numbering is sequential and
gapless; a withdrawn record keeps its number and says it was withdrawn.

New or unobvious terms go in [`docs/glossary.md`](docs/glossary.md) in the same change that
introduces them.

## Test policy

**Test-driven development is the policy of this project, and the commit sequence is the
evidence for it.** Declaring the policy is not the same as following it, so the history is
where to check — starting with the hook tests, which were written RED-first before the checks
they cover existed:

1. Write the failing test first. Run it. Confirm it fails, **and that it fails for the
   reason you expect** — a test that passes before the behaviour exists is testing nothing.
2. Write the minimum code that makes it pass.
3. Refactor with the test green.
4. Commit. One behaviour per commit.

Implementation and its tests are never written in the same pass. Tests written against code
that already exists are **characterization tests**, and are named as such, so a later reader
can tell which tests specified behaviour and which merely recorded it.

Assert behaviour a caller can observe, not the shape of the implementation. The check: would
the test survive a rewrite that kept the behaviour? If changing *how* the code works forces
the test to change, the test describes the code rather than constraining it, and it can never
report a regression.

This project's hardest thing to test is a model, not a function. Two rules follow:

- **A model's behaviour is measured on a sealed set, never on anything it was trained on.**
  Splits are grouped by perturbation family, never random rows, because random splits leak
  a family across the boundary and report a score the model did not earn.
- **Abstention is a measured behaviour with a rate, not a prompt instruction that either
  worked or did not.** A model that answers confidently where the evidence does not support
  an answer has failed, even when the answer happens to be right.

## Numbers

Anything numeric added to the README, an ADR, an RFC, or any other document must trace to a
recorded run, and that record must name the hardware, OS and runtime versions that produced
it. Estimated, extrapolated, or plausible-sounding figures are not acceptable in any file.
**Where a value is not yet measured, write `TBD`.**

Results that make this project look bad are published exactly as prominently as results that
make it look good. A negative result with numbers is a result.

## Fixtures and examples

Fixtures are **synthetic and invented**, and this is a hard rule rather than a preference:
the reconciliation cases this project works on are financial records.

- No real people, businesses, addresses, account numbers, or ledger entries. Not an
  employer's, not a client's, not your own. Procedurally generated cases are both safer *and*
  better, because the ground truth is known by construction rather than inferred.
- Phone numbers, where an example needs one, take the form `+<country-code> 000 000 000`.
  Never a locale-plausible number: many countries reserve no range for fictional use, so a
  "made up" number can route to a real person. The same goes for national ID, licence and
  registration numbers.
- No credentials, keys, tokens, or connection strings, in any file, ever — including in an
  example that "obviously" would not work. If one has been committed, do not open an issue
  naming it; follow [`SECURITY.md`](SECURITY.md).

## Commits

Conventional Commits:

```
<type>(<scope>): <subject>
```

Types: `feat` `fix` `docs` `style` `refactor` `perf` `test` `chore`. Present tense,
lowercase type and scope, subject under 50 characters. The body explains **why**; the diff
already says what.

**Sign off every commit:**

```sh
git commit -s
```

That appends a `Signed-off-by:` line, certifying your contribution under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). There is **no
CLA** — the DCO is the whole of it, and an unsigned commit cannot be merged.

`Signed-off-by:` is the **only** trailer this project uses. Commit messages carry no others,
so that provenance in the history means exactly one thing and a reader never has to work out
which trailers are load-bearing.

Commit messages are public surface, permanently, and a tree sweep never sees them. They name
the change and its reasoning — not the tooling, the local paths, or the private systems that
happened to be involved in making it.

## Branches

**GitHub Flow.** `main` is always releasable. Every change rides a short-lived branch off
`main` and lands through a pull request; the branch is deleted on merge. There are no
long-lived integration branches, no `develop`, and no direct commits to `main`.

Branch names are `<type>/<short-description>`, using the same types as commits and
kebab-case for the description:

```
docs/adr-0002-base-model
feat/sealed-packet-generator
fix/token-budget-assertion
```

A branch name is public the moment it is pushed. It names the change, not the tooling or
the local paths involved in making it.

**`main` is merged into by rebase only.** Squash and merge commits are both disabled, and
that is a deliberate cost: a squash would be tidier to read and it is refused anyway,
because this project's history carries two things a squash destroys. One behaviour per
commit is the evidence for the test policy above — collapse a branch and the RED-then-GREEN
sequence becomes one commit that proves nothing about the order it was written in. And each
commit carries its own `Signed-off-by`, which is a per-commit certification; a squashed
commit's sign-off certifies a diff nobody signed off.

`main` is protected by a repository ruleset: no deletion, no force-push, linear history
required, and changes arrive by pull request. **Zero approvals are required** — this is a
solo repository and pretending otherwise would be the half-met checklist this file argues
against elsewhere. The substitute is stated in §How changes land: a linked decision record,
and a green run of the documented command once there is one. Review threads must be
resolved before merge, which is the part of review that still works with one maintainer.

The rules that cannot be waived by a maintainer in a hurry are the ones the ruleset
enforces: released history stays immutable because force-pushing `main` is refused by the
host, not because a policy asks nicely.

## Pull requests

**Every pull request names the ADR or RFC it implements or amends.** Put it in the
description: *implements RFC-0001*, *amends ADR-0001*.

If the honest answer is "none", the change is one of two things: outside the scope the PRD
fixes, or a design decision nobody has written down yet. In the second case, open the RFC
first — [`docs/rfcs/`](docs/rfcs/) exists so designs are argued before they are implemented,
and so someone reading this in five years finds the reasoning instead of guessing at it.

Keep a pull request to one behaviour.

## Changelog

A change a reader or user would notice is recorded in [`CHANGELOG.md`](CHANGELOG.md) under
`## [Unreleased]`, in the pull request that makes it. Format is
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/): ISO dates, and only the six
section types `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. It is written
by hand and never generated from `git log`.

Versioning will be [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html). The latitude rule 4
grants `0.y.z` releases is not used: a breaking change bumps MINOR and is listed under
`Changed` or `Removed`. A released version is immutable — a bad release is superseded by a
higher one and marked `[YANKED]`, never re-cut.

## Licensing

Consylr is MIT ([`LICENSE`](LICENSE)), decided in
[ADR-0001](docs/adrs/0001-mit-licence-and-public-repository.md). By signing off a commit you
agree your contribution is offered under that licence.

- **Every source file begins with an SPDX identifier as its first comment line** —
  `# SPDX-License-Identifier: MIT`, immediately after the shebang where there is one. One line,
  machine-readable, and it survives a single file being copied out of the tree.
  **Shell counts as source**, and so do the hook files in `.githooks/`, which carry no
  extension: that directory is exactly the kind of thing people copy between repositories, so
  the rule matters there at least as much as in product code. `check_spdx` enforces it for
  `*.py`, `*.sh` and everything under `.githooks/`.
- **No REUSE machinery** (`LICENSES/`, `.license` sidecars, `REUSE.toml`). That specification
  exists to disambiguate multi-licence trees; this is a single-licence repository with a root
  `LICENSE`, so the machinery would add files and buy no clarity. **The moment a second
  licence enters the tree, REUSE becomes mandatory in that same commit.**
- Every dependency's licence must be MIT/Apache/BSD-compatible. Check before adding it.
- Third-party algorithms are credited in the ADR that adopts them; a third-party snippet
  carries its own `SPDX-FileCopyrightText` at the point of use.
- **Model weights and datasets are licensed separately from this code**, and their terms do
  not follow from the repository's licence. They are recorded in `DATA_PROVENANCE.md`, which
  must exist before the first training run. The ADTC submission template is GPL-3.0; that
  governs the fork made from it, not this repository.

## How changes land, stated plainly

This project has one maintainer. That fact is not hidden behind process language, and the
substitutes it forces are written down here rather than left to inference.

A change lands when it carries **a linked decision record**, and — once there is code — a
green run of the documented command. Changes submitted from outside are reviewed by the
maintainer before merge. Changes authored by the maintainer are not reviewed by a second
person, and **this project does not claim peer review it did not have.**

The same directness applies to the practices commonly expected of an open-source project.
Adopting a standard that cannot be satisfied is worse than declining it, because a half-met
checklist reads as a met one:

| Practice | Status here |
|---|---|
| OpenSSF Scorecard `Code-Review` | **Not adopted.** One maintainer. The substitute is stated plainly: every change lands with a linked ADR or RFC. This project does not claim peer review it did not have. |
| OpenSSF Scorecard `Contributors` (3+ organisations) | **Not adopted.** Not achievable by decision, and not a property of the work. |
| CI / `CI-Tests` | **Deferred, with a date attached to a condition rather than a calendar:** the workflow lands in the commit that adds the first thing worth running, and it runs the same command this file documents. A workflow over an empty tree is a green tick that means nothing. |
| `Pinned-Dependencies`, `Token-Permissions` | **Adopted in advance of the workflow they govern.** When CI arrives, actions are pinned to full 40-character commit SHAs — a tag is mutable, so pinning to a tag is pinning to nothing — and `permissions: contents: read` sits at workflow top level with write scopes declared only on the job that needs them. |
| `Fuzzing` / OSS-Fuzz | **Not adopted.** The surface is local files parsed into an evidence packet. Revisit when the project parses an untrusted binary format. |
| `Signed-Releases` + SBOM | **Deferred, not declined.** Mandatory at the first tag: build-provenance attestation bound to the workflow run, and an SBOM published beside the artefact. There is nothing to sign before a release exists. |
| SAST | **Deferred with CI.** Adopted on the condition that findings get fixed rather than annotated away — a run whose findings are waived fails the criterion it claims to meet. |
| `CITATION.cff` | **Declined, for now.** Consylr is a product and a competition entry, not a citable research artefact: there is no paper, no dataset and no measurement to cite, and a citation file naming a work nobody can cite is a false signal rather than a courtesy. Reconsidered if the sealed evaluation produces a result worth citing on its own — at which point the file goes at the default-branch root, because anywhere else it silently does nothing. |
| REUSE full compliance | **Declined.** Single licence, root `LICENSE`. See §Licensing for the condition that reverses this. |
| Contributor Licence Agreement | **Not used.** The DCO (`git commit -s`) instead. |
| OpenSSF Best Practices badge enrolment | **Not enrolled.** The criteria are adopted on merit; displaying a badge is a separate act, not a goal. |

## Reporting problems

- **Defects and behaviour questions** — open an issue. For anything involving a measured
  number, include the architecture, OS and the run it came from; without those, a reported
  number cannot be attributed to a machine, which makes it unusable.
- **Proposals** — open a proposal issue. Design changes are argued as an RFC before they are
  built, and the issue is where the shape is agreed first.
- **Suspected vulnerabilities** — do not open an issue. Follow
  [`SECURITY.md`](SECURITY.md).
- **Conduct** — [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies to every space this
  project uses.
