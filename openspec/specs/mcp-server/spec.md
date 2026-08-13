# mcp-server Specification

## Purpose

The MCP server is Reprolith's agent-facing surface. It exposes the same catalog, ingestion,
reconstruction, oracle, and certificate engine that humans use through the repository, so an
AI agent can use Reprolith as a **deterministic reproducibility oracle inside its own
workflow** — claim work, submit a paper, and receive a certificate it can trust and cite.

## Requirements

### Requirement: Read-only and effectful tools are separated

The server SHALL make the distinction between querying and mutating obvious to a calling
agent, so read-only use is friction-free and effectful use is deliberate.

#### Scenario: Query tools are side-effect-free

- **WHEN** an agent calls a query tool (browse the catalog, fetch a certificate, get a
  paper's status, list gaps)
- **THEN** the call returns data and changes no state
- **AND** such tools are safe to call repeatedly and in parallel

#### Scenario: Effectful tools are explicit

- **WHEN** an agent calls a tool that changes state (submit a paper, claim work, apply a
  dossier correction, request verification)
- **THEN** the tool is clearly identified as effectful and reports exactly what it changed
- **AND** submitting the same paper twice resolves to the existing catalog entry rather than
  creating a duplicate

### Requirement: Certificates are returned verbatim and self-describing

An agent consuming a Reprolith result SHALL receive the certificate's own qualifications,
not a lossy summary that could mislead it.

#### Scenario: Verdict comes with its qualifications

- **WHEN** an agent fetches a result for a paper
- **THEN** it receives the per-claim verdicts, the overall verdict, the scope flag, and any
  assumption qualifications together as one object
- **AND** the server never returns a bare "reproduced/not" boolean stripped of scope and
  qualification

#### Scenario: Scope flag is inescapable over MCP too

- **WHEN** any certificate or verdict is returned through the server
- **THEN** the reproducible-not-correct-not-clinical scope statement travels with it

### Requirement: The published body of work is queryable across classes

The read surface SHALL make every model class's published certificates reachable, not only the
class whose work queue it is loaded from, so an agent can fetch and cite any reproduction Reprolith
has certified.

#### Scenario: A certificate from any class is fetchable

- **WHEN** the default read surface is queried for a certificate, verdict, or gap report
- **THEN** the certificates of every class that shipped a milestone are reachable — a
  constraint-based, logical, kinetic, stochastic, or spatial verdict, not only a PK/PD one
- **AND** each such verdict still travels with its scope flag and qualifications

### Requirement: Self-validation track record is queryable and honest

The read surface SHALL expose Reprolith's blind self-validation evidence — how each class's
verdicts matched independently-established ground truth — so an agent can weigh a class's proven
reliability before citing one of its certificates, and SHALL report it without a metric that
misrepresents the discipline.

#### Scenario: Track record reported per class and overall

- **WHEN** an agent requests the self-validation track record
- **THEN** it receives, per model class, the blind agreement of that class's verdicts against its
  independent ground truth, plus an overall summary across classes
- **AND** the call returns data and changes no state

#### Scenario: An abstention is never counted as a wrong verdict

- **WHEN** the overall track record summarizes disagreements between a blind verdict and its label
- **THEN** a verdict that abstained (a `blocked` verdict — insufficient information) is counted
  apart from a verdict that confidently differed from the label
- **AND** no single blended agreement rate is presented that would conflate honest abstentions
  with wrong verdicts

### Requirement: Deterministic linter mode

The server SHALL support the common agent pattern of checking a single model or claim inline,
returning a fast, deterministic pass/fail an agentic workflow can gate on.

#### Scenario: Inline check of a supplied model

- **WHEN** an agent submits a model bundle and a claim to check directly, without going
  through the full catalog lifecycle
- **THEN** the server runs the oracle and returns the per-claim verdict, discrepancy, and
  tolerance used
- **AND** the same submission yields the same verdict, so the agent can treat it as a
  deterministic gate

### Requirement: Work handoff is lease-aware

The server SHALL let an agent claim and progress catalog work without colliding with other
agents or humans.

#### Scenario: Agent claims and reports work

- **WHEN** an agent requests the next work item and later reports progress or an outcome
- **THEN** the server leases the item to that agent, accepts its progress, and releases or
  advances the item accordingly
- **AND** an expired or abandoned lease returns the item to the queue with partial work
  preserved

### Requirement: Parity with the human surface

The MCP server SHALL not become a divergent second implementation of Reprolith's contracts.

#### Scenario: Same verdicts through either surface

- **WHEN** the same entry is inspected through the repository and through the MCP server
- **THEN** the verdicts, certificates, and states reported are the same
- **AND** the server exposes no verdict-producing behavior that the core engine does not
  itself define
