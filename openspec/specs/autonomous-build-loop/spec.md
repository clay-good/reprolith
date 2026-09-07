# autonomous-build-loop Specification

## Purpose

The autonomous build loop turns a single stated goal into continuous, self-verifying progress.
Pointed at a goal (e.g. "bring the constraint-based class to its self-validation gate"), a
coding agent selects the next best unit of work, does it, proves it against deterministic
gates, records it, publishes it, and continues — escalating only what it cannot safely decide.
It is how Reprolith is built and operated with a human setting direction rather than driving
every step. Its defining discipline: it advances on everything it is confident about and never
silently commits a low-confidence, load-bearing choice.

## What carries each requirement today

The loop is a *process* a coding agent runs, not a module. No code drives it, so most
requirements below are carried by the agent and are checkable only in the record it leaves —
the git history, the certificates, and the CI runs. Two are carried by code and genuinely
enforced: the acceptance gates (CI runs `ruff`, `mypy`, `pytest`, and `openspec validate
--specs --strict` on every push) and the honesty invariants (derived in
`reprolith.certificate.derive_overall`, re-derived again when a stored certificate is loaded).

A third is carried by code as of 2026-09-06: *load-bearing uncertainty is escalated*.
`reprolith.queue_from_certificates` opens a verification-queue item for every load-bearing
assumption on every standing certificate, and `reprolith verification-queue` (MCP:
`verification_queue`) is the read. Before it, the queue's shapes existed and nothing built an
item — four published certificates cited `verify:time-unit-of-the-Zake2021-deposits` and a reader
following that citation found nothing. Two properties are worth stating here because they are
what make the escalation total rather than selective: it changes no verdict (a load-bearing
assumption already withholds a clean pass through `derive_overall`, so opening its item adds a
route to the question and nothing else), and items are keyed by the *question* rather than by the
assumption's own id, so one solver limitation asked by three claims is one item with three
dependents. The queue is derived from the ledger on every call, never stored, so it cannot drift
from the certificates it describes.

It reports in two parts, because escalating everything and then ranking it together overstated
what escalation buys: some of the load-bearing assumptions on today's certificates are this
engine's own limits — the ensemble the stochastic class drew — and no expert decision closes one.
`Assumption.author_can_close` already carried that distinction for the author-facing fix list, and
it carries it here. The split is three of seven today and it *moves as the engine changes*: the
spatial wall sat in the engine's half until a claim could carry the boundary its source states,
and the flag stayed False for a day after that, filing a question somebody could answer under
"not waiting on anyone". A count written into prose here would have gone stale the same way, so
the surfaces report it and this says only that both halves exist.

*Goal-directed work selection* gained its evidence at the same time, though the selecting is
still the agent's. `backlog_health` now reports `blocked_on`: what each blocked entry is waiting
on, counted and ranked by how many entries the capability would release. On the shipped catalog
that turns "27 blocked, 0 claimable" — a depth, and a dead end — into "27 blocked, all on one
missing input", which is the sentence the requirement below asks an agent to be able to write
about why it chose one unit over the alternatives.

The *decision* half became code-carried on 2026-09-06 as well. `VerificationQueue.decide` and
`reverify_dependents` were live APIs that could not be reached from outside one Python process,
because the queue is derived on every call and stored nowhere — so a decision made against it
evaporated with the interpreter. Decisions are committed data now
(`datasets/verification_decisions.json`, read by `reprolith.decisions.load_decisions`), joined to
the derived queue by `queue_report`, so an item somebody has answered stops asking on all three
surfaces at once. Three properties keep the record from overstating itself: a decision never lifts
a certificate's qualification (that requires re-issuing the dependents, and it is mechanically
evident — a re-issued dependent's assumption is no longer load-bearing, so its item would not be
derived at all); competing judgments are retained with a `disputed` flag rather than resolved; and
every record carries the fingerprint of the question as it was answered, so a decision under an
author-named id whose wording later changed is reported as stale and its item returns to pending.
This repository records no decision yet, and the report says so **from the file** rather than from
a constant that could outlive it.

The step after became half code-carried on 2026-09-06 as well. A merged correction still triggers
no re-certification on its own — `reverify_dependents` implements the re-issue and a person has to
call it, because re-running a class means its models, its scripts and its solver, none of which a
decision file carries. What *was* missing beside it is the question a person would have to answer
before calling it at all: which standing certificates the correction reaches.
`reprolith recertification-due` (MCP: `recertification_due`) answers it, and answers the other
half of freshness with it — a certificate naming an older revision of the judging code states a
number the current code would not produce, which `tests/test_pins.py` held the *committed* corpus
to and no surface could be asked about any other. Three distinctions are what make it a report
rather than a list: a **confirmation** owes nothing (the value is still one Reprolith chose, the
numbers do not move, and the qualification stands either way), a **rejection** owes a re-run it
cannot have (it supplies no replacement value, so its dependents are blocked rather than due), and
a certificate whose class the surface cannot name is reported as unchecked rather than passed —
the read surface spells the constraint-based class with a hyphen and the pin map with an
underscore, and a label falling through there would take a whole class out of the check while the
report still read as complete.

*Repeated failure is parked* became code-carried on 2026-09-06. Before it there was no attempt
counter anywhere, and the gap was worse than an absent number: `release_lease` records nothing and
an abandoned claim ends by lease expiry, which is only the clock passing, so a claim that achieved
nothing left no trace of any kind. The entry was offered again the instant its lease lapsed — and
since the pool is ranked by readiness first, an *easy* entry that defeats everyone who takes it sat
at the head of the queue in front of every agent that asked for work, forever. `CatalogEntry.lease`
now records the claim (`Attempt`), `attempts_without_progress` reads the trailing run of claims
during which no transition was recorded, and `Catalog.claimable` leaves such an entry out after
three. Parking is *derived* rather than latched, so any transition — including one into `blocked` —
clears it with nothing having to lower a flag; the entry is out of the automatically-offered pool
and not out of reach (`include_parked`), because no surface performs the quarantine that is the
state machine's only other way out of `queued`, and an unreachable entry would be a permanent
wedge; and both `claim_work`'s refusal and `backlog_health` name what was parked and why, since a
pool that quietly shrinks is the dead end this surface has had to talk its way out of once already.

*Defined stopping points* gained its evidence on 2026-09-06 too. The stop condition the spec
states — "the publishable backlog is exhausted, or further progress is gated entirely on open
escalations" — had become machine-readable in pieces and was assembled by nobody, so an agent
deciding to stop called three reads and merged them by eye, which made "the backlog is exhausted"
an assertion rather than an answer. `reprolith loop-status` (MCP: `loop_status`) answers it:
`stop_reason` is `None` exactly when a requester would be handed something, and otherwise names
which of four situations holds — everything blocked on one input, everything parked, entries that
carry no accession, or a backlog genuinely empty — since what would lift each is entirely
different. It carries the parks with their diagnoses and the escalations split into what an expert
can decide and what only this engine can, which is what a loop needs to know whether a gate is one
it could lift itself. What it does **not** report is the spec's "what it accomplished": that is the
git history, and a field summarizing a run would invent a record this package does not keep, so it
counts what stands and says so.

What remains agent-carried cannot produce a wrong certificate — an unescalated uncertainty still
travels as a load-bearing assumption, which downgrades the verdict on its own — but the
requirements below are stated as goals, and a reader should not take the agent-carried ones as
implemented machinery.

## Requirements

### Requirement: Goal-directed work selection

The loop SHALL, given a goal, choose the next unit of work that best advances it, and SHALL be
able to explain the choice.

#### Scenario: Selecting the next unit

- **WHEN** the loop is given a goal and asked to proceed
- **THEN** it selects the next unit of work — a build slice (implement a spec or task) or an
  operation slice (reproduce catalog entries) — that most advances the goal under the backlog
  prioritization rules
- **AND** it can state why that unit was chosen over the alternatives

#### Scenario: A unit is a slice, not the whole goal

- **WHEN** a goal is larger than one safe change
- **THEN** the loop decomposes it into slices small enough to verify and publish independently,
  rather than attempting the whole goal in one step

### Requirement: Deterministic acceptance gates before publishing

The loop SHALL publish only work that passes Reprolith's deterministic gates, so autonomy never
lowers the quality bar.

#### Scenario: Gates must pass to land

- **WHEN** the loop finishes a slice
- **THEN** it runs the applicable deterministic gates — spec validation, tests, the reproduction
  oracle's self-checks, and the determinism check — before publishing
- **AND** a slice that fails any gate is not published; it is revised or parked with the failure
  recorded

#### Scenario: Honesty invariants cannot be weakened

- **WHEN** a slice would alter certificate scope, assumption-qualification, or blind
  self-validation
- **THEN** the loop treats weakening any of these invariants as an automatic gate failure, never
  a permitted change

### Requirement: Best-estimate-and-escalate, never block the whole loop

The loop SHALL record a best estimate for anything it is uncertain about, escalate the
load-bearing cases, and keep making progress on everything independent of them.

#### Scenario: Load-bearing uncertainty is escalated, not guessed-through

- **WHEN** proceeding would require committing a low-confidence value or judgment that plausibly
  changes an outcome
- **THEN** the loop records its best estimate with a confidence signal and opens a verification-
  queue item for it, rather than silently adopting it
- **AND** any result that depends on that estimate is qualified as resting on an unverified value

#### Scenario: Independent work continues

- **WHEN** one unit is blocked on an open escalation
- **THEN** the loop continues with other units that do not depend on the unresolved item
- **AND** it does not stall the entire goal on a single uncertainty

### Requirement: Every autonomous change is auditable

The loop SHALL leave a trail a human can review, so unattended progress never becomes opaque.

#### Scenario: Traceable commits

- **WHEN** the loop publishes a slice
- **THEN** the change records the goal it served, the unit it completed, the gates it passed, and
  any verification-queue items it opened
- **AND** a reviewer can reconstruct what the loop did and why without reading its internal state

#### Scenario: Human can steer or stop at any time

- **WHEN** a human changes the goal, pauses the loop, or overrides a decision
- **THEN** the loop honors it at the next slice boundary and records the intervention

### Requirement: Safe continuation and stop conditions

The loop SHALL keep going while there is gated, publishable work, and SHALL stop or pause
deliberately rather than spinning.

#### Scenario: Repeated failure is parked, not retried forever

- **WHEN** a unit fails its gates repeatedly without progress
- **THEN** the loop parks it with a diagnosis and moves on, rather than looping on it
  indefinitely

#### Scenario: Defined stopping points

- **WHEN** the goal is met, the publishable backlog is exhausted, or further progress is gated
  entirely on open escalations
- **THEN** the loop stops with a summary of what it accomplished, what it parked, and what it
  escalated
