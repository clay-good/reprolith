# simulation-oracle Specification

## Purpose

The simulation oracle is Reprolith's deterministic judge. It runs a reconstruction on a
registered engine and compares each output against the paper's own claim, within a declared
tolerance, producing a per-claim verdict of `reproduced`, `partial`, or `failed`. This is
the point where a paper's published figure functions as a checkable oracle.

## Requirements

### Requirement: Per-claim deterministic verdict

The oracle SHALL judge each claim independently and deterministically, so a reconstruction
is never globally passed or failed on a single blended score.

#### Scenario: Verdict vocabulary

- **WHEN** the oracle evaluates a claim
- **THEN** it returns exactly one of `reproduced`, `partial`, `failed`, or `not-evaluable`
- **AND** `not-evaluable` is used only when the reference is unusable (e.g. no data and no
  digitizable figure) and is distinguished from `failed`

#### Scenario: Determinism of judgment

- **WHEN** the same reconstruction is evaluated against the same claim under the same pinned
  engine and tolerance
- **THEN** the verdict and the numeric discrepancy are identical across runs
- **AND** any unavoidable engine nondeterminism is bounded and folded into the declared
  tolerance, never left to chance

### Requirement: Declared comparison protocol per claim

Each verdict SHALL name the comparison method and tolerance it used, so the judgment is
auditable and contestable.

#### Scenario: Comparison method is explicit

- **WHEN** the oracle compares an output to a claim
- **THEN** it records the comparison method appropriate to the reference (scalar summary
  metric, sampled curve distance, or qualitative shape/behavior check)
- **AND** it records the tolerance threshold and the actual measured discrepancy

#### Scenario: Two levels of reproduction are distinguished

- **WHEN** a claim is evaluated
- **THEN** the oracle records whether it performed **simulation reproduction** (run the
  described model with the reported parameters and check the shown output) or **estimation
  reproduction** (re-fit parameters from provided raw data and check the reported estimates)
- **AND** the default and primary target is simulation reproduction; estimation reproduction
  is attempted only when raw data is available and is reported separately

#### Scenario: Tolerance provenance

- **WHEN** a tolerance is applied
- **THEN** its origin is recorded (a model-class default, a paper-stated precision, or a
  reviewer override), never an unexplained magic number

### Requirement: Distributional (population) claims are compared honestly

Many PK/PD and QSP figures report a population, not a single trajectory — a percentile
envelope over time, a prediction interval, or a variability metric. The oracle SHALL judge
such a distributional claim against the paper's reported distribution under a declared
distributional tolerance, and SHALL qualify the verdict to reflect that the reproduction
depends on the variability model and the sampling.

#### Scenario: Percentile-band envelope comparison

- **WHEN** a claim is a population envelope reported as percentile bands over time (e.g.
  median with a lower and upper percentile curve)
- **THEN** the oracle compares each reported band to the corresponding simulated band and
  reports the distributional discrepancy as the worst-matched band, so a well-matched median
  cannot mask a divergent tail
- **AND** it records which percentile governed the discrepancy

#### Scenario: Population reproduction is a qualified verdict

- **WHEN** a distributional claim is judged
- **THEN** the verdict is assumption-qualified by default, because reproducing it depends on
  the reconstructed between-subject variability model and the population sampling — load-bearing
  assumptions the manuscript often under-specifies
- **AND** the qualification is only lifted when the paper fully specifies the variability model
  and the sampling is made deterministic

#### Scenario: Distributional tolerance provenance

- **WHEN** a distributional tolerance is applied
- **THEN** its origin is recorded like any other tolerance, and the class default for a
  population envelope is wider than for a single deterministic trajectory to absorb the
  Monte-Carlo sampling error inherent in a simulated population

#### Scenario: Population-specific failure modes

- **WHEN** a distributional claim is `partial` or `failed`
- **THEN** the root cause may be selected from population-specific causes in addition to the
  shared set, including an unspecified between-subject variability model and an unspecified
  population size or sampling scheme

### Requirement: Estimation reproduction is a distinct verdict

When a paper ships the raw data it was fit to, Reprolith SHALL be able to reproduce the
*estimation*, not just the simulation — re-fitting the model with the paper's stated method and
checking the reported parameter estimates — and SHALL keep that verdict distinct from a
simulation verdict so the two levels are never conflated.

#### Scenario: Estimation verdict is reported separately

- **WHEN** an estimation reproduction is judged
- **THEN** the resulting per-claim verdict is recorded at the estimation reproduction level and
  is distinguishable from simulation-level verdicts on the same paper
- **AND** a recovered estimate is compared to the paper's reported estimate within a declared
  tolerance, with the same attribution and provenance discipline as any other verdict

#### Scenario: Estimation tolerance reflects re-fit sensitivity

- **WHEN** no paper-stated precision or reviewer override exists for an estimation claim
- **THEN** the oracle applies a documented estimation-level default tolerance that is wider than
  a simulation scalar's, because a re-fit is sensitive to the optimizer, its starting values,
  and the objective
- **AND** the tolerance's origin is recorded like any other tolerance

#### Scenario: Estimation-specific failure modes

- **WHEN** an estimation claim is `partial` or `failed`
- **THEN** the root cause may be selected from estimation-specific causes in addition to the
  shared set, including an unstated estimation method or objective, unstated parameter starting
  values, and convergence to a different local optimum

### Requirement: Figure references are handled honestly

When a claim's only reference is a rendered figure, the oracle SHALL be explicit about the
added uncertainty of comparing against it.

#### Scenario: Digitized-figure comparison

- **WHEN** the reference is a figure image rather than numeric data
- **THEN** the oracle compares against digitized or paper-reported summary values and records
  that the comparison inherits digitization uncertainty
- **AND** the tolerance for a figure-only claim reflects that added uncertainty

### Requirement: Root-caused failures

A non-reproducing verdict SHALL carry enough diagnosis to be actionable, because "did not
reproduce" without a reason is not useful to the field.

#### Scenario: Failure attribution

- **WHEN** a claim is judged `partial` or `failed`
- **THEN** the oracle attaches a root-cause category (e.g. missing parameter, unit mismatch,
  ambiguous initial condition, engine/algorithm sensitivity, apparent manuscript error,
  load-bearing assumption dependence)
- **AND** it points to the specific dossier element or assumption implicated where possible

#### Scenario: Distinguishing paper fault from reconstruction fault

- **WHEN** a failure is attributed
- **THEN** the attribution states whether the shortfall is most consistent with an
  under-specified or erroneous manuscript versus a limitation of Reprolith's reconstruction
- **AND** this attribution is explicitly marked as a hypothesis, not a proven cause

### Requirement: Engine independence checks

Where feasible, the oracle SHALL support running a reconstruction on more than one engine to
separate a model's behavior from a single engine's quirks.

#### Scenario: Cross-engine corroboration

- **WHEN** a reconstruction can run on multiple compatible registered engines
- **THEN** the oracle can report whether the verdict is stable across them
- **AND** a verdict that flips between engines is surfaced as engine-sensitive rather than
  reported as a clean pass or fail
