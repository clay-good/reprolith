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

### Requirement: A reconstruction ships in the standard runnable form

A reconstruction SHALL be exportable as a COMBINE archive — the model, the simulation experiment
that runs it, and a manifest saying what each file is — so re-running it needs no Reprolith.

#### Scenario: Exporting a reconstruction

- **WHEN** a reconstruction is exported
- **THEN** the archive holds the model as SBML, a SED-ML document giving the run duration, its
  step count, and the variables recorded, and a manifest that singles out that document as the
  archive's master experiment
- **AND** the archive is byte-identical for the same model and run conditions, so it can be
  digested and compared like every other published artifact

#### Scenario: Exporting a published reconstruction

- **WHEN** a reconstruction bundle is exported
- **THEN** each recipe step becomes a task stating its window, its sample count, the output it
  records, and the parameter values that step sets, so the values that distinguish two claims on
  one model travel in the file rather than only in Reprolith's own record
- **AND** a step the document cannot state is reported with its reason, never dropped, since an
  archive quietly short of a claim reads as a reconstruction that never had one
- **AND** an override naming a parameter the model does not declare is one such step, because
  writing it would ship an archive that silently runs the unmodified model

#### Scenario: What an exported document does not assert

- **WHEN** the exported document names the quantities a run records
- **THEN** it names them as a report — the columns to write — and never as plotted results,
  because SED-ML cannot say that a *paper* published a value and a plot read back as claims would
  manufacture one published result per recorded variable
- **AND** re-ingesting an exported archive therefore yields the model's structure and no
  targetable claims

#### Scenario: An exported experiment agrees with the model it ships with

- **WHEN** the exported document records a variable
- **THEN** the variable resolves in the model the archive ships, by its nesting
- **AND** an export asked to record something the model does not have is refused with the name
  reported, rather than written as a column that cannot exist

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
- **AND** a certificate whose claims were reproduced at estimation level renders as distinct from a
  simulation reproduction on every surface — never green, and never described as a clean pass

#### Scenario: A published certificate is escaped and self-consistent

- **WHEN** a certificate contributed by someone else is published to the registry
- **THEN** every value interpolated into the page — including the scope statement carried in the
  badge — is escaped, so a certificate cannot inject markup into the public page
- **AND** a stored certificate whose overall verdict does not follow from its own assessments and
  assumptions is refused on load rather than published, so the honesty invariants hold for a
  certificate read off disk and not only for one built in process

### Requirement: Publication carries the scope statement

Published artifacts SHALL travel with the reproducible-not-correct-not-clinical scope statement,
so a certificate cannot be re-shared stripped of its meaning.

#### Scenario: Scope travels with the artifact

- **WHEN** a certificate or badge is published or embedded elsewhere
- **THEN** the scope statement accompanies it and cannot be emptied
