# kinetic-class Specification

## Purpose

This is Reprolith's third fully supported model class: **generic systems-biology (kinetic ODE)
models** — signaling, metabolic, and gene-regulatory reaction networks. Unlike the constraint-based
class, its oracle is *not* new: a kinetic model's reproducible result is a species time-course, the
same kind of result the PK/PD class reproduces. So this class exists to demonstrate the time-course
contract is general, not PK/PD-specific. It reuses the PK/PD curve oracle, simulation engine,
certificate, and catalog unchanged, specializing only in the breadth of networks it covers.

## Requirements

### Requirement: Time-course reproduction target

A kinetic reproduction SHALL target a species time-course and judge it with the shared curve
oracle, so a kinetic verdict is produced by the same contract as a PK/PD curve verdict.

#### Scenario: A species trajectory is the claim

- **WHEN** a kinetic model is certified against a reported species time-course
- **THEN** the model is simulated under the pinned engine over the claim's time span at the claim's
  sample points, and the trajectory is compared to the reference with the normalized-distance curve
  oracle within a declared tolerance
- **AND** the resulting assessment is the same `ClaimAssessment` the certificate consumes, carrying
  its method, discrepancy, tolerance, and the inescapable scope flag

#### Scenario: An oscillator's period is the claim

- **WHEN** a kinetic model oscillates and the claim is its reported period or peak-to-trough height
- **THEN** the quantity is read off the run — the period from the mean crossings the trajectory
  makes, interpolated between samples — and judged by the shared scalar comparison, because a curve
  distance over a limit cycle is dominated by phase and a model reproducing the biology while
  drifting a percent in period reads as a total failure
- **AND** the window the claim states is honoured, since "after transients" is how a source says
  which part of the run its period was measured over
- **AND** a run that completes no cycle is abstained on rather than being given a period it does not
  have, and a period the sampling grid has not settled is abstained on by the same convergence check
  every grid-dependent metric passes

#### Scenario: Solver tolerance and determinism are preserved

- **WHEN** a kinetic time-course is reproduced
- **THEN** the verdict is deterministic (same model and reference under the same pin yield the same
  verdict) and the applied tolerance is recorded with its provenance, exactly as other classes
  declare theirs

### Requirement: Generalization is demonstrated, not assumed

Adding this class SHALL reuse the shared engine contracts unchanged, and any contract that cannot
absorb it SHALL be surfaced rather than forked.

#### Scenario: Shared contracts carry the new class

- **WHEN** a kinetic entry moves through the pathway
- **THEN** it uses the same catalog lifecycle, dossier/claims model, curve oracle, certificate
  format, and scope flag as the PK/PD class, tagged only as its own model class
- **AND** if a shared contract cannot express something this class needs, that gap is raised as a
  change to the shared spec, not worked around inside this class

### Requirement: Self-validation against independent reproduction

Before this class's verdicts are trusted, the pathway SHALL be measured against models whose
reproducibility is independently established.

#### Scenario: Cross-tool blind agreement measurement

- **WHEN** the kinetic pathway is evaluated on curated models whose reference trajectory is produced
  by an independent simulator (one sharing no implementation with the pinned engine)
- **THEN** Reprolith produces verdicts blind to the reproducibility label and reports agreement,
  disagreement, and the nature of each disagreement
- **AND** a disagreement is treated as a defect to investigate, not silently accepted

#### Scenario: Diversity of dynamics is covered

- **WHEN** the self-validation set is assembled
- **THEN** it spans distinct dynamic regimes (for example signaling, gene-regulatory, metabolic,
  cell-cycle, circadian, and calcium networks), so the class is shown general rather than tuned to a
  single model
