# The constraint-based (FBA) oracle

Flux-balance analysis models make a different kind of claim than the PK/PD curve models: not
"does the model regenerate a time course" but "does the model's optimization reproduce the
reported outcome." So the constraint-based-class gets its own oracle in
[`reprolith.fba`](../python/reprolith/fba.py). It reuses the shared contracts — every judge
returns the same `ClaimAssessment` the certificate consumes, classified by the same tolerance
machinery as the PK/PD oracle — and adds only the FBA-specific comparisons.

The oracle lives behind the optional **`fba`** extra (scipy's linear solver), imported lazily so
the core stays dependency-free. Install with `pip install -e ".[fba]"`; the tests skip without it.

## Why FBA needs its own honesty rule

An FBA model's optimum is unique, but the *flux distribution* that achieves it usually is not:
many different flux vectors hit the same objective value (**alternate optima**). A naive oracle
that solved once and compared the returned flux vector to a paper's reported fluxes would report
disagreement that is an artifact of solver tie-breaking, not a real discrepancy — or, worse,
agreement that is luck. Both betray design goal 2: *a confidently wrong verdict is worse than an
honest abstention.*

Every method below is built to be well-defined regardless of which optimal vertex the solver
happens to land on.

## The fingerprints

| Function | Answers | Well-defined under alternate optima because… |
|---|---|---|
| `solve_objective` / `judge_objective` | What is the optimal objective value, and does it match the reported one? | the objective value is unique even when the flux vector isn't |
| `reaction_essentiality` / `essentiality_agreement` | Which reactions, knocked out, collapse the objective? Do they match the reported essential set? | essentiality is a property of the objective optimum, not of any one flux vector |
| `flux_variability` | What min/max can each reaction's flux take while the objective stays optimal? | it reports the *whole* feasible interval instead of picking one vector |
| `judge_flux` | Does a reported reaction flux reproduce? | it judges against the variability interval, and abstains when the model leaves the flux free |

### `judge_flux` — the honest verdict for a reported flux

Given a reported flux and its variability interval `(min, max)` (from `flux_variability`):

- **pinned and contains the report** (`min == max` within tolerance) → the model uniquely
  produces this flux: judged as a scalar, so it reproduces.
- **inside a non-trivial interval** → the model is *consistent with* the value but does not
  determine it. Certifying "reproduced" would overstate what the model earns, so the verdict is
  **`not-evaluable`** (abstain), with a reason naming the interval.
- **outside the feasible interval** → the model cannot reach this flux at the optimum: judged
  against the nearest feasible flux, so it lands `partial`/`failed` and — like any non-pass —
  requires a root-cause attribution.

## Example

```python
from reprolith import flux_variability, judge_flux

# S: rows = metabolites, columns = reactions. v_in -> A -> {r1, r2} -> B -> v_out.
stoich = [[1.0, -1.0, -1.0, 0.0],   # A
          [0.0,  1.0,  1.0, -1.0]]  # B
objective = [0.0, 0.0, 0.0, 1.0]    # maximize the outflow
lower = [0.0, 0.0, 0.0, 0.0]
upper = [10.0, None, None, None]

intervals = flux_variability(stoich, objective, lower, upper)
# intervals[1] == (0.0, 10.0): the two parallel routes split the optimum freely.

judge_flux(
    claim_id="r1", quantity="parallel-route flux", source_location="Table 2",
    reported=5.0, interval=intervals[1],
).verdict            # -> NOT_EVALUABLE: consistent, but the model doesn't pin it.
```

The resulting `ClaimAssessment` feeds `build_certificate` exactly like a PK/PD assessment, so an
FBA reproduction produces the same scope-flagged, honestly-qualified certificate as the rest of
the engine.
