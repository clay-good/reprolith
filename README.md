# Reprolith

**Point it at a modeling paper. Get back proof of whether the model reproduces its own results.**

About half of published biomedical models can't be reproduced from the information in
their own paper. Reprolith rebuilds the model from the paper, re-runs it, and checks the
output against the paper's own figures and tables — then hands you a **certificate**:
reproduced, partially, or not — for each result, with the reason.

That is what it is *for*, and it is worth being exact about how much of it is done today.

Of the thirty-three published certificates, **four** check a reconstruction against numbers read
from a paper — one for each model that paper deposited. Between them they carry **eighty claims**,
every one a number the paper's own model reports: ten tissues at 500, 1000 and 1500 mg after a
single human dose, again under twice-daily dosing, seven tissues in mice by peak and by 24-hour
exposure, three validation arms that each follow an earlier dose, and the intravenous mouse model's
three exposures.

The mouse entry is the first in this class to come back **`reproduced`** — a clean, unqualified
pass. Seven tissues, worst error 0.17%, and no assumption: that paper dosed its mice with metformin
rather than the hydrochloride salt, so nothing had to be converted. It is also the first agreement
the blind self-validation run has recorded for this class, which stood at 0 of 31 this morning.

**Seventy-two reproduce, seven do not, and one cannot be evaluated — each with its reason.** Three because the
deposited model runs four of the eight administrations its own name states — which matters only for
a tissue slow enough to still be accumulating, so the cause is recorded per claim rather than as a
verdict on the model. Three because one cell of the paper's table contradicts the rest of its own
row: its Brain Cmax equals plasma's, while that row's AUC and mean concentration are four fifths of
plasma's — and the reconstruction regenerates that row's AUC to 0.07% while missing its Cmax by
20%, so it reproduces every other number the paper published for that tissue. One more misses by
75% with **no cause established**, and says exactly that rather than inventing one. And one claim
cannot be evaluated at all: an intravenous exposure whose value still moves 22% when the run is
sampled twice as finely, so no verdict is stated. Each publishes what was measured, what it
implicates, and that a fault is a hypothesis. That is the output this project exists to produce.

Two things are deliberately not claimed. The paper's Intestine and Kidney rows: the model splits
each across three compartments, and which one the row means is a judgement about the paper. And
anything not committed: every reference value is quoted from the article in
[`datasets/manuscripts/`](datasets/manuscripts/) and checked against it by a test, because for most
of this repository's life nothing did — one of the first two was recorded as 6.2, a number the
paper does not contain.

The other twenty-nine certificates check Reprolith's engine against an independent tool — COBRApy,
libRoadRunner, CANA — or against closed-form mathematics, re-running the same model file. Each
certificate says which on its own claim line. Getting a paper's claims out of its manuscript *at scale* is the piece that is not built.
`claims-propose` reads candidates out of a paper's **tables**, which is how those sixty-three
arrived — but a curator still chooses which candidate is a claim and which model output it reads,
and measured on this test set, only **three papers in ten** of the open-access subset print a
reported model output in a table at all
([`datasets/manuscripts/table_survey.json`](datasets/manuscripts/table_survey.json)). The rest put
their results in figures — and that is about the pictures, not about unread text. Reading a
paper's prose is built (`propose_claims_from_prose`) and measured to reach no paper the tables
miss, and the figure *captions* were inside that same sweep all along: 87 of 87 caption paragraphs
across the ten papers, carrying ten candidates and not one that names a quantity a model reports.
It is not a shipped command for exactly that reason — it buys nothing a curator does not already
have.

For those figures, the **intake** half is now built and the reading half is not, and the split is
deliberate. Reprolith digitizes nothing: a curator reads the curve off the picture with a plot
digitizer, and what arrives is that tool's output. What Reprolith does is the part the digitizer
cannot — refuse a reading that is *wrong* rather than imprecise (a point outside its own axes is a
calibration error, and produces values that are ordered, smooth, plausible and off by a constant
factor), and put the series on the run's own sample grid, interpolated in the axis's own scale,
never extrapolated past what was read. A value read off a picture can only ever be recorded as
`digitized-figure`, so the wider band it is judged in is not escapable. That turns a figure claim
from a permanent abstention into a judged one: a SED-ML document says which curve the paper plots,
the curator's file says what that curve read, and the certificate carries a verdict marked
`[figure-reading]` so a reader can see the number was read off a picture rather than printed. No published figure is in this corpus, so it is
validated against series generated from known functions — mathematics, not a paper's picture. See
[`docs/figure-values.md`](docs/figure-values.md).
[`docs/findings-note.md`](docs/findings-note.md) and [`openspec/`](openspec/) say so in detail. Where a paper ships a **SED-ML** document, the half of that
job the document already did is read from it: its plots say which curves the paper shows, and those
become the dossier's claims. Their *values* are still not there, so such a claim is figure-referenced
and the oracle abstains — unless the document ships them: a curve plotted from a data file the
archive carries travels with those values, as the paper's own recorded points rather than a result
the model owes. No document in the corpus does that today. See
[`docs/sedml-fast-path.md`](docs/sedml-fast-path.md).

---

## Why this works when biology usually doesn't

You normally can't check a biology claim without a lab. But a paper's own figure is different:
it's a **computational result**, and re-running the model either matches it or it doesn't —
checkable, for free, to a stated tolerance. Reprolith lives entirely in that gap. No lab, no
guessing — just: *does the described model produce the shown result?*

## What you get

- **A per-result verdict, not a vibe.** Every figure and reported number is checked on its own —
  a curve has to match on average *and* at its worst point, so a doubled peak cannot average
  itself into a pass.
- **Honest by construction.** If a result only reproduced because Reprolith had to assume a
  missing value, the certificate says so. It never takes credit for its own guesses.
- **A "what was missing" list.** When a paper can't be reproduced, you get the exact
  parameter, unit, or condition it left out — the thing the field actually needs to fix.
- **Standard, runnable artifacts.** The model ships as SBML and the engine is pinned by
  version, so anyone can re-run it. A paper that ships a COMBINE archive is read straight out of
  it — the manifest names the model and the experiment, and one file becomes a dossier with
  structure and claims, including a check that the two files refer to the same model elements
  (an override aimed at a parameter that is not there silently runs the unmodified model) and a
  check that the experiment they describe runs what the *paper* reports — both files can be
  perfectly consistent and still never run the reported arm, which is what the shipped metformin
  archive does: it scans the dose over 389.2, 778.4 and 1167.6 mg, and the paper's 1000 mg result
  is 779.9 mg of free base.
  A reconstruction now leaves in that same form: a published bundle — per claim, the window, the
  sample count, the output, and the parameter values that claim sets — is written as SED-ML and
  packaged with the model and a manifest, in deterministic bytes no Reprolith is needed to re-run.
  The overrides are the point: metformin's 779.9 mg free-base dose is what separates its two claims
  and used to live only in Reprolith's JSON. A step the document cannot state is listed with the
  reason, never dropped, and the exported document *reports* its columns rather than *plotting*
  them, so re-reading it manufactures no published results the paper never staked
  ([`docs/sedml-fast-path.md`](docs/sedml-fast-path.md)). The metformin worked example ships its
  archive: [`datasets/worked_examples/metformin_reconstruction.omex`](datasets/worked_examples/).
  The certificate itself still travels as Reprolith's own JSON record.
- **A verdict that expires.** Every certificate names the software that computed it — including,
  for the classes Reprolith solves itself, the revision of that code — so changing a solver flags
  every certificate it invalidates instead of leaving them looking current.

## What it is *not*

Reproducible is not the same as correct, and neither is the same as safe to use on a patient.
A certificate attests to one thing only: that the model regenerates its own published results.
It makes **no** claim about biological truth or clinical use. Every certificate says this in
plain text.

## For agents, too

Reprolith runs as an **MCP server**, so an AI agent can call it mid-workflow as a deterministic
reproducibility check — submit a model, get a verdict it can trust and cite. Same engine,
same answers as the human-facing repository.

The server is dependency-free (JSON-RPC over stdio, no third-party SDK) and exposes read-only
tools — browse the catalog, get a paper's status, fetch a certificate, read its gaps, inspect a
dossier or bundle — each delegating to the same query surface the repository uses, so a verdict
always travels with its scope flag and qualifications. A separate set of effectful tools closes
an agent's work loop: claim the next entry, then record the result against
that certificate's digest so the finished unit leaves the queue. The outcome state is read from
the certificate's own verdict, never asserted by the caller. Run it with `reprolith-mcp` (after
`pip install -e .`); see [docs/mcp-server.md](docs/mcp-server.md) to register it in a client and
for the tool reference.

## For humans, at a terminal

The same read-only surface is a plain CLI, so you don't need to speak JSON-RPC or write Python to
read a verdict. It reads the exact state the MCP server does through the exact same query model —
the terminal view and the agent view can't disagree — and every certificate prints in the same
scope-flagged human form the repository publishes. Both surfaces aggregate every class's published
milestone certificates, so any of the six classes' verdicts is reachable, not just PK/PD's.

```bash
reprolith catalog                    # browse the catalog (blind public view)
reprolith backlog                    # backlog depth by state, class, difficulty
reprolith certificate <digest>       # the full certificate, human-readable
reprolith verdict <digest>           # the scope-qualified verdict, never a bare boolean
reprolith gaps <digest>              # the "what was missing" report
reprolith status <accession>         # a paper's lifecycle status and history
reprolith certificates-for <id>      # every certificate digest for one paper, newest first
reprolith self-validation            # the blind track record, per class and overall
reprolith export <accession> \       # the reconstruction as a runnable COMBINE archive
  --model <model.xml> --out <out.omex>
reprolith archive-check <file.omex> \ # what a reproducer would find in your archive
  [--claims <claims.json>]
reprolith archive-check \             # ...or the two files loose, unpackaged
  --sedml <exp.sedml> --model <model.xml>
reprolith claims-template \           # write the claims file archive-check reads
  --model <model.xml> [--sedml <exp.sedml>] [--out <claims.json>]
reprolith claims-propose \            # candidate claims from the tables your paper prints
  --tables <tables.json> [--out <candidates.json>]
reprolith claims-check \              # is each value printed in the table it cites?
  --claims <claims.json> --tables <tables.json>
reprolith params-check \              # does your model carry the values your paper reports?
  --model <model.xml> --parameters <parameters.json>
reprolith figure-template \           # the digitization file, with the claim pairing filled in
  <file.omex> | --sedml <exp.sedml> [--out <figure3a.json>]
reprolith figure-check \              # is this digitization of your figure usable as a reference?
  --series <figure3a.json> [<file.omex> | --sedml <exp.sedml>]
```

`archive-check` is the author-facing counterpart: point it at a COMBINE archive and it says what a
reproducer would find — whether every reaction states a rate law, whether the experiment and the
model agree, whether the document states any published result, whether the run can be adopted
verbatim — and exits non-zero when it cannot. It runs no model and issues no certificate, and it
says so rather than borrowing a certificate's words.
Give it `--claims` — the results your paper reports — and it also answers the question the archive
cannot answer about itself: does the experiment *run* them? On the metformin paper's own archive
that is one line, and it is the load-bearing one:

```
the manuscript's claim 'Cmax-1000mg' sets 'Metformin_Dose_in_Lumen_in_mg' to 779.9, which the
archive never runs: the model states 389.92 and the experiment runs it at 389.2, 778.4, 1167.6
```

`params-check` asks the question in the other direction, about the model's **inputs**. Every
certificate here checks a model's outputs; nothing checked whether the deposit carries the
parameter values its own paper reports. Pair each parameter id with the number your paper prints —
the pairing is yours, and never guessed — and it compares them at the precision the paper printed,
refusing to compare any value an `initialAssignment` or a rule makes inert. On the four deposited
metformin models it comes back clean: all ten tissue-plasma partition coefficients in each are the
ones the paper's Table 3 prints.

`figure-template` and `figure-check` are the same shape for the other half of claim extraction.
The template writes the one mechanical part of a digitization — which curve of your document each
series is the reading for, an id nobody could guess and that has to match exactly — and leaves
blank everything that is a reading: the figure, the tool, both axis ranges, every point. Then
`figure-check` takes a plot digitizer's output for one figure panel and says what each series
carries, how coarsely it was read, and refuses the readings that cannot be trusted. It reports the widest gap between readings
rather than judging it — between two read points the reference is the curator's straight line, and
how much of a comparison rests on that is theirs to weigh.

Give it the document too — the archive, or `--sedml` — and it also checks the half of the file the
template filled in: that each series is paired with a curve the document actually plots, that the
curve can carry a reading at all, and that it is not one the document already ships values for. A
claim id is `plot_0__plot_0_0_0__plot_0_0_1` and has to match exactly, so a typo, a renamed output,
or a digitization read against last month's document is a reading of nothing — and those three
refusals used to be reachable only from Python, which is to say only after somebody else ran the
join. It also compares each reading against the window the document runs: nothing
here is extrapolated, so a curve read from 0.5 h against a run that starts at 0 is a file that is
internally perfect and cannot be used, and both numbers that say so are on disk while the curator
is still at the terminal. Without a document the report says the ids were not checked, rather than
reading clean over a check nobody made. The curves this panel does not read are named and not counted against it: a
curator reads one panel at a time, and "clean" over one of four curves would otherwise read as
four.

`claims-template` writes that file, so an author is not starting from a blank one: it emits one
stub per curve the document plots — the document's own statement of which curves are shown results
— each naming the model output it reads, alongside the parameters a claim can set and the ones the
model's own math determines and will overwrite. It never writes a `reported` value. A template that
read one off the model would hand the check the model's own output as the paper's claim, and the
comparison would pass by construction — the failure the check exists to catch, moved one file
upstream. Reading the numbers out of a *manuscript* is still not built, and this does not pretend
to: the two fields only the author has are left blank, and a file still carrying them is refused
rather than checked.

Without `--claims` that comparison does not run, and the report says so — a clean fix list never
stands in for a check nobody made. It counts what was actually compared, not what it was handed:
an archive with no experiment compares nothing, however many results you supply.

[`docs/author-check.md`](docs/author-check.md) is the guide for the author running it: the two
input forms, the claims-file schema, and what it deliberately will not tell you.

Most papers ship the document and the model loose rather than packaged — BioModels does, and so
does this repository — so `--sedml` and `--model` check them where they are. They are packaged into
the archive they describe and that archive is checked, so the two forms cannot reach different
conclusions; the report says the manifest was generated, since a defect in yours is out of reach
when you do not have one yet.
What Reprolith's *own extraction* would not carry is listed separately and never as a fix, because
some of it the archive omits and some of it the archive states perfectly well.

Every command reads except `export`, which writes the archive named by `--out` — and says so when
that replaced a file that was already there. It packages the
published bundle for that accession — the window, the sample count, the output each claim reads,
and the values that claim sets — and refuses a `--model` the bundle was not built from, since an
archive built from another model packages a run the certificate never judged.

`certificates-for` takes `--by title|doi|pubmed-id|accession`, and it is how you reach the classes
the catalog does not list: the catalog is the PK/PD work queue, while the ledger carries all six
classes' published certificates. The certificate and verdict commands take the digest it returns.

Add `--json` to any read command to get the exact object an agent receives over MCP. Run
`reprolith --help` for the full command list.

## Where it starts

Narrow and deep first: **ODE pharmacokinetic/pharmacodynamic models** — dose-in,
concentration-and-effect-out — end to end, validated against models whose reproducibility is
already independently known. Then it widens, one model class at a time, over a backlog that
never runs dry.

---

*Reprolith · reproduce + monolith · the bedrock layer under a literature that should be
runnable.*

> The failure-mode catalogue, the tolerance defaults, and every disagreement between a blind
> verdict and its label carry a written, machine-audited record of what put them there — see
> [`docs/discipline-loop.md`](docs/discipline-loop.md).

> Status: pre-alpha. Six model classes (PK/PD, constraint-based, kinetic, logical, stochastic,
> spatial) are built and self-validated in the open. See [`openspec/`](openspec/) for the full spec.

## Build and contribute

The core engine is dependency-free (standard library only): the catalog, ingestion dossier,
reconstruction, oracle, certificate, agreement report, and read-only query surface all run
without third-party packages, so the required-checks gate stays fast and trivially
reproducible. The honesty invariants — determinism, the inescapable scope statement, and
assumption-qualification — are enforced in code and checked in CI.

```bash
python -m pip install --upgrade pip   # editable installs need pip >= 21.3
pip install -e ".[dev]"
ruff check . && mypy && pytest -q
```

Work from a clone. The committed body of work — the labelled blind sets, every class's milestone
certificates, the registry — is repository data, not packaged resources, so a non-editable install
carries the code but none of the state the surfaces read. Both surfaces take `--data-dir` if you
need to point an installed copy at a checkout — but it reads exactly the one directory you name,
deliberately, so a digest can never be certified against a certificate the operator's data
directory has never held. The aggregated view over all six classes is what a source checkout gives
you by default; under `--data-dir` you get that directory and nothing else, and a paper outside it
reads as unknown rather than as an error.

Actually running a model needs the optional **`engine`** extra, which pins COPASI (a
BioSimulators-registered engine) and the SBML tooling. It stays out of the core so the fast
gate does not depend on it; the engine-backed tests skip when it is absent.

```bash
pip install -e ".[dev,engine]"   # then pytest -q runs the simulation-backed tests too
```

With the extra installed the full loop runs end to end: a dossier compiles to SBML
([`reprolith.build_model_sbml`](python/reprolith/sbml.py)), runs under the pin
([`reprolith.simulate`](python/reprolith/engine.py)), is judged by the oracle, and produces a
scope-flagged certificate. The blind PK/PD self-validation set lives in
[`datasets/pkpd_test_set.json`](datasets/pkpd_test_set.json), labelled from BioModels'
curation status — which is also the accession prefix, so read that run as evidence of abstention
discipline (30 abstentions, zero wrong verdicts) rather than of blind classification skill; the
dataset and [docs/self-validation.md](docs/self-validation.md) both spell out why.

Constraint-based (FBA) models reproduce a different kind of claim — an optimization outcome, not
a time course — so they get their own oracle behind the optional **`fba`** extra (scipy's linear
solver). It reports the full FROG fingerprint the constraint-based-class spec names — objective
value, flux variability, and both reaction- and gene-deletion outcomes — each preserving the
"abstain when unsure" rule under alternate optima, plus the LP dual (`shadow_prices`: metabolite
shadow prices and reaction reduced costs, validated against the primal by strong duality),
parsimonious FBA (`parsimonious_fluxes`: the minimal-total-flux tie-break among alternate optima),
loopless FVA (`loopless_flux_variability`: the flux-variability interval with thermodynamically
infeasible internal loops removed, so a spurious cycle can't inflate it), synthetic-lethal pairs
(`synthetic_lethal_reactions` / `synthetic_lethal_genes`: double-deletion epistasis — reactions or
genes viable to delete singly but lethal together — that single deletion is blind to), and the
production envelope
(`production_envelope`: the growth-vs-byproduct Pareto front, a provably concave frontier); see
[docs/fba-oracle.md](docs/fba-oracle.md). The same shared pathway carries it end to end: a
constraint-based dossier adopts the paper's SBML-fbc model and records its load-bearing medium,
then certifies to a scope-flagged verdict, reproduced or honestly not. It self-validates against a
real published model: [datasets/constraint_based/](datasets/constraint_based/) ships the *E. coli*
core model, and the `ingest_fbc_sbml` → `solve_objective` pathway reproduces its independently-known
maximal growth rate (0.873922) to every published digit — with a
[worked example](datasets/constraint_based/worked_example/) walking the whole dossier → certificate.
The blind milestone then scales this to **8 real BiGG models** spanning bacteria, a pathogen, and a
eukaryote (up to genome-scale *E. coli* iJO1366, 2583 reactions), each reproduced against the growth
rate the independent COBRApy implementation computes — 8/8 blind agreement — with FROG variability
cross-checked on two models and synthetic lethality (reaction- and gene-level), loopless-FVA, pFBA,
and the production envelope against COBRApy too.

```bash
pip install -e ".[dev,engine,fba]"   # fba brings the LP solver; engine (libsbml) reads the .xml model
```

Generic **systems-biology kinetic models** (signaling, metabolic, gene-regulatory networks) are the
third class. They reuse the PK/PD curve oracle unchanged — the reproducible result is a species
time-course — so adding them is mostly demonstrating the contract generalizes. The class is
self-validated non-circularly against an independent simulator (libRoadRunner): curated BioModels
networks spanning six dynamic regimes (signaling, gene-regulatory, metabolic, cell-cycle, circadian,
calcium) reproduce, and the [milestone blind run](datasets/kinetic/milestone/) scores 6/6 through the
same catalog and agreement machinery as the other classes. See
[docs/kinetic-class.md](docs/kinetic-class.md).

**Logical / Boolean network models** are the fourth class, and the sharpest generalization proof: a
discrete oracle with no continuous trajectory and no optimization, where the reproducible result is
the network's steady states and attractors. It reuses the shared contracts and adds exact,
dependency-free attractor analysis (synchronous and asynchronous), reads standard SBML-qual, and is
self-validated non-circularly against CANA (Correia et al. 2018), an independent Boolean-network
library, on real published models (the Arabidopsis flower, Drosophila segment-polarity, and
budding-yeast cell-cycle networks, and a schemata example). For networks too large to enumerate, a
scalable SAT path (optional `sat` extra) finds fixed points without walking the 2ⁿ state space — the
steady states of three real 44–60-node signalling networks (T-LGL leukemia, MAPK cancer cell-fate,
guard-cell ABA) are reproduced against an independent solver — so the
[milestone blind run](datasets/logical/milestone/) scores 9/9 through the same catalog and agreement
machinery. See [docs/logical-class.md](docs/logical-class.md).

**Stochastic (SSA) models** are the fifth class: discrete-molecule reaction networks where a single
run is a random sample, so the reproducible result is a distribution. An exact, pure-Python
Gillespie simulator (deterministic under a pinned seed) feeds the same distributional oracle the
population figures use, and the class is self-validated non-circularly against closed-form results —
the immigration-death process's Poisson stationary mean and variance and a reversible reaction's
binomial equilibrium — with a 3/3 [milestone blind run](datasets/stochastic/milestone/).

**Population figures** — a median with outer percentiles across a virtual population, which is how
a large slice of the PK/PD and QSP literature reports its results — are judged by the same
distributional oracle, and Reprolith now simulates the population as well as judging it: a
log-normal between-subject variability model, drawn under a stated seed, run subject by subject.
The variability model, the draws, and the percentile definition are written into the certificate's
protocol, because an envelope read without them is a picture rather than a result. It is validated
against mathematics — the closed-form percentiles of a one-compartment model whose volume varies —
not against itself. What is missing is a *paper's* population figure to point it at.

**Reported parameter estimates** — the strongest form of reproducibility, when a paper ships the
data it was fit to — are re-derived rather than taken on trust: `refit_parameters` minimizes least
squares with a deterministic Nelder-Mead written here rather than imported, searching on the log
scale so a rate cannot wander negative and no dependency's version can move the answer. The
objective, the optimizer, the starting values, and the dataset and grid all travel in the
certificate's protocol, and a fit that does not converge inside its budget is refused rather than
reported. Validated by recovering a rate constant that a closed-form regression gives exactly.
Here too, what is missing is a *paper's* shipped dataset to point it at. Both this and the
population path are written up in
[docs/population-and-estimation.md](docs/population-and-estimation.md).

**Spatial reaction-diffusion (PDE) models** are the sixth class: the reproducible result is a
concentration profile over space, so a pure-Python finite-difference solver feeds the same curve
oracle, self-validated non-circularly against the exact analytical diffusion solution (a Gaussian
whose variance grows by 2·D·t) with a 3/3 [milestone blind run](datasets/spatial/milestone/). Every
spatial certificate reads *partially* reproduced even where the profile matches the closed form
exactly: this solver imposes a zero-flux boundary the paper never stated, so the verdict rests on a
choice Reprolith made and says so — the same qualification the stochastic class carries for its
ensemble.

All six classes are measured blind against independently-established ground truth on the same
machinery — [docs/self-validation.md](docs/self-validation.md) is the one-look evidence summary.

Reprolith gets better when people who know the science validate its judgment. When it isn't sure
about a load-bearing value it records the value, marks the result as resting on it, and reports it
in the certificate's gap report — confirming or correcting one is the most valuable thing you can
do here. Those questions are raised as issues **by hand** today, from the verification template;
wiring the queue to GitHub automatically is unbuilt. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licensing

The code is MIT ([LICENSE](LICENSE)). The data Reprolith *produces* — certificates, catalog
entries, dossiers, bundles, agreement reports, the registry page — is CC BY 4.0
([LICENSE-DATASET](LICENSE-DATASET)), so cite it if you build on it. The third-party model files
redistributed under `datasets/` keep their own upstream licenses, and some are more restrictive:
the BiGG models — `e_coli_core` included, not only the genome-scale ones — are academic
and non-profit use only. See
[datasets/THIRD-PARTY-NOTICES.md](datasets/THIRD-PARTY-NOTICES.md) before redistributing.
