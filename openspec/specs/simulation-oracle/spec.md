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

#### Scenario: A simulated verdict states the run behind it

- **WHEN** a claim is judged from a time course Reprolith ran
- **THEN** the assessment records the run: the window it was simulated over, the number of
  samples taken, and any parameter override the claim set
- **AND** without them the published number cannot be re-derived — a vanishingly short window
  returns the initial condition and can agree with the paper for no reason, a curve distance and
  an area both move with the sample count, and two claims that differ only by dose are otherwise
  indistinguishable on the certificate

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

### Requirement: A claim's protocol may be more than one administration

A published result is often reported for an arm that begins from a prior dose, and a claim whose
protocol cannot say so is judged against a run the paper did not describe. A claim SHALL be able
to state prior administrations, and everything that reports the run SHALL carry them.

#### Scenario: Prior administrations condition the reported window

- **WHEN** a claim states a schedule of administrations
- **THEN** each segment runs the adopted model with its own values, starting from the state the
  previous segment ended in, so the model's own dosing machinery administers every dose and
  nothing is added to the model
- **AND** the claim is judged over the final segment, since that is the arm the paper reports
- **AND** a claim states a schedule or plain parameter overrides and not both, because the
  overrides are the one-segment spelling and carrying both leaves it unsaid which segment they
  belong to

#### Scenario: The prior administrations travel with the verdict

- **WHEN** a scheduled claim is judged
- **THEN** its protocol records the prior administrations as well as the reported window, since a
  reader who re-runs that window alone gets a different number
- **AND** a cross-engine check of that claim runs the same segments under each engine, because
  corroborating the unscheduled model would report engine agreement about a run the claim never
  made
- **AND** a published experiment document that cannot state a run beginning from another run's end
  lists the claim with that reason rather than writing it as a single run

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
- **AND** the qualification names what it qualifies: the sampling the bands came from is recorded
  as a load-bearing assumption, so the downgrade is never a flag pointing at nothing

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

#### Scenario: The population the bands came from

- **WHEN** Reprolith simulates the population itself rather than being handed its bands
- **THEN** the variability model, the draw mechanism, and the percentile definition are stated
  in the protocol the certificate carries, because an envelope read without them is a picture
  rather than a result — a mean-preserving variability model and a median-preserving one place
  every band differently, and percentile definitions disagree materially at small ensembles
- **AND** the same seed and inputs reproduce the same population, on any machine
- **AND** a parameter whose between-subject variability could not reach the run — one the model
  does not declare, one a rule determines, one a kinetic law shadows — is refused before the
  ensemble runs, since that failure is otherwise silent: every subject identical, the bands one
  line, and nothing saying the variability was discarded

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

#### Scenario: A supplied estimate states how it was recovered

- **WHEN** an estimate is judged that Reprolith was handed rather than re-derived itself
- **THEN** the claim states the estimation protocol behind it — the objective, the optimizer, the
  starting values, and the dataset — and is refused without one
- **AND** the protocol travels on the assessment, because a re-fit nobody can repeat is not
  evidence and a recovered value equal to the reported one proves nothing on its own

#### Scenario: An estimate Reprolith re-derived itself

- **WHEN** Reprolith runs the re-fit rather than being handed the estimate
- **THEN** the objective, the optimizer, the starting values, and the dataset and grid it ran on
  are recorded in the protocol the certificate carries, as they are for a supplied estimate —
  running the fit does not exempt it from stating how
- **AND** the optimizer is deterministic and owned, so the same data and starting values give the
  same estimate on every machine and no dependency's version can move the answer
- **AND** the starting values are the caller's, never defaulted, because a starting point is part
  of an optimizer's answer for any objective that is not convex
- **AND** a fit that does not converge inside its iteration budget is refused rather than
  reported: an optimizer that stopped early has not produced an estimate

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
