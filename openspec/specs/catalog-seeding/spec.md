# catalog-seeding Specification

## Purpose

Seeding is the policy layer that keeps the catalog full of the *right* work in the *right*
order. Where `model-catalog` owns the mechanics of adding and de-duplicating entries, seeding
owns the strategy: which sources to draw from, how to prioritize what they yield, how to keep
self-validation possible, and how to do all of it within licensing and ethical limits. Its job
is to guarantee the backlog grows faster than it drains — deliberately, not randomly.

## Requirements

### Requirement: Ground-truth-first seeding

Seeding SHALL prioritize sources that carry independent reproducibility signal, so
self-validation never runs dry as the catalog grows.

#### Scenario: Prefer labelled sources early

- **WHEN** a new model class is being brought online
- **THEN** seeding first draws from sources whose entries carry ground-truth reproducibility
  labels (curated repositories, published reproduction studies, fingerprint-checked models)
- **AND** enough labelled entries are seeded to support a blind agreement measurement before
  the class's verdicts are trusted

#### Scenario: Un-curated tail follows, on purpose

- **WHEN** a class has passed its self-validation gate
- **THEN** seeding expands to the un-curated literature, where reproducibility is unknown and
  the "what was missing" reports carry the most value
- **AND** the shift from labelled to un-curated seeding is explicit, not accidental

### Requirement: Explainable prioritization

Every seeded entry SHALL carry the signals that determine its queue position, and the ranking
SHALL be explainable, so no entry's priority is a black box.

#### Scenario: Priority signals are recorded

- **WHEN** an entry is seeded
- **THEN** it records the signals used to rank it — for example expected tractability
  (model-class fit and input completeness), value (citation weight, community request,
  reproducibility unknown-ness), readiness (a shipped model or simulation recipe present), and
  freshness
- **AND** the catalog can state, for any entry, why it holds its current position

#### Scenario: Readiness boosts tractable wins

- **WHEN** a candidate ships a runnable model or a simulation recipe in a standard format
- **THEN** seeding ranks it as high-readiness, because adopt-and-verify yields a certificate at
  low cost
- **AND** high-readiness entries are surfaced early to build momentum and test set coverage

### Requirement: Source registration and provenance

Seeding SHALL treat every source as a declared, auditable input, so provenance is never lost.

#### Scenario: Registering a source

- **WHEN** a source is configured for seeding
- **THEN** its identity, access method, and the model classes it is expected to yield are
  recorded, and every entry it produces links back to it
- **AND** the same source can be re-run incrementally, seeding only candidates not already in
  the catalog

#### Scenario: Provenance survives de-duplication

- **WHEN** the same paper is seeded from more than one source
- **THEN** the merged entry retains every source that contributed it, not only the first

### Requirement: Licensing and ethical gating

Seeding SHALL respect the terms of each source and SHALL not ingest content it has no right to
redistribute, because credibility with the community depends on it.

#### Scenario: Respecting redistribution terms

- **WHEN** a candidate's source material carries licensing or access restrictions
- **THEN** seeding records what may and may not be stored or redistributed, and stores only
  what is permitted (e.g. metadata and citations rather than restricted full text)
- **AND** an entry whose required inputs cannot be lawfully obtained is marked `blocked` on
  access grounds, not `failed`

#### Scenario: No scope creep into patient or personal data

- **WHEN** a source could carry patient-level or personally identifying data
- **THEN** seeding excludes it; Reprolith seeds published models and their stated results, not
  primary human data

### Requirement: Quality gate before a candidate becomes work

Seeding SHALL screen candidates so obvious non-targets do not clog the queue, without
discarding uncertain cases prematurely.

#### Scenario: Screening at intake

- **WHEN** a candidate is seeded
- **THEN** it is screened for whether it plausibly contains a reproducible computational model
  and at least one targetable claim
- **AND** a candidate that clearly contains no model is set aside with a reason, while an
  uncertain candidate is retained as backlog rather than dropped

### Requirement: Sustained cadence and backlog health

Seeding SHALL run continuously and report the health of the backlog, so the "never runs out"
guarantee is observable rather than assumed.

#### Scenario: Backlog health is reportable

- **WHEN** the state of the catalog is queried
- **THEN** seeding can report backlog depth by model class and difficulty, the labelled-versus-
  un-curated mix, and the drain-versus-refill trend
- **AND** a class whose claimable backlog is running low can be flagged so a new source is
  brought online before work runs out
