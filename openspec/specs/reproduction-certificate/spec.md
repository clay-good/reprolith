# reproduction-certificate Specification

## Purpose

The reproduction certificate is Reprolith's deliverable: a signed, machine-readable,
human-readable record of whether a paper's model reproduces its own claims, and why. It is
the artifact an agent consumes, a curator trusts, and an author is held to. Its defining
property is honesty — it qualifies every verdict and never overstates.

## Requirements

### Requirement: Certificate as the durable record of an attempt

Every completed verification SHALL produce exactly one certificate that stands on its own,
readable without access to Reprolith's internals.

#### Scenario: Self-contained certificate

- **WHEN** a verification run completes for an entry
- **THEN** a certificate is produced containing: the paper identity, the per-claim verdicts,
  the reconstruction provenance, the assumptions made, the engine and tolerance pins, and
  the overall summary
- **AND** the certificate is rendered in both a machine-readable form and a human-readable
  form derived from the same data

#### Scenario: Reproducible certificate identity

- **WHEN** the same inputs and pins are certified again
- **THEN** the resulting certificate is byte-identical except for run metadata (timestamps,
  actor), and it references the prior certificate it supersedes or confirms

### Requirement: Per-claim, qualified verdicts

The certificate SHALL report verdicts at claim granularity and SHALL never round a mixed
result up to a clean pass.

#### Scenario: Overall verdict derivation

- **WHEN** claims receive mixed verdicts
- **THEN** the overall verdict is one of `reproduced`, `partially-reproduced`,
  `not-reproduced`, or `blocked`, derived by an explicit, stated rule from the per-claim
  verdicts
- **AND** the number of claims at each verdict is shown, so `partially-reproduced` is never
  mistaken for full reproduction

#### Scenario: Assumption-qualified verdicts

- **WHEN** a claim reproduced only because of a load-bearing Reprolith assumption
- **THEN** its verdict is marked as assumption-qualified and the assumption is named in the
  certificate
- **AND** the overall verdict cannot be an unqualified `reproduced` if any counted claim is
  assumption-qualified

### Requirement: Provenance and citation integrity

Every quantitative statement in a certificate SHALL trace to a source.

#### Scenario: Traceable claims and parameters

- **WHEN** the certificate references a claim, parameter, or reference value
- **THEN** it cites the source location it was extracted from and, where applicable, the
  reference data used for comparison
- **AND** a value Reprolith supplied is labelled as Reprolith's, distinct from the paper's

### Requirement: Explicit, unavoidable scope statement

Every certificate SHALL carry a scope statement that prevents its misuse.

#### Scenario: Reproducibility is not correctness or clinical validity

- **WHEN** a certificate is produced
- **THEN** it carries a machine-readable and human-readable scope flag stating that the
  certificate attests only to computational reproducibility of the paper's own results, and
  makes no claim about biological correctness, model appropriateness, or clinical use
- **AND** this flag cannot be omitted or emptied

### Requirement: Structured "what was missing" report

For anything short of full reproduction, the certificate SHALL tell the field exactly what
would be needed to close the gap.

#### Scenario: Actionable gap list

- **WHEN** an entry is `blocked`, `not-reproduced`, or `partially-reproduced`
- **THEN** the certificate includes a structured list of the specific missing or ambiguous
  inputs, each tied to the claim it blocks
- **AND** the list is precise enough that an author or curator could act on it directly

### Requirement: Versioning and supersession

Certificates SHALL form an auditable history as models, tolerances, and engines evolve.

#### Scenario: Re-certification under new pins

- **WHEN** an entry is re-verified under a new engine version or revised tolerance
- **THEN** a new certificate is issued that links to the ones it supersedes and states what
  changed
- **AND** prior certificates remain retrievable rather than being overwritten
