# human-cli Specification

## Purpose

The CLI is Reprolith's human-facing surface at a terminal, the counterpart to the agent-facing
MCP server. It exposes the same read-only query model — browse the catalog, read a certificate,
list its gaps, see the blind self-validation track record — so a person can obtain a verdict
without speaking JSON-RPC or writing Python. It re-presents what the engine already produced; it
computes no verdict of its own.

## Requirements

### Requirement: Read-only human surface with parity

The CLI SHALL read through the same query model the MCP server uses, so the terminal surface
cannot become a divergent second implementation of Reprolith's contracts.

#### Scenario: Same result through either surface

- **WHEN** the same entry or certificate is inspected through the CLI and through the MCP server
- **THEN** the verdicts, certificates, states, and gaps reported are the same
- **AND** the CLI exposes no verdict-producing behavior of its own — it formats what the query
  returns

#### Scenario: Every command is side-effect-free

- **WHEN** any CLI command runs
- **THEN** it returns data and changes no repository state
- **AND** an unknown certificate digest or unknown paper is reported as such with a non-zero exit
  status, not a fabricated result

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
