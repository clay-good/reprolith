# Bootstrap findings note (preliminary)

What the ODE PK/PD bootstrap has shown so far. Every claim here traces to committed code, the
labelled test set, or the metformin worked-example certificate. It is preliminary: one paper
has been certified end to end; the full blind run over the test set is still ahead.

## What was built

The complete reproduction engine, dependency-free at its core, with the honesty invariants
enforced in code and checked in CI:

- **Determinism** — same inputs and pin give a byte-identical certificate.
- **Inescapable scope** — every certificate states, in machine and human form, that it attests
  only to computational reproducibility, never biological or clinical validity.
- **Assumption-qualification** — a result that reproduces only because of a load-bearing
  Reprolith assumption can never be reported as an unqualified `reproduced`.

The pipeline runs end to end with the pinned COPASI engine: a dossier compiles to SBML, runs
under the pin, is judged by the oracle against declared tolerances, and produces a per-claim,
scope-flagged certificate. The blind PK/PD test set (31 real BioModels models, 21 curated +
10 non-curated) is labelled from BioModels' curation status.

## What reproduced

**Zake2021 metformin PBPK model** (PLOS ONE 2021), two plasma-Cmax claims from the paper (see
[`datasets/worked_examples/`](../datasets/worked_examples/)):

- **500 mg** dose — reported 6.2, simulated 6.07 nmol/mL (**2.2 %**), `reproduced` cleanly, no
  assumption.
- **1000 mg** dose — reported 11.2, simulated 11.25 nmol/mL (**0.4 %**), but `reproduced` **only
  under a load-bearing assumption**, so reported as assumption-qualified.

Overall verdict: `partially-reproduced` — a clean claim and a qualified one, never rounded up.

## What the field under-specifies most

Two findings, both from real data:

1. **Dosing conventions (salt form) are under-specified.** Metformin reproduction hinges on
   whether the stated 1000 mg is the HCl salt or the free base the model consumes. Get it
   wrong and the claim fails by 26 %; get it right and it reproduces to 0.4 %. The paper's
   nominal dose alone does not tell you which. This is the single most load-bearing detail in
   the one case examined, and it is exactly the kind of ambiguity an honest certificate must
   flag rather than silently resolve.

2. **Published models ship as runnable artifacts but without machine-checkable claims.** The
   SBML encodes the model; it does not encode the paper's figures and reported values. So
   automated reproduction is bottlenecked not at simulation — that works — but at **claim
   extraction from the manuscript**. Every downstream stage is ready; the missing input is a
   machine-readable statement of what each paper claims.

   This is concrete, not hypothetical. Metformin's Cmax was reproducible because the paper
   reported it in a **table** (text). A second attempt — the Sluka2016 acetaminophen PBPK model
   (PLOS ONE 2016) — reached the opposite wall: its validation values live only in **figures**
   (Figs 7–8), with no numeric Cmax in the text. With no digitized reference, the honest verdict
   is to abstain, not to guess a number off a plot. Text-reported claims like metformin's are
   the exception; figure-locked claims are the norm, and the scaling constraint is therefore
   **figure digitization**, not simulation.

## The figure boundary is not PK/PD-specific — FBA hits it too

The same wall recurs in the constraint-based class, which rules out "PK/PD figures are just
unusually visual" as the explanation. The landmark *E. coli* iAF1260 reconstruction (Feist et al.,
*Mol Syst Biol* 2007, open access) is on BiGG and ingests and solves cleanly — Reprolith reproduces
COBRApy's maximal growth on the model's distributed minimal medium (glucose uptake 8, O₂ 18.5
mmol·gDW⁻¹·h⁻¹) to solver tolerance (0.7367009…, agreeing to ~10 significant figures). But the
paper reports its predicted growth rate only as
a **figure** — the growth-rate-versus-glucose-uptake sensitivity curve — with no single growth value
in the text (the O₂ cap of 18.5 is text-stated; the growth number is not). So a *manuscript-claim*
reproduction abstains for exactly the reason Sluka2016 does: the number lives on a plot axis, and
guessing it off the figure would violate the honesty rule.

The boundary holds on a second flagship model, so it is not an iAF1260 quirk. Its successor **iJO1366**
(Orth et al., *Mol Syst Biol* 2011, open access via PMC) — the current-generation genome-scale *E.
coli* reconstruction — was fetched and read in full. Its predicted growth rate is likewise never a
single text-stated number: growth is discussed qualitatively and shown in figures, and the paper even
states that phenotypic predictions were "not expected" to change from iAF1260. Its most reproducible
numeric claim is *gene essentiality*, but that is reported in the supplement and rests on the exact
minimal medium and a genotype-matching knockout adjustment that the main text does not pin down — so
an honest per-paper reproduction abstains rather than guess the medium. Two independent flagship
reconstructions, read in full, both wall off at the same place.

This is why the constraint-based blind set is labelled by an **independent tool** (COBRApy) rather
than by paper-reported numbers: cross-implementation agreement on the shipped model is honestly
attainable at scale, whereas paper-figure reproduction is blocked on digitization in every class.
Reprolith's own textbook *E. coli* core value (0.873922, stated in the model's documentation) and
the metformin table remain the exceptions that prove the rule.

## The engine is robust across diverse real models

The engine was hardened against real BioModels, not just synthetic tests. Sweeping the full
31-entry test set surfaced three genuine robustness bugs, now fixed: species resolution by SBML
id (models reuse display names across species), state variables encoded as parameters with rate
rules (the pharmacometrics "parameter + rateRule" idiom, which ships no species), and divergence
detection (an intractable model is blocked, not silently returned as inf/nan). Further sweeps
over 36 more structurally-diverse curated models — glycolysis, cell cycle, signalling, and higher
BioModels ids — ingested and simulated cleanly with no further fixes. Across 67 real models the
engine either runs to a finite result or honestly blocks, which indicates it already generalises
beyond PK/PD toward the kinetic (systems-biology ODE) class the roadmap picks up next.

## Known limits of the distributional oracle

Measured, not estimated — a deep-audit pass ran the population path over a realistic population-PK
envelope (lognormal CV 30% on clearance and volume, 12 sample times, P5/P50/P95 bands, the default
0.15/0.35 band-distance tolerance, 200 replicates per cell):

| Ensemble size | False-fail rate on a *correct* model | Pass rate for a clearance 10% too high |
|---|---|---|
| 20 | 80% | 16% |
| 100 | 21% | 69% |
| 1000 | 0% | 100% |

Two things follow, and neither is a bug in the code. Below ~50 subjects the verdict is dominated
by Monte-Carlo noise, so a correct reproduction routinely reads as failed — fail-safe, but noisy.
At large ensembles the fixed 0.15 default is simply below the power needed to reject a 10% error,
so it passes every time. **The oracle's operating point is set by the ensemble size**, and the
tolerance is not a function of it. Until that is addressed, a population claim's ensemble size and
seed must be read as part of its verdict; `PopulationClaim.protocol` now carries them into the
certificate for exactly that reason.

Related: `ensemble_percentile_bands` feeds `judge_distribution`, but for small integer counts the
pairing does not work. Each band is normalized by its own *temporal* span, so an SSA envelope whose
P5 band runs (3,4,5,5,5) has a span of 2, and a one-molecule sampling wobble is a normalized
distance of 0.5 — an outright failure. Measured on the immigration-death network, the identical
correct model reproduces 0/60 times at n=12 and 1/60 at n=150. Nothing false-certifies, but the
documented integration is not usable at those counts.

## What a model loses on the way in, and what it no longer loses

Artifact intake (`ingest_sbml`) and reconstruction (`build_model_sbml`) are two halves of a round
trip, and anything the dossier in between cannot express is a model silently rebuilt into a
different one. Two such losses were found by auditing the round trip against the repo's own
datasets, and both are closed:

- **Rule kind.** An extracted equation recorded only a target and an expression, so an assignment
  rule (`Y = 2X`, an observable) and a rate rule (`dY/dt = 2X`, a state that grows) were the same
  dossier entry — and reconstruction emitted every one of them as a rate rule. The rebuilt model
  ran, produced finite output, and could be certified against the paper. Equations now carry their
  kind, reconstruction emits the kind it was given, and a parameter an equation determines is
  emitted non-constant instead of frozen at its initial value with its rule dropped.
- **Amount versus concentration.** A species may state its initial value either way, and the two
  agree only in a unit compartment. Adopt-and-verify read the initial *amount* unconditionally, so
  on a concentration-stated model it compared every species against an unset field: 3 of the 6
  shipped kinetic datasets reported a full set of mismatches against their own source file (and in
  Level 3 the unset field reads NaN, so a real mismatch could never be reported at all). Both
  sides now read the value in the convention the model states it in; a concentration in a
  compartment reconstruction cannot represent is refused at intake rather than recorded as an
  amount wrong by that volume.

The general lesson is the one the refusal pattern elsewhere in the codebase already encodes: an
intake path that cannot represent a construct must say so. Silently flattening it produces a model
that is runnable, plausible, and not the one the artifact described.

## When the solver is Reprolith, the certificate says which Reprolith

Re-verification fires when a certificate's engine pin differs from the current one. That works for
the classes an external engine computes — COPASI's version moves, scipy's moves — but four classes
are computed by this package: the SSA, the finite-difference solver, the attractor enumerator, and
the constraint-based analysis layer above the LP call. Their pins carried a package version that has
never been bumped, so the freshness check compared two identical pins: fixing the sampler, the
discretization, or the class-default tolerance table left every certificate that fix invalidated
looking current, and the whole committed corpus of 23 pure-Python certificates was unflaggable.

Those pins now name a *revision*: a digest over the source of the solver and of the oracle it judges
through (`reprolith.pins.algorithm_revision`), since a class-default tolerance decides what the
solver's numbers mean as much as the solver does. It is deliberately blunt — a digest of file bytes,
so a docstring edit moves it too, and nothing depends on a human remembering to bump a constant. A
needless re-run of a dependency-free solver costs seconds; a missed one publishes a number the
current code would not produce. A test holds the corpus to it: a committed certificate carrying an
older revision than the code fails, and the fix is re-running that class's milestone script.

## A doubled peak that averaged out to a pass

The curve verdict was an RMSE over the reference's span, and an average divides a localized miss by
the sample count: a single point passes whenever its error is under `0.10·√N` times the range —
half the range at 25 samples, the whole range at 100, three times it at 1000. Measured on a
201-point one-compartment PK curve, a reconstruction whose **Cmax was twice the paper's** scored
0.0705 and certified as a clean reproduction. Cmax is precisely what such a paper reports, and the
sample count is the reconstruction's own choice, so sampling more finely bought more room for the
peak.

The verdict now answers to the worst single point as well as to the average. The worst point's
budget is the tolerance's own *partial* threshold — the width it already calls tolerable — rescaled
onto the pass threshold, so no new constant enters and the certificate reports both numbers. On the
committed corpus the worst point runs 2.2× to 9× the RMSE ratio with both under 1e-3, so every real
reproduction keeps two orders of magnitude of headroom; the doubled peak now fails.

## Two solvers computing a model the file did not describe

The ingestion lens of the ninth audit found two places where the numbers were right for a model
nobody had written down.

**A dimerization ran at half its stated rate.** The stochastic ingester verifies a rate law
structurally — it refuses anything that is not `k·∏Aᵢ^sᵢ` — and then handed `k` to the SSA
unchanged. But `k` is the deterministic constant and the SSA's propensity is the stochastic form:
for `2A → B` the sampler computes `c·n(n−1)/2` where the law says `k·A²`, and the two agree only at
`c = 2k`. Measured on `2A → B` with `k = 0.001` from 200 molecules, the ensemble tracked
`dA/dt = −k·A²` (mean 167) where the artifact says `dA/dt = −2k·A²` (mean 143). The constant is now
multiplied by `∏sᵢ!`, and the ensemble lands on 143.2. Any ingested model with a reactant
stoichiometry above one was affected.

**Diffusion and decay spent one stability budget twice.** The explicit scheme's amplification at the
shortest wavelength is `1 − 4α − k·dt`, but the two terms were bounded separately (`α ≤ 0.5`,
`k·dt ≤ 1`). A grid at `α = 0.4` with `k·dt = 0.6` — inside both limits — amplifies by −1.2 per step
and oscillates to divergence *while staying finite*, so the oracle's non-finite abstention never
fires and the class publishes a confident `not-reproduced` against a discretization it should have
refused. The joint bound is now checked.

Alongside them, four ways an artifact was read past rather than refused: a flux-bound parameter whose
value is NaN (the solver drops the bound, so the constraint simply vanishes), a gene rule naming a
product the model never declares (the raw id became a gene, and entered the deletion fingerprint as
real), a species declared in moles fed to a molecule-counting sampler, and rules or events that move
a flux bound during a run the LP treats as a steady-state snapshot. The ODE dossier is the one path
that records rather than refuses: it carries most of a model, so an event, an initial assignment, or
a conversion factor it cannot represent is written down as a load-bearing gap. The shipped metformin
artifact has thirty-two initial assignments and an oral-dose event, and the dossier had been silent
about all thirty-three.

## A lethal knockout judged in whatever units it happened to use

The scalar judge divided by the reported magnitude and, when that magnitude was exactly zero, fell
back to the bare absolute difference — a raw number compared against a unitless tolerance. The
verdict was then a function of the claim's units. A knockout a paper calls lethal, against a model
still growing at 0.05 1/h — about 6% of wild-type — read as a "5% relative error" and certified as
reproduced; the identical claim stated in 1/day failed. This is reachable from the constraint-based
front end and from the inline linter an agent gates on, and a reported zero is the *standard* form
of the lethality claim that class exists to check.

A reported zero now needs the scale it is zero relative to. An exactly-zero prediction is exact
agreement and passes without one. Anything else is judged as a fraction of that declared scale, and
a claim that states none abstains, naming what it needs — the abstention discipline the rest of the
oracle already follows.

## Recording work that was not done

The write surface closes the loop: an agent claims a queued paper, reproduces it, publishes a
certificate, and records the result so the unit is not handed out again. Two of its checks were
weaker than they read.

Recording required only that *nobody else* held the lease, so an unclaimed entry could be recorded
by any caller — including one who had just submitted a paper whose title matched another class's
certificate, filing a genome-scale FBA result under a PK/PD accession. Recording is the claim that
this requester did this work, so it now requires holding a live lease; the state check runs first,
so a second recording of finished work is still told that the entry is already certified.

And the timestamp on every transition was the caller's own string, taken verbatim and unparsed —
the record of when a paper was certified was free text supplied by whoever recorded it. It is the
server clock now, and the parameter is gone from the advertised schema.

## What the surfaces were still allowed to say

The read surfaces are where a verdict actually reaches someone, and four of them overstated:

- **The pre-submission report served a withdrawn verdict.** `verdict` and `certificate` both
  carried `superseded_by`; the report that says *"ready to submit"* did not, so an author or agent
  gating a submission could act on a certificate a correction had already replaced. It carries it
  now, and so does the gap report.
- **`gaps` was the one read path returning verdicts bare.** Each gap item carries its claim's
  verdict, and the list came back with no scope flag anywhere — the single exception to the rule
  that no verdict leaves this surface unqualified. It is now returned wrapped, with the scope and
  the supersession beside it.
- **Nothing rendered supersession.** Neither the plain-text certificate nor the published registry
  showed it, though it is part of the machine content — so a withdrawn `reproduced` and the
  `not-reproduced` that replaced it appeared as two equal cards, green badge intact. The human
  certificate names what it supersedes, and the registry marks the superseded card with its
  replacement's digest.
- **The inline stochastic linter answered where the certificate path abstains.** `certify_stochastic`
  refuses to decide a claim whose ensemble noise is comparable to the pass threshold; the linter an
  agent gates a workflow on judged the same number at any trajectory count and recorded no seed. On
  a *provably correct* immigration-death model at ten trajectories, that returns a false `failed` on
  about one seed in eight. Both paths now share one rule about what an ensemble can decide, and the
  inline result records the sampling behind it.

Also closed: an argument of the wrong shape — a list where a mapping belongs — crashed a tool
instead of being refused, escaping a function documented as pure request-to-response.

## An agreement rate that could not have come out any other way

The oracle refuses a bare non-pass: a `partial` or `failed` verdict must carry a root cause, or the
certificate tells the field nothing. The rule was enforced by *raising* when no cause was supplied
— and the callers that matter supply none. `Claim.from_record` does not parse a shortfall at all
(the dataset claims are the reproducing case), and neither the spatial nor the constraint-based
milestone script passes one. So those runs had exactly two possible outcomes: a clean pass, or a
traceback. Measured on the published configurations: the spatial class certifies a diffusivity 40%
wrong as `reproduced` and raises past that, and the `iNF517` growth rate raises at a 20%
overstatement. The 3/3 and 8/8 agreement rates in the milestone artifacts were structurally
guaranteed rather than measured.

An unattributed shortfall is now recorded as one — `uncategorized`, the catalogue's own escape
hatch, against the claim's quantity, with the fault hypothesis pointing at the reconstruction
rather than at the manuscript, because Reprolith does not accuse a paper of an error it has not
diagnosed. Every class front-end uses it, so a genuine miss is published as `not-reproduced` with a
cause attached instead of vanishing into an exception. Tests now perturb a correct reproduction in
each class until it is wrong and assert the certificate says so; the stochastic and logical classes
already discriminated, and now the other four do too.

## Auditing the audit's own code

The ninth pass turned five agents on the repository, and the sharpest lens was pointed at the code
written that same day. Four of its findings were real, and all four are closed:

- **A revision that stopped short of the verdict.** The freshness digest spanned each class's solver
  and the oracle, but not the layer above them — `constraint_based.py`, which builds every
  genome-scale certificate, and `certificate.py`, which decides the headline verdict. Renaming a
  function in the constraint-based layer moved no pin. Revisions now span the whole path from solver
  to verdict.
- **A refusal that only guarded the front door.** The protocol requirement lived on the claim types,
  and the judges and the certificate builder are both public — so the same clean estimation pass for
  `recovered == reported` could be assembled from assessments directly. The invariant now sits in
  `build_certificate` with the other two, where there is no path around it.
- **An assumption for a claim nobody judged.** A stochastic claim that abstains because its ensemble
  cannot resolve it was still given a sampling assumption saying its mean rested on that ensemble —
  and, being load-bearing, it downgraded the certificate on behalf of a judgment never made.
- **A guard that could go vacuous.** The corpus check counted certificates across all four classes
  against one floor, so an empty class directory was covered by the others' count.

## A qualification that names nothing, and a number with nothing behind it

Two flags were carrying weight they could not support.

The stochastic and population classes qualify every verdict they issue, correctly: the mean of an
ensemble and the shape of an envelope both move with the sampling that produced them. But
`assumption_qualified` reads as "this reproduced only because of an assumption Reprolith supplied",
and the certificates listed none — a reader saw a downgrade with no cause attached, which is
indistinguishable from a bookkeeping slip. Both classes now record the sampling itself as a
load-bearing assumption, with the ensemble or the subject count and seed as the value chosen and
"a different seed" among the alternatives, so the qualification points at something.

The estimation and population glue does not run the thing it certifies — the re-fit and the virtual
population are the deferred halves, so the recovered estimate and the simulated bands are handed in.
That made the protocol the only evidence on the certificate that a run happened at all, and it was
optional: a caller could pass `recovered == reported` with no objective, optimizer, starting values,
or dataset stated and publish a clean estimation pass with nothing behind it. Both claim types now
refuse a blank protocol where the claim is built, the way an engine pin refuses a missing version.

## A number nobody could re-run

A simulated metric is a function of the run behind it, and a time-course certificate recorded none
of that run. The sampled classes had already learned this — the stochastic and population claims
carry their seed and their ensemble size, because a mean that agreed on one seed leaves no trace
otherwise — but the two engine-backed front-ends, the scalar PK/PD path and the kinetic curve path,
published a number with no window and no sample count. Three things followed. A claim run over a
vanishingly short duration returns the initial condition, and the metric read off it can agree with
the paper for no reason at all. An AUC and a curve distance both move with how finely the run was
sampled, so the same reconstruction earns different numbers on different grids. And the metformin
example's two claims differ only by dose, so on the certificate they were two identical runs
disagreeing about the answer, with the 779.9 mg free-base figure surviving only as prose in the
assumption block.

Every assessment those two paths produce now carries the run: the window, the sample count, and any
parameter override the claim set. The field was already on the assessment and already omitted from
the content when unset, so the twenty-three certificates whose front-ends state no protocol are
byte-identical; the seven time-course certificates re-digest, and the metformin claims are now
distinguishable from each other in the published file. The rendered certificate labels it
`protocol` rather than `sampling`, since a window is not a seed.

## A dossier that recorded everything about a model except how it moves

Artifact intake reads species, parameters, and rules, and rules become equations — so on a
rule-based PK/PD model the dossier carries most of the model, which is what its docstring claims.
A reaction-based model is the other case, and it is the common one: its laws of motion are its
reactions, and the ingester never read one. The MAPK cascade's dossier recorded eight state
variables, zero equations, and zero gaps. The shipped metformin dossier lists sixty-three
equations, none of which governs any of its twenty-one state variables — they are observables and
compartment volumes. Simulating exactly what that dossier describes gives a plasma curve that is
identically zero, against the 6.07 the certificate is about.

Nothing wrong was ever simulated, because reconstruction refuses to build a model whose state
variables have no rate equation — the fail-safe held for every one of the nine shipped models. But
the artifact was still misdescribed, and one surface believed it: difficulty estimation reads the
gap list, so a dossier missing every law of motion was published in the catalog as `low`, defined
as "a valid shipped model and no gaps: adopt-and-verify with nothing to assume". A reaction network
is now recorded as a load-bearing gap, as are function definitions the model's own expressions
call, and the difficulty follows.

Two smaller fabrications went with it. A unit the model does not state was being filled in as
`dimensionless` — 81 of the 115 values in the metformin dossier, including hepatic blood flows and
a glomerular filtration rate, all at `quoted` confidence — though `Parameter` says in its own
contract that an unstated unit is a gap rather than a value. Dimensionless is not an absence but a
physical claim, and `unit-mismatch` is a catalogued failure mode, so the magnitudes are still
recorded and the missing units are now reported as one gap. And compartments were dropped entirely
while reconstruction builds a single compartment of unit size: a concentration-stated species in a
1799 mL liver was already refused at intake, but an amount-stated one passed through, and the
dossier said nothing about the volume. It says it now.

## Two surfaces that could only agree by luck

The inline linter is what an agent gates its workflow on; the judge is what publishes. They ran the
same comparison until a rule was added to one of them. The worst-point rule that closed the
doubled-peak hole went into `judge_curve` alone, so the same doubled peak on the same 201-point
curve was `not-reproduced` at the certificate and a clean pass at the linter. Both curve linters
now judge through the rule the judge uses.

The reported-zero abstention had drifted the same way. `judge_scalar` abstains and names what the
claim needs; the linter called `relative_error` directly, which raises without a scale — so an
agent linting a lethality claim, the canonical constraint-based claim shape, got a server error
where the certificate would have said "not evaluable, and here is what it needs". `judge_estimation`
had the same hole on its own path.

## Front-ends that could publish a pass or a traceback

The ninth pass found that a class front-end which raises on an uncategorized miss can only ever
emit a clean pass or an exception, and fixed four of them. Three were missed: the estimation, the
population, and the logical front-ends all pass the claim's `shortfall` straight through, and all
three take claims whose `shortfall` defaults to `None`. Each now falls back to the uncategorized
attribution the others use, with the fault hypothesis pointing at the reconstruction. No published
number was affected — the logical milestone attributes its own non-matches, and neither the
estimation nor the population path produces anything committed — but a class that cannot say a
result did not reproduce is not a class that has checked anything.

Alongside them, the pre-submission report was reading its own priority-1 blocker as nothing at all:
the overall rule drops abstentions before deciding, by design, so a certificate with one clean pass
and one un-judgeable claim is `reproduced` — and the report announced "every claim reproduces
cleanly under the pinned engine" directly above a fix list whose first entry was "a reproducer
cannot evaluate this claim". It looks for itself now. An abstained estimation claim was also being
filed at simulation level, so the never-green estimation badge and the estimation fix list did not
see it.

## What the terminal was allowed to leave out

The read surfaces keep paying. Three qualifications the code deliberately computes were reaching
the JSON view and the published registry page but not the terminal:

- **A superseded verdict read as the current one.** `verdict` computes `superseded_by` precisely so
  a withdrawn answer never travels as the live one, and the gap report prints it — the verdict
  command and the human certificate did not. The registry has warned about it since the sixth pass,
  so the terminal was the last surface where a corrected certificate looked current.
- **The self-validation table published six near-perfect scores with no caveat.** `label_basis`
  exists because a class whose entries all carry one label cannot be scored for discriminative
  skill — "always answer that label" scores 100%. It reaches the JSON and the registry banner; the
  human table printed the numbers alone.
- **A mistyped `--data-dir` invented a repository.** A missing `catalog.json` falls back to seeding
  a fresh catalog, which is right for a first run in an empty directory — but the fallback also
  answered a path that does not exist, and a path that is a regular file, with a confident thirty-
  one-entry queue and a claimable backlog. The bootstrap case still works; a directory that is not
  there is now an error naming the path.

`certificates-for` also could not distinguish "this paper has no certificate" from "there is no
such paper", while every other identifier-taking command exits 1 on the second.

## Known limits the audits found and left in place

Recorded rather than fixed, because each needs a design change rather than a patch, and none
can produce a certificate that claims more than it checked:

- **The curve threshold is a different standard on every curve, measured.** The distance is an
  RMSE over the reference's span, so the systematic error admitted at the 10% default depends
  entirely on shape: 15.6% on a sigmoid, 23.2% on a one-compartment bolus, 43.7% on a decaying
  exponential, 75.3% on a sharp Gaussian peak. A reconstruction with a half-life 25% short of the
  paper's scores 0.0797 and certifies as reproduced.
- **The curve judge is far more permissive than the scalar judge on the same models.** Over 4,000
  lognormal perturbations of a one-compartment oral PK model at σ=0.2, 70.0% of models passed as
  curve claims while 14.7% passed as scalar AUC claims, and 34% of the curve-passers had AUC or
  Cmax wrong by more than 20%. Which verdict a reconstruction earns depends on how the paper
  phrased its result. (The judge does not falsely accuse: 10% iid noise on a correct curve produced
  zero false failures in 2,000 trials.)
- **The catalog grows without bound from submissions.** Every mutation rewrites the whole file, so
  cost is quadratic in the number of entries: 2,000 submissions took 44 s and produced a 769 KiB
  file both surfaces read at startup. The free `blocked → queued → blocked` cycle is now capped at
  five requeues per entry, but nothing bounds submission itself, and rate-limiting a shared server
  is a deployment concern rather than an engine one.
- **A pinned-at-zero flux and a huge-but-finite value still have edges.** `normalized_curve_distance`
  raises `OverflowError` rather than abstaining once squaring overflows (predicted ≳ 1e155), and an
  all-zero reference has a subnormal cliff where 1e-165 reads as an exact match and 1e-160 as a
  failure. Neither is reachable from a class front-end today: the spatial solver refuses the
  discretizations that would produce them, and a diverging ODE reaches infinity and abstains.

- **A certificate does not record whether the model was author-supplied or rebuilt.** The
  reconstruction bundle records it (`ModelOrigin`), and so do the mismatches it found and the
  claims it could not run — but nothing maps a bundle to a certificate, and `Certificate` has no
  field for any of it. The model-reconstruction spec asks for the origin on the certificate. The
  honesty that matters does travel: a load-bearing assumption downgrades the verdict wherever it
  is recorded.
- **The engine pin is declared, not dispatched on.** `certify_model` runs COPASI whatever pin it
  is handed; a pin naming another engine would be published without ever having run. The pin is
  now required to name an engine and a version, but validating it against the engine that
  actually ran needs engine dispatch, which does not exist.
- **The certified tolerance is far looser than the agreement achieved**, measured across the whole
  set. The constraint-based certificates carry the 5% class default while agreeing with COBRApy to
  about 1e-14, so a 4.8% mis-stated glucose uptake — the class's own first-named failure mode —
  passes as a clean reproduction. The spatial certificates carry the 10% curve default while
  agreeing with the closed-form Gaussian to 4e-05, so the diffusivity the class exists to reproduce
  can be anywhere from 43% low to 85% high and still pass. Only the PK/PD and stochastic classes
  actually consume their tolerance budget. Tightening the others is a recalibration of the whole
  table, not a local change.
- **A curve verdict's threshold means different things on different curves.** The curve distance
  is an RMSE divided by the reference's span, so 10% is between 5% and 54% amplitude accuracy
  depending on the curve's shape — and the certificate reports the ratio, never the normalizer.
- **The published PK/PD bundle cannot re-run the run it describes.** `RecipeStep` has no field for
  the sample count or a parameter override, so the metformin bundle's two steps are identical
  where the claims differ by dose. The certificate now carries both (each claim's protocol states
  the window, the sample count, and the override), so the run is recoverable from the verdict — but
  the bundle, the artifact whose job is to describe how to re-run it, still is not.
  Re-running at hourly output — the only resolution the published recipe supports — adds
  about 4.4% to the Cmax metric, which is most of the 5% tolerance.
- **Cross-engine corroboration is not reproducible run to run, because the engine is not.**
  Repeated `simulate` calls on one model in one process alternate between two results with call
  parity — a last-place difference, but a real one, against a docstring promising byte-identical
  series. It is why regenerating the corroboration file moves distances that no code change
  touched (2.08e-05 to 2.38e-05 on one model), and it means the corroborated curve is not
  bit-for-bit the certified one. Four of the seven engine-backed models show it. The suspect is
  COPASI's global container state, and finding out needs its own investigation, not a patch.
- **The certified engine version is whatever the machine last resolved.** The engine extra names a
  floor, so a certificate pinning `copasi 4.46.300` can be regenerated under a different version
  without anything objecting — the pin is recorded, never dispatched on. This is not theoretical:
  an upstream release published and then yanked as incompatible was installed by CI in that
  window, and every engine job aborted inside the simulator. That release is now excluded by name,
  which is a patch for one version, not for the class of problem.
- **A published bundle still cannot re-run the run it describes, and now says less than the
  certificate does.** The certificate records the window, the sample count, the readout, and the
  dose; `RecipeStep` records none of them, so running the metformin bundle strictly as published
  gives both claims the same 6.07 and fails the 1000 mg one. And `covers()`, which exists to stop
  a bundle overstating what it addresses, is called from nowhere: on the shipped pair it returns
  false, because the claims come from the claims dataset rather than from the dossier the bundle
  names as its source.

  What *was* fixed here is the bundle's mismatch list. It published `[]` for a comparison that had
  never run, and "checked and agreed" is not the same artifact as "never checked" — the field now
  distinguishes them, and the milestone records the comparison as unchecked, because a dossier
  ingested from the same file it would be compared against can only ever come back empty.
- **The units a dossier does carry are unresolvable from the dossier.** The parameters that state
  a unit cite model-local ids (`unit_0`, `unit_1`), and the dossier carries no unit definitions, so
  "389.92 unit_0" needs the original file to read. (A unit the model states *nothing* for is no
  longer fabricated — see below.)
- **The committed corroboration file records no engine versions**, so its staleness cannot be
  detected. A CI job does now install the extra and run the cross-engine tests against live
  engines, so what CI checks is no longer only that a committed JSON says `true`.
- **An estimation or population certificate accepts any engine pin.** Both are built from numbers
  the caller supplies, with no run of their own, so the pin can name an engine that is not
  installed. Validating it needs engine dispatch, which does not exist; what the claim *can* be
  held to — the protocol behind the supplied number — it now is.

## Status and what remains

The engine and one real reproduction are done. The full blind run over the 31-entry set (task
7.1), the agreement report against ground truth, and the complete milestone artifact (8.1) and
findings (8.2) all wait on the same thing finding 2 names: a scaled way to extract each paper's
targetable claims. The metformin example shows that, given a claim, the rest of the pipeline
delivers an honest, root-caused verdict.
