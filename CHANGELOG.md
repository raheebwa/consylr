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
- `consylr.budget` — the token-budget assertion. It rejects rather than warns, counts with a
  tokeniser the caller supplies rather than a character heuristic, and measures the rendered
  prompt rather than the packet before templating. Headroom being eaten is reported separately
  from the packet cap being exceeded, because they are different mistakes with the same symptom.
- `consylr.quota` — the two quota constraints. Certainty allocation and family coverage are
  checked separately, since certainty is a property of a case rather than of a family, and a
  corpus that cannot satisfy its plan is refused before it is built rather than after.
- Planted-failure tests on both gates: an over-budget prompt the check must reject, and an
  unsatisfiable plan the build must refuse. A gate that cannot fail is not a gate.
- `consylr.templates` — scenario templates as data files with a stable id, and the two notions
  of identity the grouped split rests on. Content identity, with the declared id excluded, so
  that one scenario committed under two ids is reported as the alias it is. Structural identity,
  taken over everything a paraphrase may not touch, so that two templates one rewording apart
  are reported as one scenario.
- `consylr.split` — the grouped split. Roles are separated by scenario template and never by
  row, the assignment draw is keyed on structural identity so an alias cannot straddle the
  boundary, and a corpus is checked against templates re-read from disk rather than against the
  identities the corpus records about itself.
- `consylr.violation` — one violation type for every gate, so that rejections from the schema,
  the budget, the quota and the split can be reported as one list.
- A rejection may name the case it came from, which RFC-0003 requires of a corpus-wide audit.
- `consylr.prompt` and the frozen prompt template it loads. The profiler applies no chat template
  of its own, so this artefact is the whole of the model's interface: it is pinned by digest,
  rendered by every surface, and changing it invalidates the corpus built against it. The packet
  is rendered first and the instructions last, because the harness left-truncates.
- `consylr.money` — one answer to how an amount is written, shared by the generator that writes
  packets and the identity model that reads them.
- `consylr.cases` — one case built from one template by applying a named deformation, so the
  correct answer is a by-product of the construction rather than a judgement made afterwards.
  All fourteen families of the frozen taxonomy have one. Every case is put to the validator
  that ships in the product before it is emitted.
- `budget.check_packet` — the packet against its own allowance, separate from the rendered
  prompt against the prompt cap. They are different strings against different caps.

### Changed

- `packet_over_budget` is now `prompt_over_budget`, and `Budget` carries a `template_overhead`.
  RFC-0003 sizes the packet and asserts on the rendered prompt; those are different strings, and
  the cap now applies to the rendered one with the wrapper declared rather than assumed away.
- A `Template` is now frozen in more than name: its body is deep-copied and both fingerprints
  are computed once, and equality covers the content rather than the declared id alone.
- Loading templates fails on a missing directory, an empty one, or a file that is not a
  `.json` template, where each previously produced an empty list.

### Fixed

- The paraphrase-invariant identity the grouped split rests on was computed over field names
  belonging to no template the generator can build, so it stripped nothing and equalled the
  exact identity. One scenario committed twice, one rewording apart, was split across the
  training and evaluation roles with every check passing — the failure that raises measured
  accuracy rather than lowering it. The identity tests had their own fixture in a shape the
  builder refuses, which is why they were green; there is now one fixture, in the shape the
  product consumes, and a test that the fixture is something the generator can build.
- The near-duplicate report inverted under scale: a fourth copy of one scenario silenced a
  defect that three had raised.
- The grouped split accepted any string as a role, including none at all, and both of its leak
  checks were unreachable on a corpus holding a single role. It also could not distinguish a
  corpus from its exact inverse, never validated `holdout_share`, and silently collapsed two
  templates that declared one id.
- `scenario_in_two_roles` was raised for every template whose own rows straddled the boundary,
  inflating a leak count with mistakes that were not leaks.
- The case builder measured the packet against the cap for packet-plus-wrapper, so declaring a
  template overhead loosened the budget gate by exactly that amount.
- A template record carrying its own identifier overrode the one the packet assigns by side and
  position.
- The quota checker counted the certainty allocation and family coverage over the same rows
  without a cross-check, so a `cause_not_established` case labelled `supported` satisfied both
  at once and a corpus fifteen points short of its supported floor passed clean. That family's
  correct answer is ambiguous or unsupported, so such a row is a mislabel; it is now reported
  and excluded from the supported count.
- The packet cap was enforced against the rendered prompt, so a generator honouring the packet
  size RFC-0003 states had every case rejected.
- No threshold in either gate was held by a test. Both edges of every band are pinned now: the
  limit, which passes, and one case past it, which does not.
- A prompt overrunning the context reported a negative remainder rather than an overrun.
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
