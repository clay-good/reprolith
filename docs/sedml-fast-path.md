# The SED-ML adopt-and-verify fast-path

Many modeling papers ship a **SED-ML** document beside their model — a machine-readable description
of the simulation experiment: which model to run, for how long, at what resolution, and which
species to observe. When that recipe exists, reproduction is mostly "adopt it and run," rather than
reconstructing the simulation settings by hand. This is the highest certificate yield per unit
effort, and it applies across every ODE class.

The document says more than that, though, and this page follows all of it: the recipe it writes
down, the **claims** its plots stake, the **archive** it usually travels in, and whether the two
files in that archive still agree with each other. One section walks an archive end to end, from a
zip to a certificate, with no hand-written claim anywhere in between. The last section goes the
other way: writing an archive, so a reconstruction leaves in the same standard form it arrived in.

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

A target selecting on any attribute other than `id`, one using a descendant axis (`//species[...]`)
or a function the resolver does not read, and one not anchored at the model document's root are all
left unreported — not resolving a path is not evidence that the model lacks the element, and
reporting one accuses a correct archive.

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

## Writing an archive

Reading is only half of it. A reconstruction that leaves as a bare SBML string has its run
conditions — how long, how finely, recording what — written down nowhere a simulator can read, so
re-running it means recovering them from prose. `build_omex_archive` closes that: the model, the
SED-ML that runs it, and the manifest, as bytes.

```python
from reprolith import build_experiment_sedml, build_model_sbml, build_omex_archive

model = build_model_sbml(dossier)
archive = build_omex_archive(model, build_experiment_sedml(model, duration=24.0, steps=240))
Path("reconstruction.omex").write_bytes(archive)
```

Two composable pieces: one writes the document, the other packages it. Both use only the standard
library, neither touches the filesystem, and the archive's bytes are deterministic — fixed member
order, fixed timestamps — so the same model and experiment produce the same archive and it can be
digested like any other artifact here.

`model_location` is the path the *document* names, which a reader resolves relative to the document.
The packager checks the two agree: an experiment whose `source` resolves to a file the archive does
not store is refused where the mistake was made, rather than shipped as bytes that fail for whoever
opens them. It also refuses a storage location that is not a plain relative path inside the archive
— a zip member name is written verbatim, and where `../x.xml` lands is the extractor's decision, not
one an exported artifact gets to make on someone else's machine.

### Exporting a published reconstruction

A bare run is not what Reprolith publishes. It publishes a **reconstruction bundle** — per claim, a
window, a sample count, the output to read, and the parameter values that claim sets — and
`build_bundle_sedml` writes that:

```python
experiment = build_bundle_sedml(bundle, model_sbml)
archive = build_omex_archive(model_sbml, experiment.sedml)
```

Each step becomes a task, over the base model or over a model derived from it by that step's
overrides, plus a report of time and the step's output. Steps that run the same window at the same
resolution share one simulation. The **overrides** are the reason this exists: they are what
separates two claims on one model, and until now they lived only in Reprolith's JSON. In the
published metformin bundle that is the 779.9 mg free-base dose — the value without which the
1000 mg claim runs the 500 mg arm, and taken naively (1000 mg straight in) overshoots the paper by
26%. It is now a `changeAttribute` in a file any simulator can act on.

From a terminal, the same thing without Python:

```bash
reprolith export BIOMD0000001028 \
  --model datasets/worked_examples/Zake2021_metformin_human_single_PO.xml \
  --out reconstruction.omex
```

It is the CLI's only writing command. It refuses a `--model` the bundle was not built from — the
store records which file a reconstruction used, never its bytes, and an archive built from another
model packages a run the certificate never judged.

`build_bundle_sedml` returns what it wrote *and* what it could not: `expressed` names the claims
that became tasks, and `unexpressed` carries one line per step it could not state — no sample
count, a window that is not a number starting at zero, an output the model does not have, or an
override naming a parameter the model does not declare. A step is listed, never dropped: an archive
quietly short of a claim reads as a reconstruction that never had one.

What it does not check is whether an override that *does* name a model parameter takes effect — one
fixed by a rule, or shadowed by a kinetic law's own local parameter. That needs the model's math
read rather than its element names, and certification already applies exactly that check to every
override before a bundle can carry one.

Two things stay outside the document on purpose. The **metric** (`cmax`, `auc`) is not written: a
report records the trajectory, and which scalar is read off it is the certificate's statement, not
the run's. And the **engine pin** is not written: SED-ML names a solver *method*, and the document
does say CVODE, but the pinned engine and version that computed a verdict belong to the certificate,
which is what expires when a solver changes.

The MCP surface has no export tool, deliberately. The server holds the catalog, the certificates,
the dossiers, and the bundles — never the model bytes — so an agent would have to send the model
over JSON-RPC and take an archive back as base64. The bundle is already readable through the
`bundle` tool, and an agent that wants the archive can build it from the same library the CLI uses.

### It reports; it does not plot

SED-ML has two ways to name the quantities a run records, and the difference is the whole honesty
question for an export:

| | What it means | What Reprolith reads it as |
| --- | --- | --- |
| `plot` | the curves this work displays | the document's own statement of a published result — a targetable claim |
| `report` | write these columns | an export format, asserting nothing about what was published |

An exported reproduction is the second thing. It knows how to run the model; it does not know which
of its outputs anyone displayed — that lives in the dossier's claims and in the certificate, and
SED-ML has no vocabulary for it. Emitting a plot would produce a document that, read back by
Reprolith's own claim reader, manufactures one published result per state variable. So the export
writes a report, and re-ingesting an exported archive gives back the model's structure and **no
targetable claims**: an honest silence rather than an invented checklist.

### What it refuses

| Refused | Why |
| --- | --- |
| A variable the model does not have | The document would record a column that cannot exist — the same mismatch `archive_mismatches` reports when reading an archive. Every target the writer emits resolves in the model it ships with, by nesting. |
| A run with a non-positive duration or step count | Not a run. |
| A model and an experiment at the same location | An archive stores one file per location. |
| A model declaring the `fbc`, `qual`, `spatial`, or `multi` SBML package | Reprolith certifies six classes and only some are integrated trajectories. An FBA model is solved at steady state; a logical one advances in discrete update steps. A uniform time course written for either is valid SED-ML describing a run nobody performs, which is worse than a refusal. Packages that only annotate (`layout`, `render`, `distrib`, `comp`) leave the run a time course and are not refused. |

The document declares SED-ML **L1V4**, which is not cosmetic: a uniform time course spells its
sample count `numberOfSteps` only from L1V4 onward (L1V3 says `numberOfPoints`), and that is the
attribute this repository's parser reads. An earlier declaration over a later attribute writes a
document that reads here and fails validation everywhere else. libSEDML — an independent
implementation, not this one — rejected exactly that, and reads the corrected document with zero
errors; `tests/test_export.py` keeps both facts.
