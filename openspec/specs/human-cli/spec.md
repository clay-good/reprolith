# human-cli Specification

## Purpose

The CLI is Reprolith's human-facing surface at a terminal, the counterpart to the agent-facing
MCP server. It exposes the same read-only query model — browse the catalog, read a certificate,
list its gaps, see the blind self-validation track record — so a person can obtain a verdict
without speaking JSON-RPC or writing Python. It re-presents what the engine already produced; it
computes no verdict of its own. Some commands write, and every one of them writes a file the
caller names and never repository state: `export` turns a published reconstruction into a runnable
COMBINE archive, because a reconstruction nobody can re-run without Reprolith is not a published
artifact, and the rest write the input files the checks need — the claims file the archive check
reads, the digitization file whose claim pairing nobody could guess, and the parameters file that
pairs a paper's reported values with the model elements carrying them. Each of those was an input
a check demanded and nothing helped an author produce. The count is deliberately not stated here:
it has been wrong once already, and the CLI's own help groups every command it has.

## Requirements

### Requirement: Read-only human surface with parity

The CLI SHALL read through the same query model the MCP server uses, so the terminal surface
cannot become a divergent second implementation of Reprolith's contracts.

#### Scenario: Same result through either surface

- **WHEN** the same entry or certificate is inspected through the CLI and through the MCP server
- **THEN** the verdicts, certificates, states, and gaps reported are the same
- **AND** the CLI exposes no verdict-producing behavior of its own — it formats what the query
  returns

#### Scenario: No command changes repository state

- **WHEN** any CLI command runs
- **THEN** it changes no repository state
- **AND** an unknown certificate digest or unknown paper is reported as such with a non-zero exit
  status, not a fabricated result

#### Scenario: Exporting a reconstruction

- **WHEN** a reconstruction is exported from the terminal
- **THEN** the only file written is the archive at the path the caller named, built from the
  published bundle the query returns and nothing the CLI decided
- **AND** it is refused if the model supplied is not the one the bundle records having been built
  from, since an archive built from another model packages a run the certificate never judged
- **AND** a recipe step the archive cannot state is reported to the terminal, never dropped
  silently

#### Scenario: Replacing a file the caller had already filled in

- **WHEN** any command that writes is pointed at a path that already holds a file
- **THEN** the success line says that a file was replaced, and says nothing of the kind when the
  path was empty
- **AND** this holds for every writing command rather than for the export alone: the templates are
  filled in by hand — points read off a figure, a reported value looked up per row — the command
  that destroys that work is the same one that created it, and re-running it after the model
  changes is the ordinary thing to do

#### Scenario: Checking an archive against the author's own paper

- **WHEN** the archive check is given a file of the results the paper reports
- **THEN** it reads that file in the shapes an author plausibly has — a list of claim records, an
  object holding one, or several papers keyed by accession — and names the papers it holds when
  the caller must choose between them
- **AND** a claims file that cannot be read is reported as a message about the claims, distinct
  from one about the archive, with a non-zero exit status

#### Scenario: Writing the claims file the check reads

- **WHEN** an author asks for a claims template, giving an archive or a model with its document
- **THEN** the template is written to the path named, or to standard output when none is, and the
  terminal says how many stubs it holds and what could not be turned into one
- **AND** a note the terminal abbreviates is counted rather than dropped, so a shortened summary
  never reads as the whole of what was found
- **AND** it is an error to give both an archive and a model, or neither

#### Scenario: Checking a document and a model that are not packaged

- **WHEN** the archive check is given a simulation document and the model it names instead of an
  archive
- **THEN** it reports what a reproducer would find in the archive those two files describe, and
  says that the manifest was generated rather than read, since the author does not have one yet
- **AND** it reports a model whose filename is not the one the document's source names, because a
  reproducer follows the document
- **AND** it is an error to give both an archive and loose files, or neither

### Requirement: The digitization a curator reads off a figure is checked before it is trusted

A value read off a picture SHALL be checkable at the terminal, on its own and against the document
whose curves it claims to be readings of. Every refusal the join makes on a pairing SHALL be
reachable here, since the join runs long after the curator has finished.

#### Scenario: Writing the digitization file, one panel at a time

- **WHEN** a curator asks for a digitization template, giving an archive or a simulation document
- **THEN** the template names the claim each series is the reading for and the curve the document
  plots there, and leaves blank everything that is a reading — the figure, the tool, both axis
  ranges, and every point
- **AND** a document plotting more than one figure is refused with its plots listed, since one
  file states its axes once and two panels under one pair of ranges is the second panel read
  against the first panel's calibration
- **AND** that refusal is reported as a question about which panel was read, not as a defect in
  the document
- **AND** a curve the document already ships values for gets no stub, with the reason

#### Scenario: Checking a reading against the document it was paired to

- **WHEN** a digitization is checked and the document its claim ids came from is given
- **THEN** a reading paired with a curve the document does not plot, with a claim that already
  carries values, or with one retained non-targetable is refused with a non-zero exit status
- **AND** so is one claim paired with readings from more than one panel, and one file holding
  readings from more than one of the document's plots
- **AND** so is a reading that does not cover a window the document runs, since nothing is
  extrapolated past what was read
- **AND** the curves the document plots that this reading does not cover are reported, not
  refused, since a curator reads one panel at a time

#### Scenario: A check nobody made never reads as a clean one

- **WHEN** a digitization is checked with no document given
- **THEN** the report says the claim ids were not checked, rather than reporting the file clean
- **AND** no model is run and no claim is judged, and the report says so

#### Scenario: A refusal names the file the caller passed

- **WHEN** a check refuses the file of the author's own it was given — unreadable, holding several
  papers, or holding no records at all
- **THEN** the message names that file by what the caller asked for, and points at the command that
  writes one, rather than at the file a shared reader was first written for
- **AND** two commands reading the same kind of file refuse an unusable one in the same words, so
  which command the author reached for does not decide what the fault appears to be

### Requirement: Scope statement inescapable in terminal output

A verdict read from the terminal SHALL carry the same honest scoping as one read anywhere else.

#### Scenario: Scope travels with a printed certificate or verdict

- **WHEN** the CLI prints a certificate or a verdict
- **THEN** the reproducible-not-correct-not-clinical scope statement is present in the output and
  cannot be emptied
- **AND** a qualified or partial result is never rendered as a clean full reproduction

### Requirement: Raw and human forms agree

The human-readable output and the machine output SHALL be two views of one underlying result, so
a reader can never be shown a friendlier verdict than an agent receives.

#### Scenario: JSON output matches the agent surface

- **WHEN** a read command is run with the raw-output option
- **THEN** it emits exactly the object the corresponding MCP tool returns for the same input
- **AND** the default human-readable form is derived from that same data and reports the same
  verdict, counts, scope, and gaps
