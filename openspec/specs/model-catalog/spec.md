# model-catalog Specification

## Purpose

The model catalog is Reprolith's backlog engine: a durable, ever-growing registry of
candidate modeling papers, each tracked through the reproduction lifecycle. It exists to
guarantee there is always well-scoped, prioritized work to claim — for a human or an agent
— and to make the state of every reproduction attempt queryable and resumable.

## Requirements

### Requirement: Catalog entry lifecycle

Each candidate paper SHALL be represented by exactly one catalog entry that moves through
an explicit, ordered set of lifecycle states, and the current state SHALL always be
knowable without inspecting downstream artifacts.

#### Scenario: Defined lifecycle states

- **WHEN** a catalog entry exists
- **THEN** its state is exactly one of: `queued`, `ingesting`, `ingested`,
  `reconstructing`, `reconstructed`, `verifying`, `certified`, `failed`, `blocked`,
  `quarantined`
- **AND** `certified` and `failed` are terminal only for a given engine-version pin; a new
  pin MAY re-open the entry for re-verification

#### Scenario: State transitions are recorded, not inferred

- **WHEN** an entry changes state
- **THEN** the transition is appended to the entry's history with a timestamp, the actor
  (human handle or agent identifier), and the reason
- **AND** the previous state, artifacts, and certificate (if any) remain retrievable

#### Scenario: A stored entry that contradicts its own record is refused

- **WHEN** a saved catalog is loaded and an entry's state is not where its recorded history
  ends, or a `blocked` entry records nothing it is blocked on, or its lease expiry is not a time
- **THEN** loading refuses, rather than restoring a state nothing recorded

#### Scenario: Blocked versus failed are distinct

- **WHEN** an attempt cannot proceed because a required input is missing (no equations, no
  parameters, paywalled supplement)
- **THEN** the entry becomes `blocked` with a machine-readable list of the missing inputs
- **AND** `failed` is reserved for attempts that ran to completion but did not reproduce
  the claims

### Requirement: Never-empty prioritized queue

The catalog SHALL always be able to hand a requester the next best unit of work, scoped to
what that requester can handle.

#### Scenario: Claiming the next work item

- **WHEN** a requester asks for work, optionally filtered by model class and difficulty
- **THEN** the catalog returns the highest-priority claimable entry matching the filter, or
  an explicit "no eligible work" result
- **AND** the returned entry is leased to the requester so concurrent requesters do not
  collide on the same entry

#### Scenario: Leases expire

- **WHEN** a leased entry sees no progress within its lease window
- **THEN** the lease is released and the entry becomes claimable again
- **AND** the abandoned attempt's partial artifacts are preserved and linked

#### Scenario: Prioritization is explainable

- **WHEN** an entry is offered as the next work item
- **THEN** the catalog can state why it was ranked where it was (e.g. citation weight,
  model-class fit, expected tractability, community request, freshness)

### Requirement: Perpetual seeding

The catalog SHALL support continuous ingestion of new candidates from external sources so
the backlog grows faster than it is drained.

#### Scenario: Seeding from a source

- **WHEN** a seeding run imports candidates from a configured source (a model repository, a
  journal feed, a curated list)
- **THEN** each new candidate becomes a `queued` entry with its source provenance recorded
- **AND** a candidate already present is de-duplicated to its existing entry, not duplicated

#### Scenario: De-duplication across identifiers

- **WHEN** the same underlying paper arrives under different identifiers (DOI, PubMed ID,
  repository accession, title match)
- **THEN** the catalog resolves them to a single entry and retains all known identifiers

### Requirement: Difficulty and class tagging

Every entry SHALL carry the metadata needed to route it to the right reproduction pathway
and to the right requester.

#### Scenario: Model-class assignment

- **WHEN** an entry is created or ingested
- **THEN** it is tagged with a model class (e.g. `ode-pkpd`, `kinetic`, `constraint-based`,
  `unassigned`) that determines which reconstruction and oracle pathway applies
- **AND** an entry whose class is not yet supported is retained as `unassigned` backlog
  rather than discarded

#### Scenario: Difficulty estimate

- **WHEN** an entry has been at least partially ingested
- **THEN** it carries a difficulty estimate derived from observable signals (presence of
  equations, parameter completeness, availability of an existing model file or dataset)
- **AND** the estimate is advisory and never blocks a requester from attempting the entry

### Requirement: Ground-truth labelling for self-validation

The catalog SHALL be able to mark entries whose reproducibility is independently known, so
Reprolith's own verdicts can be measured against them.

#### Scenario: Attaching a ground-truth label

- **WHEN** an entry's reproducibility has been established by an external authority (e.g. a
  curation repository's status, a published reproduction study)
- **THEN** the entry can carry a `ground_truth` label with its source and the expected
  verdict
- **AND** the label is never shown to the reconstruction or oracle pathway that produces a
  verdict, so self-validation stays blind

#### Scenario: Agreement reporting

- **WHEN** a verdict is produced for a ground-truth-labelled entry
- **THEN** the catalog can report agreement or disagreement between Reprolith's verdict and
  the label, across any queryable slice of entries
