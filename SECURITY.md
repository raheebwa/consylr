# Security Policy

## Supported versions

Nothing has been released. This repository is pre-code: it holds the product definition,
the decision records and the evidence underneath them. There is no installable artefact, so
there is no version to support.

| Version | Security fixes |
|---|---|
| No release exists | — |
| Default branch | Not a supported artefact |

When a first version ships, this table is replaced with a real one and the policy becomes:
[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html), fixes in a new version,
listed under `Security` in [`CHANGELOG.md`](CHANGELOG.md), no long-term-support branch and
no backporting.

Until then, the reportable surface is the contents of this repository — see **Scope**.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting:**
[open a draft advisory](https://github.com/raheebwa/consylr/security/advisories/new).
The same form is reachable from the repository's **Security** tab under
**Report a vulnerability**. Either route opens a private draft visible only to you and the
maintainer.

**Do not open a public issue, pull request, or discussion for a suspected vulnerability.**
A public report is a public disclosure.

Reports are received privately through GitHub rather than by email. A published address
attracts more automated noise than reports, and gives no way to attach a draft advisory to
the fix.

A useful report includes:

- what the defect is, and the commit it is present in;
- the smallest input or sequence that triggers it;
- the architecture and OS you observed it on;
- what an attacker gains, in your assessment.

## What to expect

| Stage | Window |
|---|---|
| Acknowledgement that the report was received | 5 working days |
| Initial assessment — accepted, needs more information, or out of scope | 10 working days |
| Fix released, or a stated plan with dates if the work is larger | 90 days from acknowledgement |

This project is maintained by one person, and these windows are what one person can hold to
without a rota. A shorter window that is routinely missed is worse than a longer one that is
met, because a reporter deciding when to disclose needs a date that means something. If a
window is going to be missed, you will be told in the advisory thread rather than left
waiting.

Reporters are credited by the name they ask to be credited by, or not at all if they prefer.

## Scope

This project's central claim is that a compact model reconciles sensitive enterprise records
**without sending source data to a hosted model**. That claim is a security property, and
what counts as a vulnerability here follows from it.

**In scope:**

- **Anything that breaks the offline property.** A network call reachable at inference time,
  from this project's code or from a dependency it pulls in, is a vulnerability and not a
  performance note. The same applies to telemetry of any kind.
- **Leaking record contents outside the process** — to a log, to disk in an unexpected
  location, or over any connection.
- Code execution, path traversal, or unintended file writes triggered by an evidence packet,
  a policy file, a fixture, or configuration.
- Unsafe deserialisation anywhere in the load path, model artefacts included.
- Unbounded resource consumption reachable from ordinary input.
- Fetching model weights over an unauthenticated or unverified channel, or accepting an
  artefact whose integrity is not checked.
- **A credential, key, or real personal or business record committed to this repository.**
  Report it privately; do not open an issue naming it.

**Out of scope:**

- Vulnerabilities in third-party dependencies themselves. Report those upstream, and tell us
  as well if this project is affected.
- Vulnerabilities in the pretrained base models, which are third-party artefacts fetched at
  setup and never redistributed here. Report those to their publisher.
- Anything requiring an attacker who already controls the machine or the environment. The
  project trusts the process it runs in.
- **Model output being wrong.** A wrong reconciliation, a missed exception, or a bad
  disposition is an ordinary defect and belongs in the issue tracker, in public, where it
  can be discussed and measured. This includes prompt-shaped input that produces a poor
  answer.
  The exception is the case that *is* a security defect: output that reveals data from
  outside the evidence packet it was given.
- **A model failing to abstain.** Abstention is a trained behaviour with a measured rate,
  not a boundary an attacker crosses. It is tracked as accuracy, in the open.
