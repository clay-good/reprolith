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
regulatory motifs this class targets first; larger networks are a later concern, not a hidden
approximation.

## The judges

| Function | Answers |
|---|---|
| `BooleanNetwork.fixed_points` | Which states does the update map to themselves? (scheme-invariant) |
| `BooleanNetwork.attractors(scheme)` | Every attractor under the chosen update scheme — deterministically ordered |
| `judge_steady_state` | Is a reported steady state one of the network's fixed points? |
| `judge_attractor_set` | Does the reported set of attractors equal the computed set under a scheme — surfacing any missing or unexpected one? |

`attractors` takes an `UpdateScheme`: **synchronous** (every node advances at once; attractors are
simple cycles) or **asynchronous** (any single unstable node may flip; attractors are the terminal
strongly connected sets of the state graph). The two schemes share the same *fixed points* but can
differ on cyclic attractors — the toggle switch's 2-cycle exists synchronously and vanishes
asynchronously — which is precisely why an unstated scheme is a first-class gap for this class, and
why `judge_attractor_set` takes the scheme it should judge under.

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
two-level (Boolean) models on purpose — a `maxLevel > 1` species raises rather than being silently
flattened — and needs the `engine` extra (python-libsbml, which bundles the qual package).

## Status

The oracle, its agent surface, and SBML-qual ingestion are complete and tested
([`tests/test_logical.py`](../tests/test_logical.py),
[`tests/test_qual_ingest.py`](../tests/test_qual_ingest.py)). What is **not** yet done, and is
therefore not claimed: a blind self-validation set against independently-known ground truth. Until a
logical entry flows from a real curated model to a blind agreement report — as the PK/PD, kinetic,
and constraint-based classes already do — this class is a validated *oracle with ingestion*, not yet
a self-validated *class*.
