# model-reconstruction Specification

## Purpose

Reconstruction turns a dossier into a **runnable reconstruction**: a model in open standard
formats, paired with an executable simulation recipe, that a registered engine can run
without further human input. Reconstruction is where any gap in the dossier must be closed —
and every closure is recorded as an explicit, attributable assumption.

## Requirements

### Requirement: Standard-format, engine-runnable output

Reconstruction SHALL emit artifacts that conform to open standards and run on a registered
simulation engine, so results are portable and independently checkable.

#### Scenario: Bundled reconstruction

- **WHEN** reconstruction succeeds for an entry
- **THEN** it produces a model in an open format (e.g. SBML or CellML), a simulation recipe
  that specifies how to run each claim's scenario, and a bundle that packages them with
  their metadata
- **AND** the bundle validates against the relevant format schemas before it is accepted

#### Scenario: Recipe covers every targetable claim

- **WHEN** the dossier lists targetable claims
- **THEN** the simulation recipe defines, for each one, the exact run (inputs, protocol,
  outputs, and time span or conditions) needed to produce the quantity the claim asserts
- **AND** a claim that cannot be given a runnable scenario is recorded as non-reconstructable
  with the reason, rather than omitted silently

### Requirement: Assumptions are explicit and load-bearing-flagged

Every value or structural choice not directly present in the dossier SHALL be recorded as an
assumption, and its influence on the outcome SHALL be discoverable.

#### Scenario: Recording an assumption

- **WHEN** reconstruction supplies a value, unit, initial condition, or structural detail to
  close a dossier gap
- **THEN** it records the assumption, the candidate it chose, the alternatives considered,
  and the basis for the choice
- **AND** the assumption is attributed to Reprolith, never presented as the paper's own value

#### Scenario: Flagging a load-bearing assumption

- **WHEN** an assumption plausibly changes whether a claim reproduces
- **THEN** it is flagged load-bearing, so the certificate and reviewers can see that the
  verdict depends on Reprolith's own choice rather than on the paper
- **AND** the eventual certificate cannot report an unqualified `reproduced` verdict for a
  claim whose reproduction rests on a load-bearing assumption; such a verdict is qualified

### Requirement: Prefer and verify existing artifacts

When the paper ships a model, reconstruction SHALL use it rather than rebuild from scratch,
but SHALL still confirm it is runnable.

#### Scenario: Adopting a shipped model

- **WHEN** the dossier includes a valid existing model artifact
- **THEN** reconstruction may adopt it as the model, adding only the simulation recipe and
  any missing run metadata
- **AND** the certificate records that the model was author-supplied, distinguishing this
  from a Reprolith-rebuilt model

#### Scenario: Shipped model does not match the dossier

- **WHEN** an adopted artifact disagrees with the paper's stated equations or parameters
- **THEN** the discrepancy is recorded and surfaced, and reconstruction does not silently
  trust the artifact over the manuscript

### Requirement: Determinism and pinning

A reconstruction SHALL be reproducible by anyone who has the bundle and the pinned engine.

#### Scenario: Engine and version pin

- **WHEN** a reconstruction is prepared for verification
- **THEN** it pins the engine identity and version (and algorithm selection) it is intended
  to run under
- **AND** running the pinned bundle again yields the same outputs within the declared
  numerical tolerance, or the nondeterminism is declared and bounded
