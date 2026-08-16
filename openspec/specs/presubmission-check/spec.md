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
- **AND** a fully reproduced certificate produces an empty fix list

#### Scenario: Ready-to-submit is honest

- **WHEN** the report states whether the model is ready to submit
- **THEN** it reports ready only for an unqualified full reproduction, and otherwise states it is
  not yet ready and points to the fix list
- **AND** the ready-to-submit signal can never be green while any claim is partial, failed,
  not-evaluable, or assumption-qualified

### Requirement: Runnable over the MCP surface

An author or their agent SHALL be able to run the check through the same read-only MCP surface as
the rest of the engine.

#### Scenario: Pre-submission check over MCP

- **WHEN** the pre-submission tool is called for a certificate digest over the MCP server
- **THEN** it returns the author-facing report — readiness, per-claim verdicts, prioritized fix
  list, and the scope statement — and changes no state
- **AND** the scope statement travels with the report and cannot be emptied
