# Reprolith

**Point it at a modeling paper. Get back proof of whether the model reproduces its own results.**

About half of published biomedical models can't be reproduced from the information in
their own paper. Reprolith rebuilds the model from the paper, re-runs it, and checks the
output against the paper's own figures and tables — then hands you a **certificate**:
reproduced, partially, or not — for each result, with the reason.

That is what it is *for*, and it is worth being exact about how much of it is done today.

Of the thirty-nine published certificates, **four** check a reconstruction against numbers read
from one paper's own tables — one for each model that paper deposited. (Two more are checked
against published numbers too, and the count below says which.) Between them they carry **one hundred and
seventy claims**,
every one a number the paper's own model reports: ten tissues at 500, 1000 and 1500 mg after a
single human dose, each by peak, by the time of that peak, and by 24-hour exposure; those same ten
tissues by peak and by exposure again
under twice-daily dosing, where the exposure is over the final dosing day and not the whole run;
seven tissues in mice by peak and by 24-hour exposure;
three validation arms that each follow an earlier dose, and the intravenous mouse model's
three exposures.

**Not one of the four is a clean pass, and the reason is a unit.** All four of this paper's
deposited models declare their time unit as 3600·10² seconds — one hundred hours. An area read off
such a model is, by the model's own units, in nmol·(100 h)/mL, where every table the paper prints
says nmol·h/mL. A **time to peak** is the same statement with nothing else in it: read entirely in
the model's clock, it comes out in units of a hundred hours against a column headed `Tmax, h`. The
dynamics say the declaration is the error and not the tables: twenty-six of the thirty times to
peak and the whole AUC24 column reproduce over a run of 24 model time units, which under the
declared unit would be 2400 hours, and the other four times to peak are unjudged for the sampling
grid rather than disagreeing.
But that is a reading *Reprolith* made about the file, so every claim resting on it
is qualified and no certificate here calls itself unqualified. Only a quantity carrying a time
dimension reaches it — an area and a time to peak — which is why seventy peak claims never touched
it, and why this repository shipped seven
AUC claims and a front page announcing a clean pass before the check that finds it was ever pointed
at more than one entry. It is pointed at every one now
([`tests/test_claim_units.py`](tests/test_claim_units.py)).

**One hundred and fifty-five reproduce, ten do not, and five cannot be evaluated — each with its reason.** Six because the
deposited model runs four of the eight administrations its own name states — which matters only for
a tissue slow enough to still be accumulating, and shows there on *both* metrics: red blood cells
miss on peak by 15% and on exposure by 37%, at each of three doses. The cause is recorded per claim
rather than as a verdict on the model. Three more because one cell of the paper's table contradicts
the rest of its own
row: its Brain Cmax equals plasma's, while that row's AUC and mean concentration are four fifths of
plasma's — and the reconstruction regenerates that row's certified AUC to 0.07% while missing its
Cmax by 20%, so it reproduces every other number the paper published for that tissue. **That
separation is the evidence**: a protocol run too short misses the whole profile, a wrong cell
misses one number in a row that otherwise reproduces. One more misses by
75% with **no cause established**, and says exactly that rather than inventing one. And five claims
cannot be evaluated at all. One is an intravenous exposure whose value still moves 22% when the run
is sampled twice as finely. The other four are times to peak, and they abstain for a sharper reason:
each landed within a fraction of a percent of the pass line while the run's own sampling moves it by
more than that, so which side of the line it fell on was the grid's answer rather than the model's.
A time to peak can only ever be one of the sample times — on this run the spacing is 0.05 h, half
the pass budget at a reported 2.0 h, spent before the model is consulted. Each publishes what was measured, what it
implicates, and that a fault is a hypothesis. That is the output this project exists to produce.

Three things are deliberately not claimed. The paper's Intestine and Kidney rows: the model splits
each across three compartments, and which one the row means is a judgement about the paper. **The
twice-daily table's Tmax column**, for the same kind of reason and a sharper one: that table's
AUC24 is unambiguously over the run's final dosing day — its ten tissues reproduce there to better
than 0.2% and to 92% off over the whole run — and its Tmax is not. Over that same window the model
peaks a flat **11.95 h** later than the column prints, at every tissue and every dose, which is one
dosing interval to within the sample spacing: the paper is timing from a different dose. Which one
is a judgement about the paper, and claiming the column anyway would manufacture thirty failures
out of an unresolved convention. Its peak *heights* are claimed, and they reproduce. **The T½ column of both tables**, for a
reason that is harder to see: this run does have a terminal phase, and over its last quarter
plasma, liver, muscle and brain decay at the *same* rate to within 0.03 h with a fit
indistinguishable from perfect — the system's slowest compartment governing everything downstream.
The paper prints 3.7, 2.5, 5.5 and 3.8 for those four. Whatever its column is fitted over, it is
not that, and the table does not say. A half-life metric written the obvious way would publish a
beautiful fit to the wrong quantity, which is the failure that is hardest to catch because the
fit's own diagnostics call it perfect. And
anything not committed: every reference value is quoted from the article in
[`datasets/manuscripts/`](datasets/manuscripts/) and checked against it by a test, because for most
of this repository's life nothing did — one of the first two was recorded as 6.2, a number the
paper does not contain.

Thirty-three of the other thirty-five certificates check Reprolith's engine against an independent
tool — COBRApy, libRoadRunner, CANA — or against closed-form mathematics, re-running the same model
file. The other two are checked against published numbers like the four above: the E. coli core
model's maximal growth rate of **0.873922**, which the publication that distributes that model
reports — that certificate also carries the **essential genes and reactions** of the same model,
checked element for element against COBRApy's single-deletion answer — and the seven basin sizes
Li et al. 2004 publish for the yeast cell-cycle network, how many initial states reach each of its
steady states, all seven reproduced exactly. Six against a
publication, then, and thirty-three against a tool or against mathematics — one certificate, the
E. coli core one, in both counts, because its growth rate is a publication's number and its two
essential sets are COBRApy's answers for the same file —
counted from the certificates themselves by `tests/test_reference_provenance.py`, because this
division is the reader's whole guide to what the corpus reaches, and it was prose that was off by
one. Each certificate says which on its own claim line. Getting a paper's claims out of its manuscript *at scale* is the piece that is not built.
`claims-propose` reads candidates out of a paper's **tables**, which is how those sixty-three
arrived — and given the model as well it now *suggests* which output each row names, where the
paper's word and the model's are the same word (measured against the four metformin deposits'
hand-written claims: 22 rows agreed, 12 silent, none wrong). A curator still chooses which candidate
is a claim and confirms every suggestion,
and measured on this test set, only **three papers in ten** of the open-access subset print a
reported model output in a table at all
([`datasets/manuscripts/table_survey.json`](datasets/manuscripts/table_survey.json)). The rest put
their results in figures — and that is about the pictures, not about unread text. Reading a
paper's prose is built (`propose_claims_from_prose`) and measured to reach no paper the tables
miss, and the figure *captions* were inside that same sweep all along: 87 of 87 caption paragraphs
across the ten papers, carrying thirteen candidates and not one that names a quantity a model
reports. That reader knows every class's units now, not just this one's — a front speed in µm/min,
a decay length in µm, a specific flux in mmol/gDW/h, a growth rate in 1/h. A unit it does not know
is a result it cannot see, since the unit is what separates a stated quantity from a figure number
or a year, so five sixths of what this engine can judge produced no candidate at all rather than a
noisy one. On the same ten papers it now reads 113 numbers where it read 107.
That measurement is about which *papers* become reachable, and it was read for a while as a verdict
on the reader itself, which left it importable and unrunnable. Per paper it does the opposite: it
broadens what can be read from a paper the tables already reach, and for an author whose peak is in
a sentence it is the only reader there is. So it ships as `claims-propose --prose`, beside the
tables it merges with — and what it does not do is de-duplicate, since a value printed in a table
and restated in a sentence is two citations and choosing between them is the curator's judgment.

For those figures, the **intake** half is now built and the reading half is not, and the split is
deliberate. Reprolith digitizes nothing: a curator reads the curve off the picture with a plot
digitizer, and what arrives is that tool's output. What Reprolith does is the part the digitizer
cannot — refuse a reading that is *wrong* rather than imprecise (a point outside its own axes is a
calibration error, and produces values that are ordered, smooth, plausible and off by a constant
factor), and put the series on the run's own sample grid, interpolated in the axis's own scale,
never extrapolated past what was read. A value read off a picture can only ever be recorded as
`digitized-figure`, so the wider band it is judged in is not escapable — and a claim that takes
that band has to name what read the figure, so it is not free in the other direction either. That turns a figure claim
from a permanent abstention into a judged one: a SED-ML document says which curve the paper plots,
the curator's file says what that curve read, and the certificate carries a verdict marked
`[figure-reading]` so a reader can see the number was read off a picture rather than printed. It
also checks what the curator cannot see in their own file — that each reading is paired with a curve
their document actually plots, that one file is one panel, and that the reading covers the window
the run covers — because every one of those refusals used to live where only the join could reach
it, long after the curator had finished.

And the cost of reading a picture is a measured number rather than a caution. Between two read
points the reference is a straight line, so a **flawless** five-point reading of an oral PK curve
misses the curve it was read off by 0.25 against a 0.20 pass budget, with no model involved; twenty
points brings it to 0.025, and an exponential read off a log axis is recovered exactly.

That number is now about *your* reading rather than about a curve nobody has. Dropping each read
point and rejoining its neighbours measures the curve's own curvature, so the reading says what
share of the pass budget it spends on its own straight lines and where it bends most — which is
where to read more. It over-states, in the safe direction. The widest gap between readings is still
reported and was never able to say this: it could not tell a peak read at three points from a
straight line read at three, and said nothing at all about a ten-point reading of a PK curve, whose
gaps are a comfortable 11% of the span while its straight lines spend one and a half times the
whole budget.

And it is measured over the window the verdict is measured over. A reading is required to *cover*
the run, so it is permitted to exceed it — and a bend past the end of the run, along with the range
that bend adds to the scale, is cost nothing is judged on. Charged against the whole file, one
reading of a curve that bends inside the run and climbs steeply after it reported 0.93 where the
run's own window carries 2.0.

A *single* value read off a picture — a peak height, a reported Cmax — has no interpolation for any
of that to measure, and its own cost turns on something a curator can act on before reading
anything. A click off by a pixel is off by one pixel's worth of the axis, so on a **linear** axis
what it costs depends on where in the axis the value sits: on a 0-10 axis drawn 600 px tall, half a
pixel is 0.6% of the pass budget at the peak, 56% at a hundredth of it, and the whole budget below
0.56% of the span. On a **log** axis a pixel is a constant ratio and costs 3.9% wherever it is read.
A value read low on a linear axis is not readable in this band; the same value on a log axis is.

It reaches all three people who need it. The **curator** sees it in `figure-check`, before the
reading is used, over the run their document states. The **certificate** carries it, over the grid
the claim was judged on, because a reader who sees `[figure-reading]` and a
band twice as wide could not otherwise tell whether the reading had already spent that band or none
of it. And the **author** gets it back in the pre-submission report — named, with the one cheap fix
only they can make, and deliberately not as something that blocks their submission: publishing
results as figures is what papers do. No published figure is in this corpus, so it is
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
- **An answer to "can it check the thing my paper reports?"** Seventeen kinds of result can be
  certified: a curve, a peak or an area, an oscillation's period, a population's envelope *and* its
  %CV, a re-fitted parameter, a Boolean network's steady states, attractors and basins, a growth
  rate, an essential-gene set, a flux and the range a flux can take, a Fano factor, a mean time to
  extinction, a diffusion profile, a decay length, a front speed, a Turing wavelength.
  [`docs/claim-types.md`](docs/claim-types.md) lists every one with what it is compared against and
  — for each — **how it refuses**, and states the quantities this engine computes and deliberately
  does not certify, so the page is a boundary rather than a brochure.
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
- **A plan for a budget you can actually afford.** A paper's thirty-three published numbers are
  not thirty-three independent things to check: ten tissues at three doses is one model shown
  thirty-three ways. `select-claims` picks the *set* that buys the most independent evidence for a
  given budget, penalizing overlap between what each claim rests on. On the metformin paper at a
  budget of four, reading a ranking one claim at a time takes plasma at four doses and witnesses 46
  model elements; choosing as a set takes four different tissues and witnesses 60. What each claim
  rests on is **derived from the model**, not from the claim's own prose — its tissue's partition
  coefficient, that tissue's blood flow, the two reactions moving drug in and out of it, and the
  arterial pool every tissue routes through. The plan itself is not a verdict: no model is run, and
  a claim left unselected is unattempted rather than unreproduced. When one *is* followed, the
  certificate says so — the budget, the objective, and every claim by id that it did not attempt,
  and its verdict is qualified for as long as one of them stands. The corpus's only unqualified
  `reproduced` (fourteen claims on the mouse oral model) stops being one under a budget of three,
  which is the point: three passes are a weaker result than fourteen and the word has to say so
  ([`docs/claim-selection.md`](docs/claim-selection.md)).
- **A second opinion, or an honest blank.** A model can reproduce its paper for the wrong reason —
  a solver artifact that agrees with the figure. So the same runs go through a second,
  independently-implemented engine and the agreement is published beside the verdict, never gating
  it: 80 PK/PD claims at the dose each was certified at and 6 kinetic models under COPASI 4.46.300
  against libRoadRunner 2.7.0; 8 constraint-based models under Reprolith's own LP against COBRApy
  0.31.1; and all 9 logical networks against CANA 1.0.0 and, for the 44-to-60-node models where no
  2ⁿ enumeration is possible, sympy's SAT against the z3 Reprolith uses. All agree, and the builds
  are the record's own, because a bound measured against one of them says nothing about the next.
  What is compared is chosen per class rather than per convenience: the **objective value** for a
  linear program, whose optimum is unique where the flux vector attaining it is not, so comparing
  flux distributions would call two correct solvers engine-sensitive on any model with alternate
  optima; and for the discrete classes the attractor set or fixed-point set itself, which two
  enumerations either return or do not — published as an exact match rather than as a distance of
  zero, which would read as the best number on the page. The stochastic class's 3 networks joined
  them under libRoadRunner's Gillespie integrator, and they are the reason this paragraph cannot
  end at "all agree": two ensembles of one model agree only up to Monte Carlo error, so what is
  compared there is the difference of the two means over their combined standard error — 1.9, 1.6
  and 1.0 against a criterion of three — and each is published with the bias it could *not* have
  seen, 6.5%, 5.2% and 1.8% of the mean. The first of those is wider than the 5% that class's own
  verdict passes at, so on that model the second opinion is weaker than the verdict it stands
  beside, and the record says so. A fourth compares the two samplers' **Fano factors** rather than
  their means, over each side's own resampled error bar — 0.4 standard errors apart, resolving 9.6%
  of the Fano factor — which is why that class's line now says "of each quantity compared" instead
  of naming a mean it is only partly about. The spatial class's 5 entries complete the set under scipy's
  LSODA — its two *scalars* are compared on the quantity each certificate publishes, a fitted decay
  length and a measured front speed, and the front is the one place in this repository where two
  engines **disagree**: 1.9154 against 2.0100 over the same window, 4.7% apart, published as a
  disagreement rather than widened away. Refining the time step walks this side toward the other
  (4.2% low at a diffusion number of 0.2, 1.9% at 0.1, 0.7% at 0.05), so what the claim's stated
  tolerance is *for* is the explicit stepper's own error and not, as this project first wrote down,
  the front's logarithmic approach to its asymptote. The profiles' 1e-03 is the other number that
  must not be misread: it is what this class's
  explicit stepper costs against an exact integration of the same semi-discrete system, and against
  the continuum solution the same profiles sit 2.0e-05 away — *closer* than the two engines are to
  each other, because the scheme's time and space errors have opposite signs. **All six classes are
  corroborated**, which for most of this project's life two were not, on the recorded grounds that
  no installed implementation answered their questions. Neither half was ever checked and neither
  held. `reprolith corroboration` still prints an unchecked class in the same list as the checked
  ones, because a class can lose an engine and a table of only the corroborated ones would read
  as a whole-repository pass — and it now says the same thing about a *partly* corroborated class,
  since a count of what has a record cannot see a certificate that has none. It is reachable from the terminal and over MCP, not only from the
  published page ([`docs/self-validation.md`](docs/self-validation.md)).

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
dossier or bundle, see what the published set is still resting on — each delegating to the same query surface the repository uses, so a verdict
always travels with its scope flag and qualifications. A separate set of effectful tools closes
an agent's work loop: claim the next entry, then record the result against
that certificate's digest so the finished unit leaves the queue. The outcome state is read from
the certificate's own verdict, never asserted by the caller. That loop is **bounded**: a claim is
recorded even when it achieves nothing, and an entry claimed three times with no lifecycle
transition between the claims stops being offered — otherwise an entry that defeats everyone who
takes it is handed out again the moment its lease lapses, and since readier work ranks first, an
easy one of those sits at the head of the queue in front of every agent forever. It is out of the
automatic pool, not out of reach, and the refusal names it with a diagnosis: how many claims, by
whom, and what those claimants said stopped them — so one shared obstacle reads as one obstacle
rather than three. Say why when you hand an entry back; a claim abandoned at lease expiry records
nothing, and the diagnosis distinguishes that silence from a considered answer. Run it with `reprolith-mcp` (after
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
reprolith backlog                    # backlog depth, and the one thing most of it waits on
reprolith certificate <digest>       # the full certificate, human-readable
reprolith verdict <digest>           # the scope-qualified verdict, never a bare boolean
reprolith gaps <digest>              # the "what was missing" report
reprolith presubmission <digest>     # the same certificate, as a fix list for its author
reprolith status <accession>         # a paper's lifecycle status and history
reprolith dossier <accession>        # what was extracted from the paper, and from where
reprolith bundle <accession>         # the reconstruction the certificate was issued against
reprolith certificates-for <id>      # every certificate digest for one paper, newest first
reprolith loop-status                # is there publishable work — and if not, what is holding it
reprolith verification-queue         # what every standing certificate rests on, awaiting review
reprolith verification-issue <id>    # one of those as the filled GitHub issue to open
reprolith issue-reconcile <issues>   # where the filed issues and that queue disagree
reprolith recertification-due        # which standing certificates owe a re-run, and why
reprolith self-validation            # the blind track record, per class and overall
reprolith corroboration              # what a second engine said — and where none was asked
reprolith select-claims <accession> \ # which claims to reproduce on a budget you can afford
  --budget <n>
reprolith export <accession> \       # the reconstruction as a runnable COMBINE archive
  --model <model.xml> --out <out.omex>
reprolith archive-check <file.omex> \ # what a reproducer would find in your archive
  [--claims <claims.json>]
reprolith archive-check \             # ...or the two files loose, unpackaged
  --sedml <exp.sedml> --model <model.xml>
reprolith claims-template \           # write the claims file archive-check reads
  --model <model.xml> [--sedml <exp.sedml>] [--out <claims.json>]
reprolith claims-propose \            # candidate claims from the tables your paper prints
  --tables <tables.json> [--model <model.xml>] [--out <candidates.json>]
reprolith claims-check \              # is each value printed in the table it cites?
  --claims <claims.json> --tables <tables.json> [--model <model.xml>]
reprolith params-propose \            # candidate parameter values from the tables your paper prints
  --tables <tables.json> [--out <parameters.json>]
reprolith params-template \           # write the parameters file params-check reads
  <file.omex> | --model <model.xml> [--out <parameters.json>]
reprolith params-check \              # does your model carry the values your paper reports?
  <file.omex> | --model <model.xml> --parameters <parameters.json>
reprolith figure-template \           # the digitization file, with the claim pairing filled in
  <file.omex> | --sedml <exp.sedml> [--plot <plot_0>] [--out <f.json> | --out-dir <dir>]
reprolith figure-check \              # is this digitization of your figure usable as a reference?
  --series <figure3a.json> [--series ...] [<file.omex> | --sedml <exp.sedml>] [--model <model.xml>]
```

`archive-check` is the author-facing counterpart: point it at a COMBINE archive and it says what a
reproducer would find — whether the model and the document name their own quantities at all,
whether every reaction states a rate law, whether the author's own recorded data can be read,
whether the experiment and the model agree, whether the document states any published result,
whether the run can be adopted verbatim — and exits non-zero when it cannot.
The first and third of those exist because their failures are *silent*. An element with no
identifier makes libRoadRunner run a model nobody wrote while COPASI refuses the file outright, and
libSBML calls it an error rather than a fatal one and hands the document back regardless. A data
series that cannot be read leaves the claim citing it with no reference values, which is exactly
what this report says about a paper that published none. Both were things Reprolith itself could
produce and nothing said so. It runs no model and issues no certificate, and it
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

And it counts **comparisons, not rows**. A parameters file straight out of `params-template` pairs
nothing, so nothing is compared — and it used to print "41 PARAMETER(S) CHECKED" over 41 rows it
had skipped and exit `0`, which is the status this command documents as droppable into a
pre-submission gate. The header now reads `10 OF 10`, and a file where nothing was compared says so
and exits non-zero when the rows are still the template's blanks. Only then: a file the author did
fill in, whose rows could not be compared for a reason printed beside each, keeps its zero, because
a value nobody could check is not a value that is wrong.

It also names what it could not check, which is the number this project is about. Ten of that
model's sixteen settable parameters are reported and **six are not** — the body weight, the cardiac
output, the glomerular filtration flow, two tissue coefficients, and the dose, which is the very
quantity the certificate's one load-bearing assumption is about. Those are values a reproducer
rebuilding from the paper has to take from the author's deposit or guess. A parameter the model's
own math determines is not counted: it does not run at the number in its `value` attribute, so a
paper omits nothing by leaving it out. Reported, never gated — which of the six belong in a paper
is the author's call.

Across all four models that paper deposited the count is **40 of 62** settable parameters paired
with a printed value, and the same handful is missing from each. That is the first measurement here
about a paper's *inputs* rather than its outputs — every certificate above checks outputs — and it
is a fact about this paper, which is what four models by one group can support. It is not a survey,
and nothing here is a rate for the literature.

That floor had a floor of its own: it read the model's parameter list and nothing else. A PBPK
paper's parameter table prints **tissue volumes**, and those are compartments; its initial
conditions are species. So an author pairing their published liver volume with the compartment
carrying it was told `MISMATCH: the model declares no parameter 'Liver'` — against a deposit
holding the very number their paper prints. Both are checked now, and named separately when
unstated, because a volume reported in a list called "parameters" answers about the wrong thing.

The measurement runs the opposite way from the guess. Across those four models the parameter count
was not seeing **96** further settable values — 16 compartment sizes and 80 initial conditions —
and the volumes are the finding: each model declares twenty compartments and scales **sixteen** of
them from the body weight with an `initialAssignment`, so the paper omits nothing by not printing
them and they are not counted. Four are left, the lumen and excreta compartments. Which is why
this is reported and never gated.

Every answer carries the unit the model declares for that value, resolved through its
`unitDefinition`: `units="volume"` is a reference and not a unit, and it is the resolved
`10^-3 litre` that tells an author whether their published litres and their deposit's millilitres
are the same number. State the unit you published in and a difference is **refused** rather than
compared — two numbers in different quantities mean nothing to each other in either direction, and
the pair that agrees at a factor of a thousand is the one no output check downstream can catch.

A claim's number gets the same question asked three ways, because three different things can be
wrong about it. `claims-check` asks whether the cited table prints that number; with `--model` it
asks whether the model reads that output in the unit the claim states; and against the table's own
column heading it asks whether the *paper* states it in that unit — a value read out of a µmol
column and labelled nmol passes the other two, since the number is printed and the model's unit is
whatever it is. All eighty committed claims pass all three.

Every deposit here fails one of those questions in a way worth naming: each metformin model
declares its time unit as `multiplier="3600" scale="2"`, which SBML reads as **360000 seconds** —
a hundred hours — while the paper's tables and the model's own shipped run are in hours. No
certificate is wrong because of it, since nothing in the pipeline reads `timeUnits`; a reproducer
rebuilding from the deposit's own declarations would be, by a factor of a hundred.

`params-template` writes that pairing file out of the model, one row per settable value with the
blanks left for the author — and never with a number in them, because a template carrying the
model's own value would hand the check that value as the paper's and the comparison would agree by
construction. It is the same rule `claims-template` follows, one file over.

`figure-template` and `figure-check` are the same shape for the other half of claim extraction.
The template writes the one mechanical part of a digitization — which curve of your document each
series is the reading for, an id nobody could guess and that has to match exactly — and leaves
blank everything that is a reading: the figure, the tool, both axis ranges, every point. One file
is one panel, so a document plotting two figures is asked which one this is and lists them rather
than choosing: the axes are stated once per file, and two panels under one pair of axis ranges is
the second one read against the first one's calibration — or `--out-dir` writes every panel at
once, still one file each. Then
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
join. `--series` repeats, because one file is one panel and a paper is several: checked one at a time,
each file reads as "the other curves are unread" — true of the file, false of the paper — and one
claim read off two panels is invisible entirely, since the join keeps whichever file it saw last.
It also compares each reading against the window the document runs: nothing
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

A command here writes only where you point it, and every one that writes says when it replaced a
file that was already there — which used to be true of `export` alone, and is the reverse of where
it matters most: filling a template in is your work, twenty points read off a figure or a reported
value looked up per row, and the command that destroys it is the same one that wrote it. `export`
is the one whose whole job is to create a file. It packages the
published bundle for that accession — the window, the sample count, the output each claim reads,
and the values that claim sets — and refuses a `--model` the bundle was not built from, since an
archive built from another model packages a run the certificate never judged.

`certificates-for` takes `--by title|doi|pubmed-id|accession`, and it is how you reach the classes
the catalog does not list: the catalog is the PK/PD work queue, while the ledger carries all six
classes' published certificates. The certificate and verdict commands take the digest it returns.

Add `--json` to any read command to get the exact object an agent receives over MCP. Run
`reprolith --help` for the full command list, and `reprolith --version` for this copy's version
*and* the judge revision each class would publish under — which is what a certificate names, and
what tells you whether your copy would still produce the one in front of you.

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
discipline (27 abstentions, and four verdicts stricter than their label — a withheld pass, never
a false one) rather than of blind classification skill; the dataset and
[docs/self-validation.md](docs/self-validation.md) both spell out why.

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
and the production envelope against COBRApy too. The **whole FROG fingerprint** of the reference
model is published beside those certificates and compared against COBRApy's across all 423 of its
components — objective, both variability bounds and the deletion objective for each of 95
reactions, and the deletion objective for each of 137 genes — agreeing to 3.4e-12 of the objective
value. The requirement had been carried by unit tests alone until then: the fingerprint was
computed and nothing published or compared one.

```bash
pip install -e ".[dev,engine,fba]"   # fba brings the LP solver; engine (libsbml) reads the .xml model
```

Generic **systems-biology kinetic models** (signaling, metabolic, gene-regulatory networks) are the
third class. They reuse the PK/PD curve oracle unchanged — the reproducible result is a species
time-course — so adding them is mostly demonstrating the contract generalizes. The class is
self-validated non-circularly against an independent simulator (libRoadRunner): curated BioModels
networks spanning six dynamic regimes (signaling, gene-regulatory, metabolic, cell-cycle, circadian,
calcium) reproduce, and the [milestone blind run](datasets/kinetic/milestone/) scores 7/7 through the
same catalog and agreement machinery as the other classes. See
[docs/kinetic-class.md](docs/kinetic-class.md).

**Five of those six models oscillate, and a curve is the wrong comparison for a limit cycle.** A
curve distance is dominated by *phase*, and phase error accumulates with every cycle: on the
repressilator's 75-cycle run, stretching the clock by **1%** — every peak height and every shape
identical — moves the curve distance to 0.395 against a 0.10 pass line, four times over. No
tolerance can tell that from a model that is simply wrong, which is exactly why these papers report
a **period** and an amplitude instead. A claim can state one now (`metric="period"`,
`metric="peak_to_trough"`), read from the trajectory's own mean crossings with the crossing time
interpolated, and the milestone publishes both for the Drosophila circadian clock against
libRoadRunner's reference trajectory. A run that completes no cycle is abstained on rather than
given a period it does not have — and so is one whose *grid* has not settled the number, which
caught the cell-cycle model's peak height moving 8.7% between 200 and 400 samples the first time it
ran.

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
[milestone blind run](datasets/logical/milestone/) scores 10/10 through the same catalog and
agreement machinery. See [docs/logical-class.md](docs/logical-class.md).

**The update scheme now reaches the run and the certificate, and is qualified only where it could
change the answer.** A claim states its scheme and its reported attractor set; the pin is refused
if it names the other scheme, since a certificate announcing asynchronous updating over a
synchronous enumeration would carry two accounts of one number with the stronger one false. Where
a claim states no scheme, the run is synchronous and the certificate carries a load-bearing
assumption — but only where the choice could move that verdict, which is *computed*: attractors are
enumerated, so "the two schemes agree" is a proof rather than a bound. On the toggle switch the
attractor set differs (three under synchronous updating, two under asynchronous — its 2-cycle is an
artifact of updating both nodes at once) while its fixed points do not, so its attractor claim is
qualified and its steady-state claim is not.

**A reported basin of attraction can be certified too** — how much of the state space reaches one
attractor, which is what these papers argue robustness with. Li et al. 2004's yeast cell-cycle
network reaches its G1 steady state from **1764 of 2048** initial states, and Reprolith reproduces
all seven of that paper's published basins exactly from the committed rules — the tenth entry in
that milestone, and the one whose reference values are a paper's rather than a second tool's. A count of states is
judged exactly (a basin is a number of states in a finite space, not a measurement with error) and a
printed percentage in a band; the size of the space it was counted in goes on the certificate,
because a paper that fixed its inputs first reports a share of a smaller whole — the same G1 basin is
86% of the paper's space and 43% of CANA's 12-node variant. A claim judged under asynchronous
updating is abstained on rather than answered with the synchronous number, since basins overlap
there rather than partitioning anything.

**Stochastic (SSA) models** are the fifth class: discrete-molecule reaction networks where a single
run is a random sample, so the reproducible result is a distribution. An exact, pure-Python
Gillespie simulator (deterministic under a pinned seed) feeds the same distributional oracle the
population figures use, and the class is self-validated non-circularly against closed-form results —
the immigration-death process's Poisson stationary mean and variance, a reversible reaction's
binomial equilibrium, and a pure death process's **mean time to extinction** (`H(n₀)/k`) — with a
5/5 [milestone blind run](datasets/stochastic/milestone/).

That last one is a *first-passage* claim rather than a state at a fixed time: how long a small
population, or a drug-resistant clone, survives before its last individual is gone. It is the one
place this class refuses to average: a trajectory that reaches its cap without going extinct has
observed no extinction time at all, so the claim abstains rather than taking the mean of the runs
that finished — which is the mean of a conditioned sample, short by an amount the sample itself
cannot bound. And it is the class's one certificate with no second engine behind it, since
libRoadRunner's Gillespie gives a mean at a time rather than a first passage; every surface says
so rather than counting four corroborated out of five as a clean sweep.

**How noisy a model is can be certified too**, which is what a stochastic model is *for*: the Fano
factor (variance over mean — 1 for constitutive expression, above 1 for bursty) and the coefficient
of variation, both reproduced against the Poisson laws and both re-run under libRoadRunner's
Gillespie. The interesting part is the error bar. A mean's is `sqrt(variance/n)`; a **ratio of
moments** has a different one, and the closed forms that exist assume the very distribution the
claim is about — so it is *resampled*, leave-one-out, which draws no random numbers and keeps the
verdict a function of the one pinned seed. That measurement then says what the quantity costs: at
the 400 trajectories this class certifies a *mean* at, a Fano factor's standard error is over 7% of
its value against a 5% pass threshold, so the claim is abstained on rather than judged. The
milestone entry uses 4,000, and its certificate prints the 2.3% it bought. And an abstention says
what would lift it: `~216 trajectories — 22x as many`, sized against the bar this check abstains at
rather than against the claim's own residual, which is the number under suspicion. The population
class's variability abstention answers in subjects through the same function.

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
concentration profile over space — or one of the three scalars a paper usually prints as a *number*
rather than a picture, and so the ones reachable without a curator digitizing a figure: the **decay
length** of a morphogen gradient (`λ = √(D/k)`), the **speed of an invasion front** (Fisher-KPP's
`c = 2√(rD)`), and the **wavelength a Turing pattern selects** — stripe, spot and digit spacing. A
pure-Python finite-difference solver feeds the same curve oracle for a profile and the scalar
comparison for a length, a speed or a wavelength, self-validated non-circularly against closed
forms — a Gaussian whose variance grows by 2·D·t, `λ = √(D/k)`, and `c = 2√(rD)` — with a 5/5
[milestone blind run](datasets/spatial/milestone/). A claim that states no boundary is run under a
wall Reprolith chose and is qualified for it — the same qualification the stochastic class carries
for its ensemble — while a claim that *does* state its wall is run under it and can reach a clean
pass, and so does a gradient, whose walls are the model rather than a choice.

**The domain a closed form is derived in is free space, and that is now a domain a claim can
state.** The three committed profile certificates read *partially* reproduced for a month, for a
zero-flux wall this engine imposed — while their reference was the free-space Gaussian, so the one
domain they actually assert was the one the engine could not honour, and the verification queue
listed it as "an unbounded domain (not implemented, so not measured)". An infinite grid still
cannot be run. What changed is that the claim is no longer trusted or refused but *measured*: the
two of the walls this solver runs **bracket** free space for a diffusive claim — one reflects everything
that reaches it, the other absorbs it, and the solution that lets it leave and never return lies
between — so the distance between those two runs bounds what standing a finite grid in for an
infinite one costs. A claim stating `boundary="unbounded"` is judged only when that bound is under
a tenth of its own pass tolerance *and* under a tenth of the distance its answer sits from the
nearest verdict line — so neither a generous tolerance nor a claim landing on its threshold lets
the substitution decide anything — and abstains with the number where it is not. On the shipped
grid the bound is 2e-07 to 3e-05 against a budget of 1e-02, so all three now read a clean
`reproduced` with no assumption at all — a wall that cannot be detected is not an assumption.
Measured between the two *runs*, never against the reported profile: the first version of this rule
compared the wall's effect to the claim's own residual, and a domain a quarter as wide passed it
*because* the wall had wrecked the profile enough to make itself look small.

**What that choice costs is measured, not asserted.** The solver runs three walls — zero-flux,
Dirichlet (absorbing or held at a value), and periodic, each checked against the exact decay of an
eigenmode satisfying it and against what it does to mass — so each certificate can report how far
re-running its own discretization under the alternatives moves the judged distance. On these three
profiles that is 2e-10 to 2e-06 against a pass threshold of 1e-01. The stochastic certificates say
the same kind of thing about their ensembles: a standard error of 1.53%, 1.26% and 0.42% of the
reported value against a 5% threshold, where the abstention line is half the threshold. Both
qualifications stand — they are still this engine's choices — but a reader can now see what each
one is worth instead of being told only that it matters.

**The wavelength claim is the one whose wall decides what is measurable at all.** A profile's
boundary shifts a judged distance; a pattern's decides which wavelengths exist — `2L/m` under zero
flux, `L/m` under periodicity — so a claim that states no wall carries a load-bearing assumption
for it, and the two-species solver runs both walls so that what the choice costs can be re-run
rather than asserted. On the self-validation domain the answer is that the alternative measures
*nothing*: periodic modes are half as dense on the same length, so its best resolution is 8.33%
against a 5% pass width. That is more useful than a number would have been.

**It also had to say what it cannot measure.** Which wavelengths are
measurable at all is set by the domain — on a zero-flux domain of length `L` only `2L/m` — so the
claim reports the finest distinction its own domain can make and abstains when that is coarser than
the width it would be judged at: agreeing to 1% where the measurable values are 16.7% apart — a
domain holding five wavelengths — is agreement nobody measured. That abstention says how much
longer a domain would do it (`needs mode 19 or higher, ... about 3.8x as long`) rather than only
which way to go, on the same rule the two sample-size abstentions follow: sized against the bar the
check abstains at, never against the measurement it does not trust. It also reads the pattern twice
and abstains if the dominant mode moved between them, because the selected mode changes while the
pattern is still growing (measured on Schnakenberg: mode 22, then 21, then 20 as it saturates). And it judges the wavelength the
*nonlinear run* selects while reporting the one linear stability predicts beside it — on that same
configuration those are 16.0 and 15.24, five percent apart, which is the entire class-default
tolerance.

All six classes are measured blind against independently-established ground truth on the same
machinery — [docs/self-validation.md](docs/self-validation.md) is the one-look evidence summary, and
[docs/claim-types.md](docs/claim-types.md) is the one-look answer to "can it check the thing my
paper reports?": every kind of result this engine certifies, what each is compared against, how each
one abstains, and — stated rather than left to be noticed — the quantities it computes and
deliberately does not certify.

Reprolith gets better when people who know the science validate its judgment. When it isn't sure
about a load-bearing value it records the value, marks the result as resting on it, and reports it
in the certificate's gap report — confirming or correcting one is the most valuable thing you can
do here.

`reprolith verification-queue` is where those questions collect. It reads every load-bearing
assumption off every *standing* certificate — a superseded one is not a live dependency — and
opens one item per distinct question: what was assumed, what Reprolith chose, on what basis,
against what alternatives, and which papers would have to be re-certified if you corrected it —
named, not digested, since a content hash tells an expert nothing about whether they know the
paper.
That last number is the ranking, so the value four published results rest on is the first thing
you see and not the twentieth.

It says how much of the corpus each value reaches, because a count of unreviewed values read
against the size of the repository is its own overstatement: three values under **4 of the 39**
standing certificates, not under all of them.

It prints in two parts, and the second is the one worth reading first. Five of the eight
load-bearing assumptions on today's certificates are **this engine's** limits rather than
anything a paper left out — the stochastic class judges an ensemble it drew itself — and no
expert confirming anything closes one. They withhold a clean pass exactly as the others do; what
they wait on is this engine, not a person, and they say so under their own heading. Three
questions are actually open to you. That split moves as the engine changes rather than standing
as a property of the work: it was six of eight until the spatial wall left this half, because a
claim can now state its own boundary and a claim stating an unbounded domain is measured against
the grid it ran on. It exists because a certificate could cite a queue item nobody had
built: four metformin certificates named `verify:time-unit-of-the-Zake2021-deposits`, and until
this landed, following that citation found nothing. The queue is *derived* from the certificates
on every call rather than stored beside them, so it cannot drift from what it describes, and a
question asked by three claims about one solver limitation is one item with three dependents
rather than three items you answer three times.

Every published certificate also has an **embeddable badge** beside it — `<accession>.svg` next to
`<accession>.json` — showing that certificate's own verdict, including the qualification: the
metformin badge reads `partially-reproduced (gaps)` and not `partially-reproduced`. They are
written from the certificates on every registry build and checked against them in CI, because a
badge is the one artifact designed to be embedded where nobody will look at the certificate behind
it. For a long while exactly one existed, nothing produced it, and it had gone stale in precisely
that direction.

The published [registry page](datasets/registry.html) carries the same two lists, beside the
blind track record and the cross-engine corroboration, derived by the same function — so what a browser
sees the whole set resting on and what `reprolith verification-queue` prints cannot disagree. Each
card already named its own certificate's assumptions; what the page had no way to say was that one
of those questions carries four of the certificates, which is the only number that says which to
look at first.

Opening an item changes no verdict, which is what makes escalating every load-bearing assumption
safe: such an assumption already withholds a clean pass, so the queue adds a reader's route to
the question and nothing else.

**An answer now outlives the process that recorded it.** `VerificationQueue.decide` and
`reverify_dependents` were both built and neither could be reached from outside one Python
run — the queue is derived on every call and stored nowhere, so a decision made against it
evaporated with the interpreter, and the queue printed a hard-coded sentence saying none was
stored. Decisions are committed data now
([`datasets/verification_decisions.json`](datasets/verification_decisions.json)), read by the same
function all three surfaces answer from, so an item somebody has answered stops asking on the
terminal, over MCP, and on the registry page at once — with the expert, the date, the rationale,
and where the decision was made.

Three things it refuses to do, because each would publish more than the record supports. It does
not lift a qualification: the certificates under a confirmed value were still computed while it
was unreviewed, so they keep withholding a clean pass until `reverify_dependents` re-issues them,
and that is mechanical rather than promised — were they re-issued, the assumption would no longer
be load-bearing and the item would not be derived at all. It does not resolve disagreement: two
experts who answer differently are two records, both shown, the item marked disputed. And it does
not trust an id — every record carries the fingerprint of the question as it was answered, so a
decision filed against an item whose wording later changed is reported as **stale** and its item
goes back to pending, rather than attributing an answer to somebody for a question they never
read. The repository records no decision today, and the queue says so from the file rather than
from a sentence that could outlive it.

Questions are still raised as issues **by hand** — nothing files one for you — but nobody fills one
in by hand any more: `reprolith verification-issue <item-id>` prints the title, the body with every
field the template asks for, and the three labels the `github-collaboration` spec names, which the
template file itself left empty. It refuses one of the engine's own limits rather than filing it,
since no expert answer closes one. And it answers the
template's *source context* field by saying what Reprolith does not have: a section, equation,
table or figure is recorded for a **claim**, not for an assumption, whose basis is a reason rather
than a place — so the body gives the basis and the assumption id to grep for instead of a plausible
location.

Once an issue is filed, `reprolith issue-reconcile <issues.json>` says where the two sides have
drifted apart — reading what `gh issue list --json number,title,state,labels,body` prints, since
nothing here touches the network. Both directions drift, and neither side could see it: the queue
is derived from the standing certificates on every call, so an item vanishes the moment its
certificates are superseded while its issue goes on asking; and an issue can be closed, relabelled,
duplicated or never opened at all with nothing in this repository noticing. It matches on the
question fingerprint the generated body carries rather than on a title anyone can edit, and it
**changes neither side**: a divergence is a question about which one is wrong, not a fact about
which one loses. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licensing

The code is MIT ([LICENSE](LICENSE)). The data Reprolith *produces* — certificates, catalog
entries, dossiers, bundles, agreement reports, the registry page — is CC BY 4.0
([LICENSE-DATASET](LICENSE-DATASET)), so cite it if you build on it. The third-party model files
redistributed under `datasets/` keep their own upstream licenses, and some are more restrictive:
the BiGG models — `e_coli_core` included, not only the genome-scale ones — are academic
and non-profit use only. See
[datasets/THIRD-PARTY-NOTICES.md](datasets/THIRD-PARTY-NOTICES.md) before redistributing.
