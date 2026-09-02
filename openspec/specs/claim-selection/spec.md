# claim-selection Specification

## Purpose

A paper publishes more results than a reproduction attempt can always afford to target. Choosing
which of them to reproduce is a decision about what evidence a certificate will and will not rest
on, and until it has a surface it is made silently — by whoever writes a claims dataset — with no
statement of what was left out or why.

Claim selection is that surface. It answers one question: **given a budget, which of this paper's
claims should a reproduction attempt target?** It answers it at the level of the *set*, because a
paper's claims are not independent evidence — several panels of one figure can rest on the same
parameters, the same model components, and the same unstated assumption, so reproducing all of
them witnesses that machinery repeatedly and the rest of the model not at all.

A selection is a plan, never a result. It runs no model, reaches no verdict, and issues no
certificate; a claim it does not select is neither reproduced nor unreproduced, only unattempted.

## Requirements

### Requirement: Selection maximizes independent evidential value across the set

Selection SHALL choose the set of claims that maximizes evidential value net of what the chosen
claims share, rather than taking the best-scoring claims one at a time.

#### Scenario: The highest-scoring claims are near-duplicates of each other

- **WHEN** a paper's highest-scoring targetable claims rest on the same parameters, model
  components, and upstream assumptions as each other, and the budget cannot cover every claim
- **THEN** the selected set does not consist of those claims alone: at least one of them is
  exchanged for a claim resting on machinery no selected claim has already witnessed
- **AND** the selected set scores higher on the stated objective than the set a one-at-a-time
  ranking produces, and witnesses at least as many distinct model elements

#### Scenario: The claims share nothing

- **WHEN** no two candidate claims share any element of what they rest on
- **THEN** the selection is the one a ranking produces, because there is no shared evidence for a
  set-level objective to act on

#### Scenario: A claim's own worth is not discarded

- **WHEN** several claims rest on the same machinery
- **THEN** the selection retains one of them rather than dropping the group, so the budget is
  never spent avoiding a paper's most valuable result

### Requirement: Only claims a verdict can come from are candidates

The candidate pool SHALL be the paper's targetable claims.

#### Scenario: A non-targetable result is retained but never selected

- **WHEN** a dossier retains a result the oracle cannot check, such as a schematic figure
- **THEN** it is not offered as a candidate, so no budget can be spent on a claim no verdict can
  ever come from

### Requirement: What a claim rests on is recorded, never inferred

A claim's footprint — the parameters, model components, and upstream assumptions its verdict
depends on — SHALL be an extracted, recorded element of the dossier, and SHALL NOT be derived from
the claim's own free-text description.

#### Scenario: An uncharacterized claim is not penalized for an unmeasured overlap

- **WHEN** a candidate claim records no footprint
- **THEN** it is charged no overlap against any other claim, so a selection never drops a claim on
  the strength of a redundancy nobody measured

#### Scenario: A footprint naming something the dossier does not record is surfaced

- **WHEN** a claim's footprint names an element the dossier records no parameter, initial
  condition, state variable, equation target, or gap for
- **THEN** the claim is still a candidate — a dossier adopted from a shipped model file keeps its
  structure in the artifact — and the report names the unanchored elements, so a reader can tell a
  footprint anchored in recorded structure from a bare assertion

### Requirement: A selection reports what it could not do

The selection report SHALL state the limits of the answer it gives, so a selection can never be
read as an analysis that was not performed.

#### Scenario: Nothing was characterized

- **WHEN** no candidate claim records a footprint
- **THEN** the report states that nothing was chosen for its independence and that the selection
  is the one a ranking produces

#### Scenario: Only some claims were characterized

- **WHEN** some but not all candidate claims record a footprint
- **THEN** the report states how many did, and that the rest competed as if independent of
  everything because no overlap was measured

#### Scenario: There was nothing to select from

- **WHEN** the paper records no targetable claim at all
- **THEN** the report says so, rather than reporting that the budget afforded nothing — a larger
  budget fixes one of those and not the other

### Requirement: The one-at-a-time alternative travels with the answer

Every selection report SHALL carry the set a one-at-a-time ranking would have chosen, scored on the
same objective.

#### Scenario: A reader can see what the selection changed

- **WHEN** a selection is reported
- **THEN** the ranking's set, its score, and its coverage are reported beside the chosen set's,
  and the report states whether the two differ

### Requirement: A selection is not a verdict and never becomes one

Selection SHALL NOT run a model, compute a verdict, or alter a certificate.

#### Scenario: The report says what it is

- **WHEN** a selection is reported at any surface
- **THEN** it carries a statement that it is a plan for what to attempt, that no model was run,
  and that an unselected claim is unattempted rather than unreproduced

### Requirement: The selection is deterministic and explainable

The same paper, budget, and inputs SHALL always produce the same selection, and the report SHALL
carry the numbers that produced it.

#### Scenario: Extraction order does not change the answer

- **WHEN** the same claims are presented in a different order
- **THEN** the selected set is identical

#### Scenario: The score can be recomputed from the report

- **WHEN** a selection is reported
- **THEN** it names the chosen set's gross value, the overlap charged against it, the resulting
  score, the budget spent, and the distinct model elements witnessed

#### Scenario: Equal evidence for less budget wins

- **WHEN** two candidate sets carry the same independent evidential value and one spends less of
  the budget
- **THEN** the cheaper set is selected

### Requirement: Reachable from both surfaces

Claim selection SHALL be reachable from the human CLI and as a read-only MCP tool, and both SHALL
return the same answer for the same repository state (spec: `mcp-server` — parity).

#### Scenario: A paper with no dossier

- **WHEN** a selection is requested for an accession the repository holds no dossier for
- **THEN** the surface says so and reaches no selection

#### Scenario: A budget that is not a budget

- **WHEN** a selection is requested with a budget that is zero, negative, or absurd
- **THEN** the request is refused with a message, and no selection is reported
