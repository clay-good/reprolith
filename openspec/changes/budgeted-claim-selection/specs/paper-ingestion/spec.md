# paper-ingestion (delta: budgeted-claim-selection)

## ADDED Requirements

### Requirement: A contributed claim may state what it rests on

A claim contributed to a claims dataset SHALL be able to record its footprint, and a dataset that
records none SHALL load exactly as it does today.

#### Scenario: An existing dataset is unchanged

- **WHEN** a claims dataset that records no footprint is loaded
- **THEN** its claims load identically to before the field existed, and every digest that depends
  on them is unmoved

#### Scenario: A contributed footprint reaches the selector

- **WHEN** a claims dataset records a footprint for a claim
- **THEN** that footprint is what the claim carries into a selection, and the report distinguishes
  it from one derived from model structure
