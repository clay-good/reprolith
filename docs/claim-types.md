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
| `SpatialClaim` | a concentration profile after diffusion | normalized curve distance | the discretization is unstable, the claim carries no reported profile, or it states an *unbounded* domain this grid is too narrow to stand in for |
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

## What each one costs

The second question, after "can it check this?". Stated as the work rather than as seconds, because
the work is what does not change with the machine — with the two places where a *size* is the
finding, both measured on this repository's own models.

| Claim | The work it does |
|---|---|
| a scalar metric, a curve | one run of the model; a **grid-dependent** metric (an area, a time to peak, a period, a peak-to-trough) runs it again at twice the resolution and abstains if the number moves more than the verdict can absorb |
| a percentile envelope | one run **per subject**, and at least thirty before the spread is the population rather than the sampling |
| a variability metric | the same subjects — but **about three times as many**: at 500, the size an envelope is drawn at, a 30% CV's own standard error is 3.6% of it against a 5% pass threshold, so the claim is abstained on; it resolves at 1,500 |
| a parameter estimate | one run per optimizer iteration (the worked example's re-fit converges in 25) |
| a steady state, an attractor set, a basin | exhaustive enumeration of 2ⁿ states, capped at 20 nodes; above that a **fixed point** is found by SAT instead and a cyclic attractor is out of reach |
| a mean species count, a first passage | one SSA trajectory per ensemble member (400 and 2,000 in the milestone) |
| a noise statistic | trajectories again — but **about ten times as many** as its mean: at 400 a Fano factor's standard error is 7.2% of its value against a 5% threshold, and 4,000 brings it to 2.3% |
| a diffusion profile, a decay length, a pattern | one finite-difference run of the claim's own step count (a gradient runs to steady state; a pattern adds a confirmation window) — **plus one run per alternative wall**, since what the boundary costs is measured rather than asserted, and a claim stating an unbounded domain is judged only once those runs bracket free space to within a tenth of its tolerance |
| a front speed | three windows of the same run, plus one more at half the time step to measure what the discretization is worth |
| an essential set | **one LP per gene** (137 on *E. coli* core) or per reaction, and a second sweep at the literature's cutoff when the claim states none |
| a flux, a flux range | two LPs for the reaction's interval — and, where that interval leaves the flux free, one mixed-integer solve to say whether the loop law would pin it |
| an objective value | one LP |

A FROG fingerprint is the one published artifact whose cost is worth stating in seconds, because it
decides what is published: a couple of LPs per reaction plus one per gene is 0.8s on the 95-reaction
core model and 145s on the 1,226-reaction iEK1008, which is why it is published for the core model
and the rest is a measurement rather than a silence.

## Certifying one, start to finish

Nothing above is reachable without a pin and a front end, and a reader assembling those from three
class documents is a reader who gives up. This is the whole thing for a Boolean network whose paper
reports a basin — every other class is the same three steps with its own claim type:

```python
from reprolith import (
    LogicalClaim, PaperIdentity, ReportedBasin, UpdateScheme,
    RunMetadata, certify_logical, parse_boolean_network, render_human, solver_pin_for,
)

rules = {"A": "!B", "B": "!A"}                      # your network, node -> Boolean rule
parse_boolean_network(rules).attractors()           # what the model has, if you want to look first
attractor = [{"A": 0, "B": 1}]                      # the attractor your paper reports a basin for

certificate = certify_logical(
    paper=PaperIdentity(title="Your paper", doi="10.0/example"),
    engine_pin=solver_pin_for(nodes=len(rules)),      # the path this size of network takes
    claims=[LogicalClaim(
        claim_id="fig-2-basin",
        quantity="states reaching the A-off steady state",
        rules=rules,
        reported={},                                  # unused: this claim reports a basin
        basin=ReportedBasin(attractor=attractor, states=1),   # your paper's number
        source_location="Fig 2",
        scheme=UpdateScheme.SYNCHRONOUS,              # omit it and the run says what that cost
    )],
)
print(render_human(certificate, RunMetadata(created_at="", actor="you", tool_version="0.0.1")))
```

The pin is not decoration: it names the code that produced the verdict, and each class refuses one
that describes a different path than the run took. `tests/test_claim_type_catalogue.py` runs this
snippet as it is written here, so a signature that changes under it fails rather than leaving a
reader with a page that no longer works.

## What can be checked *inline*

A certificate is the full answer; an agent gating a workflow often wants a faster one. The MCP
server's `lint_*` tools give that for **seven** of the quantities above — a curve, an objective, a
mean species count, a diffusion profile, a steady state, an estimate, and a percentile envelope.
The rest reach a certificate and not a gate, which
[`docs/mcp-server.md`](mcp-server.md) says in the same words, because a reader meeting one lint per
class reasonably infers there is one per claim type.

An inline verdict is the *same judgment*, not a looser one. It states the protocol it rests on, it
runs the wall a spatial claim states — `unbounded` included — and where the certificate would carry
a load-bearing assumption it abstains instead, because there is no assumption block on a result this
shape. The rule is the certifying oracle's own code rather than a second copy of it: two
implementations of one judgment is how two surfaces come to disagree about what a verdict means.

## What is not here

A claim type exists when a *spec* names the target. This engine computes several quantities no claim
carries — synthetic lethal pairs, production envelopes, shadow prices, parsimonious fluxes — because
no class spec names them as reproduction targets. They are library functions, cross-validated
against COBRApy, and reachable from a script rather than from a certificate. That is a deliberate
boundary, not an oversight: a claim type is a promise about what a certificate means.
