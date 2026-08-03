# model-catalog (delta: bootstrap-ode-pkpd-mvp)

## ADDED Requirements

### Requirement: Blind self-validation test set

The bootstrap milestone SHALL assemble and maintain a labelled PK/PD test set that is the
acceptance gate for the class, and SHALL keep its labels blind from the verdict path.

#### Scenario: Assembling the test set

- **WHEN** the milestone begins
- **THEN** the catalog holds a test set of PK/PD entries carrying independent ground-truth
  reproducibility labels, weighted toward roughly twenty known-reproducible and ten
  known-hard or irreproducible cases
- **AND** each entry records the label's external source and its expected verdict

#### Scenario: Labels never reach the verdict path

- **WHEN** an entry in the test set is ingested, reconstructed, or judged
- **THEN** the ground-truth label is structurally unavailable to those stages
- **AND** any pathway that reads the label before a verdict exists is a defect

### Requirement: Agreement as the milestone gate

The milestone SHALL not be considered complete until agreement with ground truth is reported
and every disagreement is resolved or explained.

#### Scenario: Agreement report exists and is reproducible

- **WHEN** the full pathway has run over the test set
- **THEN** the catalog can produce a per-entry and aggregate agreement report comparing
  Reprolith's blind verdicts to the labels
- **AND** the report is reproducible from stored certificates and labels

#### Scenario: Every disagreement is accounted for

- **WHEN** a Reprolith verdict disagrees with a ground-truth label
- **THEN** the disagreement carries a written defect note and either a fix that was re-run or
  a documented explanation for why the label and verdict legitimately differ
