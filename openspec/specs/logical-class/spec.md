# logical-class Specification

## Purpose

This is Reprolith's third fully supported model class: **logical / Boolean and rule-based network
models**. It is a second generalization proof — a third *distinct* oracle. A logical model has no
continuous trajectory and no optimization; its reproducible result is a discrete-dynamics claim: a
steady state (fixed point), the set of attractors a network settles into, or a qualitative
behavior. Passing this class checked by discrete attractor analysis, alongside curve-matching
(PK/PD, kinetic) and linear programming (constraint-based), hardens the claim that the engine is
oracle-agnostic.

Boolean-network attractor analysis is exact and dependency-free, so this class carries no deferred
simulator: the oracle computes the attractors it judges.

## Requirements

### Requirement: Logical dossier shape

A logical dossier SHALL capture the elements that determine a network's discrete dynamics, so a
reproduction is fully specified without the paper.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `logical`
- **THEN** the dossier records the network's nodes, each node's Boolean update rule (its logic in
  terms of the other nodes), the input/fixed nodes, and the update scheme under which each claim
  holds (synchronous or asynchronous)
- **AND** each element cites its source location

#### Scenario: Update scheme is load-bearing

- **WHEN** a reported attractor depends on the update scheme
- **THEN** the update scheme is recorded as a first-class dossier element, and an unstated scheme
  is recorded as a gap, because synchronous and asynchronous updating can yield different
  attractors

#### Scenario: The scheme reaches the run, and the certificate

- **WHEN** a claim states its update scheme
- **THEN** it is judged under that scheme, and the certificate's pin names the scheme its verdicts
  were actually computed under — a pin naming the other one is refused rather than published, and
  claims judged under two schemes are refused a single pin
- **AND** a claim that states no scheme is judged under synchronous updating and carries a
  load-bearing assumption **only where the choice could change its verdict**, which is computed
  rather than assumed: the two schemes' results for the quantity the claim was judged on are
  compared exactly, a fixed point being one under either scheme, and the difference is reported on
  the assumption as a count
- **AND** where the network is too large for that comparison to be computed, the assumption says
  so, since "not comparable here" is not "the schemes agree"

#### Scenario: A multi-valued model is refused, not flattened to Boolean

- **WHEN** an ingested logical model uses more than two levels — declared by a maximum level, an
  initial level, or a threshold above one, or implied by a level literal in its transition logic —
  or uses a transition the Boolean oracle does not implement, such as one that adds to its output's
  level rather than assigning it, consumes an input, or omits its default term
- **THEN** ingestion refuses the model and names what it cannot honour
- **AND** the refusal is preferred because reading such a model as Boolean makes its higher-level
  conditions permanently false, so the oracle would judge a state that is not a steady state of the
  model the artifact describes, and report it as reproduced

### Requirement: Standard logical reproduction targets

The oracle for this class SHALL evaluate the results logical-model papers actually report, using
discrete-dynamics analysis.

#### Scenario: Fixed-point (steady-state) reproduction

- **WHEN** a claim is a reported steady state (a node pattern the network holds fixed)
- **THEN** the oracle computes the network's fixed points and judges whether the reported state is
  among them
- **AND** the analysis used is recorded so the comparison is auditable

#### Scenario: Attractor-set reproduction

- **WHEN** a claim is the set of attractors a network settles into (fixed points and cyclic
  attractors)
- **THEN** the oracle computes the network's attractors under the claim's update scheme and
  compares the reproduced set to the reported set
- **AND** a reported attractor absent from the computed set, or an extra computed attractor, is
  surfaced rather than hidden

#### Scenario: Basin-of-attraction reproduction

- **WHEN** a claim is the basin of one attractor — how much of the state space reaches it
- **THEN** the oracle computes that attractor's basin under synchronous updating and compares it to
  the reported one, judging a reported count of states exactly and a reported share of the space by
  relative error
- **AND** the size of the state space it was counted in is recorded, so a share taken of a smaller
  space (a paper that fixed its inputs first) is visible rather than compared against the wrong
  whole
- **AND** a claim judged under asynchronous updating is abstained on rather than answered with the
  synchronous number, because a basin does not partition the state space under that scheme

### Requirement: Known logical failure modes are first-class

The oracle SHALL recognize the recurring reasons logical reproductions fail.

#### Scenario: Catalogued root causes

- **WHEN** a logical claim is `partial` or `failed`
- **THEN** the root cause is selected from a maintained set that includes at least: an unspecified
  update scheme, an ambiguous or missing logic rule, and an unspecified initial state or input
  fixing
- **AND** a failure fitting none of these is recorded as uncategorized and flagged to extend the set

### Requirement: Generalization is demonstrated, not assumed

Adding this class SHALL reuse the shared engine contracts unchanged, and any contract that cannot
absorb it SHALL be surfaced rather than forked.

#### Scenario: Shared contracts carry the new class

- **WHEN** a logical entry moves through the pathway
- **THEN** it uses the same catalog lifecycle, dossier/claims model, assumption-recording,
  certificate format, and scope flag as the other classes, specialized only in its structural
  elements, reproduction targets, tolerances, and failure modes
- **AND** if a shared contract cannot express something this class needs, that gap is raised as a
  change to the shared spec, not worked around inside this class
