# What Reprolith can certify

Every kind of published result this engine can check, what each one is compared against, and how
each one refuses. A modeller's first question is "can it check the thing my paper reports?", and
until this page existed the answer was spread across six class documents and a test suite.

The table is **held to the code**: `tests/test_claim_type_catalogue.py` fails if a claim type exists
that this page does not list, or if this page lists one that does not exist. A capability nobody can
find is one this repository has shipped before.

| Claim type | The published result it reproduces | Compared by | It abstains when |
|---|---|---|---|
| `Claim` | a scalar read off one trajectory — peak, time of peak, area, end value, an oscillation's period or its peak-to-trough height | relative error | the metric is a property of the sampling grid at this resolution, or a cycle metric's run completes no cycle |
| `CurveClaim` | a whole species time course | normalized curve distance, governed by both the average and the worst point | the source states which curve is plotted but not the values it showed |
| `PopulationClaim` | a percentile envelope across a virtual population | worst-matched band, so a good median cannot mask a divergent tail | the reported and simulated envelopes are not on the same grid |
| `VariabilityClaim` | an inter-individual variability metric — a %CV or SD of a metric across subjects | relative error, against the statistic's own resampled error bar | the population is too small to resolve its own spread, or its metric is zero everywhere |
| `EstimationClaim` | a parameter estimate, re-fitted from the paper's raw data | relative error, at the wider estimation default | — (the fit itself refuses to report a non-converged estimate) |
| `LogicalClaim` | a Boolean network's steady state, its attractor set, or one attractor's basin | exact set match, or an exact state count for a basin | a basin is asked under asynchronous updating, where it is not defined, or the network is past the enumeration ceiling |
| `StochasticClaim` | a mean species count from an SSA ensemble | relative error | the ensemble's noise is too large to tell a reproduction from a miss |
| `ExtinctionTimeClaim` | a mean time to extinction — a first passage, not a state at a time | relative error | any trajectory reached its cap without going extinct, so the mean would be of a conditioned sample |
| `NoiseClaim` | a Fano factor or coefficient of variation — what a stochastic model is *for* | relative error, against a jackknife error bar rather than a mean's | the ensemble cannot resolve the statistic, or every trajectory ended at zero |
| `SpatialClaim` | a concentration profile after diffusion | normalized curve distance | the discretization is unstable, or the claim carries no reported profile |
| `GradientClaim` | a morphogen decay length | relative error | no exponential can be fitted over the stated window |
| `FrontSpeedClaim` | an invasion front's asymptotic speed | relative error | the front reached the domain's wall, or the time step decides the verdict |
| `PatternClaim` | a Turing pattern's wavelength | relative error | no pattern formed, or the domain cannot resolve the wavelengths in question |
| `EssentialityClaim` | the set of genes or reactions whose deletion abolishes growth | exact set match, or an exact count where the paper prints only a number | the model carries no gene–protein–reaction rules to delete |
| `FluxClaim` | a reported reaction flux | relative error against the flux-variability interval | the interval does not pin the flux — the model permits that value rather than producing it |
| `FluxRangeClaim` | the interval a reaction can carry at the optimum | its worse-matched bound | — |
| an objective claim (in the dossier) | a maximal growth rate or other objective value | relative error | — |

Every one of them, and the front end that judges it, imports from the package root:

```python
from reprolith import EssentialityClaim, certify_constraint_based, fba_solver_pin
```

That was not true until a modeller's day-one script was actually written: `certify_constraint_based`
was on the surface and not one of the claim types it takes, so a consumer could reach the function
and could not build anything to pass it. `tests/test_public_api.py` now reads each exported front
end's own signature and requires the claim types in it to be exported too, so the next class to add
one is covered without anybody remembering.

## Two things every row shares

**A miss is published, not raised.** Each of these can produce the failure it earns, with a root
cause on it: `tests/test_every_front_end_can_publish_a_miss.py` drives all of them through their
front ends with a wrong number. Two front ends have been caught doing the opposite, publishing a
pass or a traceback and nothing in between.

**An abstention is a verdict about the evidence, not about the model.** Every "abstains when" above
produces `not-evaluable` with a reason and the protocol of the run behind it — never a `failed`,
which would blame a model for a question this engine could not ask.

## What is not here

A claim type exists when a *spec* names the target. This engine computes several quantities no claim
carries — synthetic lethal pairs, production envelopes, shadow prices, parsimonious fluxes — because
no class spec names them as reproduction targets. They are library functions, cross-validated
against COBRApy, and reachable from a script rather than from a certificate. That is a deliberate
boundary, not an oversight: a claim type is a promise about what a certificate means.
