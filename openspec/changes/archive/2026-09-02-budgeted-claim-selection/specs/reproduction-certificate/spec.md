# reproduction-certificate (delta: budgeted-claim-selection)

## ADDED Requirements

### Requirement: A certificate records the claims it did not attempt

A certificate produced from a budgeted selection SHALL record which of the paper's claims were not
attempted, so its silence about a claim can never be read as the paper not having made it.

#### Scenario: An unattempted claim is present and has no verdict

- **WHEN** a certificate is produced for a paper whose claims were selected under a budget
- **THEN** every unattempted claim appears in the certificate as unattempted, with the budget and
  the objective that excluded it
- **AND** no verdict counter counts it, and no surface reports it as reproduced, partial, failed,
  or not-evaluable

#### Scenario: A budgeted verdict is qualified by its selection

- **WHEN** every attempted claim reproduces cleanly but claims were left unattempted
- **THEN** the overall verdict is qualified by the selection and is not an unqualified
  `reproduced`, for the same reason a load-bearing assumption qualifies one

#### Scenario: An unbudgeted certificate is byte-identical

- **WHEN** a certificate is produced without a budgeted selection
- **THEN** its content is unchanged, and every already-published digest regenerates identically
