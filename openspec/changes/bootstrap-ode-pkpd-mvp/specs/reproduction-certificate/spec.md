# reproduction-certificate (delta: bootstrap-ode-pkpd-mvp)

## ADDED Requirements

### Requirement: MVP certificate is the walkable artifact

The bootstrap milestone's certificates SHALL be legible to an outside reader with no access
to Reprolith internals, because the milestone's whole purpose is an artifact to show the
reproducible-modeling community.

#### Scenario: A stranger can follow a certificate

- **WHEN** a reviewer outside the project opens a milestone certificate
- **THEN** they can see the paper identity, each claim and its verdict, the tolerance and
  method used, the assumptions Reprolith made, and the scope statement, without further tools
- **AND** for anything short of full reproduction, they can read the precise list of what was
  missing

#### Scenario: Certificates back the findings note

- **WHEN** the milestone's findings note states what reproduced, what did not, and what the
  field most under-specifies
- **THEN** every such statement is traceable to specific certificates in the labelled set
