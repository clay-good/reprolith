# The logical / Boolean-network oracle

Logical models make a third kind of claim, distinct from both the PK/PD/kinetic curve models and
the constraint-based optimization models: not "does the model regenerate a time course" nor "does
its optimization hit the reported outcome," but "does the network settle into the reported
discrete state." A Boolean network has no time axis and no objective — its reproducible result is a
**steady state** (fixed point) or the **set of attractors** the dynamics fall into. Judging that by
exact attractor analysis, alongside curve-matching and linear programming, is a second proof that
the engine's abstractions are oracle-agnostic.

The oracle lives in [`reprolith.logical`](../python/reprolith/logical.py). It reuses the shared
contracts — every judge returns the same `ClaimAssessment` the certificate consumes, classified by
the same machinery as the other classes — and adds only the discrete-dynamics comparison.

## No deferred half

The PK/PD and constraint-based oracles each defer their heavy engine (COPASI, scipy's LP solver)
behind an optional extra. Boolean-network analysis needs neither: fixed points and synchronous
attractors are computed by exact enumeration, in pure Python. So unlike the other classes, this
one **computes the attractors it judges** — there is nothing stubbed, and the tests run
unconditionally with no extra installed.

Exhaustive enumeration is 2ⁿ in the node count, which is exactly right for the small signaling and
regulatory motifs this class targets, and is used directly up to `MAX_ENUMERABLE_NODES` (20).

**Fixed points scale past that** without enumeration: a steady state satisfies `xᵢ ⟺ ruleᵢ(x)` for
every node, so `fixed_points()` on a large network encodes that condition and enumerates its
solutions with a SAT solver (z3, the optional `sat` extra), returning each verified steady state.
Real signalling models are then tractable — the 60-node T-LGL leukemia network's 71 fixed points come
back in a fraction of a second where 2⁶⁰ enumeration is impossible. The scalable path needs the
network's symbolic rules (a network built from opaque callables has none) and refuses fast, rather
than blowing up, when free input nodes would multiply the fixed points by 2^(#inputs). Ingesting an
SBML-qual file yields those rules too — each transition's ordered function terms are written out as
one expression per node — so a published model of the size this path exists for reaches it, instead
of refusing at the enumeration ceiling.

**Cyclic attractors do not scale** — finding them still walks the state space, so `attractors()`
above the cap raises `NetworkTooLarge`, an honest boundary rather than a silent hang. Single-state
stepping never enumerates and stays available at any size.

## The judges

| Function | Answers |
|---|---|
| `BooleanNetwork.fixed_points` | Which states does the update map to themselves? (scheme-invariant) |
| `BooleanNetwork.attractors(scheme)` | Every attractor under the chosen update scheme — deterministically ordered |
| `BooleanNetwork.basin_sizes` | How many states flow into each synchronous attractor — the basins, which partition the 2ⁿ space (so the sizes sum to 2ⁿ) and answer "which attractor dominates" |
| `judge_steady_state` | Is a reported steady state one of the network's fixed points? |
| `judge_attractor_set` | Does the reported set of attractors equal the computed set under a scheme — surfacing any missing or unexpected one? |
| `judge_basin_size` | Does the reported basin of one attractor — a count of states, or a share of the space — match the one this network has? |

`attractors` takes an `UpdateScheme`: **synchronous** (every node advances at once; attractors are
simple cycles) or **asynchronous** (any single unstable node may flip; attractors are the terminal
strongly connected sets of the state graph). The two schemes share the same *fixed points* but can
differ on cyclic attractors — the toggle switch's 2-cycle exists synchronously and vanishes
asynchronously — which is precisely why an unstated scheme is a first-class gap for this class, and
why `judge_attractor_set` takes the scheme it should judge under.

That gap was a check on the way *in* only. A `LogicalClaim` carries `scheme` and `attractors` now,
so a stated scheme reaches the run and a reported attractor set is certified through the front end
rather than through `judge_attractor_set` directly; `certify_logical` refuses a pin naming a
different scheme than its claims were judged under, and refuses to give one pin to claims judged
under two. Where a claim states no scheme, the run is synchronous and the certificate carries a
load-bearing assumption — but only where the choice could move *that* verdict, which
`scheme_sensitivity` computes exactly: enumerate under both and compare what the claim was judged
on. A fixed-point claim needs no run to answer it, since a fixed point is one under either scheme,
and a network past the enumeration ceiling says the comparison is out of reach rather than reading
as agreement. Unlike the spatial class's wall, this assumption is `author_can_close=True`: a paper
can state its scheme.

Both judges map onto the shared assessment contract via `assess_match`: a match reproduces,
otherwise it fails and — like any non-pass — requires a root-cause attribution. So a logical
verdict feeds `build_certificate` exactly like a scalar, curve, or fingerprint one, and the
attractor computation is deterministic, so the verdict is too.

`judge_attractor_set` names the discrepancy honestly — how many reported attractors were not found
and how many computed ones were unexpected — so under-reporting the dynamics (e.g. omitting a
2-cycle) fails rather than passing on the fixed points alone.

## The JSON-friendly network form

An agent or an ingester supplies a network as rule *expressions*, one per node — the form papers
actually write. `parse_boolean_network({"A": "!B", "B": "!A"})` compiles each expression to a
callable. The parser is **safe by construction**: it compiles from an allow-listed AST
(`and`/`or`/`not` and the bitwise `&`/`|`/`^`/`~` spellings, the field's `!` negation, node names,
parentheses, and the constants 0/1) and never `eval`s, so a rule string can never execute arbitrary
code. A rule naming an undeclared node raises rather than silently treating the name as a constant.

## Over the MCP surface

The class is reachable through the same read-only agent surface as the rest of the engine. The
`lint_steady_state` MCP tool — the logical counterpart of `lint`/`lint_objective` — takes a
network's rules and a reported steady state and returns a deterministic, scope-flagged verdict an
agentic workflow can gate on. Being pure Python, it needs no engine extra.

```python
from reprolith import parse_boolean_network, judge_steady_state

# A toggle switch: two mutually repressing nodes.
net = parse_boolean_network({"A": "!B", "B": "!A"})
net.fixed_points()          # [{'A': 0, 'B': 1}, {'A': 1, 'B': 0}]

judge_steady_state(
    claim_id="ss", quantity="steady state", source_location="Fig 3",
    reported={"A": 1, "B": 0}, network=net,
).verdict                   # -> REPRODUCED
```

## Failure modes

A `partial` or `failed` logical verdict carries a first-class logical root cause, not a borrowed
one. The maintained set (`reprolith.FailureMode`) adds the recurring reasons logical reproductions
fail — an unspecified update scheme (synchronous vs asynchronous updating can change the cyclic
attractors), an ambiguous or missing logic rule, and an unspecified initial state or input fixing.
A failure fitting none of them is recorded as `UNCATEGORIZED`, flagging the catalog to be extended
rather than silently misclassifying.

## Ingestion from SBML-qual

`ingest_qual_sbml` is the class front-end, the logical counterpart of `ingest_fbc_sbml`: it reads a
standard **SBML-qual** model — the field's interchange format for logical models — into a
`BooleanNetwork`. Each transition's function terms are compiled into pure-Python closures (the first
satisfied term's result level, else the default term's), so the returned network retains nothing
libsbml owns; a species with no transition is a constant input that holds its value. It is scoped to
two-level (Boolean) models on purpose, and refuses anything multi-valued rather than flattening it:
`maxLevel` is optional in SBML-qual, so an initial level above 1, a threshold above 1, or a level
literal in the transition math all raise on their own. Transition constructs the Boolean oracle does
not implement — a production (additive) output, a consuming input, a missing default term — raise
too, because running them as ordinary assignment logic would certify a different model. It needs the
`engine` extra (python-libsbml, which bundles the qual package).

## The basin of an attractor

`basin_sizes` answered "how much of the state space reaches this attractor" from the day the class
was written, and no claim could reach it — the same shape as `judge_attractor_set` before it. It is
the number these papers argue robustness with: Li et al. 2004's yeast cell-cycle network reaches its
G1 steady state from **1764 of 2048** initial states, which is the result that paper is remembered
for, and two networks can agree on every attractor while disagreeing entirely on how much of the
space reaches each one.

`ReportedBasin` carries it and `judge_basin_size` judges it. Four decisions are what make it a
comparison rather than a number:

- **A count is judged exactly; a share is judged in a band.** A basin is a number of states in a
  finite space, so there is no numerical error for a tolerance to absorb and a band would pass a
  network that reaches its attractor from eighty states fewer. A printed *percentage* is a rounded
  number, so that form is judged by relative error.
- **The denominator is on the protocol line.** A paper that fixed its input nodes before counting
  reports a share of a smaller space. CANA's 12-node variant of the yeast network adds `CellSize` as
  a free self-loop, which doubles the space without moving anything: the G1 basin is 1764 states in
  both networks, and **86% of the paper's space against 43% of CANA's**. The count survives the
  change of whole and the fraction does not, which is why the space it was counted in is recorded
  beside the verdict.
- **An asynchronous claim abstains.** Under asynchronous updating a state has one successor per
  unstable node, so it can reach several attractors and the basins overlap rather than partitioning
  anything. The synchronous count exists; answering with it would answer a question the claim did
  not ask.
- **An attractor this network does not have fails, and does not abstain.** No state flows to an
  attractor that is not there, so the observed basin is zero and the discrepancy says which of the
  two disagreements it is. That is the strongest non-reproduction this class can find, and filing it
  as "could not be judged" would hide it.

An **unstated** update scheme is load-bearing here in a way it is not for a fixed point, and — like
its sibling — the cost is measured rather than asserted. The comparable asynchronous quantity is
*reachability*: from how many states the attractor can be reached at all. Where every state that can
reach it also flows to it, the reading cannot move the number and no assumption is minted; where the
two differ, the basis carries both counts. On Li's network they differ (1764 against 1960), so an
unstated scheme there is a real ambiguity and not a formality. Reachability holds the async state
graph's edges rather than one successor per state, so it has its own, lower ceiling
(`MAX_REACHABILITY_NODES`) and says it is out of reach past it rather than reading as agreement.

A reported attractor that is not there gets the same treatment rather than a blanket answer: the
claim has already failed on the attractor, so the question is whether the *scheme* explains that,
and an attractor absent under synchronous updating can exist under asynchronous updating. Where it
does, the certificate says the verdict may rest on the reading; where the attractor is absent either
way, no assumption is minted, because a scheme choice that cannot explain the failure should not be
recorded as what the verdict rests on.

No certificate in the shipped corpus carries a basin claim yet: the milestone's networks have no
independently published basin to judge against, and Li's 11-node network is a *derivation* from the
committed 12-node rules — a load-bearing reconstruction that owes its own assumption. What is
committed is the check: [`tests/test_logical_basin_claim.py`](../tests/test_logical_basin_claim.py)
proves the restriction faithful state-by-state against the 12-node network and reproduces all seven
of the paper's published basins (1764/151/109/9/7/7/1) exactly.

## Self-validation

The class is measured against **CANA** (Correia et al. 2018), an independent Boolean-network
library, on four real published models — the Arabidopsis flower, Drosophila segment-polarity,
budding-yeast cell-cycle, and a schemata example network. Each model's rules are exported from CANA
and *proven faithful* (checked against CANA's own per-node step over every input), and Reprolith's
own attractor computation reproduces CANA's independently-computed attractor signature on all four —
including the 11 attractors of CANA's 12-node budding-yeast network, whose seven `CellSize=0`
fixed points are exactly Li et al. 2004's published steady states (basins
1764/151/109/9/7/7/1). See
[`datasets/logical/cross_validation/`](../datasets/logical/cross_validation/) and
[`tests/test_logical_cross_validation.py`](../tests/test_logical_cross_validation.py). The oracle
itself is additionally validated by differential and property testing over ~1,800 random networks
([`tests/test_logical_properties.py`](../tests/test_logical_properties.py)).

This is the same non-circular discipline as the FBA (vs COBRApy) and kinetic (vs libRoadRunner)
classes, so the logical class is now a self-validated class, not only a validated oracle.
