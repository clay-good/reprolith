# claim-selection (delta: budgeted-claim-selection)

## ADDED Requirements

### Requirement: A footprint may be derived from the model's own structure

A claim's footprint MAY be derived from the reconstructed model — the parameters, species, and
compartments its target quantity transitively depends on, together with the gaps a reconstruction
must close to run it — and the derivation SHALL be recorded, because a footprint read from a model
and one asserted by a curator do not carry the same weight.

#### Scenario: A structural footprint is a measurement, not a guess

- **WHEN** a claim's target resolves to an element of the reconstructed model
- **THEN** its footprint is the transitive closure of what that element's rate law depends on, plus
  every gap that must be closed to run it
- **AND** the report states that the footprint was derived from model structure rather than
  extracted from the paper

#### Scenario: A target the model does not resolve stays uncharacterized

- **WHEN** a claim names a quantity the reconstructed model has no element for
- **THEN** no footprint is derived for it, and it is counted as uncharacterized in the report
  rather than given a footprint the model does not support

#### Scenario: Free text is still never a source of dependencies

- **WHEN** a footprint cannot be derived from model structure
- **THEN** it is not derived from the claim's `quantity` or `conditions` text under any
  circumstances
