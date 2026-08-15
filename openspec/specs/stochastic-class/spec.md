# stochastic-class Specification

## Purpose

This is Reprolith's fifth model class: **stochastic (discrete-state, continuous-time) chemical
reaction-network models**, simulated by the Gillespie stochastic simulation algorithm (SSA). Unlike
the deterministic classes, a single trajectory is a random sample, so the reproducible result is a
*distribution* or a summary statistic (a mean, a variance, a stationary distribution), not one
curve. The class reuses the population/distributional oracle unchanged — its comparison is exactly
the distributional one — and specializes only the simulation (SSA) and the reproducible-sampling
discipline that keeps a stochastic reproduction deterministic.

The parking reason for this class ("weaker free oracle; revisit after the deterministic classes are
broad") is now discharged: four deterministic classes are self-validated, and the distributional
oracle needed to judge this class already exists.

## Requirements

### Requirement: Reproducible sampling makes a stochastic reproduction deterministic

A stochastic simulation is random, but a certificate SHALL still be byte-reproducible, so the
sampling is pinned, not left to chance.

#### Scenario: A pinned seed is part of the protocol

- **WHEN** a stochastic reproduction is run
- **THEN** the random seed (and the number of trajectories) is recorded as part of the claim's
  protocol, and re-running with the same seed and pin yields the identical summary statistics and
  the identical verdict
- **AND** the certificate's determinism invariant holds via the pinned seed exactly as the
  deterministic classes hold it via the pinned engine

### Requirement: Stochastic dossier shape

A stochastic dossier SHALL capture the elements that determine the network's stochastic dynamics.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `stochastic`
- **THEN** the dossier records the species with their initial molecule counts, each reaction's
  reactant/product stoichiometry and its mass-action rate constant, and the sampling protocol
  (duration, number of trajectories, seed) each claim holds under
- **AND** each element cites its source location

#### Scenario: A non-mass-action rate law is refused, not reinterpreted

- **WHEN** a reaction's kinetic law is not mass action — its rate expression is anything other than
  the rate constant times each reactant raised to its stoichiometry (a constant flux over a consumed
  reactant, a saturating or inhibitory rate, an order that disagrees with the stoichiometry)
- **THEN** ingestion refuses the model rather than reading the single rate parameter and running a
  fabricated mass-action propensity, so the SSA never certifies a network the artifact did not describe

### Requirement: Standard stochastic reproduction targets

The oracle for this class SHALL evaluate the results stochastic papers report, using the
distributional comparison, so a stochastic verdict is judged honestly against sampling noise.

#### Scenario: Summary-statistic reproduction

- **WHEN** a claim is a reported summary statistic of the ensemble (e.g. a mean or variance of a
  species count at a time, or at steady state)
- **THEN** the oracle simulates the pinned ensemble, derives that statistic, and compares it to the
  reported value within a declared tolerance wide enough to absorb finite-sample noise

#### Scenario: Distribution reproduction

- **WHEN** a claim is a reported distribution or percentile envelope of a species over time
- **THEN** the oracle compares the simulated ensemble's distribution to the reported one with the
  distributional (population) oracle, governed by its worst-matched band and qualified for its
  sampling dependence

### Requirement: Self-validation against analytically known stochastic results

Before this class's verdicts are trusted, the SSA SHALL be measured against systems whose
stochastic result is known in closed form — a non-circular ground truth that needs no external tool.

#### Scenario: Analytical agreement

- **WHEN** the SSA is run on a system with a known analytical stationary result (e.g. an
  immigration-death process, whose stationary distribution is Poisson with mean and variance equal
  to the immigration/death ratio)
- **THEN** the simulated ensemble's summary statistics agree with the closed-form values within the
  declared finite-sample tolerance
- **AND** a disagreement is treated as a defect to investigate, not silently accepted
