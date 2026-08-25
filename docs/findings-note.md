# Bootstrap findings note (preliminary)

What the ODE PK/PD bootstrap has shown so far. Every claim here traces to committed code, the
labelled test set, or the metformin worked-example certificate. It is preliminary in a narrower
sense than it once was: the full blind run over the 31-entry set is done and committed, but one
paper is certified end to end and the other thirty abstained for want of extracted claims.

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

   One half of that bottleneck is now closed where a paper ships a **SED-ML** document beside its
   model: its plots are a machine-readable statement of which curves the paper shows, and
   `enumerate_sedml_claims` reads them as dossier claims (see
   [the fast-path note](sedml-fast-path.md)). On the BioModels SED-ML for Kholodenko's MAPK model
   that is exactly the four curves of Figures 2A and 2B, with the second pair correctly attributed
   to the *modified* model. What it does not supply is the other half — the values those curves
   showed — so such a claim is marked figure-referenced with no reference data and the oracle
   abstains. Figure digitization remains the constraint; the document removes the guesswork about
   *which* results a reproduction should be aiming at.

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

Recording it truthfully then broke the one surface that reads the gap list. Every SBML entry now
carried a load-bearing gap, so the advisory difficulty estimate scored all of them `high` — the
spread across the shipped models inverted from eight `low` and one `high` to the reverse — and an
estimate that is constant routes nothing, which is the only thing it is for. The distinction that
fixes it is the one the honest record needs anyway: a reaction network is missing from the
*dossier* and present in the *artifact*, so adopt-and-verify closes it, while a medium the paper
never stated is missing from both. A gap now says which it is, difficulty ignores the first kind
when the shipped model validates, and the spread is back where it was — with a dosing event still
counting, because that is where reproduction actually fails.

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

## The artifact whose job is re-runnability could not re-run anything

A reconstruction bundle exists so someone else can run what was certified, and the shipped one was
strictly less informative than the certificate beside it. `RecipeStep` recorded a claim id, a
protocol string, an output, and a time span — no sample count, no parameter override, no metric —
so metformin's two steps were identical where the claims differ by dose. Running the bundle exactly
as published gave both claims the 500 mg answer, failing the 1000 mg one by a factor of two, and
the 779.9 mg free-base figure survived only as prose in the assumption block, attached to no claim.

The recipe now carries the three things that make one run differ from another, each omitted from
the record at its default so a recipe stating none is written exactly as before. A test runs the
metformin recipe and nothing else, and lands on both of the paper's reported values.

Its mismatch list was a second version of the same problem: `"mismatches": []` was published for a
comparison nobody had run, because the milestone script never called it. An empty list and an
unrun check are different claims about a paper, so the field distinguishes them now, and the
milestone records the comparison as unchecked with its reason — the dossier was ingested from the
very file it would be compared against, so the result could only ever be empty.

## How wrong a result has to be before each class says so, measured

The tolerances had been described but never measured as a set. Perturbing a real shipped
reproduction until its published verdict changes gives the number each class actually enforces,
beside the agreement it actually achieves:

| Class | Perturbed quantity | Agreement unperturbed | Still `reproduced` at | First non-pass |
|---|---|---|---|---|
| constraint-based | glucose uptake bound, *E. coli* core | rel. err 0 | ±3% | +5% → partial |
| ode-pkpd scalar | metformin dose | 2.2% | +8% / −3% | +10% → partial |
| kinetic curve | rate constant, five models | ≤ 2e-5 | ×1.001 to ×2.0 | ×1.01 to none found |
| spatial | diffusivity | 1.5e-4 | ×1.5 | ×2.0 → partial |
| stochastic | rate constant | 0.6–2.3% | ×1.05 to ×1.20 | ×1.08 to ×1.30 |
| logical | one dropped negation | exact | — | 3 of 6 models: no edit changes the verdict |

Three things in that table are worth stating plainly.

**The curve judge's effective tolerance is 25% of span, not 10%.** The verdict is now the stricter
of an RMSE at 10% and a worst point at 25%, and the worst-point statistic binds whenever the error
is concentrated in under about a sixth of the samples — so on four of five curve shapes even a
*systematic* error is decided by the worst point, at 24.8% to 25.0%. The doubled-peak regression
that motivated the rule is closed at every sample count (it scored 0.0705 and passed at 201
points; it now fails at 25, 101, 201, and 1001), and sample-count gaming is closed with it: the
single-point allowance used to grow as 0.10·√N and is now flat. But a Cmax 25% wrong still passes
as a *curve* claim, while the same Cmax as a *scalar* claim gets 5% — a factor of five that depends
only on how the paper phrased its result. Tightening the worst point to the pass threshold was
measured and rejected: at coarse per-point noise it fails correct work about half the time, where
the present budget never does (0 false failures in 15,000 trials up to 5% per-point noise, three
orders coarser than any real integrator).

**A rate constant can be twice its stated value and still reproduce**, because the certified
species is insensitive to it. The verdict is about one time-course, not about the model, and
nothing on the certificate scopes it that way.

**A logical certificate can attest to a signature that does not identify the network.** For one
published model, all 42 single-literal edits produce the same attractor signature the certificate
matched; for another, five of eight sampled edits do. The method name says `attractor-signature-
match` and its docstring says what that is weaker than, but the certificate does not report how
many other networks would have passed the same check.

## Five figures of a number the machine cannot reproduce

The corroboration artifact recorded each cross-engine distance to five significant figures, which
reads as a measurement. It is not one. Two engines that agree differ by a difference of nearly-equal
numbers, so the pinned engine's own last-place wobble — about 1e-11 relative, and not deterministic
across repeated calls — is amplified into the leading digits. Measured over three regenerations of
the committed corpus, five of six models reproduce their distance exactly and one moves by 8%; the
value committed for that model was not among the three a re-run produced. So the file could not be
regenerated even on the same machine, and the digits that moved were being published as evidence.

The distance is now published as a bound rounded *up*, which is the direction that stays honest: the
number never states better agreement than was measured. The granularity took two attempts, and the
second one is the more interesting result. One significant figure survived the repeated-call wobble
here and was exceeded on CI — a bound of 4e-07 taken on this machine against a live 4.55e-07 there —
because the distance moves between *machines* too, with different engine builds. So the published
granularity is the decade. It still says what the number is for, agreement three to five orders
below the tolerance, without asserting digits no second machine reproduces. The test that caught it
is the one that stays: the committed bound must bound the live distance on every committed model, so
genuine drift toward the tolerance still fails loudly.

## Every class now states what its number rests on

The protocol field started as a PK/PD and kinetic fix, and two classes still published nothing.
A constraint-based optimum is a function of its medium — the thing this class names as its own
first failure mode — so a growth rate certified without one could not be re-derived from the
certificate. The eight published FBA certificates now state the bounds they were solved under and
the reaction maximized, including the honest case: *the model's own distributed bounds (none stated
by the paper)*. The nine logical certificates state the search: how many nodes, and whether the
state space was walked exhaustively or handed to a solver, which is what tells a reader which of
the two paths produced the number.

The logical milestone does not route through the class front-end, so the rule lives in one shared
helper that both call — the same drift that put the worst-point rule in the judge and not the
linter, avoided this time by construction rather than by a later audit.

## A class that could refuse but never fail

The spatial milestone ran at a diffusion number of 0.4 against an explicit scheme stable to 0.5.
That left so little headroom that a diffusivity only 25% larger than stated was *refused as an
unstable discretization* rather than judged — so for the one quantity the class exists to
reproduce, the published configuration could emit a pass or a refusal and nothing else. It is the
same defect the ninth pass found in the verdict path, arriving through the solver's guard instead.

The published grid now runs at 0.2 with twice the steps, which keeps the elapsed time and the
physical scenario identical and still certifies 3/3. A diffusivity twice the stated one now
publishes `not-reproduced` where it used to raise, and a test holds the class to it.

## The rules that reached one surface and not its neighbour

The eleventh audit pass found the same shape of defect three more times: a rule added where it was
first needed, and never carried to the surface beside it.

- **The worst-point rule never reached population envelopes.** A doubled peak that `judge_curve`
  calls `failed` certified as `reproduced` when the identical 201 samples were submitted as a P50
  band, because a band was judged by its RMSE alone. The hole was *larger* here than the one the
  curve rule closed, since the band tolerance is wider: at 201 samples a single point could miss by
  about 2.1x the whole span and still pass.
- **The linter never checked tolerance provenance.** The judge refuses a `class-default` pair that
  is not that comparison's documented default; the linter accepted any of them, so the widest pair
  in the table certified a 24% relative error as reproduced under a provenance reading
  `class-default` — the third linter-versus-judge drift the audits have found.
- **The scope statement was fixed on the way in and not on the way out.** A stored certificate that
  reworded it never loaded, but nothing stopped a caller minting `Scope(machine=
  "clinically-validated", …)` in memory, and the badge rendered it. It is fixed at the type now.

Three more were single-surface bugs of the same family: a one-trajectory SSA ensemble bypassed its
own under-power guard (zero variance reads as "resolvable", but one draw has zero variance by
construction — an exactly-correct model then published `reproduced` on 6 of 40 seeds and `failed`
on 27); `certify_logical` consumed its claims iterable twice, so a generator published an earned
`not-reproduced` as an empty `blocked` certificate; and the cross-engine record judged the raw
distance while publishing it rounded up to the next decade, so a measured 0.011 would have read
"at most 1e-01 -> engine-independent" against a 0.02 criterion.

## What the discipline-loop record does not check

The record ([`discipline-loop.md`](discipline-loop.md)) audits that every disagreement, failure
mode, and default tolerance has a written note, that no note explains a subject that no longer
exists, and that every citation is a path in the repository. Three things it still cannot check,
all found by auditing it the day it landed:

- ~~**A citation that exists but does not say what the note says it says.**~~ Fixed the same day
  it was found: a citation may now carry the literal words it is cited for, every note must have at
  least one such anchored citation, and the audit reads the file. One of the seventeen notes had
  cited a spec that does not contain the requirement it attributed to it.
- **The two default tolerances that are not in the keyed table** — the estimation level's and the
  zero-slack exact match — are named as literals rather than derived from the code, so a third
  non-keyed default would need no note and the gate would stay green. The current set is complete:
  every `CLASS_DEFAULT` tolerance in the package is one of the six table rows, the estimation
  default, or the zero pair.
- **Whether a note is true.** Three claims in the first seventeen notes were wrong on the day they
  were written — a quoted tolerance attributed to all nine logical certificates when six carry it,
  a cross-engine headroom stated as three-to-five orders when the measured range is two-to-five,
  and a spec citation pointing at the wrong file. The gate caught none of them; an audit did.

## What "no disagreement" was allowed to mean

The twelfth pass went at the stages the eleventh had not: the catalog and its persistence, and
ingestion and reconstruction. The theme repeated, one layer down — a check that guarded the way in
and not the way out.

- **Adopt-and-verify reported agreement without comparing anything**, three ways: an initial
  condition held as a parameter plus a rate rule (the PK/PD idiom this ingester supports on
  purpose) was never looked for among the parameters, so a hundred-fold disagreement in a dose read
  as agreement; an initial condition naming nothing in the model at all was passed over, though the
  parameter branch beside it reports exactly that; and a dossier parameter whose counterpart is a
  compartment — a volume of distribution, the commonest PK dossier parameter — matched by name and
  was never compared by value.
- **A load-bearing gap that was not about the medium vanished from an FBA certificate.** The gap
  report filtered on one gap kind, so an objective the paper never named passed validation and then
  reached neither the report nor the per-claim qualification: a clean, unqualified `reproduced`
  with the gap gone from the record. This is the 2026-08 audit's crown-jewel finding, back through
  a door one filter over.
- **The load path accepted certificates the builder refuses.** Deriving the verdict and pinning the
  scope text was only half of "the invariants hold for the ones read back off disk": a stored
  estimation assessment with no protocol, or two assumptions sharing an id, loaded clean. The
  public registry reads certificates from disk and never rebuilds them.
- **A saved catalog could carry a history the state machine forbids.** Only the *endpoint* was
  checked, so a hand-edited file could publish an entry as `certified` through a single
  `queued -> certified` hop that the in-process transition rejects, with a back-dated,
  non-chaining history.
- **Two of the six classes' certificates never expired.** The revision pin exists because "the
  judge is part of the computation", and the four classes Reprolith solves itself carry it — but
  the COPASI and libRoadRunner pins carried only the external engine's own version, so changing a
  class-default tolerance invalidated every PK/PD and kinetic certificate while leaving them
  looking current. Both pins now carry the judge's revision beside the engine's.
- **The pre-submission report said "not yet ready — address the fix list" over an empty fix list**,
  for a claim that reproduced only under a Reprolith-supplied assumption, and for an assumption
  awaiting expert confirmation. Its sibling gap report handles both.
- **Ingestion read past more than it recorded.** A dynamic species with no stated initial value was
  dropped in silence, so the dossier could carry a rate rule for a variable it never declared;
  algebraic rules and unstated compartment sizes produced neither gap nor refusal; and the
  repository's own SBML-qual toggle switch ingested through the core path to a *completely empty*
  dossier — no state variables, no equations, no gaps — which then rated "a valid shipped model
  with nothing to assume". Package content is now a gap, except for `layout` and `render`, which
  describe how to draw a model rather than what it does.
- **The unstated-units gap was flagged as carried by the artifact**, which is definitionally
  backwards: the gap exists *because* the artifact states no unit, so adopting the author's file
  closes nothing. Flagged that way it was discounted out of the difficulty estimate entirely, and
  six shipped models whose every extracted unit is unknown rated `low` while `unit-mismatch` is a
  catalogued failure mode.

## The same-day audit of the same-day fixes

An adversarial pass over the eleventh's own diff, with measurements rather than impressions:

- The new envelope worst-point rule **produced 0 failures in 7,800 trials** of correct work at
  per-point noise up to 5% of band span, and 0 non-reproductions across 1,800 realistic
  Monte-Carlo trials where a paper's 5/50/95 envelope from 5,000 subjects is re-sampled with 50 to
  1,000. The motivating case (a doubled median peak) fails in both the judge and the linter. But
  the discrepancy string named the worst *band* beside another band's worst *point* — it now names
  the band each number came from.
- The new linter provenance gate was exercised over **132 calls** — every entry point crossed with
  paper-stated, reviewer-override, and all seven documented defaults — and refused **nothing**
  legitimate.
- The stochastic guard was correct at one trajectory and **stopped one value short**: two draws of
  a genuinely stochastic model land on the same value **14.6% of the time** (500 seeds), 2.8% at
  three, 0.0% by ten. A zero spread is now evidence of determinism only at 30 trajectories or
  more, which is well above the largest size where a false zero was seen.
- Judging cross-engine agreement on the *published* bound silently made the criterion **2x to 5x
  tighter** than the number passed in, because the bound is a decade. The effective criterion is
  now reported rather than left to be derived.
- The citation anchoring held — **all 25 quotes across the 17 notes are genuinely present** — but
  the gate accepted a quote of one character, or of none. A quote must now be at least twelve
  characters, and the two anchors that pinned only an enum name now quote the tolerance literals
  they are cited for.

## Known limits the audits found and left in place

Recorded rather than fixed, because each needs a design change rather than a patch, and none
can produce a certificate that claims more than it checked:

- **An entry with no accession is queued but not workable.** `submit_paper` needs only a title,
  while `release_work` and `record_result` address an entry by accession, so such an entry could be
  leased and then neither finished nor handed back. It is now refused at claim time with that
  reason rather than stranded, but the catalog still accepts the submission, because a genuinely
  new paper may have no accession yet.
- **The curve threshold is a different standard on every curve** — though much less so than it
  was. The RMSE is taken over the reference's span, so what it admits depends on shape: measured
  before the worst-point rule existed, 15.6% systematic error on a sigmoid, 23.2% on a
  one-compartment bolus, 43.7% on a decaying exponential, 75.3% on a sharp Gaussian peak. Now that
  the worst point also governs, the same measurement gives 14.9% on the sigmoid and 24.8–25.0% on
  the other three, because the worst point binds first there. The spread is a factor of 1.7 rather
  than 4.8, and the ceiling is the 25%-of-span figure above.
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
- **The pinned engine is not bit-identical across repeated calls in one process.** `simulate`
  alternates between two results with call parity — about 1e-11 relative, on four of the seven
  engine-backed models — against a docstring promising byte-identical series. Datamodel lifecycle
  is not the cause: adding and removing one per call (what the code does) alternates, never
  removing them settles after two calls, and reusing a single datamodel is worse still, giving
  five distinct results in six calls. It is inside COPASI. No certificate is affected — a
  discrepancy is recorded to four decimals and the wobble is eight orders below that — but the
  published *corroboration* distances were, and that is fixed below.
- **The certified engine version is whatever the machine last resolved.** The engine extra names a
  floor, so a certificate pinning `copasi 4.46.300` can be regenerated under a different version
  without anything objecting — the pin is recorded, never dispatched on. This is not theoretical:
  an upstream release published and then yanked as incompatible was installed by CI in that
  window, and every engine job aborted inside the simulator. That release is now excluded by name,
  which is a patch for one version, not for the class of problem.
- **`covers()`, which exists to stop a bundle overstating what it addresses, is called from
  nowhere.** On the shipped pair it returns false, because the claims come from the claims dataset
  rather than from the dossier the bundle names as its source. The honest-coverage machinery an
  earlier pass added is dead code on the shipped data.
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

## What a certificate was allowed to say about how it was computed

The thirteenth audit pass ran six independent lenses over the engine, each required to measure its
findings rather than argue them. The recurring shape this time was a *second* account of the same
run that nothing forced to agree with the first — and, where two accounts existed, the stronger one
was the false one.

- **A logical certificate could announce exhaustive enumeration of a space z3 searched.** The pin
  is a claim about what ran and the assessment protocol is another, and `certify_logical` took
  whichever pin the caller passed: a 25-node network published "exhaustive enumeration of all 2^25
  states" one line from a protocol field saying the state space was beyond enumeration, with z3's
  version nowhere on the certificate. The path is a fact about the network's size, so it is read
  off the network now (`solver_pin_for`) and a pin that disagrees is refused.
- **The freshness mechanism did not cover the code that decides which number is judged.** For the
  two classes whose solver is external, the pin's revision spanned the oracle and the certificate
  rule but not `engine.py` (the sampling grid, the species column) or `certify.py` (the metric
  derivation). Measured: a one-line change inside `_metric` flipped both metformin claims from
  `reproduced` (relative error 0.0216 / 0.0045) to `failed` (0.84 / 0.84) while the pin stayed
  byte-identical and `certificates_needing_review` returned zero. Every other class already pinned
  its own analysis layer.
- **The spatial class published clean passes for runs under its own boundary condition.** Its
  docstring called the zero-flux boundary "an unconditional assumption of this class" and left the
  qualification to the caller, who never set it — so a shipped milestone certificate read
  `reproduced` with no assumption block, while the stochastic class took the analogous downgrade
  for its ensemble. On a domain 2.2 standard deviations wide the walls alone cost 23% of the pass
  budget, and at 1.7 the class published `not-reproduced` blaming the paper. Qualified by default
  now, with a load-bearing `spatial-boundary-*` assumption, and the milestone's own ground-truth
  label says `partially-reproduced` so dropping the qualification reads as a disagreement rather
  than as a better number.
- **A reaction term turned a stable-looking grid into finite garbage.** `react_diffuse_1d` accepted
  the pure-diffusion limit of 0.5, where the shortest-wavelength amplification is −1 and the even
  and odd grid points decouple. Measured on Fisher-KPP: correct through α = 0.45, and at α = 0.48
  every value finite and in range with a front speed of −0.005 against an analytic 2.19 — a
  confident `failed`, blamed on the paper, caused by a time step the engine accepted. The
  reaction-bearing solvers are held to 0.4 now, and `front_position` refuses a non-finite profile
  instead of reporting the first crossing among the nodes that survived.
- **The guard that identified a paper compared nothing for 29 of the 30 published certificates.**
  `require_same_paper` compared DOI and PubMed ID only when both sides stated one, and five of the
  six classes certify models that state neither. Filing one kinetic model's certificate under
  another's accession was accepted in silence and scored against that paper's label, and the run
  still reported 6/6. Titles are compared now when nothing stronger exists on either side, loosely
  enough that "E. coli core" and "E. coli core metabolic model" still pass.

Four more were the same door the twelfth pass named — a check on the way in and not the way out, or
the reverse. `build_certificate` and the load path accepted a `failed` verdict with no root cause,
which `render.gap_items` then explained as "no evaluable output" for a claim the certificate says
was evaluated and missed. `summarize_report` refused an inflated abstention count and never checked
the confusion rows it had already parsed, so 55 matches and 45 wrong verdicts published as "100
matched, 0 other of 100" off one edited integer. `compare_sbml_to_dossier` walked dossier to model
only, so a boundary species carrying its own rate rule vanished from the dossier and adopt-and-verify
— which never rebuilds, so never reaches the way-out refusal — reported agreement over half a model.
And the SSA ingester refused a fractional *initial* amount while silently rounding a fractional
*product* stoichiometry, deleting a "0.5 B" product from the network entirely.

Smaller, all measured: `time_to_extinction` returned its own time cap as an extinction time (a
process that never goes extinct reported a mean of 9.13 against a true 39.2); percentile envelopes
had no resolvability guard, so a provably correct model published `failed` on 96 of 100 seeds at
three trajectories; SED-ML paired `numberOfSteps` with `outputEndTime` as though it were a duration
from zero, so a model reproducing its reference exactly linted `failed` at a normalized distance of
4.07; `band_worst_point` used a plain `max`, which steps over the NaN band its twin reports; the
MCP server aggregated every class's certificates regardless of `--data-dir`, so an agent could
certify against a certificate the operator's directory never held; `record_result` was the one
verdict on the server returned without its scope; and two stdio server processes over one data
directory handed out the same unit, with one server's unrelated `submit_paper` erasing another's
recorded certification and all six of its transitions.

Three findings were confirmed and documented rather than fixed, because the honest fix is a
contract change and no certificate this repo publishes reads them: the LP dual is not unique at a
degenerate optimum (20 of 72 shadow prices on *E. coli* core are not determined by the optimum, and
the conserved-moiety pools are reported as 0.0 with the dual unbounded), pFBA's individual fluxes
have alternate optima of their own, and the FVA rescue path relaxes the floor in a way that turns
93 pinned reactions into 8 — converting an earned failure into a silent abstention. Each now says
so where a caller reads it.

## The audit of that audit

Two adversarial agents were then pointed at the fixes above, told to treat them as guilty until
measured innocent, and asked specifically for guards that were too strict, guards that were too
weak, fixes that moved a bug rather than closing it, and tests that would still pass if the fix
were reverted. They found seventeen. The pattern worth recording: **a guard is a claim about what
cannot happen, and it is exactly as trustworthy as the measurement behind it.**

- **The concurrency lock did not lock anything.** It was taken on `catalog.json`'s inode, but the
  catalog is written by atomic rename — so a waiter that opened the file before the rename woke up
  holding an exclusive lock on an orphaned inode and rewrote the winner's work. Measured losing one
  process's write in 4 of 6 runs, which is verbatim the loss it was added to prevent. It also
  raised `FileNotFoundError` on a first run, where the catalog does not exist yet, and that escaped
  the tool-error path entirely. The lock lives on a sidecar now — a file that is only ever locked,
  never replaced.
- **A limit on the diffusion number alone cannot stabilize a reaction term.** `dt = α·dx²/D`, so
  the reaction's share of the amplification grows with `dx²` at fixed α: at the newly-tightened
  α = 0.40, dx = 1.1 still produced a Fisher-KPP front speed of −0.0000 against an analytic 2.19,
  every value finite and in range. The reaction is budgeted against the same [−1, 1] band the
  diffusion number is checked in now, with `f′` estimated by differencing over the profile's own
  range. The rule reproduces the measured cliff (α ≈ 0.465 at dx = 0.5) instead of guessing at a
  constant, and admits every discretization measured to be correct.
- **The NaN fix moved the bug one level down.** `band_worst_point` stopped stepping over a diverged
  band, but `worst_point_deviation`'s own bare `max` still swallowed the NaN, so the same clean
  number next to the same NaN was still published.
- **Two guards were weaker than the sentence they promised.** `require_stated_cause` accepted an
  `implicated`-only assessment, which `render.gap_items` still explained as "no evaluable output" —
  the exact invented sentence — and accepted whitespace as a cause. `require_same_paper`'s new
  title check went quiet whenever *either* side stated a DOI, which is the ordinary case for a
  certificate that cites its paper properly; and raw substring containment accepted a title of "a".
- **The new pin check guarded the builder and not the load path** — in the same batch that hoisted
  `require_stated_cause` onto both, for the stated reason that the registry reads certificates off
  disk and never rebuilds them. Both the pin and the protocol are on the certificate, so the load
  path can compare them, and now does.
- **The confusion cross-check was opt-out by deleting one key**, and the threat model it names is a
  hand edit. **The spatial boundary assumption attached to claims nobody judged**, because the flag
  was read off the claim and the judge abstains internally without raising. **`except ValueError`
  was broad enough** to publish a caller's sign error as an honest abstention. **The percentile
  guard was off by one at its own boundary**, so P2.5 at 40 trajectories — an ordinary 95% envelope
  — still returned the observed minimum wearing a band label. **`max_time` was not a cap**: the
  clock was tested before the jump, so 747 of 2000 runs returned a finite time exceeding it, up to
  4.4x. **The new model-to-dossier sweep reported the ingester's own deliberate omission**, so a
  rules-only model with an unread fixed input could never return "no disagreement".

And four of the new guards had no behavioral test at all — the adversarial pass proved it by
reverting each one and watching the suite stay green apart from the source-hash pins, which fire on
any edit including a comment. Every fix in both batches now has a test that fails when the fix is
removed.

### And the audit of that

A third pass over the fixes-to-the-fixes found twelve more. Three of them were the same mistake
wearing different clothes, and it is worth naming precisely: **the reaction-stability probe
evaluated the caller's function at values the run never visits.** Widening the sampled range by 10%
to anticipate a growing profile meant probing below zero, and so a reaction carrying an ordinary
non-negativity check raised, the probe swallowed the exception, and the entire guard was skipped —
the pathological grid it had just been written to refuse came straight back, admitted. The same
widening sent `u**0.5` complex and crashed the solver, and on a uniform profile at large magnitude
the widening fell below one ulp and the sample step divided by zero. The probe stays inside the
profile's own closed range now, does not swallow anything, and handles growth the way the run does
— by re-checking when the profile leaves the range already checked, which also closes the case
where a profile grows into a stiffer region than the one it started in.

A fourth of the same family: the two-species probe held the partner species at `0.0`, a value the
run never visits, and a slope that is identically zero there — `g(0, v)` for a Brusselator, any
mass-action `−k·u·v` — reported no reaction at all. Measured, that admitted `dt·|∂f/∂u| = 3.0` and
returned 1.1e15 against a converged 2.3e-66. It probes at the partner's real extremes now.

The rest: the model-to-dossier sweep's new restriction read the set of needed values off the
*dossier's* surviving equations, so a state variable the dossier lost entirely — which takes its
equation with it — was never in the set, and the silence it was written to close reopened. A
read-only data directory made the lock's sidecar unopenable, and `PermissionError` escaped the
handler where the previous code returned a clean rolled-back tool error. The pin/protocol check
required the pin to name the *wrong* path, leaving the easier hand edit — deleting the solver, so
the pin names no path at all — loading clean. And the title rule compared token *sets*, so word
order was free: "Effect of insulin on glucose uptake" matched "Effect of glucose on insulin uptake".

Three passes, forty-six findings, and the shape of the last two is the same: **a fix is a claim,
and the claim is worth what its measurement is worth.** None of the second- or third-round defects
were found by reasoning about the code. All of them were found by running it.

### Round four: the rule was written down and not applied to the code written beside it

Twelve more, four of them regressions the previous round introduced. The pattern is sharper than
the last one and worth stating exactly: **round three fixed which values a probe may evaluate,
wrote that rule into the docstring, and then authored two new code paths in the same commit that
break it.** The uniform-profile branch probed `lo + ε` — outside the profile, three lines under a
docstring saying "every probe is a value the profile holds" — and a reaction defined only up to its
carrying capacity crashed with a bare `math domain error`. The two-species probe held the partner
species at `0.0`, a value the run never visits.

A uniform profile is not probed at all now. That is sound rather than a gap: the instability being
guarded against is neighbouring grid points decoupling, and a profile with no spatial variation has
no such mode — the moment the reaction moves it, the re-check fires on the range it reaches.

The same round-three commit added the growth re-check to the one-species solver and not to its
two-species neighbour, so an identical model refused at `dt = 0.008` in one and returned 5.65
against a true 10.0 in the other. Threading the range already checked matters as much as the
re-check itself: a profile that stays uniform at every step is degenerate on every individual
check, so without the union the guard probes nothing at all while the values walk somewhere far
stiffer.

Three guards were still weaker or stricter than their own stated rule. A pin naming *both* paths
satisfied whichever branch was asked. The builder did not enforce the pin/protocol agreement its
own loader does, so `build_certificate` could mint a certificate `certificate_from_content`
refuses — and the logical front-end's version of the check disagreed with both, which is three
guards and two answers about one certificate. And the title rule swung from a token set (word order
free: "Effect of insulin on glucose uptake" matched "Effect of glucose on insulin uptake") to
contiguous words (refusing an inserted word, including this note's own example), when what it wanted
was an order-preserving subsequence with a length floor — because every one-word title is a
subsequence of something, so "model" would otherwise name any paper containing the word.

Four rounds, fifty-eight findings. The yield per round has barely moved: 26, 17, 12, 12. What has
moved is where they live — from the engine, to the fixes, to the fixes' own new branches.

### Round five: a performance margin that blinded the check it was optimising

Six findings, down from twelve — the first real drop in five rounds. One was a genuine regression,
and it is the most instructive kind: the re-check added in round four was measurably slow, so round
four bought speed with a 1% tolerance before re-probing. The tolerance was measured against the
*accumulated* band, which only ever grows, so a profile drifting step by step into a region with
``dt·|f′| = 25`` was never re-probed at all. A case the previous commit refused now returned 4.92
against a true 5.00 — finite, plausible, and wrong, which is this module's own name for the failure
it exists to prevent.

The fix is the one that should have been reached for first: re-check on *any* departure, and pay
for it by probing only the sliver newly entered rather than the whole range again, carrying the
largest slope already measured. That is both correct and faster than the version with the
tolerance — a 20-point grid over 5000 steps went from 0.50s to 0.09s — and it tightened the
estimate enough that a discretization the old code refused now runs and returns the exact steady
state. A guard bought with a heuristic was slower *and* wrong.

Two more of the same family as earlier rounds. The two-species check threaded each partner value's
probed range into the next, so after the first partner the range looked covered and the other eight
never probed anything: an activation window that fires at exactly one partner value reported a
slope of zero, and the run returned 6.4e33. And the pin rule — by then living in three places —
still gave two answers: one layer refused a pin naming no path where the others accepted it, and
two refused a pin naming both where the third accepted it. There is one implementation now, called
from all three.

Five rounds: 26, 17, 12, 12, 6.

## A rule that held everywhere except where it mattered most

Six agents were given disjoint territory — the oracle and agreement layer, certificate provenance,
the constraint-based class, the logical/spatial/stochastic trio, the kinetic and ODE pipeline, and
the three query surfaces — and told that a finding without a runnable repro printing real numbers
was worth nothing, and that they had to try to refute themselves before reporting. Between them
they killed about forty candidates and kept eleven. Two found the same pin defect independently.

The pattern this round is narrower than the last few, and it is a stubborn one: **the rule was
right, and it was applied to all but one of the cases it was written for — and the omitted case
was the one where it mattered most.**

- **A relief that fired at a point instead of on a condition.** `normalized_curve_distance`
  divides by the reference's range, falling back to its mean magnitude when the range is zero,
  because a flat reference has no range to be a fraction of. But the fallback tested
  `span == 0.0`, so it covered exactly the references that never occur and missed every one that
  is *nearly* flat — which is all the real ones: a plateau, a steady state, the median band of a
  stationary ensemble, a digitized flat line. Measured: two 400-trajectory ensembles of one
  stationary immigration-death model, differing only in seed, certify as `failed | worst band P50
  normalized distance 0.7528 | fault: reconstruction` over a 2-copies-in-50 disagreement — and the
  P50 band named "worst-matched" carries the same absolute error as the P90 band that passes at
  0.20, so the certificate points the reader at the best-agreeing band. Worse in both directions
  at once: a digitized plateau reconstructed to 0.5% failed at 0.4208, while an exactly-flat
  reference reconstructed 10% wrong passed at 0.1000. The scale is now the larger of the range and
  the level, which can only widen the denominator — so no comparison that passed can be turned
  into a non-pass, and the committed spatial curves (span/|mean| of 3.89, 4.24, 3.48) are
  bit-identical. The near-flat plateau now scores 0.0050 and the flat band's 4% miss scores 0.0396
  against a true 0.0400. The discrepancy line no longer says "of span", because the denominator is
  no longer always the span.
- **A guard switched off at the value it should be strictest at.** `unresolvable_ensemble_reason`
  returned "this ensemble can resolve the claim" for a reported mean of zero *before* the
  zero-spread check ran, so an extinction or no-expression claim skipped resolvability entirely.
  A one-trajectory ensemble that happened to land on 0 published `reproduced` at "relative error
  0.0000": 87 of 200 seeds on immigration-death with a true mean of 1.0, and 27 of 200 at two
  trajectories. With the two checks in the other order, 0 of 200 at every ensemble size measured,
  while a genuinely deterministic zero model still resolves.
- **A guard covering two of the three ways a parameter is determined.** An override of a parameter
  fixed by a rule or an initial assignment was refused, on the stated ground that "an override that
  does not take is a claim about a run that did not happen". An event assignment determines a
  parameter too, and was not refused — so in a repeated-dose or infusion model, the ordinary shape
  for a COPASI-exported PK model, the event rewrites the very parameter the claim moves. Measured:
  a 3x override changed the answer by 0.01% and published `overrides: kin=3.0` beside
  `reproduced, relative error 0.0000`.
- **A pin spanning four of the five modules that decide the number.** The constraint-based engine
  pin named `fba`, `constraint_based`, `oracle` and `certificate` — but the LP it solves is fixed
  by `ingest_fbc_sbml`, which sets the stoichiometry, the flux bounds and the objective vector.
  Halving the ingested bounds moves *E. coli* core growth from 0.873922 to 0.436961 and leaves the
  pin byte-identical, so the freshness gate keeps certifying the corpus as current. This has
  already happened: commit `2b814dc` ("refuse a minimize objective instead of returning a
  wrong-signed optimum") touched `sbml.py` alone, changed a verdict away from FAILED, and moved no
  revision. The other three self-solved classes were checked before generalizing — none of their
  certified paths reads `sbml.py`, so this was the only pin to widen.
- **A validator the publishing path never called.** `validate_constraint_based` requires each
  objective claim to carry exactly one *numeric* reference value. `certify_constraint_based` never
  called it, read `reference_data[0]`, and let the judge default to a numeric reference — so a
  growth rate the dossier recorded as digitized off a figure was judged at the numeric tolerance
  and then published as `reference_kind: "numeric"`, the certificate asserting a precision of
  reference the paper never gave. It flips real verdicts: a relative error of 0.1062 is
  `reproduced` inside the digitized band and `not-reproduced` inside the numeric one. The rule was
  guarding the way in and not the way out; the milestone's own entry reaches certification through
  `dossier_from_dict`, which validates nothing.

Four more were the same shape one level up — a check that validated its inputs and never its
outputs, and a rule that reached one surface and not its neighbour:

- **A truncated run published as a complete one.** COPASI signals a time course it abandoned —
  step-limit exceeded, integration failure — by returning `False` and recording only the samples it
  reached. `simulate` discarded that return value and never compared the recorded count to the
  requested one. Every recorded sample is finite, so `require_finite` cannot see it. Measured on a
  chattering-event model: 2 of 21 samples, the run stopping at t = 5.0 of 100, and the certificate
  publishing `REPRODUCED, relative error 0.0000` for a claim stated at t = 100, with
  `protocol: duration=100.0, steps=20` printed beside it. Curve claims are caught downstream by the
  oracle's sample-count check; scalar claims — the whole PK/PD class — were not. An abandoned run is
  now the blocked-not-failed signal the module already raises for divergence, and the libRoadRunner
  path, which sets corroboration distances, carries the same check.
- **A stability failure raised as a caller bug.** The decay-step check raised a bare `ValueError`
  while both of its siblings in the same function raise `UnstableDiscretization` — the one exception
  `certify_spatial` catches in order to abstain on a single claim. So an ordinary discretization
  (a 5/min degradation rate at dt = 0.5 min) took down the whole certificate and discarded every
  sibling claim's honest verdict. The threshold itself was measured correct; only the type was wrong.
- **One un-workable entry froze the entire queue.** A previous round taught `claim_work` to refuse an
  accession-less entry, since nothing can finish or release one. It refused the head of the queue and
  *returned*. `seed_candidates` gives every un-curated candidate no accession and nothing in the
  surface can add one, so a single such entry withheld every workable entry behind it, permanently,
  while `backlog_health` went on publishing them as claimable: 3 claimable, 0 obtainable. The refusal
  now steps over them and names how many it stepped over.
- **The terminal could not learn what a blocked paper was blocked on.** `missing_inputs` is *required*
  to be non-empty for a blocked transition — "what is missing is the whole point of the state" — and
  30 of the 31 shipped entries are blocked. The JSON an agent receives carried it; the CLI printed
  only `(blind run)`. Likewise a certificate whose overall verdict is derived from its claims alone
  could show a green badge and an unqualified verdict summary over a non-empty "what was missing"
  report, because a gap that never became a claim cannot lower the overall.

And one that the fix for it immediately caught a second instance of. The metformin certificate —
the render the README and `docs/mcp-server.md` send readers to — published `Engine pin: copasi
4.46.300 / deterministic-lsoda` with no judge revision, while the machine-readable certificate for
the same paper carried one; it had also drifted two code changes behind the protocol text it
printed. Two accounts of how one result was computed, and the reader-facing one was the weaker and
the staler. The freshness gate globbed `*.json` under six milestone directories and could not see
it. It now checks every committed render, and fails on any it cannot attribute to a class rather
than skipping it — which found that the *E. coli* core worked-example render names no revision
either. `scripts/render_worked_examples.py` regenerates all three from the certificates they are
renderings of, so the two accounts cannot drift apart again.

## The audit of that audit, again — and the direction a fix points

Round one's eleven fixes were handed to a fresh agent told to treat them as guilty until measured
innocent, alongside three angles nobody had used: the specs read line by line against the code,
whether the *failure* paths are reachable at all, and the whole project walked as a first-time user
executing every documented claim. Every angle found something. Eight of the survivors were in the
previous round's own fixes, and the two worst were the same mistake: **a repair that is safe in one
direction is not safe, and I checked the wrong direction.**

- **The oracle fix loosened the number it was meant to make honest.** Widening a denominator to
  `max(range, level)` was verified one-directional over 200,000 random references — 0 narrowed,
  3,752 widened — and that argument is worthless, because widening can only turn a miss into a
  pass. On Chassagnole's *E. coli* carbon-metabolism curve, a shipped kinetic milestone reference
  with a range of 2.18 mM against a level of 4.09 mM, the denominator grew 1.87x and a
  reconstruction missing by **43% of everything the curve does** certified as `reproduced`. Six
  further flips were measured on the same model. The level is now used only where the range really
  is noise: below a tenth of the level. That boundary is measured twice over — every curve the
  oracle judges has a range/level of 0.534 or more (then 1.45, 2.45, 2.61, 3.25, 12.18) while the
  flat cases the fallback exists for sit at 0.02 and 0.01, whose geometric midpoint is 0.103; and
  independently it is the curve tolerance's own pass threshold, since a curve that does not move by
  one tolerance-width cannot be measured in units of its own excursion.
- **The badge fix upgraded the verdicts it was meant to leave alone.** Setting amber whenever a gap
  report is non-empty was written for the green case and applied to all four. `run.blocked_certificate`
  always carries a gap report, so all 30 PK/PD abstentions turned from grey to amber, a
  not-reproduced result with a gap turned from red to amber, and grey became unreachable. It now
  only ever downgrades.

Two more of round one's fixes were too strict, which is a defect in this repo and not a safe
default:

- **The event-assignment override guard is reverted.** An event overwrites its target only when its
  trigger fires, so an override still governs the run until that moment and governs all of it if
  the trigger is never satisfied in the window. Three measured shapes — an event firing at the
  moment the claim is read, a trigger never satisfied, an assignment writing the value already
  held — each moved the answer threefold and each was refused. What was actually missing is a
  fourth route the guard never had: a kinetic law's own local parameter shadowing a global of the
  same id, where the law reads the local one, the run comes back bit-identical, and the protocol
  publishes an override that did nothing. That one is unambiguous, and is what the guard now
  refuses. The residual event case needs the trigger evaluated over the protocol window, not a name
  lookup, and is left recorded rather than guessed at.
- **The constraint-based validator aborted where an abstention was available.** A dossier with no
  targetable claim states nothing to be wrong about — the judging loop is empty and the certificate
  comes out `blocked`, which is first-class output here. Raising on it would have taken down a
  whole eight-model milestone run for one not-yet-extractable entry.

And two were right but reported wrongly: the truncated-run refusal named a stopping time one grid
step later than the engine reached, because COPASI appends a duplicate final row when it abandons a
course, and the text reaches an agent verbatim through the MCP lint tools — erring toward *the run
got further than it did*. It reads the engine's own time column now. The queue fix stepped over
un-workable entries but left `backlog_health` counting them, so a queue of fifty un-curated
candidates still advertised fifty claimable and handed out none.

### What the failure paths could not say

Asking whether each class can publish a true negative — never asked before — found the stochastic
class bounded in a way nothing stated. `unresolvable_ensemble_reason` divided the *reconstruction's*
standard error by the *paper's* reported mean, and for a counting process the variance grows with
the mean, so the further a reconstruction over-predicted the noisier it was and the more certainly
it was ruled unresolvable. At the shipped settings a model over-predicting threefold sat **71
standard errors** outside the pass band and was published as `blocked`, whose published meaning is
"insufficient information", under a reason that was arithmetically false. It was one-sided, too: a
hundredfold *under*-prediction was judged, because under-predicting shrinks the variance. Past about
2.5x over-prediction the class could not publish a true negative at all.

However noisy the ensemble, a mean clear of the pass band by more than three standard errors is not
there by sampling accident, and is now judged. Three is measured: on the immigration-death model
over 200 seeds a *correct* model would be published as a false `not-reproduced` on 9 of 200 seeds at
two standard errors and 2 of 200 at three, with four buying no further improvement, and at forty
trajectories and above it is 0 of 200 — while every wrong model measured re-opens at all three
values. The change can only turn an abstention into a judgement, so no verdict that stood can flip
to blocked.

The same class was also the only front-end still defaulting a shortfall to a *named* cause,
`finite-ensemble-sampling-noise` — on the far side of the guard that has just established the
ensemble's noise is too small to explain a miss. It was filing a 107% discrepancy under a 2.2% noise
source, which is precisely the nearest-wrong-cause the `uncategorized` escape hatch exists to
prevent, and it made this note's own earlier sentence — "every class front-end uses it" — false.
All eight front-ends use it now.

### What the documents claimed

Reading the specs against the code, and then the whole project as a first-time user:

- **An assumption could be attributed to the paper.** `attributed_to` was free text with a default,
  which is to say the invariant "always attributed to Reprolith, never to the paper" was carried by
  the sentence asserting it. A certificate can print "supplied by Reprolith, not the paper" over an
  assumption whose machine form names the paper's own table — two contradictory statements about one
  number, with an agent reading only the false half. Refused now on the build path and the load
  path, the boundary the loader exists to defend. All eight committed assumptions were already clean.
- **The dossier recorded SBML unit *identifiers* as units.** `unit_0`, `unit_2`, `substance` — and
  the units gap counted only the values with no reference at all, so "81 of 115 extracted values
  state no unit" implied the remaining 34 carried usable ones. Every one of those 34 resolves to a
  real unit in the file's own `unitDefinition`s, and none of them said so; the dossier now carries
  both, the source's wording for provenance and what it resolves to (milligram, millilitre,
  nanomole), which is what the ingestion spec asked for and nothing implemented.
- **The spatial milestone README published a cleaner verdict than its certificates carry** —
  "the verdicts are clean **reproduced**", where all three are `partially-reproduced` and every
  claim is assumption-qualified by the boundary condition Reprolith chose. The top-level README and
  `docs/self-validation.md` both say so correctly; this file was missed by the commit that fixed
  them. Corrected, along with a milestone README whose headline said 31 entries "yielded a
  certificate" when thirty are abstentions with no certificate file, a worked example labelling
  `e_coli_core` CC-BY where the repo's own third-party notice says academic and non-profit only, and
  a `--data-dir` flag documented as the remedy for an installed copy without saying it reads exactly
  the one directory named and drops the aggregated six-class view.
- **`github-collaboration` promised an MCP view of collaboration state that no tool provides.** It
  now carries the same "what carries each requirement today" disclosure the autonomous-build-loop
  spec already sets as the precedent, naming both this and the unfiled queue issues as intent rather
  than machinery.

The render freshness gate added last round was itself too weak: it checked the pin line and nothing
else, so a hand-edited verdict in a committed render passed untouched — the same two-accounts-of-one-
result it was added to close, one field over. It now asserts the render is byte-for-byte the
rendering of the certificate beside it.

## The corpus, the modeller's reading, and two servers over one directory

Round three took four angles, three of them new: the previous round's own fixes again; the
ingestion path read as a domain modeller rather than a programmer; the committed *data* recomputed
against independent tools, which nobody had ever checked; and the write path driven from five
concurrent processes.

**The data is sound.** Every FBA growth value reproduces bit-identically against COBRApy, every
kinetic reference curve byte-identically against libRoadRunner, every CANA attractor signature and
SAT fixed-point digest twice over, and every closed form — Poisson, binomial, Gaussian diffusion,
Fisher-KPP, Nagumo, morphogen decay length, bursty Fano, harmonic extinction, Derrida — derived and
checked numerically rather than asserted. Every count in all six agreement reports, in
`docs/self-validation.md`, and on the registry page recomputes from the per-entry rows, and all
thirty published content digests recompute from the certificates. That is the first independent
audit of the corpus itself, and it came back clean but for one thing:

- **A number attributed to a paper that reports a different one.** Four documents, and the
  certificate's own `source_location`, credited "the 11 fixed points of the Li et al. 2004 yeast
  cell-cycle network". Li et al. 2004 report **7**, over 11 nodes, with basins
  1764/151/109/9/7/7/1. The 11 belongs to CANA's bundled *12*-node variant, which adds `CellSize`
  as a free self-loop node; seven of the eleven sit at `CellSize=0` and are exactly the paper's,
  and four exist only at `CellSize=1`. The count was never wrong — CANA returns 11, brute force
  returns 11, and the protocol line honestly said "12 nodes" — but a reader following the
  certificate's own pointer landed on a source reporting something else. The network is now named
  for what it is everywhere it appears.

**What a modeller would notice.** Reading ingestion as someone who might hand Reprolith their own
model found the unit resolution added last round publishing units *inverted*:

- SBML defines a factor as `(multiplier × 10^scale × kind)^exponent`, and the renderer applied the
  exponent to the kind alone. The metformin model's eleven blood flows were published as 3.6e5
  mL/s where the file states mL per 360000 s — wrong by 1.3e11, in a committed artifact — and a
  second-order rate constant came out 1e6 the other way. Strictly worse than the bare `unit_2` it
  replaced, because it reads as resolved. Every rendering now agrees with libsbml's own.
- **A value a rule computes is not a value the paper stated.** SBML makes a rule-determined
  parameter's `value` attribute inert, and models ship whatever was there: BIOMD0000000058 declares
  eight such parameters at `0` that the model runs between 0.5 and 21, and BIOMD0000000051 carries
  seven time-varying cofactor pools — ATP decays 45% over the run — as if they were clamped
  constants. Recorded at `quoted` confidence, the dossier asserted numbers the model never holds,
  and `compare_sbml_to_dossier` compared the dossier against that same inert attribute and
  published "no disagreement" over every one of them. The rule was already written into the two
  neighbouring surfaces — `build_model_sbml` emits such a parameter non-constant, `_apply_overrides`
  refuses an override on one — and had reached neither the ingester nor the check. Metformin's
  dossier drops from 94 stated parameters to 48; the rules that determine the other 46 were always
  carried, so nothing is lost but the false value.
- **The published observable named an amount and meant a concentration.** The bundle recipe and the
  certificate protocol both said `mPlasmaVenous`, which in this SBML is declared
  `hasOnlySubstanceUnits`, in a compartment of 2247 mL. `simulate` reads the engine's concentration
  data, so the number is 6.07 nmol/mL; a stranger resolving the symbol as SBML defines it gets
  13,630.8 nmol and a `failed` verdict at 2199% error. Every other committed model has a
  compartment of size 1, which is why the same ambiguity had already produced a cross-engine defect
  and been recorded as harmless. Protocols and recipes now write `[X]`, and the engine accepts that
  notation, so a bundle re-run strictly as published resolves.

**Two servers, one data directory.** The lock on the sidecar and the atomic write hold: five
processes, SIGKILL mid-write, a real full disk, verdict laundering, replay, unbounded history —
all clean. Two things were not.

- **A blank catalog was silently reverted rather than refused.** The guard re-reads the catalog
  under its lock so a mutation applies to current state; for an *empty* file it skipped the re-read,
  mutated this process's start-up snapshot and wrote that back whole — destroying twenty entries
  another server had persisted, and replying `created: true`. Reachable from the repository's own
  regeneration scripts, which rewrote the catalog with a plain `write_text` that truncates to zero
  before writing ~52 KB and takes no lock. Start-up already refuses a blank catalog and the guard
  already refuses a corrupt-but-non-empty one; this was the third reader of one condition, and it
  disagreed with both. It refuses now, and the six scripts write atomically.
- **A correction published after start-up was invisible to the write path.** `record_result`
  refuses a superseded certificate — "recording one would write that stale verdict into the catalog
  permanently" — but decided supersession against the ledger as it stood when the process started,
  and supersession is expressed by *adding* a file. The same digest was accepted or refused
  depending on whether the server happened to be running, and the retracted verdict went into the
  entry's permanent history while the CLI reading the same directory reported it superseded. The
  ledger is now re-read under the same lock, keyed on the certificate directory's mtime.

## Six classes compared with each other, and a file that means something else

Round four took four angles: the previous round's fixes again; a differential audit *across* the six
classes rather than within one; a sweep for silent truncation; and semantically hostile model files
checked against independent tools. Every angle paid, and half the findings were again in the
previous rounds' own work.

**The unit resolution, third time.** Two more ways it was wrong. SBML Level 2 predefines five unit
names — `substance`, `volume`, `area`, `length`, `time` — that a model may use without defining
them, and reading them as unresolvable identifiers made the units gap say "N of M extracted values
state no unit **in the artifact**" about values whose unit the artifact does state, pushing a fully
specified model from low difficulty to high: the exact defect this resolution was added to remove,
re-created one level down. And `getExponent()` truncates, so a valid `exponent="0.5"` published as
`metre^0` — a different physical dimension, at `quoted` confidence.

**The guard that was both too narrow and too strict at once.** The kinetic-law shadow check added
last round read `getNumLocalParameters`, a Level 3 accessor that returns 0 on Level 2 — and *all
six* committed kinetic models are Level 2, including the one whose 135 local parameters the guard
was written for. It saw none of their 224; the 10 of the corpus's 234 it did see all belong to the
Level 3 PK/PD model, which is a different class. (This read "five of the six" until a claims audit
counted them — the true statement is the sharper one, since no kinetic model was visible at all.) It also unioned every reaction's locals flatly, so a
global shadowed in one reaction was refused where it is the live value in another — the ordinary
"global default, per-reaction local override" idiom — refusing an override that moved the answer
7.4×, under a message stating the opposite. It now refuses only an id that no law anywhere reads
from global scope, read level-agnostically: 119 ids on the model that previously showed 0.

**Comparing the six classes with each other** found two contracts that five honour and one does not.
A zero-duration ensemble comes back as the initial state, and a claim stated there certified as
`reproduced` at relative error 0.0000 — while both time-advancing siblings refuse exactly that at
their certifying front end, and the MCP boundary already refuses it here. And the stochastic protocol
was the only one not naming what it read: the network, the initial state and the species count are
all certificate-level, so two claims reading different species had byte-identical protocol strings
while disagreeing about the answer.

The same comparison caught the resolvability fix reaching one surface and not its twin: the linter
omitted the observed mean, so a threefold over-prediction sitting 66 standard errors outside the
pass band certified as `failed` and linted as "insufficient information" — the sentence this note
already called arithmetically false, still live on the agent-facing gate. The test meant to keep the
two aligned called the shared function directly and never the call sites, so it stayed green; it now
drives both.

**Files that mean something else.** Three well-formed artifacts, zero libSBML diagnostics each,
walked past guards written for exactly their hazard — all in the path an untrusted MCP caller
reaches:

- A Level 2 `stoichiometryMath` (`A → n B`, n=5) read as stoichiometry 1. libRoadRunner gives 500
  molecules; Reprolith gave 100, and `reported_mean=500` — the model's own answer — published as
  `failed`. The `constant` attribute the guard tested is Level 3 only.
- A model-level `substanceUnits="mole"` is the default for every species that omits the attribute,
  so a model declaring itself in moles passed the guard whose docstring says "a species declared in
  moles is read verbatim, so 100 mol becomes 100 molecules and every noise statistic the class
  exists to reproduce is computed for a different system". The sibling ingester already reads that
  fallback.
- Only the *model's* `conversionFactor` was refused, not a *species'*, which rescales that species'
  contribution to every reaction's extent: 1000 under libRoadRunner against 100 here.

**And four things that quietly did less than they said.** A missing class agreement report was
skipped rather than refused, so the registry banner, the CLI table and the MCP payload all published
a smaller denominator as the whole truth — 60 labelled entries becoming 57, on a page still
rendering that class's three certificates. `compare_sbml_to_dossier` kept the *first* value seen
under a local parameter name, so a model holding `k1` at 0.1 and 999.0 reported "no disagreement"
against a dossier stating either one, decided by reaction order. A blocked entry recorded the first
of several gap notes as though it were the blockers. And the non-constant-stoichiometry gap named
one reaction and stopped, under-naming the affected set with no count.

And three more in the round before's fixes, found by re-auditing it:

- **A parameter the model does contain, reported as absent.** Excluding rule-determined names from
  the model's parameter dictionary excluded them from *membership* too, so a faithfully ingested
  dossier reported its own source file as "not present in the model". Worse, the exclusion covered
  *rate*-rule targets, whose `value` is not inert at all — it is the initial condition, and
  "a parameter plus a rate rule" is the PK/PD idiom the ingester supports on purpose. It silently
  undid the earlier fix whose comment sits four lines below it, the one that exists because
  comparing against species alone read a hundred-fold disagreement in a dose as agreement. What has
  no stated value to compare is a narrower thing than what the model does not contain.
- **A change signal blind to how this repository publishes.** The ledger refresh keyed on the
  certificate directory's mtime — which moves when a file is added or removed, and does not move
  when an existing file is rewritten in place. Every milestone script writes `<accession>.json`, so
  a corrected certificate republished under its own name stayed invisible to a live server for the
  life of the process: precisely the case the refresh was added for. It now fingerprints the
  listing.
- **One bad file, then permanent quiet degradation.** The directory was marked seen *before* the
  load, so a single unreadable certificate raised once and was then skipped forever, leaving every
  valid file beside it unread — the smaller-track-record failure that `load_certificates` refuses
  to allow for one file, reintroduced for a whole directory.

## What twenty certificates were pointing at

Round five's sharpest finding came from an angle nobody had taken: reading a finished certificate
as the outside reader it exists to persuade — a reviewer checking an author's reproducibility
claim — rather than auditing the code that produced it.

**Twenty of the thirty published certificates cited a publication as the source of the reference
value, and the reference had been computed by a different tool re-running the same model file.**
The claims dataset states the rule in as many words: *"A claim's reference value comes from the
paper (cited in `source_location`), not from re-running the model."* Every other use of the field
honours it — `"Table 4, Zaharenko dataset (reported 6.2 nmol/mL)"`, `"Fig 3"`, `"Table 2"`. But the
kinetic curves are libRoadRunner's, the seven genome-scale growth rates are COBRApy's, and the
logical attractor structures are CANA's, each recomputed from the committed model, and no
certificate named the tool. The provenance was stored right beside the reference in every dataset
file — `reference_tool` — and dropped on the way to the claim.

That is not a small wording point. Those references are *why* the cross-validation is
non-circular, and the project's documentation says so accurately in five places. None of them is
reachable from the certificate, which `render.py` describes as "a self-contained, plain-text
certificate a stranger can follow". A reader following `doi:10.1038/msb.2011.65` from the iJO1366
certificate finds a paper that publishes no such growth rate. This note's own earlier section
records the internal analysis that for exactly those two models "an honest per-paper reproduction
abstains rather than guess the medium" — while the public artifact said `reproduced`, green, over
their DOI and PMID.

It is also the same defect as the budding-yeast attribution fixed one round earlier — *"a reader
following the certificate's own pointer landed on a source reporting something else"* — which was
fixed for the one entry that surfaced it and not for the nineteen beside it. The rule reached one
certificate and not its neighbours.

Every publication-citing claim now says what produced the number judged against it: *"…
— reference value computed by COBRApy 0.31.1 `slim_optimize` on the model's distributed medium,
not a number read from the paper"*. Nineteen claims across three classes, pinned by a test with a
floor so the guard cannot quietly stop biting. No verdict moved: 8/8, 6/6 and 9/9 as before.

The same reading reached the README's first paragraph, which says Reprolith "checks the output
against the paper's own figures and tables". One of the thirty certificates does that. The claim
is what the project is *for*, and it now says so while being exact about how much of it is built.

**One finding declined, with the reason recorded.** The seven genome-scale certificates disclose on
their protocol line that the paper stated no medium, and that fact reaches neither the gap report
nor the badge — where the spatial class treats an identically-shaped omission as a load-bearing
gap and goes amber. Measured, the alternative matters enormously: an anaerobic medium changes
iJO1366's growth by 75% and iMM904's by 100%. But nothing was *guessed* here. The medium is stated
— by the model file, named in the claim's own `conditions` and in its protocol — and the reference
was computed under that same stated medium. With the reference provenance now on the claim line, a
reader is told exactly what was compared with what. Recording it as a load-bearing gap would
downgrade eight verdicts and invalidate their ground-truth labels for an omission that, once the
claim is honestly scoped, is not there. A too-strict fix is a defect too.

### The pipeline reproduces byte for byte

Determinism is one of the three honesty invariants this project claims, and until now it had been
checked at the level of the content hash — stable under `PYTHONHASHSEED`, `canonical_json` sorting
its keys — never by running the generation pipeline twice and diffing everything it makes.

Five independent clean trees, each extracted with `git archive`, running all eight generators:
baseline; reverse order with `PYTHONHASHSEED=12345`, `LC_ALL=C`, `TZ=Asia/Tokyo`, invoked from `/`
by absolute path with the registry built *before* any milestone; a five-level-deeper path with a
comma-decimal locale (`de_DE.UTF-8`), `TZ=UTC` and `OMP_NUM_THREADS=1`; a from-scratch run with all
64 generated files deleted first; and a third order permutation under `PYTHONHASHSEED=random`.
`diff -rq` across whole trees returns nothing, in every pairing. Checked against the committed
blobs rather than a working directory: **64 produced files, 0 differing from HEAD**.

The solver noise is real and does not reach the artifacts. Four consecutive `simulate` calls on
Kholodenko's MAPK model alternate by 2.94e-4 with call parity, exactly as `engine.simulate`'s
docstring describes — and certifying that model *alone, in a fresh process, at a different parity*
still reproduces the published digest, because the discrepancy is published to four decimals and
the corroboration figure is published as a bound rather than a measurement. Planting a stale
certificate in a milestone directory is pruned, and the registry sorts its rows rather than
inheriting filesystem order, so no iteration order leaks into a published page.

One thing is unexercised rather than proven: `content_hash({"v": -0.0})` differs from
`content_hash({"v": 0.0})`, so a solver sign flip on a zero could in principle move a digest. No
committed certificate contains `-0.0`.

### A claim I made that was not true

The round-four commit said its regression tests were "verified red against a reverted package". For
one of the three — the test covering the hostile stochastic artifacts — that was false, and the
re-audit caught it. All three fixtures declared their rate constant at model scope, so the
mass-action reader refused them *before* any of the three guards under test was reached, and
`pytest.raises(ValueError, match=r".+")` accepted that refusal as proof. The test passed against a
package with every one of the fixes reverted. The numbers quoted in its docstring — 500 molecules
under libRoadRunner against 100 — could not have come from those files, because the reverted code
never ingested them at all.

I ran the revert check per-test in earlier rounds and batched it in that one, then wrote the
stronger sentence anyway. The fixtures now put the rate constant inside the kinetic law so each
file reaches the guard it is for, and each case asserts the specific refusal rather than any
`ValueError`; verified red against the reverted package, one test at a time. A guard is worth what
its measurement is worth, and so is a claim about a test.

Three more of that round's fixes were defective in the same pass:

- **The shadow guard saw only kinetic laws.** Everything else that reads a global — a rule, an
  initial assignment, an event trigger — reads global scope and cannot be shadowed by any
  reaction's local. So one reaction declaring a local `k` made a global `k` that a rate rule
  integrates look fully shadowed, and an override of it was refused under a message saying it has
  no effect on the run. Measured: 54.6x. That is the same defect the round before had just fixed at
  7.4x, one route over — the third time this one guard has been wrong.
- **The Level 2 twin of its own substance-units fix.** Level 2 has no model-level `substanceUnits`;
  its default is the predefined `substance` unit, which a model may redefine — and four of the six
  committed Level 2 kinetic models define it as scaled moles (1e-9, 1e-9, 1e-3, 1e-6). Reading only
  the species attribute returned nothing there, so a model whose amounts are nanomoles passed the
  guard that exists to catch amounts that are not counts. `ingest._resolve_unit` had learned exactly
  this Level 2 rule in the same commit; its neighbour had not.
- **Two flags turned to silence, and one true value to a false one.** Restoring rule-determined
  names to the comparison dictionaries — the fix for a *different* over-reporting defect — put
  their inert `value` attributes back into the comparison, so a dossier stating one agreed with it
  and the check fell silent precisely where it had just been taught to speak. And reading only the
  local values for a reused name published "model 9.0" for a model whose global is 5.0, the
  dossier's own number and the live value in another reaction: a mismatch naming a value the model
  does not hold. There are three cases here, not two — present with a comparable value, present
  with none because a rule computes it, and absent — and collapsing the middle one into either
  neighbour is what produced both defects.

### Breaking the invariants on purpose

Thirty mutations against a frozen copy, full suite each time, with a no-op control to calibrate:
appending a comment to a pinned module turns two `test_pins` cases red on its own, so "773 passed,
2 failed, both test_pins" is the signature of an *unguarded* invariant, not a caught one.

That control is understated, and a later claims audit measured the correction: for `oracle.py`,
`certificate.py` and `logical.py` the no-op signature is **three** failures, not two — the logical
worked example's byte-for-byte rebuild embeds a pin spanning all three, so it fires on a comment
too. Those happen to be the modules carrying most of the mutations below, which means a mutation
caught *only* by that rebuild would read as a behavioural catch under the two-failure signature. It
is worth stating plainly that this weakens the exercise's precision, not just its arithmetic.

Most of what this project claims held. `derive_overall`'s three downgrade routes, the scope
statement at construction and on load, `certificate_from_content` re-deriving the overall verdict
rather than trusting it, all four `require_*` guards, the blindness rules on both the entry and the
query surface, `verdict_for`'s bands, the non-finite abstention, the curve worst-point term, the
`_reference_scale` repair that was explicitly rejected, `load_bearing` in all five modules that mint
assumptions, and tampering with a committed certificate's discrepancy, protocol or tolerance — every
one was caught by a behavioural test. So was inflating the PK/PD agreement report, by the registry's
byte-for-byte rebuild.

Two were not, and both were tests of mine that asserted the wrong thing:

- **The spatial abstention could be deleted.** Replacing the `except UnstableDiscretization` branch
  with "judge the initial profile" left the suite green apart from the pin control. A grid at
  α = 20, against an explicit scheme's limit of 0.5, then published `reproduced` — the "a simulation
  that never happened reads as a perfect reproduction" failure the module names as its own. The test
  guarding it had the right comment above the right call and asserted only that nothing raised.
- **A source-text test let a fixed defect return.** The stochastic root-cause test read
  `inspect.getsource` and checked for two substrings. Comments are source, so restoring the defect
  while leaving the original line in place as a comment satisfied it — and satisfied the loop note
  citing that same line. A previous round's agent had already flagged this test as pinning the
  letter rather than the behaviour, and I did not act on it; that is the second time in this session
  I was told something about my own test hygiene and left it.

Both now assert the published verdict and root cause. And the citation check no longer matches
commented-out code: a note citing source has to find the words in code that runs, since a line that
no longer executes is not the evidence the note claims to rest on.

One thing survived that is not an escape but is the familiar shape. Widening the scalar tolerance
from 5%/15% to 20%/35% fails thirteen tests — ten of them behavioural, the other three being the
pin-and-rebuild control that a bare comment also trips, a distinction the original claim of
"thirteen behavioural catches" did not draw — but the *written record*
does not notice, because the notes for the two defaults every committed certificate actually uses
cite `oracle.py` as a bare path with no quotes, while the other four quote their exact `Tolerance(…)`
lines. The record could have stated 5% over code saying 20%. The rule reached four cases and not the
two that mattered most; both now quote their source.

## What the surfaces told the person being judged

Round six read the outputs aimed at the *author* — the gap report, the fix list, the dossier, the
blocked status — as the modeller whose paper had just been assessed, and used the package as a
third-party library consumer would. Both found things the code audits could not.

**Six of the thirty certificates told an author to fix something no paper could fix.** The spatial
engine implements exactly one boundary condition and the stochastic class judges an ensemble it
sampled itself; both assumptions are Reprolith's limits, not omissions in anyone's paper. The
fix list said *"state the value this claim rests on so it need not be assumed"* anyway — and the
one sentence that explains why the item is unclosable, the assumption's `basis`, was printed by the
sibling `gaps` report and dropped by the surface whose entire purpose is to be acted on. Assumptions
now record whether an author can close them, and an item they cannot says so.

**The spatial certificate asserted a fact about the author's paper that nothing checked.** It read
"evolved under a boundary condition Reprolith imposes, *not one the paper stated*". This front-end
takes claims rather than a dossier and never learns what was stated — its own docstring says it
"cannot see" the dossier's boundary gap — and for the three committed entries there is no paper at
all. It now says what is true: this engine implements one boundary, and Reprolith did not check
what the source specifies.

**Thirty blocked papers were told their model file had been examined.** The reason read "no
machine-checkable claims extracted from the shipped model artifact", naming a source and an
operation that never happened: nothing is fetched and nothing is opened on that path. An entry is
blocked because Reprolith holds no extracted claims for the paper, and the recorded `ingesting`
step — required by the lifecycle, not evidence of ingestion — corroborated the false account. The
reason now says what happened, who owns the missing input, and how to supply it, and the lifecycle
step says it is a lifecycle step.

**And a real, author-fixable gap never reached the author.** The metformin dossier records that 45
of 69 extracted values state no unit — load-bearing, and the only one of its six gaps the artifact
does *not* carry. The constraint-based class routes its dossier's load-bearing gaps into the
certificate; the PK/PD path never consulted a dossier, so the fix list told that author there were
two things to fix where Reprolith's own records held three. The rule reached one class and not its
neighbour, again.

### Using it as a library

Reading `__all__` and trying to build something with it found the surface incomplete in a way no
internal test could: **an exported `certify_logical` refused every pin the exported names could
construct.** Four of the six classes keep their `solver_pin` in a module the package `__init__`
does not re-export, and the guard's own error message names `solver_pin_for(nodes=...)` — also
unreachable. The only route through the public API was to hand-write the magic algorithm substring
into an `EnginePin`, which the guard accepts. `undetermined_shortfall` was unreachable the same way,
so a consumer whose claim did not reproduce could not supply the escape hatch the package itself
uses. All are exported now, and a test builds a logical certificate from exported names only.

Three smaller ones, each the same shape as findings the engine audits kept producing:
`default_tolerance` raised a bare `KeyError` for three of the six comparison methods, where its own
sibling `require_documented_default` holds an exact comparison to 0/0 and says so; `list_catalog`'s
filters were annotated `object` and compared with `is`, so passing the string `"logical"` — which
compares *equal* to `ModelClass.LOGICAL` — returned an empty list rather than an error, a read
surface answering "there are none" to a question it did not understand; and one missing extra
raised two different exception types.

The sharpest of the three is an honesty escape rather than an ergonomic one. `advance_to_outcome`
was widened to record every missing input and `blocked_certificate` was not, so passing a sequence
to both put a *list* inside `Certificate.gap_report` — declared `tuple[str, ...]` — and it
serialized, digested, reloaded through `certificate_from_content` and rendered, with nothing on the
honesty path refusing it. An annotation is not a check, least of all at a boundary that mints
certificates.

### A fix that did not achieve its purpose

Re-auditing the previous round found four more, and the first is the sharpest kind: a repair that
looked right, passed, and did not do the thing it was for.

- **The curve tolerance's loop note still did not redden when the tolerance was widened.** The
  previous round gave the two load-bearing tolerance notes quoted citations, and the commit said
  "both now quote". They did — but the curve note was split into two quotes and the second,
  `"0.10, 0.25, ToleranceSource.CLASS_DEFAULT"`, is *not unique*: it also matches
  `_ESTIMATION_DEFAULT`. Widen the curve default and the note stays satisfied by a line it does not
  cite. Measured: scalar and band mutations redden the note gate, the curve one does not. Both notes
  now quote the whole three-line block, which occurs exactly once. Quoting is not enough; the quote
  has to be unique.
- **The new provenance gate exempted three of the six kinetic certificates.** It sniffed the
  rendered citation for `doi:` or `et al.`, and three entries cite their paper by author-year model
  name — "Tyson1991 - Cell Cycle 6 var". They were never checked, and because they were never
  *counted*, the `>= 19` floor could not notice: their attribution could be stripped with the whole
  suite green, which is exactly the defect the gate was added to prevent. It is driven from the
  datasets that record `reference_tool` now, and asserts an exact count rather than a floor — a
  floor cannot see an entry it never counted.
- **The Level 2 rule was not, in fact, taught to the neighbour whose docstring claimed it.** The
  stochastic ingester learned that Level 2 defaults a species to the predefined `substance` unit,
  and its docstring said "`_resolve_unit` learned this same rule one module over; this is its
  neighbour." It had not: the call site applied only Level 3's model-level fallback, so on Level 2
  every species' unit was recorded as unstated. Measured on the committed corpus, that published a
  *load-bearing* gap reading "8 of 8 extracted values state no unit in the artifact" about a model
  that defines `substance` as nanomole — and pushed a fully specified model's difficulty to high,
  which is verbatim the Level 3 defect recorded as fixed a few lines above it. Four of the six
  committed Level 2 kinetic models were affected. Two of them now report no units gap at all, and
  two drop from `high` difficulty to `low` — BIOMD0000000010 and BIOMD0000000051, both of which
  define `substance` as scaled moles. (Recorded as one until it was counted; three more improve
  without clearing.)
- And the initial-condition branch still said "not present in the model" for a parameter that is
  present and rule-determined — the three-case split the parameter branch had just been given,
  missing from its twin ten lines below.

## Does the answer change with scale?

Every previous round tested the committed corpus or a small constructed model. This one pushed the
solvers until something broke. **Nothing did** — no surviving honesty finding — and since a clean
result is only worth its numbers, here they are.

**The finite-difference solver converges cleanly and roundoff is not a factor.** A Gaussian on
`x ∈ [-10, 10]`, D = 1, judged against the analytic `σ² = σ₀² + 2Dt` at fixed α = 0.4, with the same
FTCS update re-run in exact rational arithmetic to separate truncation from floating point:

| grid | dx | steps | RMSE/span | worst/span | float vs exact rational |
|---|---|---|---|---|---|
| 51 | 0.400 | 31 | 1.708e-03 | 4.525e-03 | 1.55e-16 |
| 101 | 0.200 | 125 | 4.247e-04 | 1.121e-03 | 1.56e-16 |
| 401 | 0.050 | 2000 | 2.736e-05 | 7.001e-05 | — |
| 801 | 0.025 | 8000 | 9.542e-06 | 4.304e-05 | — |

Clean second-order convergence, accumulation at 1.5e-16, and the coarsest grid measured is still 58x
inside the pass threshold. The committed certificates sit in this regime and publish their grid.

**The LP matches COBRApy at genome scale**, objective and parsimonious total flux alike — relative
error 1.3e-16 on *E. coli* core rising to 2.9e-11 on iAF1260's 2,382 reactions. Summation order,
which the brief asked about specifically, is immaterial everywhere measured: the largest
`sum`-versus-`fsum` gap anywhere was 5.7e-13, and 7.1e-15 for the AUC trapezoid at 48,000 samples,
against tolerances of 1e-6 and 0.10.

**A published verdict does not move with sample count.** The one committed PK reproduction, varying
only `steps`: 24 samples gives a relative error of 0.0223 and 48,000 gives 0.0215, across a
2,000-fold change, against a 0.10 threshold. The committed choice is fully converged, and the
protocol publishes it anyway.

**The SAT path is correct at 44–60 nodes** — 16, 12 and 71 fixed points, matching a sympy-derived
reference independent of z3, with every solution re-checked definitionally before it is kept. And
the SSA is unbiased: immigration-death bias falls 0.500 → 0.128 → 0.018 from 100 to 10,000
trajectories, always under two standard errors.

### What the scale run did change

One measured claim was false. The comment on `_FVA_OPTIMUM_TOLERANCE` said the constant keeps a
rescued flux "within the FROG cross-validation tolerance (1e-6)". Reprolith-versus-COBRApy interval
agreement degrades with model size — 2.97e-12 on *E. coli* core, 2.55e-08 on iIT341, **1.85e-03** on
iAF1260 — which is three orders of magnitude *above* the constant, not below it. That is LP
conditioning rather than this slack, and it makes no verdict wrong: a wider interval reads as
un-pinned and abstains, the conservative direction. But the number was not a bound on how closely
two solvers agree, and the comment said it was.

The same run showed that slightly *inverted* intervals — `hi` below `lo` by about 1e-11 — are
routine at scale, 86 of 200 sampled reactions on iIT341. `judge_flux` already treats them as pinned,
because a negative width satisfies any positive slack, which is right: two bounds solved to
different roundoff is a pinned flux, not a contradiction. Nothing said so, and absorbing a case
silently looks exactly like absorbing it deliberately.

### Named as unmeasured, not clean

The agent was stopped while still working and reported honestly on what it had not reached, which is
recorded here so a later session does not read this section as coverage it is not: the pinned-verdict
comparison against COBRApy was cut off before iJO1366, so whether the iAF1260 divergence is a trend
or a one-off is unknown; SSA ensembles above 10,000 trajectories and single trajectories of
10⁵–10⁷ events were not run; shadow prices at genome scale were scripted but never executed; and
the 2-D and reaction-diffusion solvers were not scaled at all — they are library-only today, with
all three committed spatial certificates using the 1-D diffusion path.

One thing worth knowing rather than fixing: exhaustive logical enumeration grows six- to eightfold
per two nodes, so the declared 20-node ceiling costs on the order of tens of minutes. It completes
and it is bounded; it is simply not free.

## What the proposal said it would build

The capability specs were read against the code two rounds ago. The *change* that drove the whole
build — its proposal, its design rationale, its thirty-six tasks — had never been. Two survivors,
and both are claims about scope rather than defects in a computation.

**The design's output-format decision was not taken.** "Stand on the standards ecosystem" listed
"Simulation recipe: SED-ML; bundle: OMEX / COMBINE archive" among the things the contract requires
outputs to validate against. Nothing emits either: there is no SED-ML writer and no archive writer
anywhere in the package — `sedml.py` is a parser, and `grep` for `omex` or `zipfile` across
`python/`, `scripts/` and `tests/` returns nothing. A published bundle is a Reprolith JSON record
that *references* a model file by path, and `ReconstructionBundle.validate()` checks presence and
duplicate ids, never a schema.

That would be a documentation tidy-up if it stayed inside the design document. It did not:
`docs/outreach-shortlist.md` — an outward-facing deliverable — tells COMBINE that the OMEX archive
is "the exact standards Reprolith's bundles target", and offers SED-ML and OMEX maintainers
"concrete recipe/archive validation failures found during reconstruction". Reconstruction produces
no archives and validates no recipes. Approaching a standards body with a conformance claim nothing
in the repository supports is the same failure as a certificate citing a paper for a number the
paper does not contain, aimed at people whose whole business is conformance.

All three now say what is true: the design lists archive emission under what is *not* built, the
outreach rows offer intake experience rather than conformance, and the README's "ships in open
formats" says which format and which container.

**And a flag that asserts a measurement.** Both milestone scripts wrote `validates=True` as a
literal into the model artifact — and `validate_constraint_based` then *checks* that flag as
evidence the adopted model validates, while `estimate_difficulty` reads it as "a runnable model
shipped". The value happens to be correct for every committed model, verified against libSBML. But
it was never measured, and the sharpest evidence that this is out of line with the project's own
standard sits eight lines below it in the same constructor, where the author refused to do exactly
this for the sibling field: *"Left unchecked, and recorded as unchecked… would publish a vacuous
agreement as though something had been verified."* Both scripts compute it now, the way ingestion
always has.

The rest of the change checked out, including the parts most likely to be flattering: the three
unbuilt tasks really are unbuilt and nothing else is quietly half-done; the blind-verdict path
provably cannot read a ground-truth label; the scope statement refuses both an empty and a reworded
value; and a tolerance labelled `class-default` is refused if its width is not one. The proposal's
"deferred, not forgotten" list is stale in the harmless direction — six of the things it defers have
since been built — and is left standing with a note, because a proposal is a record of what was
proposed.

## Auditing the claims, not the code

Nine commits landed in one day, each asserting what was wrong, what was measured, and what was
fixed. Two of those assertions had already been caught and self-reported — a "verified red against a
reverted package" that was not, and three comments claiming a parity the code lacked. So an agent was
pointed at the record itself: re-derive every number, and actually perform every claimed revert.

**The "verified red" claim held.** For the two commits examined in depth, all twenty named tests were
reverted one at a time — the fixed module swapped for its parent's version, that single test run
against the reverted package — and every one went red, 10 of 10 and 10 of 10, each with a distinct
and appropriate failure. That is the claim that had failed once before, and it is worth recording
that it was true here rather than only recording the time it was not.

Most of the numbers held too, and to more precision than they were written with. The 87 of 200 seeds
reproduced to the seed, along with the 27 at two trajectories. The 9 / 2 / 0 measurements behind the
three-standard-error threshold reproduced exactly, including that four buys no further improvement.
The 71 standard errors, the 1.87x denominator growth, the 0.534 and the geometric midpoint of 0.103,
the 135 local parameters, the 34 resolved units, the one-grid-step overstatement — all confirmed.

**Two were false, and both were mine.**

A comment in a regression test said the old normalizer "scored this 0.4208 and failed it". Re-derived
against the parent revision, it scored **0.5000** — RMSE and worst point are both exactly 0.5 on a
plateau alternating half a pixel about 100, over a span of exactly 1.0. No denominator available in
that fixture produces 0.4208; it appears to be left over from an earlier draft of the data. The
number understates rather than flatters — both values fail — which makes it a false measurement
rather than a flattering one, and no less false for that.

And this note itself claimed the committed spatial curves have span over level of "3.67, 2.83 and
4.42". Recomputing them from the milestone's own configuration gives **3.89, 4.24 and 3.48**. No
permutation matches, and no plausible variant — initial profiles, simulated profiles, max over mean,
the pre-tightening diffusion number — produces the claimed triple. The sentence was supporting an
argument that a later round then judged worthless on other grounds, so nothing rested on it; it was
simply wrong, sitting in the document that exists to be the honest record.

Both are corrected in place. The pattern they share with the earlier two is worth naming: every one
was a number or a parity asserted in prose, next to code that was itself correct. The code got
measured; the sentence about the code did not. A claim in a commit message or a comment is exactly
as checkable as a claim in a certificate, and this project already knows what to do about an
unchecked claim — it just had not been applying it to its own record.

Two smaller inaccuracies, both understating: "nine regression tests" was ten, and "seven" was eight.

## Re-running fifty defects, and the gate that skipped the file it was built for

Six rewrites of the same handful of functions in one day is exactly the churn where an early fix
quietly disappears, so every defect fixed today was re-run against HEAD. Almost all held: the
truncated-run refusal, the queue that froze, the badge over a gap report, the resolvability guard,
the blank catalog, the atomic writes, the exported pins, the six tolerance defaults, the twelve
`default_tolerance` combinations, and all six agreement reports recomputed from their own per-entry
rows. Three did not, and two of those contradict something I wrote.

**The badge fix reached one branch of two.** The commit said "it now only ever downgrades", and that
is true of the gap branch it changed — three lines above it, the estimation branch does the identical
unconditional repaint. So a *failed* estimation claim rendered amber instead of red, and an
*abstained* one amber instead of grey: for any estimation-level certificate, red and grey were
unreachable. The spec asks that an estimation result never be green and never read as a clean pass.
That is a cap. It does not authorize promoting a failure, and the abstention path that reaches it is
one an earlier round deliberately created. It is a cap now.

**The render freshness gate skipped the render it was written for.** Two independent holes. Its
byte-for-byte check ran only `if sibling.exists()` — and the three worked-example renders have no
sibling JSON, including the metformin certificate that produced the original finding and that the
README sends readers to. Hand-editing its overall verdict from `partially-reproduced` to
`reproduced` left the entire suite green. And the gate enumerated its population as "every `.txt`
containing `Engine pin:`", so deleting that line removed the file from the gate altogether: verdict
edited, pin line gone, suite green. **The population a check runs over must not be defined by the
thing the check is looking for.** Renders are enumerated by location now, a missing pin line is a
failure rather than an exemption, and the two worked examples are byte-checked against the
certificates `scripts/render_worked_examples.py` already knows they come from.

That is the third claim of mine this session that an audit had to correct, and the most pointed,
because the gate exists precisely to stop a published render from drifting from its certificate.
Writing the check was not the same as checking that the check ran.

**Two real fixes had nothing pinning them.** Reverting the missing-agreement-report refusal to a
`continue` left the suite green; so did truncating a blocked entry's missing inputs to the first of
several. Both are pinned now. And the lesson recorded last round — *a quote is evidence only if it
is unique* — was a sentence in a document, which does not fail a build; `Citation.unmet` now refuses
a source quote that matches more than one line, with prose files exempt.

One more, smaller: `build_certificate` still accepted a non-string into `gap_report`. The previous
round fixed that at `blocked_certificate`, one caller, and named the lesson "an annotation is not a
check at a boundary that mints certificates" — while leaving it unchecked at the boundary that
actually mints them, and on the load path the same commit chose to defend for `attributed_to`. A
list of `Gap` objects passed straight through, serialized, digested, reloaded and printed its `repr`
into the "what was missing" section as though it were a sentence about a paper. Both paths refuse
now.

### The claims audit, second pass

A second agent re-derived every number in today's commits from the code at each revision, and
rebuilt four trees to actually perform every "verified red against a reverted package" claim. It
also checked all eighty backticked `module.symbol` references added today against the package.

**The revert claims hold.** Ten of ten, eight of eight, four of four, and four of five — the single
green being exactly the one already self-reported and recorded above. Nothing new failed.

**Most numbers hold, several to more precision than they were written with.** The 45 of 69 unstated
metformin units, the 8 of 8 Level 2 gap, the 119 shadowed ids, the 87 and 27 seeds, the 71 and 66
standard errors, the six span-over-level ratios and the 0.103 midpoint, the 14.6 / 2.8 / 0.8 / 0.0
zero-variance measurements, the 2.968e-12 FVA agreement on *E. coli* core, the 1.3e11 unit
inversion, the 2247 mL compartment and its 2199% consequence, the Li et al. basins summing to 2048,
the four Level 2 models defining `substance` as scaled moles, the three comparison methods that
raised, the twenty tool-computed references, the six unclosable assumptions — all re-derived.

**Three more of mine were wrong, and one is sharper than I wrote it.**

I recorded that "five of the six committed kinetic models are Level 2". **All six are.** The
Level 3 accessor therefore saw *none* of their 224 local parameters — the 10 it did see belong to
the metformin model, which this repository classes `ode-pkpd`, not `kinetic`. I had reached "five
of six" by counting the PK/PD model among the kinetic ones to make the arithmetic come out. The
correct statement is worse for the old code and better as a description: the guard was blind to the
entire kinetic corpus.

A parity comment cited **`ingest._read_species`, a function that has never existed**. The parity it
asserts is real and the neighbouring citation on the line above resolves, which is precisely why
this one reads as checkable. It is the only dangling symbol reference among the eighty added today,
and it survives as a finding only because two commits ago this project decided that a citation a
reader cannot follow is not evidence.

And "one drops from high to low" was two — BIOMD0000000010 and BIOMD0000000051, with three more
improving without clearing. Understating, which is the harmless direction, and still not what the
measurement says.

**What was not checked, so that it is not read as verified:** the genome-scale FVA figures
(2.55e-08 and 1.85e-03) and the 86-of-200 inverted-interval count were not re-derived; nor were most
of the convergence, summation and sample-count numbers from the scale audit beyond the SSA line;
nor the byte-for-byte reproducibility run; nor the two override magnitudes, 54.6x and 7.4x, whose
surrounding structural claims did check out.

## Status and what remains

The engine, the blind run over the 31-entry set (7.1), the agreement report (7.2), the milestone
artifact (8.1), this note (8.2), and the discipline-loop record (7.3, 7.4) are all done and
committed. What remains is what finding 2 names: a scaled way to extract each paper's targetable
claims (tasks 2.1-2.3). Thirty of the thirty-one entries abstained for want of exactly that, so
verdict *accuracy* across the set is still unestablished — the metformin example shows only that,
given a claim, the rest of the pipeline delivers an honest, root-caused verdict.
