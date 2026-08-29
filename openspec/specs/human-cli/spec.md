# human-cli Specification

## Purpose

The CLI is Reprolith's human-facing surface at a terminal, the counterpart to the agent-facing
MCP server. It exposes the same read-only query model — browse the catalog, read a certificate,
list its gaps, see the blind self-validation track record — so a person can obtain a verdict
without speaking JSON-RPC or writing Python. It re-presents what the engine already produced; it
computes no verdict of its own. Two commands write, and both write a file the caller names, never
repository state: `export` turns a published reconstruction into a runnable COMBINE archive,
because a reconstruction nobody can re-run without Reprolith is not a published artifact, and
`claims-template` writes the claims file the archive check reads, because the one input that check
cannot derive was also the one nothing helped an author produce.

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

#### Scenario: The one command that writes a file

- **WHEN** a reconstruction is exported from the terminal
- **THEN** the only file written is the archive at the path the caller named, built from the
  published bundle the query returns and nothing the CLI decided
- **AND** it is refused if the model supplied is not the one the bundle records having been built
  from, since an archive built from another model packages a run the certificate never judged
- **AND** a recipe step the archive cannot state is reported to the terminal, never dropped
  silently

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
