# Self-validation across all model classes

Reprolith's central discipline is that its verdicts are measured blind against reproducibility
whose truth is independently established, on the *same* shared machinery for every model class. This
page is the one-look summary of that evidence; each row links to a walkable milestone a stranger can
follow end to end, all regenerable from the repository alone.

| Class | Blind agreement | Independent ground truth | Milestone |
|---|---|---|---|
| **PK/PD (ODE)** | 1 partially-reproduced + 30 honest abstentions, **0 wrong verdicts** over 31 BioModels entries | BioModels manual-curation status; the metformin claim read from the paper | [`datasets/milestone/`](../datasets/milestone/) |
| **Constraint-based (FBA)** | **4/4** blind agreement | E. coli core's documented growth rate; COBRApy references for the genome-scale set | [`datasets/constraint_based/milestone/`](../datasets/constraint_based/milestone/) |
| **Generic-kinetic (ODE)** | **6/6** blind agreement across six network types | libRoadRunner (independent CVODE) reference trajectories | [`datasets/kinetic/milestone/`](../datasets/kinetic/milestone/) |
| **Logical (Boolean)** | **4/4** blind agreement on real published models | CANA (independent Boolean-network library) attractors | [`datasets/logical/milestone/`](../datasets/logical/milestone/) |
| **Stochastic (SSA)** | **3/3** blind agreement | Closed-form Poisson / binomial means (analytical) | [`datasets/stochastic/milestone/`](../datasets/stochastic/milestone/) |
| **Spatial (reaction-diffusion)** | **3/3** blind agreement | Closed-form Gaussian diffusion (analytical) | [`datasets/spatial/milestone/`](../datasets/spatial/milestone/) |

## What makes each row honest

- **Blind by construction.** The ground-truth label lives on the catalog entry but has no field in
  the blind view handed to the verdict path; every verdict is produced without reading it.
- **Non-circular ground truth.** The FBA, kinetic, and logical references come from *independent*
  implementations (COBRApy, libRoadRunner, CANA) that share no code with Reprolith's engines, and
  the PK/PD metformin value is read from the manuscript, not re-derived. Reprolith reproducing them
  is a genuine cross-check, not a tool agreeing with itself. For the logical class the exported
  rules are additionally *proven faithful* to CANA's model — checked against CANA's own per-node
  step over every input — before the attractor signatures are compared.
- **Depth beyond a single number.** FBA cross-validates all three FROG components (objective,
  flux-variability, gene/reaction deletion) across five models up to genome scale (iJO1366, 2583
  reactions). Kinetic verdicts are additionally shown **engine-independent** — every model
  reproduces identically under COPASI and libRoadRunner (`corroborate_curve`), so no verdict rests
  on one solver's quirk.
- **The same contracts throughout.** All six classes flow through one catalog lifecycle, one
  agreement report, one certificate format, and one inescapable scope flag — the generalization is
  demonstrated, not asserted. The logical class proves the point hardest: a third, discrete oracle
  (attractors) with no continuous trajectory and no optimization, carried by the same contracts.

## Regenerate it

```bash
pip install -e ".[dev,engine,fba]"
python scripts/run_milestone.py            # PK/PD
python scripts/run_fba_milestone.py        # constraint-based
python scripts/run_kinetic_milestone.py    # generic-kinetic
python scripts/run_logical_milestone.py    # logical (reads committed CANA references)
python scripts/run_stochastic_milestone.py # stochastic (closed-form Poisson/binomial ground truth)
python scripts/run_spatial_milestone.py    # spatial (closed-form Gaussian diffusion ground truth)
```

The reference values themselves are regenerable from the independent tools with the `refgen` extra;
see [CONTRIBUTING.md](../CONTRIBUTING.md). Every certificate says, in plain text, that it attests
only to computational reproducibility — never biological correctness or clinical fitness.
