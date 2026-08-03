# autonomous-build-loop Specification

## Purpose

The autonomous build loop turns a single stated goal into continuous, self-verifying progress.
Pointed at a goal (e.g. "bring the constraint-based class to its self-validation gate"), a
coding agent selects the next best unit of work, does it, proves it against deterministic
gates, records it, publishes it, and continues — escalating only what it cannot safely decide.
It is how Reprolith is built and operated with a human setting direction rather than driving
every step. Its defining discipline: it advances on everything it is confident about and never
silently commits a low-confidence, load-bearing choice.

## Requirements

### Requirement: Goal-directed work selection

The loop SHALL, given a goal, choose the next unit of work that best advances it, and SHALL be
able to explain the choice.

#### Scenario: Selecting the next unit

- **WHEN** the loop is given a goal and asked to proceed
- **THEN** it selects the next unit of work — a build slice (implement a spec or task) or an
  operation slice (reproduce catalog entries) — that most advances the goal under the backlog
  prioritization rules
- **AND** it can state why that unit was chosen over the alternatives

#### Scenario: A unit is a slice, not the whole goal

- **WHEN** a goal is larger than one safe change
- **THEN** the loop decomposes it into slices small enough to verify and publish independently,
  rather than attempting the whole goal in one step

### Requirement: Deterministic acceptance gates before publishing

The loop SHALL publish only work that passes Reprolith's deterministic gates, so autonomy never
lowers the quality bar.

#### Scenario: Gates must pass to land

- **WHEN** the loop finishes a slice
- **THEN** it runs the applicable deterministic gates — spec validation, tests, the reproduction
  oracle's self-checks, and the determinism check — before publishing
- **AND** a slice that fails any gate is not published; it is revised or parked with the failure
  recorded

#### Scenario: Honesty invariants cannot be weakened

- **WHEN** a slice would alter certificate scope, assumption-qualification, or blind
  self-validation
- **THEN** the loop treats weakening any of these invariants as an automatic gate failure, never
  a permitted change

### Requirement: Best-estimate-and-escalate, never block the whole loop

The loop SHALL record a best estimate for anything it is uncertain about, escalate the
load-bearing cases, and keep making progress on everything independent of them.

#### Scenario: Load-bearing uncertainty is escalated, not guessed-through

- **WHEN** proceeding would require committing a low-confidence value or judgment that plausibly
  changes an outcome
- **THEN** the loop records its best estimate with a confidence signal and opens a verification-
  queue item for it, rather than silently adopting it
- **AND** any result that depends on that estimate is qualified as resting on an unverified value

#### Scenario: Independent work continues

- **WHEN** one unit is blocked on an open escalation
- **THEN** the loop continues with other units that do not depend on the unresolved item
- **AND** it does not stall the entire goal on a single uncertainty

### Requirement: Every autonomous change is auditable

The loop SHALL leave a trail a human can review, so unattended progress never becomes opaque.

#### Scenario: Traceable commits

- **WHEN** the loop publishes a slice
- **THEN** the change records the goal it served, the unit it completed, the gates it passed, and
  any verification-queue items it opened
- **AND** a reviewer can reconstruct what the loop did and why without reading its internal state

#### Scenario: Human can steer or stop at any time

- **WHEN** a human changes the goal, pauses the loop, or overrides a decision
- **THEN** the loop honors it at the next slice boundary and records the intervention

### Requirement: Safe continuation and stop conditions

The loop SHALL keep going while there is gated, publishable work, and SHALL stop or pause
deliberately rather than spinning.

#### Scenario: Repeated failure is parked, not retried forever

- **WHEN** a unit fails its gates repeatedly without progress
- **THEN** the loop parks it with a diagnosis and moves on, rather than looping on it
  indefinitely

#### Scenario: Defined stopping points

- **WHEN** the goal is met, the publishable backlog is exhausted, or further progress is gated
  entirely on open escalations
- **THEN** the loop stops with a summary of what it accomplished, what it parked, and what it
  escalated
