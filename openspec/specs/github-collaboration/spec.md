# github-collaboration Specification

## Purpose

This capability binds Reprolith's collaboration surfaces to GitHub, so contributing needs no
new accounts or infrastructure: verification-queue items become issues, expert corrections and
new contributions become pull requests, and the deterministic gates become required checks.
GitHub is where the human-in-the-loop actually happens — the place experts validate Reprolith's
judgment and keep the dataset fresh, with every contribution attributed and reviewed.

## What carries each requirement today

No code in this repository touches the GitHub API. The gates are real — CI runs `ruff`, `mypy`,
`pytest`, and `openspec validate` on every push, and every contribution goes through a pull
request — but the *issue* half of this capability is carried by people, not machinery:

- *Verification-queue items are GitHub issues.* Still opened by hand, and the issue template says
  so in its own text. What a person opening one has to write, though, is now nothing:
  `reprolith verification-issue <item-id>` prints the whole issue — the title, the body with every
  field the template asks for, and the three labels the requirement names (model class, impact
  rank, pending-verification status), which the template file itself left empty. It refuses an
  engine-limit item by name, because no expert decision closes one and filing it asks a stranger
  for a judgment that cannot help. It touches no network: it prints, and a person or
  `gh issue create --body-file -` files it. It is on both surfaces (MCP: `verification_issue`),
  because a command that reads this repository and exists on only one of them is how the two
  drift. **Nothing files the issue** — that half is still uncarried.

  One field is answered by saying it cannot be: the template requires the section, equation, table
  or figure a value comes from, and Reprolith records that for a *claim* and not for an
  *assumption*, whose basis is a reason rather than a place. The generated body says so and gives
  the basis and the assumption id to grep for, rather than filling a required field with a
  plausible location.
- *Queue and issue stay in sync.* Carried since 2026-09-06: `reprolith issue-reconcile <issues>`
  reads what `gh issue list --json number,title,state,labels,body` prints and reports where the
  two sides disagree. Before it, the drift was invisible in both directions and each direction
  had its own cause: the queue is *derived* from the standing certificates on every call, so an
  item disappears the moment its certificates are superseded and its issue keeps asking a
  question nothing rests on; and an issue can be closed, relabelled, or never opened at all with
  nothing in this repository able to see it. It matches on the question fingerprint the generated
  body carries rather than on the title or the item id, for the reason the decision record does:
  a reworded question is a different question, and an issue still asking the old one has diverged
  rather than stayed attached. Two properties are what make it worth running rather than
  believing. It **reconciles and does not resolve** — nothing here closes an issue, reopens one,
  or edits the queue, because a divergence is a question about which side is wrong and both sides
  are somebody's record. And it is keyed on the label *or* the fingerprint, since keying on the
  label alone would let a relabelled issue — the drift it exists to report — disappear from the
  report by having drifted. It is the one command on the terminal that reads this repository and
  has no MCP tool: the server holds no GitHub credentials and no issue list, so the tool would
  have to be handed the same file, and `docs/mcp-server.md` says so in its own row.
- *An expert's decision is the record.* Carried since 2026-09-06:
  `datasets/verification_decisions.json` holds the decision, its author, its rationale and where it
  was made, joined to the derived queue by `queue_report`, so an answered item stops asking on
  every surface. What it deliberately does **not** do is lift the dependent certificates'
  qualification — that is a re-issue, not an answer — and the record is captured by a pull request
  rather than read out of the issue by any machinery.
- *An agent can query collaboration state over MCP.* This is carried now. The `verification_queue`
  tool returns what is pending human validation, split into what an expert can decide and what
  only this engine's development can close, ranked by how many standing certificates rest on it.
  This section said there was no tool for it, which stopped being true the morning the tool
  landed — the sentence is here rather than deleted because the gap it describes was real, and a
  spec that quietly drops what it once admitted is worth less than one that says when it closed.

The remaining gap — nothing files an issue — cannot produce a wrong certificate — an unescalated uncertainty still travels
as a load-bearing assumption, which downgrades the verdict on its own — but a reader should not
take the issue-filing requirement below as implemented machinery.

## Requirements

### Requirement: Verification-queue items are GitHub issues

Each load-bearing, low-confidence item the engine escalates SHALL surface as a structured GitHub
issue an outside expert can act on.

#### Scenario: Opening a queue issue

- **WHEN** the verification queue creates an item
- **THEN** a GitHub issue is opened from a structured template carrying the specific question,
  the source context, Reprolith's best estimate and reasoning, and what depends on it
- **AND** the issue is labelled with its model class, its impact rank, and a pending-verification
  status

#### Scenario: Queue and issue stay in sync

- **WHEN** a queue item's state changes, or its issue is closed or relabelled
- **THEN** the queue state and the issue state are reconciled so neither silently diverges from
  the other

#### Scenario: Expert acts in the issue

- **WHEN** an expert confirms, corrects, or rejects within the issue
- **THEN** the decision, its author, and its rationale are captured as the verification-queue
  decision of record, retaining Reprolith's original estimate

### Requirement: Corrections and contributions are pull requests

Any change to the dataset — a corrected extraction, a new candidate paper, a new ground-truth
label — SHALL enter through a pull request, so it is reviewed, gated, and attributed.

#### Scenario: A correction becomes a PR

- **WHEN** a confirmed correction changes a dossier value, an assumption, or a tolerance
- **THEN** the change is proposed as a pull request that references the originating issue, rather
  than edited silently
- **AND** merging it triggers re-verification of dependent entries per the verification-queue and
  certificate contracts

#### Scenario: An outside contribution is welcomed and gated

- **WHEN** a contributor opens a pull request adding a candidate, a label, or a fix
- **THEN** the same deterministic gates that govern autonomous changes run as required checks
  before it can merge
- **AND** the contribution is credited to its author on merge

### Requirement: Deterministic gates are required checks

The quality bar SHALL be enforced by GitHub, not by trust, so no unverified change reaches main.

#### Scenario: Gates block a merge

- **WHEN** a pull request would land on the main branch
- **THEN** spec validation, tests, oracle self-checks, and the determinism check must pass as
  required status checks before merge is allowed
- **AND** a change that weakens a certificate scope flag, assumption-qualification, or blind
  self-validation fails these checks

#### Scenario: Autonomous and human changes meet the same bar

- **WHEN** either the autonomous build loop or a human contributor lands a change
- **THEN** both are subject to the identical required checks, so autonomy never enjoys a lower
  standard than a human PR

### Requirement: Attribution and provenance are preserved

Every contribution SHALL carry durable credit and traceability, because collaborators are earned
by making their work visible and their corrections consequential.

#### Scenario: Durable credit

- **WHEN** a contribution or verification is merged or recorded
- **THEN** its GitHub author is retained as the contributor of record and is discoverable from the
  affected entries and certificates

### Requirement: Collaboration state is readable over MCP

An agent using Reprolith SHALL be able to see what is pending human validation, so it can factor
open questions into its own work.

#### Scenario: Agent reads pending validations

- **WHEN** an agent queries collaboration state through the MCP server
- **THEN** it can see the open verification issues, their impact rank, and their status, without
  the ability to resolve them on a human's behalf
