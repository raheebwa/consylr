# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Semantic Versioning rule 4 permits a `0.y.z` release to break anything without notice.
This project does not take that latitude: before `1.0.0` as after it, a breaking change
bumps the MINOR version and is listed under `Changed` or `Removed`. "0.x, caveat emptor"
warns nobody.

This file is written by hand and is never generated from `git log`. A commit log records
how the work was done; a changelog records what changed for someone depending on the
project, and the two are not the same document.

## [Unreleased]

Nothing released yet. The first version heading appears when there is something worth
installing.

### Added

- `consylr.schema` — validation of model output against RFC-0001. The same validator is
  intended to ship in the product and to validate the training corpus, so that a corpus is
  not checked by a second implementation that only tests itself. It reports every violation
  rather than raising on the first.
- The residue rule as an executable check: a record is residue if and only if it appears in
  no match whose certainty is `supported` or `ambiguous`.
- Cross-output coherence checks: a `request` disposition must be covered by an `open` entry,
  and every disposed identifier must appear elsewhere in the output.
- Refusal of uncalibrated numeric certainty anywhere in an output.
- A test that executes every JSON example in RFC-0001 against the validator, so the
  specification and the code cannot drift apart silently.
- `pyproject.toml` with a PEP 639 licence expression, and `mise.toml` pinning the interpreter.
- Continuous integration, running the same commands `CONTRIBUTING.md` documents.

### Fixed

- The illustrative example in RFC-0001 violated the residue rule that RFC defines: a record
  named in `open` and in no match is residue, and the example omitted it from `residue`.
  Found by executing the examples rather than by reading them.
- RFC-0001 prescribed an answer for the empty packet that its own request-coverage invariant
  rejected. The invariant wins and the prescribed answer now carries an `open` entry: asking
  for evidence without recording what is needed is exactly the dangling disposition that rule
  exists to prevent, and it is likeliest on the packet where there is nothing else to say.
- RFC-0001 referred to a cap on its one free-text field without giving one. `need` is capped
  at 120 characters, because "capped" is not a rule a validator can enforce.
- RFC-0001 left the packet contract implicit, and a policy line span is a locator inside a
  document rather than an identifier of its own — a validator expecting packets to enumerate
  citable lines would reject every correctly-cited policy reference.

[Unreleased]: https://github.com/raheebwa/consylr/commits/main
