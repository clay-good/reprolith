# spatial-class Specification

## Purpose

This is Reprolith's sixth model class: **spatial reaction-diffusion models** — partial differential
equations over space and time, the machinery behind morphogen gradients, tumour-growth fronts, and
tissue-scale drug distribution. Its reproducible result is a **concentration profile over space**
(or a derived spatial summary such as a gradient length or a front position), so it reuses the curve
oracle unchanged and specializes only the simulator: a deterministic finite-difference solver.

The parking reason ("different simulation machinery and a weaker free oracle; revisit after the
deterministic classes are broad") is discharged for the tractable, checkable slice this class
targets: 1-D diffusion has an exact analytical solution, which is the non-circular ground truth for
its self-validation.

## Requirements

### Requirement: Deterministic spatial simulation

The solver SHALL be deterministic and numerically stable, so a spatial certificate is
byte-reproducible under its pinned discretization.

#### Scenario: Discretization is part of the protocol

- **WHEN** a spatial reproduction is run
- **THEN** the spatial step, time step, and diffusivity are recorded as part of the claim's
  protocol, and re-running with the same discretization yields the identical profile and verdict
- **AND** a discretization that violates the solver's stability condition is rejected with a clear
  error rather than producing a diverging profile

### Requirement: Spatial dossier shape

A spatial dossier SHALL capture the elements that determine the spatial dynamics.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `spatial`
- **THEN** the dossier records the species and their diffusivities, the reaction terms coupling
  them, the spatial domain and boundary conditions, and the initial spatial profile each claim holds
  under
- **AND** each element cites its source location

### Requirement: Standard spatial reproduction targets

The oracle for this class SHALL evaluate the spatial results papers report, using the curve oracle.

#### Scenario: Concentration-profile reproduction

- **WHEN** a claim is a reported concentration profile over space at a stated time
- **THEN** the oracle simulates the reconstructed model to that time and compares the predicted
  spatial profile to the reference with the shared curve-distance comparison and its tolerance

### Requirement: Self-validation against an analytically known spatial result

Before this class's verdicts are trusted, the solver SHALL be measured against a spatial system
whose solution is known in closed form — a non-circular ground truth needing no external tool.

#### Scenario: Analytical agreement

- **WHEN** the solver simulates pure 1-D diffusion of a Gaussian profile
- **THEN** the simulated profile agrees, within the declared tolerance, with the exact analytical
  solution (a Gaussian whose variance grows by twice the diffusivity times the elapsed time)
- **AND** a disagreement is treated as a defect to investigate, not silently accepted
