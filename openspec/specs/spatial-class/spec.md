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

#### Scenario: A run that cannot advance is refused, not reported

- **WHEN** a spatial run is asked for with a discretization whose per-step update cannot change the
  profile — a zero or subnormal time step, a zero diffusivity, or a grid spacing so large the
  diffusion number underflows — or with a negative diffusivity, decay, or grid spacing
- **THEN** the run is refused with an error naming the offending input, rather than returning the
  initial profile as if it were a result
- **AND** a spatial claim is refused unless it evolves the profile by at least one step, because a
  reported profile near the initial condition would otherwise certify a simulation that never ran

### Requirement: Spatial dossier shape

A spatial dossier SHALL capture the elements that determine the spatial dynamics.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `spatial`
- **THEN** the dossier records the species and their diffusivities, the reaction terms coupling
  them, the spatial domain and boundary conditions, and the initial spatial profile each claim holds
  under
- **AND** each element cites its source location

#### Scenario: Reading a shipped spatial model file

- **WHEN** a paper ships its model in the standard spatial interchange format (SBML Level 3
  `spatial`)
- **THEN** ingestion reads what this class solves — the Cartesian domain's stated extent, one
  isotropic diffusion coefficient per spatial species, each species' uniform initial concentration,
  and the first-order decay of a species where the file states one — and the resulting dossier
  records the domain as stated rather than as a gap, since the artifact ships it
- **AND** anything the solver cannot honour is refused by name: a non-Cartesian or higher-
  dimensional geometry, a stated domain shape or more than one domain, an anisotropic coefficient,
  a field-valued initial condition or one the model's own math overrides, a spatial species with no
  coefficient or one the model holds fixed, a prescribed non-zero flux across the boundary, more
  than one kind of boundary condition in one file, an
  advection term, a parameter standing for a coordinate, and any reaction that is not a first-order
  decay — each of these read and ignored would produce a profile from a
  model nobody wrote, with no sign that it happened
- **AND** a boundary condition the solver *does* run — a zero-flux wall or a wall held at a fixed
  value — is carried through to the run rather than refused, so the model is evolved under the wall
  its own file states

### Requirement: Standard spatial reproduction targets

The oracle for this class SHALL evaluate the spatial results papers report, using the curve oracle
for reported profiles and the scalar comparison for the length scales papers state as numbers.

#### Scenario: Decay-length reproduction

- **WHEN** a claim is a reported decay length of a morphogen gradient
- **THEN** the oracle runs the gradient to steady state, fits the length over the grid window the
  claim states, and compares it to the reported value with the shared scalar comparison
- **AND** the certificate records every input the number turns on — the source, the diffusivity,
  the degradation rate, the discretization, and the fitting window — since each moves the result
- **AND** the run carries no boundary assumption: a fixed source at one end and a zero-flux far
  field are the gradient model itself rather than a wall this engine chose in the absence of one

#### Scenario: Front-speed reproduction

- **WHEN** a claim is a reported invasion or growth-front speed
- **THEN** the oracle advances the front through a settling window and then a measuring window,
  takes the speed from the distance between two front positions rather than from the initial
  condition, and compares it to the reported value with the shared scalar comparison
- **AND** the certificate reports how much that speed is still changing over a further identical
  window, because a Fisher-KPP front approaches its asymptotic speed only logarithmically and a
  reader cannot otherwise tell a still-converging measurement from a converged one
- **AND** it reports how much the speed moves when the time step is halved, since that is a
  different question with a different answer: on this class's own configuration the run is settled
  to 0.2% and the step is worth 2.4% of a 4.2% deficit, so a reader who had only the first number
  would attribute the whole of it to the front
- **AND** a front that has run out of domain abstains, saying so — past the wall the distance
  travelled is the domain's length rather than the model's speed, and reporting that as a front
  that never existed would send a reader after the wrong cause

#### Scenario: Pattern-wavelength reproduction

- **WHEN** a claim is a reported Turing pattern wavelength
- **THEN** the claim names one of the reaction families this class implements and states its
  parameters, rather than supplying a reaction function, so the number can be re-derived from the
  certificate; a family the class does not implement is refused by name rather than approximated
  by a neighbouring one
- **AND** the oracle grows the pattern from a broadband seed on every admissible mode, measures the
  dominant mode of the activator field, and compares the wavelength it selects — not the one linear
  stability predicts — to the reported value, recording the prediction beside it, since the
  saturated pattern and the linearization can select different modes
- **AND** the reading is confirmed over a further window and abstains if the dominant mode changed
  across it, because the selected mode moves while the pattern is still growing
- **AND** a domain whose neighbouring measurable wavelengths are further apart than the width the
  claim is judged at abstains, saying so: wavelength is quantized to 2L/m there, and a pass and a
  fail would be the same measurement
- **AND** a claim that states its own wall is run under it and carries no boundary assumption;
  where it states none the run carries a load-bearing one — unlike a gradient's, whose walls are
  the model — because the admissible modes, and therefore the set of measurable wavelengths,
  follow from the wall
- **AND** what that wall costs is measured rather than asserted: the same grid is re-run under the
  other wall this solver implements and the certificate reports what it measured there, including
  when the answer is that it could measure nothing, since the two walls admit different mode sets

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
