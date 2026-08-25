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

## What the document claims

The same file also says which curves the paper *shows*. `reprolith.enumerate_sedml_claims(sedml_text)`
turns each `curve` of a `plot2D` (and each `surface` of a `plot3D`) into a dossier claim — the
quantity plotted, the task it holds under, and the plot and curve it came from as its source
location. `ingest_sbml(sbml, entry=..., sedml=...)` attaches them, so a paper that ships both files
gets a dossier with structure *and* targets; without the document it gets structure and no claims,
because this path never reads the manuscript.

A claim records the task it holds under, and a task that *scans* says so: the metformin document
shipped in [`datasets/worked_examples/`](../datasets/worked_examples/) plots 81 curves, every one of
them an arm of one range scan, and a claim reading only `task 'task2'` would be indistinguishable
from a claim about a single run — which is also precisely why no recipe is adopted for it. A
repeated task inherits the model and simulation of the task it wraps, because that is what it runs.

Two things are deliberately not claims:

| Not a claim | Why |
| --- | --- |
| A data generator built only from `urn:sedml:symbol:time` | It is the axis a curve is plotted against. `time` and `time/60` are the same axis in different units. |
| A `report`'s data sets | A report is an export format, not a statement that the paper published the value. |

The reports in the shipped Kholodenko document show why that second rule earns its place: two of
them restate the plots verbatim, and a third dumps every symbol in the model — ten reaction fluxes
and the compartment volume included. Reading them as claims would manufacture seventeen results the
paper never staked. Instead they are retained with `targetable` false, so nothing is dropped and a
reviewer can promote one as a [tracked revision](../openspec/specs/paper-ingestion/spec.md). A
document that ships *only* reports therefore yields no targetable claims — an abstention, because
nothing in it says which of its columns the paper published.

Every claim is marked `digitized-figure` with no reference data. A SED-ML document says what to
plot; it never says what values the paper's figure showed, and the oracle abstains on a claim with
no reference rather than inventing one. That is the same wall
[the findings note](findings-note.md) describes: the document closes the "which results are there"
half of claim extraction, and leaves the "what values were shown" half where it was. `certify_curves`
takes such a claim and abstains on it — `not-evaluable`, with the reason on the claim line — rather
than running the model and judging it against nothing.

## The archive around it

A paper more often ships the whole experiment as a **COMBINE archive** (`.omex`): a zip whose
`manifest.xml` says, by format URI, what each file is. `reprolith.ingest_omex(archive, entry=...)`
reads one — path or bytes, standard library only, nothing written to disk and nothing executed —
finds the master SED-ML and the model it runs, and returns the dossier: model structure from the
SBML, claims from the document's plots. Every member is recorded as an artifact with the format the
manifest gives it, including files ingestion does not read, and a member the manifest never lists
is recorded as `unlisted` rather than dropped.

It refuses rather than guesses, each refusal naming the ambiguity:

| Refused | Why |
| --- | --- |
| A zip with no `manifest.xml` | The manifest is what makes a zip an archive; without it nothing says what each file is. |
| Several SED-ML documents with none marked master | Which experiment the paper ran is the archive's to say. |
| An experiment that runs more than one model file | A dossier is the extraction of one model. |
| An experiment or model the manifest lists but the archive does not contain | The archive is incomplete; the missing file is named. |
| No experiment and more than one model | With no experiment to name the model, nothing says what the dossier is of. |

An archive that ships a model and no experiment is not a refusal: it yields structure and no
claims, for the same reason a bare SBML does.

## Do the two files agree?

Nothing in an archive checks that its experiment and its model refer to the same elements, and
when they do not the failure is quiet in the worst way: a `changeAttribute` aimed at a parameter
that is not there overrides nothing, so the run reproduces the *unmodified* model and looks fine.
`reprolith.archive_mismatches(sedml_text, sbml_text)` reports both that case and a data generator
observing a species the model does not define — one line each, empty when the pair agrees, the
same shape `compare_sbml_to_dossier` uses for an adopted model.

Targets resolve **by nesting**, not by a flat search for the id. A rate constant named `KK2`
inside reaction `J1` is a different element from one named `KK2` inside `J0`, so an override aimed
at the wrong reaction is caught rather than waved through. `ingest_omex` runs the check and records
each mismatch as a load-bearing gap: it is missing from the archive, and it changes what a run
produces.

A target selecting on any attribute other than `id`, or using an axis or function the resolver
does not read, is left unreported — not resolving a path is not evidence that the model lacks the
element.

## One archive in, one certificate out

Put the three pieces together and the fast-path runs end to end with no hand-written claim:

```python
dossier = ingest_omex(archive_bytes, entry="BIOMD0000000010")   # structure + claims
recipes = {r.task_id: r for r in parse_sedml_recipes(sedml)}    # what to run, for how long
certificate = certify_curves(sbml, paper=..., engine_pin=engine_pin(), claims=[...])
```

Nothing above says which curves to check or how long to run them; the archive says both. The only
input still supplied by hand is the reference each curve is judged against, and for a document that
ships no values that reference is an independent simulator re-running the same model file — stated
on the claim line, never dressed up as the paper's own numbers.

On the Kholodenko archive the honest result is a split certificate: the two curves of Figure 2A
reproduce under the pinned engine, and the two of Figure 2B are `not-evaluable`, because the
document runs them on a model it modifies and an adopted recipe carries no overrides.
`tests/test_archive_end_to_end.py` walks exactly that.

It is a test rather than a thirty-first published certificate on purpose. This model is already
certified through the [kinetic milestone](../datasets/kinetic/milestone/); a second certificate for
the same model, with a reference computed the same way, would add a registry row and no information.
What is worth proving is that the path runs.
