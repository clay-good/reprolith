# claim-selection (delta: budgeted-claim-selection)

## ADDED Requirements

### Requirement: A footprint may be derived from the model's own structure

A claim's footprint MAY be derived from the reconstructed model — the parameters, species, and
compartments its target quantity depends on, out to a stated depth — and every footprint SHALL
record how it was arrived at, because a footprint read from a model and one asserted by a curator
do not carry the same weight and are indistinguishable once written down.

#### Scenario: A structural footprint is a measurement, not a guess

- **WHEN** a claim's target resolves to an element of the reconstructed model
- **THEN** its footprint is what that element depends on out to the derivation's stated depth,
  read from the model's rate laws, rules, initial assignments and compartments
- **AND** the report states that the footprint was derived from model structure rather than
  stated by a curator

  The transitive closure is deliberately not the rule: on a strongly-connected model it returns the
  whole model for every claim, so every pair overlaps completely and the selection reports that
  reproducing any one claim makes every other worthless — a statement about the walk, not the
  paper. The depth is a measured choice and belongs to the derivation, which states it.

#### Scenario: A target the model does not resolve stays uncharacterized

- **WHEN** a claim names a quantity the reconstructed model has no element for
- **THEN** no footprint is derived for it, and it is counted as uncharacterized in the report
  rather than given a footprint the model does not support

#### Scenario: A footprint that does not say where it came from is refused

- **WHEN** a claim records a footprint without recording its origin
- **THEN** it is refused, on the path that builds a dossier and on the path that loads one
- **AND** a report over footprints of both kinds states how many of each it weighed

#### Scenario: Free text is still never a source of dependencies

- **WHEN** a footprint cannot be derived from model structure
- **THEN** it is not derived from the claim's `quantity` or `conditions` text under any
  circumstances
