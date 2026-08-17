# verification-queue Specification

## Purpose

The verification queue is Reprolith's collaboration surface. Whenever the engine or the build
loop is not confident about a load-bearing value — a shaky extraction, a load-bearing
assumption, a non-default tolerance, a verdict near the margin — it records its best estimate
and queues that item for a human expert to confirm, correct, or reject. This is how the engine
keeps moving while experts validate its judgment, and how the dataset stays fresh over time. Its
purpose is to turn uncertainty into an invitation to collaborate rather than a blocker.

## Requirements

### Requirement: What gets queued

The queue SHALL hold exactly the low-confidence, load-bearing decisions where expert judgment
would change or confirm an outcome, and SHALL not drown reviewers in trivia.

#### Scenario: Load-bearing uncertainty is queued

- **WHEN** a low-confidence extraction, a load-bearing assumption, a non-default tolerance, or a
  near-margin verdict is produced
- **THEN** a queue item is created carrying Reprolith's best estimate, the alternatives it
  considered, the basis for its choice, and which claims or certificates depend on it

#### Scenario: Confident or non-load-bearing values are not queued

- **WHEN** a value is directly stated in the source or does not affect any outcome
- **THEN** it is not queued, so reviewer attention is reserved for what matters

### Requirement: Best estimate is usable but honestly marked

An unverified value SHALL be allowed to flow through the engine as Reprolith's estimate, but its
unverified status SHALL travel with every result that depends on it.

#### Scenario: Unverified value is qualified downstream

- **WHEN** a certificate depends on a queued, still-unverified value
- **THEN** the certificate is qualified as resting on an unverified estimate, and cannot report
  an unqualified full-reproduction verdict on that basis
- **AND** the qualification names the queue item, so anyone can see exactly what is pending

#### Scenario: Verification upgrades the result

- **WHEN** a queued value is confirmed by an expert
- **THEN** the dependent results are re-evaluated and their qualification is lifted or updated
  accordingly

### Requirement: Human decisions are recorded, attributed, and propagated

Every expert action SHALL be captured with its author and rationale, and its consequences SHALL
flow through automatically.

#### Scenario: Confirm, correct, or reject

- **WHEN** an expert confirms, corrects, or rejects a queued item
- **THEN** the decision, the deciding expert, and the rationale are recorded, and the original
  estimate remains retrievable
- **AND** a correction triggers re-verification of every dependent entry, with superseded
  certificates linked to their replacements

#### Scenario: Disagreement is preserved, not overwritten

- **WHEN** experts disagree on a queued value
- **THEN** the competing judgments are retained with their rationales rather than silently
  resolved to one

### Requirement: Items are self-contained and low-barrier

A queue item SHALL be actionable by an outside expert who knows the science but not Reprolith's
internals, because that is what makes collaboration possible at all.

#### Scenario: An expert can act with only the item

- **WHEN** an expert opens a queue item
- **THEN** they see the specific question, the source context, Reprolith's best estimate and
  reasoning, and the stakes (what depends on it), sufficient to decide without studying the
  engine

### Requirement: Impact-ordered queue

The queue SHALL be ordered so the most consequential validations come first.

#### Scenario: Prioritize by dependence

- **WHEN** the queue is presented
- **THEN** items are ranked by how much depends on them (how many claims or certificates hinge
  on the value) and by how close a verdict sits to its tolerance margin
- **AND** the ranking is explainable

### Requirement: Freshness and re-opening

The queue SHALL keep the dataset current by re-opening validations when the ground beneath them
shifts.

#### Scenario: Source or standard changes

- **WHEN** a source value, tolerance convention, or pinned engine changes in a way that could
  affect a previously verified value
- **THEN** the affected items are re-opened for re-validation and the certificates that depend on
  them are flagged as needing review
- **AND** nothing is treated as permanently settled merely because it was once confirmed

#### Scenario: The solver is Reprolith itself

- **WHEN** a class's result is computed by this package rather than by an external engine, and that
  code changes
- **THEN** the pin recorded on its certificates names a revision of that code, so the changed
  solver produces a different pin and every certificate it invalidates is flagged for review
- **AND** a published certificate that names an older revision is regenerated rather than kept,
  because its number is not the one the current code produces
