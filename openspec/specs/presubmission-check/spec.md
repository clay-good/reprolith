# presubmission-check Specification

## Purpose

The pre-submission check is the adoption flywheel: the same reproduction engine, re-presented so
an author runs it on their *own* model **before** publishing. Instead of an after-the-fact audit,
it hands the author a precise, prioritized "fix this before you submit" report — the per-claim
verdicts plus, in impact order, exactly what a reproducer will be missing. It turns the
un-curated tail into fewer irreproducible papers at the source, and it introduces no new oracle:
it consumes an existing certificate and re-frames it for the author.

## Requirements

### Requirement: Author-facing report from an existing certificate

The check SHALL derive its report from a certificate the engine already produced, so an author's
pre-submission verdict cannot diverge from the reproduction the certificate records.

#### Scenario: Report is derived, not recomputed

- **WHEN** a pre-submission report is produced for a certificate
- **THEN** its per-claim verdicts, overall verdict, and scope statement are exactly those of the
  certificate, and no verdict is recomputed
- **AND** the report carries no less qualification than the certificate — a partial or
  assumption-qualified result is never presented as ready to submit

#### Scenario: Ready to submit means nothing is left to fix

- **WHEN** a certificate reproduces every claim cleanly but records a gap — something the artifact
  did not state
- **THEN** the report is not ready to submit, because the same report lists that gap as something
  to fix first, and a readiness signal that contradicts its own fix list tells an author the
  opposite of what the evidence says

### Requirement: Prioritized, actionable fix list

The report SHALL turn the certificate's gaps into an ordered checklist, most impactful first, so
an author knows what to fix first rather than reading an unordered list.

#### Scenario: Gaps are ordered by impact

- **WHEN** the report lists what is missing
- **THEN** each item names the claim it blocks, its source location, the issue, and the concrete
  fix, and the items are ordered by impact: claims a reproducer cannot even evaluate first, then
  failed claims, then partial claims, then load-bearing values the author left for the engine to
  assume, then certificate-level gaps
- **AND** each item's fix is an instruction the author can act on, never the issue restated: a
  finding handed back under a heading that says to fix it gives them nothing to do
- **AND** one fix that blocks many claims is one item naming all of them, not one item per claim:
  an assumption is a value, and repeating it per claim buries the fixes that differ among the rows
  that do not
- **AND** a fully reproduced certificate produces an empty fix list

#### Scenario: Ready-to-submit is honest

- **WHEN** the report states whether the model is ready to submit
- **THEN** it reports ready only for an unqualified full reproduction, and otherwise states it is
  not yet ready and points to the fix list
- **AND** the ready-to-submit signal can never be green while any claim is partial, failed,
  not-evaluable, or assumption-qualified

#### Scenario: A claim judged from a reading of the author's figure

- **WHEN** a certificate carries a claim whose reference was read off a figure
- **THEN** the report names that claim, states the consequence — judged against a reading rather
  than a published value, in the wider band that carries — and says how the author can remove the
  step, since they hold the numbers and the reproducer does not
- **AND** the widening it states is the one that claim's own comparison carries (3x for a scalar,
  2x for a curve, 1.67x for a distribution band), not a single number that is right about one of
  them
- **AND** it does not gate readiness on it, for the reason the archive check does not: publishing
  results as figures is what papers do, and a report marked not-ready for it tells an honest author
  their work is broken
- **AND** an estimation-level claim still gates, because re-fitting answers a different question
  while a figure reading answers the same one in a wider band

### Requirement: An archive can be checked before any certificate exists

An author with a COMBINE archive and no certificate SHALL be able to learn what a reproducer would
find in it, since a file that cannot be read or states no result never reaches a verdict at all.

#### Scenario: What the archive check reports

- **WHEN** an archive is checked
- **THEN** it reports what the archive ships, whether its experiment and its model agree, whether
  it states any published result, and how many of its runs a reproducer can adopt verbatim
- **AND** an archive that cannot be read is reported as the whole finding rather than raising,
  because a malformed archive is the most actionable result there is
- **AND** no model is run and no verdict is reached

#### Scenario: Checking the archive against the paper's own results

- **WHEN** the author supplies the results their paper reports alongside the archive
- **THEN** a reported result the experiment does not run — an output the model does not declare,
  an output the experiment never records, or a parameter value the run never holds — is reported
  in the top tier of the fix list, since it fails as silently as an experiment/model mismatch
- **AND** when no such results are supplied, the check says that this comparison did not run,
  because an empty fix list must not read as an archive that runs what the paper reports

#### Scenario: An unpackaged document and model

- **WHEN** an author has a simulation document and its model as loose files
- **THEN** the same check is available on the pair, by checking the archive those files describe
- **AND** the report states that the archive around them was assembled, so a reader does not take
  a clean result as evidence about a manifest that does not exist yet

#### Scenario: A model no time course describes

- **WHEN** the archive's model declares an SBML package that means it is not run as a uniform
  time course — constraint-based, logical, spatial, or multi-component
- **THEN** the findings that presume a time course — that the document states published results,
  and that a run can be adopted verbatim — are withheld and named as not judged, rather than
  issued as fixes about a run nobody performs
- **AND** the archive is not reported ready, since readiness would claim a reproducer knows what
  to check and nothing established that
- **AND** everything that still applies is still checked and reported

#### Scenario: The check does not speak as a certificate

- **WHEN** the archive check is rendered
- **THEN** it states what it is — a read of the archive that runs no model and issues no
  certificate — rather than carrying the certificate scope statement, whose first words are
  "This certificate attests"

#### Scenario: An extraction limit is not an author's defect

- **WHEN** Reprolith's own extraction of the archive's model leaves load-bearing gaps
- **THEN** they are reported separately from the fix list and do not decide readiness
- **AND** they are not phrased as something for the author to state, because the same gap shape
  covers both something the archive omits and something the archive states fully that Reprolith
  cannot represent — and telling an author to repair a correct file is worse than saying nothing

### Requirement: The claims file can be generated from the author's own files

The check against the paper's own results needs an input the author's files do not carry. An
author SHALL be able to generate that file from the model and simulation document they already
have, so the one input the check cannot derive is the only one they write.

#### Scenario: What the template contains

- **WHEN** a template is generated from a model and its simulation document
- **THEN** each curve the document plots becomes one claim stub naming the model output it reads,
  because a plot is the document's own statement that a curve is a shown result
- **AND** the model outputs a claim can read, the parameters a claim can set, and the parameters
  the model's own math determines are each listed, so a stub can also be written by hand
- **AND** a parameter the model's own math determines is never offered as one a claim can set,
  since an override aimed at one is refused when the claim is run

#### Scenario: A template never states a result

- **WHEN** a template is generated from any model
- **THEN** no stub carries a reported value or a source location
- **AND** a claims file still carrying those blanks is refused, naming each one, rather than
  checked — a value read off the model would be compared against the model that produced it, and
  the comparison would pass by construction

#### Scenario: A model with no simulation document

- **WHEN** a template is generated from a model alone
- **THEN** no claim stub is written, and the reason is stated: a model says what can be read and
  never what the paper showed
- **AND** the lists needed to write stubs by hand are still provided

#### Scenario: A curve no single output explains

- **WHEN** a plotted curve is an expression over several model elements, or reads an element no
  time course records, or plots values the document itself ships
- **THEN** the stub names no output — or, for shipped values, is not a stub at all — and the
  reason is reported, rather than a plausible output being guessed at

### Requirement: A claim's reference value can be checked against the paper's own tables

A reference value read from a manuscript is the one kind this engine cannot check against a
generator, and a wrong one inside tolerance passes every other check. An author or curator SHALL
be able to ask whether each value a claims file states is printed in the source it cites.

#### Scenario: A value the cited table does not print

- **WHEN** a claims file is checked against the rows of the tables the paper prints
- **THEN** a claim whose reported value does not appear in the table it cites is reported, naming
  the value and the table
- **AND** the check is non-zero only for that finding

#### Scenario: What the check declines to decide

- **WHEN** a claim cites a table
- **THEN** only whether the value appears in it is answered, never which cell is the right one,
  because that is the curator's judgment and a guess would accuse a correct claim
- **AND** a value is matched as the paper prints it rather than by rounding, since rounding would
  accept the number the paper would have printed instead of the one it did

#### Scenario: A claim that cannot be checked

- **WHEN** a claim cites a figure, a sentence, or a table that was not supplied
- **THEN** it is reported as not checked, separately from the values that were checked and failed,
  and it does not make the check fail
- **AND** an unfilled claim template is reported the same way, since a value not yet written is
  not a wrong value

### Requirement: A model's own values can be checked against the ones its paper reports

Every certificate this engine issues checks a model's *outputs*. Nothing checked its **inputs**: a
deposit carrying a value its own paper does not report reproduces every claim and says nothing. An
author SHALL be able to ask whether the model they are depositing carries the values their paper
prints, and SHALL be told what that question could not reach.

#### Scenario: A value the model does not carry

- **WHEN** a model is checked against values a paper reports, each paired with the model element it
  names
- **THEN** a value the model does not carry is reported, naming both numbers
- **AND** agreement is judged at the precision the paper printed and no finer, since demanding
  equality would accuse a correct deposit of a mismatch its own source cannot support

#### Scenario: A value the model's own math determines

- **WHEN** the paired element's value is set by an initial assignment or a rule
- **THEN** it is reported as not compared, separately from a mismatch, because the number in its
  declaring attribute is not what runs and agreement with it would be a confident wrong answer

#### Scenario: What the paper does not report at all

- **WHEN** the check completes
- **THEN** every settable value the model declares that the supplied pairs do not cover is named,
  grouped by what it is — a parameter, a compartment's size, a species' initial condition — since
  a value the paper omits is one a reproducer must take from the deposit or guess
- **AND** this is reported and never gated, because which of them belongs in a paper is the
  author's judgment

#### Scenario: A pairing the author has not made yet

- **WHEN** a row states a value and names no model element
- **THEN** it is reported as not compared, because a file that is not finished is not a model that
  fails its paper

#### Scenario: A run that compared nothing does not report a pass

- **WHEN** no pair in the file could be compared
- **THEN** the report states that nothing was compared, rather than a count of rows it read
- **AND** the check exits non-zero when every row is an unfilled template blank, since this
  status is documented as droppable into a pre-submission gate and the author has not yet said
  what to check
- **AND** it exits zero when the author did fill the file in and each row was skipped for a
  stated reason, since a value that could not be compared is not a value that is wrong

### Requirement: A claim's number is checked in the unit it is a number of

Two numbers agreeing says nothing until they are the same quantity, and a paper's litres against a
deposit's millilitres agree at a factor of a thousand — an error no output check downstream can
see, since the reconstruction runs the model's own number and reproduces the model's own curve. A
claim that states the unit its value is in SHALL have that unit checked against the model and
against the paper, and a difference SHALL abstain rather than be compared.

#### Scenario: The unit a model reads an output in

- **WHEN** a claim states the unit its value is in and a model is supplied
- **THEN** the unit that model reads that output in is composed from the model's own declarations
  and compared against it, and a difference is reported as not compared rather than as a
  disagreement about the value
- **AND** the answer names the factor between the two units where both are readable

#### Scenario: The unit the paper's own heading states

- **WHEN** a claim states a unit and cites a table that names one for the claim's metric
- **THEN** the two are compared, so a value taken from one column and labelled with another's unit
  is reported

#### Scenario: A unit that cannot be read

- **WHEN** either unit cannot be read as a unit, or the claim states none, or the row states no
  metric
- **THEN** it is reported as not checked, because naming another unit is an accusation and an
  unreadable unit is not evidence of one

### Requirement: Runnable over the MCP surface

An author or their agent SHALL be able to run the check through the same read-only MCP surface as
the rest of the engine.

#### Scenario: Pre-submission check over MCP

- **WHEN** the pre-submission tool is called for a certificate digest over the MCP server
- **THEN** it returns the author-facing report — readiness, per-claim verdicts, prioritized fix
  list, and the scope statement — and changes no state
- **AND** the scope statement travels with the report and cannot be emptied
