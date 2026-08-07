# ode-pkpd-class Specification

## Purpose

This is Reprolith's first fully supported model class: **compartmental ODE
pharmacokinetic/pharmacodynamic (PK/PD) models**. It specializes the general engine
(catalog, ingestion, reconstruction, oracle, certificate) with the concrete structure,
reproduction targets, tolerances, and failure modes of PK/PD modeling. It is the narrow,
deep pathway we test → note → iterate against before generalizing to other classes.

## Requirements

### Requirement: PK/PD dossier shape

An ODE PK/PD dossier SHALL capture the elements that determine whether a concentration or
effect prediction can be reproduced.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `ode-pkpd`
- **THEN** the dossier records the compartment structure, the rate expressions linking
  compartments, absorption terms (e.g. first-order, zero-order, lag, transit), elimination
  terms (linear or saturable/nonlinear), and any PD link model (e.g. direct-effect,
  effect-compartment, indirect-response/turnover, or target-mediated disposition) with its
  response equation
- **AND** each element cites its source location

#### Scenario: Parameters and dosing

- **WHEN** the dossier is built
- **THEN** it records the model parameters with values and units (e.g. clearances, volumes,
  rate constants, effect parameters), the initial conditions, and the full dosing protocol
  (route, amount, timing, repetition)
- **AND** covariate relationships that change parameters for a described subject or scenario
  are recorded as part of the protocol

#### Scenario: Parameterization is normalized without losing the original

- **WHEN** a paper states the model in one parameterization (e.g. volumes and clearances)
  where another is equivalent (e.g. micro-rate constants)
- **THEN** the dossier records the stated parameterization and, where it converts, records
  the conversion and keeps the original
- **AND** an ambiguous or internally inconsistent parameterization is recorded as a gap

### Requirement: Standard PK/PD reproduction targets

The oracle for this class SHALL evaluate the reproduction targets PK/PD papers actually
present, so verdicts match how the field judges a model.

#### Scenario: Curve reproduction

- **WHEN** a claim is a concentration-time or effect-time profile
- **THEN** the oracle simulates the reconstructed model under the claim's protocol and
  compares the predicted profile to the reference over the stated time span
- **AND** the comparison reports curve-distance against the claim's tolerance

#### Scenario: Derived PK/PD metric reproduction

- **WHEN** a claim is a reported summary metric (e.g. peak concentration, time to peak,
  exposure/area, steady-state level, half-life, or an effect metric)
- **THEN** the oracle derives that metric from its simulation using the metric's standard
  definition and compares it to the reported value within tolerance
- **AND** the definition used for the metric is recorded so the comparison is auditable

#### Scenario: Population figure reproduction

- **WHEN** a claim is a population figure (a percentile envelope, prediction interval, or a
  reported inter-individual variability metric) rather than a single-subject trajectory
- **THEN** the oracle compares the reported distribution to the simulated population's
  distribution under the class distributional tolerance, judging a percentile envelope by its
  worst-matched band and a variability scalar by relative error
- **AND** the verdict is assumption-qualified to reflect its dependence on the variability
  model and sampling, per the simulation-oracle distributional contract

### Requirement: Class-default tolerances

This class SHALL define sensible default tolerances so verdicts are consistent across papers,
while allowing principled overrides.

#### Scenario: Default tolerance applies

- **WHEN** no paper-stated precision or reviewer override exists for a PK/PD claim
- **THEN** the oracle applies the documented class-default tolerance for that claim type
  (curve versus scalar metric)
- **AND** the certificate records that the default was used

#### Scenario: Principled override

- **WHEN** the paper states a precision, or a reviewer sets one with a rationale
- **THEN** that tolerance is used instead and its provenance is recorded
- **AND** an override without a rationale is not accepted

### Requirement: Known PK/PD failure modes are first-class

The oracle SHALL recognize the recurring reasons PK/PD reproductions fail, so its root causes
are specific and useful.

#### Scenario: Catalogued root causes

- **WHEN** a PK/PD claim is `partial` or `failed`
- **THEN** the root cause is selected from a maintained set that includes at least: unit or
  scaling mismatch, ambiguous or missing parameterization, unstated initial or steady-state
  condition, dosing-protocol ambiguity, absorption-model ambiguity, and apparent
  manuscript-internal inconsistency
- **AND** a failure that fits none of these is recorded as uncategorized and flagged for the
  failure-mode set to be extended

#### Scenario: Sensitivity note for load-bearing PK/PD assumptions

- **WHEN** a reproduced PK/PD claim depended on a load-bearing assumption (e.g. an assumed
  initial condition or an inferred unit)
- **THEN** the certificate notes how sensitive the verdict is to that assumption
- **AND** the verdict is assumption-qualified per the certificate contract

### Requirement: Self-validation against known PK/PD reproducibility

Before this class's verdicts are trusted, the pathway SHALL be measured against entries whose
reproducibility is independently known.

#### Scenario: Blind agreement measurement

- **WHEN** the PK/PD pathway is evaluated on a set of catalog entries carrying ground-truth
  reproducibility labels
- **THEN** Reprolith produces verdicts without access to the labels and reports agreement,
  disagreement, and the nature of each disagreement
- **AND** a disagreement is treated as a defect to investigate in the test → note → iterate
  loop, not silently accepted
