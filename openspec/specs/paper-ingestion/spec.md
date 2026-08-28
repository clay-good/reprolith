# paper-ingestion Specification

## Purpose

Ingestion turns a modeling paper and its artifacts into a **dossier**: a normalized,
provenance-tagged extraction of the model's structure, parameters, protocol, and — most
importantly — the specific published **claims** a reproduction must target. The dossier is
the sole input to reconstruction; ingestion never runs a model.

## Requirements

### Requirement: Dossier as the ingestion contract

Ingestion SHALL produce a single structured dossier per catalog entry that downstream
stages depend on, and SHALL never silently invent content.

#### Scenario: Dossier contents

- **WHEN** ingestion completes for an entry
- **THEN** the dossier contains: the model's state variables and equations (as extracted),
  parameters with values and units, initial conditions, the simulation/experimental
  protocol, and the list of claims
- **AND** every element records where in the source it came from (section, equation number,
  table cell, figure panel, supplement location)

#### Scenario: Extracted versus assumed

- **WHEN** a required element is not stated in the source
- **THEN** it is recorded as an explicit gap with a description of what is missing
- **AND** ingestion never fills the gap with a guessed value; guessing is reserved for
  reconstruction, where it is separately recorded as an assumption

### Requirement: Claims are first-class and enumerable

The dossier SHALL enumerate the concrete published results the paper stakes, because these
are exactly what the oracle will check.

#### Scenario: Claim identification

- **WHEN** a paper presents a reproducible result (a plotted curve, a table of predicted
  values, a reported summary metric such as a peak, area, or steady-state)
- **THEN** ingestion records it as a claim with a stable identifier, the quantity it
  asserts, the conditions under which it holds, and the source location
- **AND** results that cannot serve as a reproduction target (purely schematic figures,
  cartoons) are marked as non-targetable rather than dropped

#### Scenario: Claims from a shipped simulation document

- **WHEN** the paper ships a simulation document (SED-ML) alongside its model
- **THEN** each curve the document *plots* is recorded as a claim, since a plot is the
  document's own statement that this is a shown result
- **AND** the independent axis is not recorded as a claim, and a report's data sets are not
  recorded as claims — a report is an export format, not a statement that the paper published
  the value — but a reported column no plot shows is retained as non-targetable rather than
  dropped
- **AND** a document that ships only reports yields no targetable claims, because nothing in it
  says which of its columns the paper published

#### Scenario: Reference data for a claim

- **WHEN** the paper provides the numeric values behind a claim (a data table, digitized
  points, supplementary data)
- **THEN** the claim links to that reference data
- **WHEN** only a rendered figure is available
- **THEN** the claim records that its reference is a figure image, so the oracle knows it
  must compare against digitized or reported summary values rather than raw data

### Requirement: Artifact intake and typing

Ingestion SHALL accept whatever the paper ships and classify it, so reconstruction knows
what it has to work with.

#### Scenario: Recognizing an existing model artifact

- **WHEN** the paper or its entry ships a model file in a known format (SBML, CellML, a
  simulation recipe, source code)
- **THEN** ingestion records the artifact, its detected format, and whether it validates
  against that format's schema
- **AND** an existing valid model artifact is preserved as a candidate starting point for
  reconstruction, not overwritten

#### Scenario: An equation keeps the kind of equation it is

- **WHEN** an ingested artifact states that a variable's value is given by an expression
  (an assignment) rather than its rate of change (a rate equation)
- **THEN** the extracted equation records which of the two it is
- **AND** reconstruction rebuilds it as that kind, because `Y = 2X` and `dY/dt = 2X` are
  different models and a rebuild that confuses them runs a model the artifact never described

#### Scenario: A stated concentration is not read as an amount

- **WHEN** an artifact states a species' initial value as a concentration
- **THEN** ingestion reads it as the amount it stands for in its compartment
- **AND** a concentration whose compartment size reconstruction cannot represent is refused,
  rather than recorded as an amount that is wrong by that volume

#### Scenario: Unit normalization

- **WHEN** parameters and variables carry units
- **THEN** ingestion records both the original stated unit and a normalized canonical unit,
  keeping the original for provenance
- **AND** an unstated or ambiguous unit is recorded as a gap, never coerced silently

#### Scenario: Recognizing a shipped archive

- **WHEN** the paper ships a COMBINE archive
- **THEN** ingestion reads its manifest, ingests the model its master simulation document runs,
  and records every file the archive ships as an artifact with the format the manifest gives it
- **AND** a file the manifest lists but the archive does not contain is recorded as a gap, not as
  an artifact, since the paper does not in fact ship it
- **AND** an archive that does not single out one experiment, or whose experiment runs more than
  one model file, is refused with the ambiguity named rather than resolved by choosing one

#### Scenario: The experiment and the model must agree

- **WHEN** a shipped simulation document refers to a model element the model does not have —
  an observed variable, or the target of a parameter override
- **THEN** the mismatch is recorded as a load-bearing gap
- **AND** the check resolves each reference by its nesting in the model, so an override aimed at
  the right name inside the wrong parent is reported rather than accepted
- **AND** a reference ingestion cannot resolve is left unreported, because failing to resolve a
  reference is not evidence that the model lacks the element

### Requirement: The archive and the manuscript must agree

A shipped archive SHALL be compared against the paper's extracted claims, because an archive
whose two files agree with each other can still describe a run that produces no result the
paper reports.

#### Scenario: The experiment does not run the reported result

- **WHEN** a paper's extracted claims and its shipped simulation document are both available
- **THEN** a claim whose output the archive's model does not declare, a claim whose output the
  experiment never records, and a claim held at parameter values the experiment never runs are
  each reported as a mismatch naming what the archive does instead
- **AND** a comparison that cannot be made mechanically — an id more than one model element
  carries, a target with no readable element id, a scan whose values the document does not
  list, a change whose effect on a value is not computable — is not made, because failing to
  read a document is not evidence that it disagrees
- **AND** the run window is not compared, since a claim states its window in the manuscript's
  units and a simulation states a number with no unit
- **AND** a quantity the document records that no claim covers is not reported as a mismatch,
  since claim extraction is partial and the difference is more often a gap in the extraction
  than a defect in the archive

### Requirement: Ingestion is inspectable and revisable

A dossier SHALL be reviewable and correctable without re-deriving it from scratch.

#### Scenario: Human or agent correction

- **WHEN** a reviewer identifies a mis-extracted equation, parameter, or claim
- **THEN** the correction is applied as a tracked revision to the dossier with the corrector
  and rationale recorded
- **AND** the original extraction remains retrievable

#### Scenario: Confidence on extractions

- **WHEN** an element is extracted
- **THEN** it carries an extraction-confidence signal distinguishing directly quoted values
  from interpreted ones, so reconstruction and reviewers can prioritize scrutiny
