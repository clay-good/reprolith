# github-collaboration Specification

## Purpose

This capability binds Reprolith's collaboration surfaces to GitHub, so contributing needs no
new accounts or infrastructure: verification-queue items become issues, expert corrections and
new contributions become pull requests, and the deterministic gates become required checks.
GitHub is where the human-in-the-loop actually happens — the place experts validate Reprolith's
judgment and keep the dataset fresh, with every contribution attributed and reviewed.

## What carries each requirement today

One module in this repository reaches GitHub — `reprolith.issue_filing`, through the `gh` command
and only when a person asks it to. The gates are real — CI runs `ruff`, `mypy`, `pytest`, and
`openspec validate` on every push, and every contribution goes through a pull request — and the
*issue* half of this capability is now machinery a person starts, rather than work a person does:

- *Verification-queue items are GitHub issues.* Carried since 2026-10-10 by
  `reprolith issue-file --apply`, which opens an issue for every pending item that no issue asks
  about and creates the labels it needs. Three things it is held to, each by a test in
  `tests/test_issue_filing.py`, because filing is the first thing here that acts on somebody
  else's record and the harmful direction is a second issue for a question already asked. **A
  question is asked once:** the plan is the reconciliation's own `unfiled` list, and an item is
  unfiled only while its fingerprint is on no issue at all, open *or closed* — so an issue a
  maintainer closed stays a divergence for a person to read, and a second run files nothing.
  **It reads the issues itself:** `--apply` refuses a file, which is a snapshot, and refuses a
  fetch that came back full, since `gh issue list` stops at its limit silently (at thirty, by
  default — the fetch this section and `CONTRIBUTING.md` documented until now asked for no more)
  and every issue past the cut would read as never filed. **It stops at the first failure** and a
  re-run is safe for the first reason. It opens and labels; it closes, reopens and relabels
  nothing, so reconciling still does not resolve. Without `--apply` it is a dry run over a file
  and touches no network.

  What it does **not** do is run by itself. The scenario below says an issue is opened "when the
  verification queue creates an item"; the queue is derived on every call and creates nothing, so
  the moment is a person's — the command, or the *Verification issues* workflow, which has no
  trigger but a click and is a dry run unless told otherwise. That is deliberate rather than
  unfinished: an issue asks a stranger for their time, and a push that reworded an assumption
  would otherwise be what asked. **As of 2026-10-10 no issue has been filed in this repository**;
  `reprolith issue-file` names the pending items that are owed one.

  What a person opening one by hand has to write is nothing either:
  `reprolith verification-issue <item-id>` prints the whole issue — the title, the body with every
  field the template asks for, and the three labels the requirement names (model class, impact
  rank, pending-verification status), which the template file itself left empty. It refuses an
  engine-limit item by name, because no expert decision closes one and filing it asks a stranger
  for a judgment that cannot help. It touches no network: it prints, and a person or
  `gh issue create --body-file -` files it. It is on both surfaces (MCP: `verification_issue`),
  because a command that reads this repository and exists on only one of them is how the two
  drift.

  Since 2026-09-09 it also prints the decision record itself — the `datasets/verification_decisions.json`
  entry with `item_id` and `question_fingerprint` filled and the human fields blank. The gap it
  closes is small and exact: the issue asked an expert to write a record and the record's shape
  lived in `CONTRIBUTING.md`, so the one thing a reader of the issue could not do without leaving it
  was the thing it asks them to do. `kind` is blank rather than defaulted to `confirm`, which in an
  issue that has just argued for an estimate would be a nudge to agree with it, and every blank
  field is refused by name by the loader rather than filled with a default.

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
  report by having drifted. With `issue-file` it is one of two commands on the terminal that read
  this repository and have no MCP tool: the server holds no GitHub credentials and no issue list, so the tool would
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

The remaining gap is the trigger, not the machinery: an item nobody has run `issue-file` for has no
issue. That cannot produce a wrong certificate — an unescalated uncertainty still travels as a
load-bearing assumption, which downgrades the verdict on its own — and `issue-reconcile` reports
every such item by name.

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
