# certificate-publication Specification

## Purpose

Publication is how Reprolith's work reaches the field: every certificate is published to a
public, browsable, citable registry, and every model or paper gets an embeddable status badge
that reflects its current verdict. This is the distribution flywheel — a badge on an author's
repository or a paper's page turns each reproduction into an advertisement and each irreproducible
result into a visible, actionable prompt to fix it. Its hardest requirement is honesty: a badge
must never show a silent green.

## Requirements

### Requirement: Every certificate is publicly browsable

Completed certificates SHALL be published to a public registry that a non-expert can navigate, so
results are usable by the community, not buried.

#### Scenario: Publishing a certificate

- **WHEN** a certificate is finalized
- **THEN** it is published to the public registry with its per-claim verdicts, overall verdict,
  assumptions, scope statement, and gap report intact
- **AND** the published form carries no less qualification than the source certificate

#### Scenario: Browsing and filtering

- **WHEN** someone visits the registry
- **THEN** they can browse and filter certificates by model class, overall verdict, source, and
  freshness
- **AND** each entry links to the reconstruction artifacts needed to re-run it

### Requirement: Stable, citable identity

Each published certificate SHALL have a stable identifier so it can be cited and linked durably.

#### Scenario: Durable reference

- **WHEN** a certificate is published
- **THEN** it is addressable by a stable identifier that continues to resolve as the certificate
  is superseded, pointing to the current version while preserving access to prior ones

### Requirement: Embeddable status badge

Each model or paper SHALL have an embeddable badge that shows its current reproduction status at a
glance and links to the full certificate.

#### Scenario: Badge reflects the verdict

- **WHEN** a badge is rendered for a model or paper
- **THEN** it shows the current overall verdict — reproduced, partially reproduced, not
  reproduced, or blocked — and links to the certificate behind it

#### Scenario: Badge updates on re-certification

- **WHEN** an entry is re-certified under a new engine, tolerance, or correction
- **THEN** the badge reflects the new verdict, and the prior verdict remains retrievable through
  the certificate history

### Requirement: No silent green

A badge or registry entry SHALL never present a qualified or partial result as a clean success,
because overstating reproducibility would betray the entire purpose.

#### Scenario: Qualified results look qualified

- **WHEN** an overall verdict is partial, assumption-qualified, or resting on an unverified value
- **THEN** the badge and the registry entry render it as visibly distinct from an unqualified
  reproduction, and the qualification is one click away
- **AND** no rendering path can collapse a qualified result into a plain "reproduced" state

### Requirement: Publication carries the scope statement

Published artifacts SHALL travel with the reproducible-not-correct-not-clinical scope statement,
so a certificate cannot be re-shared stripped of its meaning.

#### Scenario: Scope travels with the artifact

- **WHEN** a certificate or badge is published or embedded elsewhere
- **THEN** the scope statement accompanies it and cannot be emptied
