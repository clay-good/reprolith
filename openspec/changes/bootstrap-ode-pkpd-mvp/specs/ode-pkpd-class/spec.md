# ode-pkpd-class (delta: bootstrap-ode-pkpd-mvp)

## ADDED Requirements

### Requirement: The fence is the reproduction method, not the model topology

The bootstrap milestone SHALL accept any PK/PD model expressible as a deterministic system of
ordinary differential equations that runs under the pinned engine, and SHALL fence only on the
*method* of reproduction — deferring methods that are different in kind, never rejecting a
model merely for being structurally large or complex.

#### Scenario: In-scope model structures

- **WHEN** an entry's PK/PD model is expressible as a deterministic ODE system that runs under
  the pinned engine — including multi-compartment PK, nonlinear or saturable elimination,
  transit-compartment or lag absorption, effect-compartment (link) PD, indirect-response
  (turnover) PD, target-mediated drug disposition, and physiologically-based
  (perfusion-limited) structures
- **THEN** the full ingestion → reconstruction → oracle → certificate pathway applies
- **AND** the number of compartments or the complexity of the ODE system is never itself a
  reason to defer

#### Scenario: Deferred by method, not topology

- **WHEN** reproducing an entry would require a method beyond the MVP — population or
  inter-individual variability distributions, parameter estimation from raw data, stochastic
  or spatial/PDE simulation, or multi-engine corroboration
- **THEN** that specific aspect is retained as an explicit, named deferral with its reason
- **AND** if only some claims need a deferred method, the in-kind claims are still evaluated
  and the deferred ones are marked, rather than deferring the whole entry

#### Scenario: In-kind but intractable degrades to blocked, not failed

- **WHEN** an in-kind ODE model cannot be run to a verdict within the milestone's resource
  limits (e.g. a very large or stiff system that does not converge under the pinned engine)
- **THEN** the entry is recorded as `blocked` with the specific limitation
- **AND** it is not reported as `failed`, since its claims were never fairly evaluated

### Requirement: MVP reproduction-level fence

The milestone SHALL perform simulation reproduction only and SHALL defer estimation
reproduction explicitly.

#### Scenario: Simulation reproduction only

- **WHEN** a PK/PD claim is evaluated in the MVP
- **THEN** the oracle runs the described model with the reported parameters and checks the
  shown output
- **AND** re-fitting parameters from raw data is not attempted and is recorded as a deferred
  capability, even when raw data is present
