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

#### Scenario: A value the model's own math determines

- **WHEN** the artifact determines an element's value by an assignment rule or an initial
  assignment, which makes the element's stated `value` attribute inert
- **THEN** that stated value is not recorded as an extracted parameter, since the model never
  holds it and a comparison against it can only agree by coincidence
- **AND** the expression that determines it is carried instead, marked with whether it holds
  throughout the run or only at its start, because a value recomputed every step and one set once
  rebuild as different models
- **AND** the element remains declared by that expression, so a model rebuilt from the dossier
  still has it — dropping the value must not drop the element

#### Scenario: A model whose dynamics are reactions

- **WHEN** the artifact's laws of motion are a reaction network
- **THEN** the reactions are carried in the form the artifact states them — a stoichiometry and a
  rate law, with the law's own local parameters travelling with it — rather than derived into
  equations, since the derivation makes semantic choices the artifact did not
- **AND** a network a model rebuilt from the dossier would not reproduce as itself is not carried,
  and the gap recorded in its place names which condition it failed, because "not carried" and
  "the model has none" are different facts

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

#### Scenario: Values a simulation document ships

- **WHEN** a shipped simulation document plots a curve from a data file it names, and the archive
  contains that file
- **THEN** the curve is recorded with the file's values as its reference data and its data source
  named in its provenance, and it is not targetable, because the paper's own recorded points are
  what a model is checked against rather than a result it must regenerate
- **AND** the values are not attached to any other claim, since a document does not state that a
  plot's data curve is the reference for the simulated curve beside it
- **AND** a data file the document names and the archive does not contain is recorded as a gap,
  so a curve with no values reads as one whose data is missing rather than one that had none
- **AND** a column that cannot be resolved without guessing — a format ingestion does not parse, a
  source that selects no single column, a column that is not numeric throughout — yields no
  reference data

#### Scenario: Reference data for a claim

- **WHEN** the paper provides the numeric values behind a claim (a data table, digitized
  points, supplementary data)
- **THEN** the claim links to that reference data
- **WHEN** only a rendered figure is available
- **THEN** the claim records that its reference is a figure image, so the oracle knows it
  must compare against digitized or reported summary values rather than raw data

### Requirement: Candidate claims can be read from the paper's own tables

The claims a reproduction targets are the input nothing else supplies, and thirty of the
thirty-one seeded PK/PD entries abstain for want of them. A curator SHALL be able to obtain
candidates from the tables the paper prints, and the result SHALL be a proposal they choose from,
never an extraction presented as decided.

#### Scenario: What is proposed

- **WHEN** the rows of a paper's tables are read for candidate claims
- **THEN** every cell that is a number on its own becomes one candidate, carrying the value and a
  source location naming the table, the row's own labels, and the column
- **AND** a value the paper prints with a stated spread is a candidate carrying that spread
  beside it, never folded into the value and never dropped, since a paper reporting a mean and a
  variation reported both
- **AND** a metric is stated only where the paper's own wording states one — a column heading, or
  a row label when the heading states none and the row names exactly one — since a defaulted
  metric is a claim about the paper the paper did not make
- **AND** a column that gives the row's conditions supplies those conditions rather than becoming
  a candidate of its own, recognised both by what its heading says and by its holding no numbers,
  since a vocabulary cannot anticipate every word a paper uses and a measurement alone would make
  a numeric dose column a result

#### Scenario: What is never proposed

- **WHEN** candidates are proposed
- **THEN** no candidate names a model output, because matching a table's row label to a model
  element is a judgment, and a wrong match checks a real number against the wrong element
- **AND** the result states that these are candidates and not claims, since a table prints
  measured values, fitted values, differences and conditions side by side

#### Scenario: A table whose rows do not line up

- **WHEN** a table's rows are not all the width of its header, as happens when a cell spans rows
- **THEN** nothing is proposed from it and the reason is stated, because putting a value under a
  column by position across a span reports a number under the wrong heading

### Requirement: A curator's figure digitization can supply a claim's reference values

Most papers state their results in figures, and a claim whose values live in one has nothing to
compare against. Reprolith SHALL accept a reading of that figure made outside it, and SHALL treat
that reading as a measurement of a picture rather than as a number the paper printed. Reprolith
performs no digitization itself: which curve a claim reads, and what its values are, remain the
curator's statements.

#### Scenario: A reading is accepted as a reference

- **WHEN** a digitization of one figure panel is supplied, naming the figure, the tool that read
  it, both axes with their units and scales, and one series of points per curve
- **THEN** each series is paired to a claim only by the pairing the curator states, and a series
  paired with a claim the dossier does not carry is refused rather than dropped
- **AND** the claim's reference kind is recorded as a figure reading whatever the claim held
  before, so the wider tolerance a figure is judged in cannot be escaped by attaching one
- **AND** the claim's source location keeps its own citation and names the figure, the curve, and
  the tool that read them
- **AND** a claim with no series is left as it was, since a partial digitization is not a reason
  to supply the rest

#### Scenario: A reading that is wrong rather than imprecise

- **WHEN** a series states a point outside the axis range it was read off, two readings at one
  position, fewer than two points, or no figure and no tool
- **THEN** it is refused with the reason named, because a mis-calibrated reading is ordered,
  smooth, plausible and wrong by a constant factor, which no later check can see

#### Scenario: Putting a reading on the run's grid

- **WHEN** a claim is judged against a digitized series
- **THEN** the series is resampled onto the same points the run is sampled at, interpolated in
  the scale each axis is drawn in
- **AND** a point outside the span that was read is refused rather than extrapolated, since the
  last value read is not a reading of what lies past it
- **AND** how coarsely the curve was read is reported — the widest gap between readings as a
  fraction of the span — and is not judged, since between two readings the reference is the
  curator's straight line
- **AND** what that interpolation costs is reported too, measured from the reading itself: each
  interior point rejoined from its neighbours, the largest residual expressed as a share of the
  pass budget the claim will be judged under
- **AND** that estimate is reported raw, since a leave-one-out join spans two gaps where the
  reference spans one and over-states by a factor that varies with how coarsely the curve was
  read — over-stating is the safe direction, and correcting it by a constant is not safe

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
