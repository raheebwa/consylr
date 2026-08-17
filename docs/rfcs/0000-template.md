# RFC-0000 — template

- **Status:** draft | accepted | implemented | withdrawn
- **Date:** YYYY-MM-DD
- **Depends on:** ADR-XXXX

## Summary

One paragraph: what this component does and where its boundary is.

## Interface

The contract another part of the system codes against — schema, CLI signature, file format.
Be exact. Ambiguity here becomes a defect later.

## Behaviour

How it behaves, including the cases that are easy to get wrong: empty input, ambiguity,
conflicting evidence, missing evidence, adversarial input.

## What it must refuse to do

Explicit non-goals and refusals. For this project the refusals are load-bearing — a
component that guesses when it should abstain is broken even if its output looks right.

## Verification

How we know it works. Name the test families and the thresholds. "Looks correct" is not
verification.

## Open questions

Numbered, so they can be closed by reference.
