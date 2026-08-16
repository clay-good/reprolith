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

A recipe is adopted and run verbatim, so it must describe the run the document specifies. Three
kinds of task are skipped rather than guessed at:

| Skipped | Why |
| --- | --- |
| The simulation is not a uniform time course (a steady state) | There is no single runnable time course to adopt. |
| The task runs a model the document *modifies* (`source="#other"` with `listOfChanges`) | A recipe names one model file and carries no overrides, so adopting it would run the unmodified model. In the shipped Kholodenko document that is the difference between an oscillating Figure 2B and a flat curve. |
| The task is a `repeatedTask` that scans a range or applies a `setValue` | The document describes several runs at several parameter values; one run at the model's default value is an arm it never plots. |

A `repeatedTask` that only wraps a subtask, changing nothing, still resolves to that subtask, and
observables come from the data generators — a variable inside a `setValue` is an input to a
modification, not a plotted quantity.

## Verifying it

Once the recipe is adopted, the run is checked like any other curve: against the paper's reported
figure where it is digitizable, or — non-circularly — against an independent simulator. The
[worked example](../datasets/kinetic/BIOMD0000000010.sedml) is the real SED-ML BioModels ships for
the Kholodenko MAPK model; `tests/test_sedml.py` reads its recipe, runs it under the pinned COPASI
engine, and confirms the adopted trajectory is engine-independent (identical under libRoadRunner).
The scope flag on the resulting certificate is unchanged: reproducibility, never correctness.
