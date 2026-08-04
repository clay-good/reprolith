# The SED-ML adopt-and-verify fast-path

Many modeling papers ship a **SED-ML** document beside their model — a machine-readable description
of the simulation experiment: which model to run, for how long, at what resolution, and which
species to observe. When that recipe exists, reproduction is mostly "adopt it and run," rather than
reconstructing the simulation settings by hand. This is the highest certificate yield per unit
effort, and it applies across every ODE class.

## Reading the recipe

`reprolith.parse_sedml_recipes(sedml_text)` returns a `SimulationRecipe` per uniform-time-course
task — the model it references, its `duration` and `steps`, and the species it observes — using only
the standard library, so the core stays dependency-free.

```python
from pathlib import Path
from reprolith import parse_sedml_recipes, simulate

recipes = parse_sedml_recipes(Path("model.sedml").read_text())
recipe = recipes[0]                       # e.g. duration=9000, steps=1000, observables=("MAPK_PP", ...)
times, values = simulate(model_sbml, recipe.observables[0],
                         duration=recipe.duration, steps=recipe.steps)
```

A task whose simulation is not a uniform time course (a steady state, a repeated task) is skipped
rather than guessed at — there is no single runnable recipe to adopt, and inventing one would be a
guess.

## Verifying it

Once the recipe is adopted, the run is checked like any other curve: against the paper's reported
figure where it is digitizable, or — non-circularly — against an independent simulator. The
[worked example](../datasets/kinetic/BIOMD0000000010.sedml) is the real SED-ML BioModels ships for
the Kholodenko MAPK model; `tests/test_sedml.py` reads its recipe, runs it under the pinned COPASI
engine, and confirms the adopted trajectory is engine-independent (identical under libRoadRunner).
The scope flag on the resulting certificate is unchanged: reproducibility, never correctness.
