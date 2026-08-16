# constraint-based-class Specification

## Purpose

This is Reprolith's second fully supported model class: **constraint-based (flux-balance /
COBRA) metabolic models**. It exists to prove the engine generalizes — its oracle shares
nothing with PK/PD curve-matching. A constraint-based model has no time axis; its reproducible
result is an optimization outcome (an objective value, a flux distribution, an essentiality
call) checked with linear programming. If the same dossier → reconstruction → oracle →
certificate abstractions carry this class, they are general, not PK/PD-specific.

## Requirements

### Requirement: Constraint-based dossier shape

A constraint-based dossier SHALL capture the elements that determine an optimization outcome,
so a reproduction is fully specified without the paper.

#### Scenario: Structural elements

- **WHEN** a paper is ingested as `constraint-based`
- **THEN** the dossier records the reaction stoichiometry, the reaction flux bounds, the
  objective (e.g. a biomass or production reaction and its direction), the gene–protein–reaction
  associations, and the growth/medium constraints under which each claim holds
- **AND** each element cites its source location

#### Scenario: Medium and bounds are treated as load-bearing

- **WHEN** the objective value or a flux depends on the exchange/medium bounds
- **THEN** the medium definition and exchange bounds are recorded as first-class dossier
  elements, and any unstated bound is recorded as a gap
- **AND** because an unstated medium silently changes the answer, such a gap is marked
  high-impact

#### Scenario: An objective the oracle cannot honour is refused, not silently re-signed

- **WHEN** an ingested model declares an objective the oracle does not support — today, a
  minimizing objective, while every analysis in this class assumes a maximum
- **THEN** ingestion refuses the model and names the unsupported feature, rather than flipping the
  objective's sign to reuse the maximizing solver and reporting an optimum whose sign no longer
  matches the value the paper reported
- **AND** the refusal is preferred because the alternative certifies a genuinely reproducible model
  as failed, and inverts the deletion and robustness analyses that assume a positive optimum

### Requirement: Standard constraint-based reproduction targets

The oracle for this class SHALL evaluate the results constraint-based papers actually report,
using the field's standard analyses.

#### Scenario: Objective value reproduction

- **WHEN** a claim is a reported optimal objective value (e.g. a maximal growth rate or
  production flux under a stated medium)
- **THEN** the oracle solves the reconstructed model under the claim's constraints and compares
  the optimal objective to the reported value within tolerance

#### Scenario: Flux, variability, and essentiality reproduction

- **WHEN** a claim is a reported flux distribution, a flux-variability range, or an
  essentiality result (genes or reactions whose deletion abolishes the objective)
- **THEN** the oracle reproduces it with the corresponding standard analysis (flux-balance,
  flux-variability, or systematic deletion) and compares within tolerance
- **AND** the analysis used is recorded so the comparison is auditable

### Requirement: FROG report as the deterministic fingerprint

The class SHALL produce and compare a standardized reproducibility fingerprint, so a verdict
is solver-independent and portable.

#### Scenario: Fingerprint generation and comparison

- **WHEN** a constraint-based reconstruction is verified
- **THEN** the oracle generates a standardized fingerprint covering the objective value, the
  flux-variability bounds, and the reaction- and gene-deletion outcomes
- **AND** where the paper or its curation provides such a fingerprint, the verdict is the
  comparison of fingerprints rather than of a single number

### Requirement: Alternate optima are handled honestly

The class SHALL not report a flux mismatch as a failure when the mismatch is an artifact of
non-unique optima.

#### Scenario: Objective unique, fluxes possibly not

- **WHEN** the reported optimal objective is reproduced but an individual reported flux differs
- **THEN** the oracle checks whether the reported flux is attainable at the same optimum
  (e.g. within its flux-variability range) before judging
- **AND** a flux that is consistent with an alternate optimum is reported as
  optimum-equivalent, not as a failure

#### Scenario: Solver tolerance is declared

- **WHEN** a numerical comparison is made
- **THEN** the applied solver/optimality tolerance is recorded as the claim's tolerance, with
  its provenance, exactly as other classes declare theirs

### Requirement: Known constraint-based failure modes are first-class

The oracle SHALL recognize the recurring reasons constraint-based reproductions fail.

#### Scenario: Catalogued root causes

- **WHEN** a constraint-based claim is `partial` or `failed`
- **THEN** the root cause is selected from a maintained set that includes at least: unspecified
  or ambiguous medium/exchange bounds, ambiguous biomass/objective definition, missing or
  inconsistent gene–reaction associations, alternate-optima flux ambiguity, and solver
  sensitivity
- **AND** a failure fitting none of these is recorded as uncategorized and flagged to extend
  the set

### Requirement: Generalization is demonstrated, not assumed

Adding this class SHALL reuse the shared engine contracts unchanged, and any contract that
cannot absorb it SHALL be surfaced rather than forked.

#### Scenario: Shared contracts carry the new class

- **WHEN** a constraint-based entry moves through the pathway
- **THEN** it uses the same catalog lifecycle, dossier/claims model, assumption-recording,
  certificate format, and scope flag as the PK/PD class, specialized only in its structural
  elements, reproduction targets, tolerances, and failure modes
- **AND** if a shared contract cannot express something this class needs, that gap is raised
  as a change to the shared spec, not worked around inside this class

### Requirement: Self-validation against known constraint-based reproducibility

Before this class's verdicts are trusted, the pathway SHALL be measured against entries whose
reproducibility is independently known.

#### Scenario: Blind agreement measurement

- **WHEN** the constraint-based pathway is evaluated on entries carrying ground-truth
  reproducibility labels (e.g. fingerprint-curated repository models)
- **THEN** Reprolith produces verdicts blind to the labels and reports agreement, disagreement,
  and the nature of each disagreement
- **AND** a disagreement is treated as a defect to investigate, not silently accepted
