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

### Requirement: Runnable over the MCP surface

An author or their agent SHALL be able to run the check through the same read-only MCP surface as
the rest of the engine.

#### Scenario: Pre-submission check over MCP

- **WHEN** the pre-submission tool is called for a certificate digest over the MCP server
- **THEN** it returns the author-facing report — readiness, per-claim verdicts, prioritized fix
  list, and the scope statement — and changes no state
- **AND** the scope statement travels with the report and cannot be emptied
