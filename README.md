# Consylr

**A compact offline model that reconciles small packets of conflicting enterprise records,
identifies supported exceptions and missing evidence, and produces traceable operational
dispositions — without sending sensitive source data to a hosted model.**

Status: **pre-code.** Docs first, by design. Nothing here is built yet.

⚠️ The name is cleared at knock-out level only — no registry clearance has been run.
See [ADR-0002](docs/adrs/0002-keep-the-name-consylr.md) for the residual risk.

## Start here

| If you want… | Read |
|---|---|
| To start working | **[docs/HANDOFF.md](docs/HANDOFF.md)** |
| What we're building and why | [docs/prd/prd.md](docs/prd/prd.md) |
| Why it's built this way | [docs/adrs/](docs/adrs/) |
| How each piece works | [docs/rfcs/](docs/rfcs/) |
| The evidence underneath all of it | [docs/research/](docs/research/) |
| What a term means | [docs/glossary.md](docs/glossary.md) |

## The immediate vehicle

**Africa Deep Tech Challenge 2026 — "The Laptop LLM Challenge."**
Gate 1 submission closes **2026-08-24 23:45 PDT** (≈ **2026-08-25 09:45 EAT**).
Grand prize USD 8,000 (UGX 29,600,000) + 6-month residency; USD 4,000 second;
USD 3,000 third; USD 1,500 Best African Use Case.
Scoring: **50% accuracy/quality · 30% throughput · 20% memory efficiency**, thermal penalty,
hard 7 GB peak-RSS ceiling.

Gate 2 runs 2026-09-08 → 09-29 (reproducibility + technical defence).
Gate 3 final live defence 2026-10-17.

> [!IMPORTANT]
> **This is not the submission repo.** ADTC Gate 1 requires a public repository generated
> from the *official ADTC template*, with an idempotent `download_model.sh` and no weights
> committed. This repo is where the product and its reasoning live; the submission repo is
> a separate artefact produced from it. See [docs/HANDOFF.md](docs/HANDOFF.md).

## The one-line boundary

> We don't use a language model where exact software is already perfect.
> We use it where reconciliation turns into evidence judgement.

Parsing and verification are deterministic. Correspondence and interpretation inside a
bounded evidence packet are model-led. Humans authorise consequential actions.

## Scope discipline

**In scope:** 2–20 records across two sides; one-to-one, one-to-many and many-to-one
correspondence; misspelled names; mangled references; timing/cut-off drift; fees and
withholding described in evidence; reversals; duplicates; partial payments; batched vs
itemised transactions; missing records; cause classification from supplied policy; explicit
ambiguous / no-match conclusions.

**Out of scope, and never claimed:** brute-force search over millions of rows; maintaining a
general ledger; unconstrained many-to-many optimisation at scale; fraud attribution;
unsourced causal claims; autonomous posting of adjustments; generation as the authority for
arithmetic.

## Contributing

Conventions, the commit and sign-off rules, and how changes land are in
[CONTRIBUTING.md](CONTRIBUTING.md). Conduct is covered by
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). For a suspected vulnerability, do not open an
issue — follow [SECURITY.md](SECURITY.md).

## Licence

MIT — see [LICENSE](LICENSE) and
[ADR-0001](docs/adrs/0001-mit-licence-and-public-repository.md).

The ADTC submission template is GPL-3.0, which governs the fork made from it rather than
this repository. Base-model and dataset licences are tracked separately in
`DATA_PROVENANCE.md`, to be created before any training run.
