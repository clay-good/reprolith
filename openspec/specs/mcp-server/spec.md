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

#### Scenario: A submission never edits an existing entry's identity

- **WHEN** a submission carries identifiers an existing entry does not already hold
- **THEN** the entry's identity is left unchanged and the reply says which identifiers were not
  recorded, identically for every entry
- **AND** the reply is the same whether or not the entry carries a ground-truth label, so
  submitting cannot be used to discover which papers are in the graded set

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

### Requirement: Cross-engine corroboration is queryable, and its absences are stated

The read surface SHALL expose what a second, independently-implemented engine said about the
verdicts it publishes — reported beside them, never gating them — and SHALL name every model class
for which no second engine was run, so a reader cannot mistake an unasked question for a passed
one.

#### Scenario: Corroboration reported per class

- **WHEN** an agent or a human surface requests the cross-engine corroboration record
- **THEN** it receives, for each class that was re-run on a second engine, how many runs were
  compared, which engines compared them, how many were engine-independent, and the weakest
  published agreement bound in that class
- **AND** the call returns data and changes no state

#### Scenario: A class with no second engine is named, not omitted

- **WHEN** a model class has no second registered engine, or its committed record holds no rows
- **THEN** that class is reported as unchecked in the same response as the checked classes
- **AND** it is never presented as corroborated on the strength of zero comparisons

#### Scenario: Runs of different kinds are counted apart

- **WHEN** one class re-runs each claim and another re-runs each model
- **THEN** the totals report the two kinds separately, and no single blended count is presented
  that would state more runs than were compared

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

### Requirement: One caller's bad request never denies service to the next

The server SHALL survive any input a caller can send, because a single long-lived process serves
every agent on the stream.

#### Scenario: A malformed or hostile request is answered, not fatal

- **WHEN** a caller sends a line that is not JSON, a payload that is valid JSON but not an object,
  or a request whose handling raises an error the tool did not anticipate
- **THEN** the server returns the corresponding protocol error and keeps serving, so the next
  caller's valid request is still answered
- **AND** a caller-supplied size — a simulation duration, a trajectory or step count, a grid
  length, a network's node count — is bounded at the tool boundary and refused when it exceeds the
  ceiling, rather than occupying the server indefinitely

#### Scenario: A call the schema does not describe is refused, not answered

- **WHEN** a caller sends positional params, arguments that are not an object, an argument whose
  type the tool's published schema does not declare, or a paper lookup naming no identifier
- **THEN** each is refused with a message naming what was wrong — the published input schema is
  enforced, not merely documented
- **AND** none is answered with a lookup result, since an empty list or a null for a malformed
  question reads as a fact about the paper rather than about the call

### Requirement: Work handoff is lease-aware

The server SHALL let an agent claim and progress catalog work without colliding with other
agents or humans.

#### Scenario: Agent claims and reports work

- **WHEN** an agent requests the next work item and later reports progress or an outcome
- **THEN** the server leases the item to that agent, accepts its progress, and releases or
  advances the item accordingly
- **AND** an expired or abandoned lease returns the item to the queue with partial work
  preserved

#### Scenario: A finished reproduction leaves the queue

- **WHEN** an agent records that a claimed entry is done, naming the certificate it published
- **THEN** the entry advances to the lifecycle state that certificate's verdict implies, the
  moves are recorded with the recording agent and the reason, and the lease is dropped
- **AND** the entry is no longer offered as claimable work, so a completed unit is never
  handed out again at lease expiry

#### Scenario: A recorded outcome cannot exceed its evidence

- **WHEN** an agent records a result
- **THEN** the outcome state is derived from the named certificate's own verdict rather than
  asserted by the caller
- **AND** a certificate that does not positively identify the entry's paper is refused — an
  identity that cannot be compared is not an identity that agrees — so one paper's result is
  never filed under another's accession
- **AND** a certificate that has since been superseded is refused, because the correction, not
  the stale verdict, is the current answer
- **AND** the reply carries the blind entry view, never a ground-truth label

#### Scenario: An effectful call that cannot be persisted is rolled back

- **WHEN** a mutation succeeds in memory but fails to reach durable storage
- **THEN** the change is undone and reported as an error, so the served catalog never runs ahead
  of the one on disk

#### Scenario: A blocked entry returns to the queue when its missing input arrives

- **WHEN** the input a blocked entry was waiting on becomes available and a requester says so
- **THEN** the entry returns to `queued` with the reason recorded, and becomes claimable again
- **AND** an entry that is not blocked is refused rather than silently moved

### Requirement: Parity with the human surface

The MCP server SHALL not become a divergent second implementation of Reprolith's contracts.

#### Scenario: Same verdicts through either surface

- **WHEN** the same entry is inspected through the repository and through the MCP server
- **THEN** the verdicts, certificates, and states reported are the same
- **AND** the server exposes no verdict-producing behavior that the core engine does not
  itself define
