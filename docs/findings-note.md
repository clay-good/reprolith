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

   Measured on Reprolith's own flagship example, the gap between the two halves is wide. The
   metformin PBPK model ships a SED-ML document beside it, and that document declares **81 plotted
   curves** across three figures — every compartment's amount, every concentration, every reaction
   flux. The published certificate checks **two** of the paper's claims, the two plasma Cmax values
   its table reports. Nothing is wrong with the certificate; the 81 are curves whose *values* the
   paper shows only as figures. But it puts a number on the shape of the problem: the artifact-declared
   half of claim extraction now scales to 81 targets in a file Reprolith already shipped, and the
   values half scales to 2.

   There is one route by which a document can close the values half itself, and it is now read: a
   `dataDescription` names a data file the archive ships, and a curve plotted from it is the
   paper's own recorded points rather than a result the model must regenerate. Those values are
   read out of the archive and travel with that curve (`read_sedml_data`). It changes nothing for
   the two documents in this corpus — neither uses one — and it is worth being exact about what it
   would change if one did: it supplies the *measured* series a figure shows, not the paper's
   claim about the model, and SED-ML does not say that the data curve is the reference for the
   simulated curve beside it. Reprolith does not infer that pairing. So the wall moves for a
   document that ships its data, and only as far as the document itself goes.

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
  lookup, so it is **disclosed rather than judged**: when an event assignment targets a parameter a
  claim overrides, the certificate's protocol says so and says that whether the event fires within
  the window was not evaluated. That is exactly what is known, and it replaces a silence in which
  the certificate published the override and said nothing about the event that might replace it.
  It fires on no committed certificate — the metformin model has two events and neither assigns to
  the dose parameter its 1000 mg claim overrides — so it is a guard for the next model, verified
  against a constructed one.
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
metformin units (13 of 37 since initial assignments stopped being read as quoted parameters —
see below), the 8 of 8 Level 2 gap, the 119 shadowed ids, the 87 and 27 seeds, the 71 and 66
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

## Four capabilities, and what auditing each one's first version found

A round of building rather than a round of auditing: the OMEX writer, the population simulator,
the re-fitting engine, and the archive check all landed here. Each was re-audited immediately, and
each first version had a real defect. Recorded because the pattern is the useful part — **every one
was found by using the thing as its consumer, not by re-reading the code.**

### The fit that returned the caller's own guess

Nelder-Mead does not diverge on a flat landscape. It shrinks its simplex until the convergence test
passes and hands back the point it started from, reporting `converged in N iterations` over a
residual that never improved. Estimating a parameter the trajectory does not read did exactly that:
the caller's starting guess came back as a *recovered estimate*, carrying a protocol saying a fit
produced it, ready for a certificate to publish. An objective that does not move when the
parameters do is now refused before the first iteration.

This is the estimation path's own worst case — a re-fit that never happened, reported as one — and
it was inside the module written to prevent it. Found by writing a test that fit a parameter
nothing reads, expecting an error and getting a number.

### The report that told an author to fix a correct file

The archive check's first output listed metformin's 35 reactions and its events under *fix before
you submit*, with the fix `state this in the archive`. The archive states both perfectly well;
Reprolith's dossier cannot represent them. The same gap shape covers that and a genuine omission —
45 of that model's 69 values stated no unit at the time, 13 of 37 now — and nothing in the shape
distinguishes them, so the
report now puts all of them in their own section, never as a fix, and lets none of them decide
readiness. Telling an author to repair a correct file is worse than saying nothing.

The same output printed the certificate scope statement, whose first words are *This certificate
attests*, above a check that runs no model and issues no certificate.

Both were found by running the new command on the repository's own published archive and reading
the result as the author being judged. Neither is visible in the code.

### The document that read here and nowhere else

The exported SED-ML declared L1V3 over a `numberOfSteps` attribute. L1V3 spells that
`numberOfPoints`; `numberOfSteps` arrives in L1V4. Reprolith's own parser reads `numberOfSteps`, so
the document round-tripped perfectly here and failed schema validation everywhere else, with its
sampling invisible to a strict reader. Found by installing libSEDML — an independent implementation
— and asking it to read the output. It rejected it; it reads the corrected document with zero
errors.

The lesson generalizes past SED-ML: **a writer validated only by its own reader is not validated.**

### Two more, both about names

An exported archive whose experiment sat in one directory and whose model sat in another named the
model by where the archive stored it, not by where a reader resolves it from — so the document
pointed at a file that was not there. Caught by a check added in the same change, on that change's
own first test.

And zip member names were normalized with `lstrip("./")`, which takes a character *set*: a member
named `.hidden.xml` lost its leading dot and matched nothing. The OMEX reader's own normalizer
strips a path prefix and had been correct all along, three files away.

## A published number that moved a decade between two runs

Extending cross-engine corroboration to the PK/PD class surfaced a defect in the mechanism that
was supposed to make corroboration numbers reproducible. `EngineCorroboration.distance_bound`
publishes the distance rounded *up* to the next decade, precisely because the raw distance between
two agreeing engines is a difference of nearly-equal numbers whose leading digits are engine noise.

That was not coarse enough for a distance sitting on a boundary. Metformin measures 1.11e-07 in
isolation and a little under 1e-07 inside a longer run, so **three runs of one milestone script on
one machine published 1e-06 twice and 1e-07 once** — the exact failure the decade rounding exists
to prevent, one boundary over. The kinetic class was checked the same way and is stable across
three runs, so this is a near-boundary effect, not a general one.

The fix lifts the distance by a factor of two before rounding up, so a value that close to a
boundary lands on the same side of it in every observation. It is one-directional by construction:
the margin is greater than one, so the published bound can only ever loosen, and it still never
states better agreement than was measured. The cost is at most one decade — one committed kinetic
bound moved from 1e-05 to 1e-04 — against a criterion three to five orders away. Every verdict is
unchanged.

The general lesson is the one the repository keeps relearning: a mitigation verified on the cases
that motivated it is not verified at its boundary, and the boundary is where the next case sits.

## Two files that agree with each other, and with nothing the paper says

The last piece of the SED-ML fast-path was the one it had been deferring: an archive's experiment
and its model can agree perfectly and still describe a run that produces no result the paper
reports. Nothing in the archive can notice, because the manuscript is not in it.

The case is the repository's own flagship. The metformin PBPK model's shipped document scans the
dose over 389.2, 778.4 and 1167.6 mg. The paper's 1000 mg result is 779.9 mg of free base in the
model's units. Every file validates, the run completes, and a reproducer adopting the document
verbatim lands a few percent away from the published number with nothing to suggest they ran a
different arm. `manuscript_mismatches` reports exactly that one line on those files and nothing
else — the 500 mg claim is silent, because the archive does run it, and Reprolith's own exported
archive passes the same check because it carries the dose as a `changeAttribute`.

What it will not compare is the more interesting half. Not the run window: a claim states hours
and a uniform time course states a unitless number, and reading `outputEndTime="30"` as thirty
hours makes every archive in existence a mismatch. Not a recorded quantity no claim covers: claim
extraction here is partial by construction, so that difference is more often a gap in Reprolith's
own reading than a defect in the archive. Not an id two model elements carry, and not a parameter
the model's own math determines. **Failing to read a document is not evidence that it disagrees**,
and a false accusation against a correct archive costs more than a missed one.

### Three defects in the same day's work, all one shape

Re-auditing the diff within the hour found three, and they rhyme: each was **a number or an
annotation standing in for a check** — which is what the capability itself was built to catch, one
level up.

The value check read a parameter's `value` attribute as what the model runs at. SBML makes that
attribute inert for a parameter an assignment rule or an initial assignment sets, and this very
model carries thirty-two initial assignments. Two harms, and the second is the bad one: a detail
line naming a number nothing uses, and a *real* mismatch silenced whenever the inert value happens
to equal the claim's.

The data-description reader handed a generator that reads both a data source and the model — a
trace normalized by its own data — the raw column as its reference values. Those are not the values
of the ratio anyone plotted.

And the author-facing report counted the claims it was *handed* as "checked against this
experiment". An archive with no experiment compares nothing, however many results an author
supplies. A count that says otherwise is precisely the defect the other two are.

### The advice about a run nobody performs

Then the same check was pointed at a class it was not written for: a real constraint-based archive,
`e_coli_core`. It said *ship a SED-ML document whose plots are the curves your paper shows*. An
fbc model is solved at steady state; there are no curves. The same held for a logical model, which
advances in discrete update steps. The writer had refused to emit a time course for these models
for months; the reader was judging them as if they were one, and telling an author whose files may
be perfect to repair them.

Those findings are now withheld and named rather than issued, and such an archive is never reported
ready — "ready" would claim a reproducer knows what to check, and the questions were withheld, not
answered.

The method is worth more than the fix: **run the tool on a real file from a class it was not
written for.** The previous round's lesson was to read the finished artifact as its reader; this
one is to hand it an input its author never pictured. Both find things no amount of re-reading the
code does.

### The same inert attribute, in three places

The ingester's own comment tells this story about assignment rules: SBML makes a parameter's
`value` inert once a rule computes it, models ship whatever number was there, and recording it made
the dossier "assert a number the model never holds". That rule reached `ingest_sbml`,
`build_model_sbml`, and the override guard. It did not reach **initial assignments**, which do the
same thing to the same attribute — and the gap turned up in three separate modules on one day.

`manuscript_mismatches` read a claim's parameter off it (fixed the hour it shipped).
`ingest_spatial_sbml` read a species' starting concentration off it, reporting 1.0 for a model that
assigns 42. And `compare_sbml_to_dossier` compared against it: measured on the metformin model, **32
of the dossier's values — every compartment volume — were compared against numbers the model
computes over**, and the comparison reported no disagreement. That is the function's own stated
definition of the defect it exists to prevent, one construct to the left. It now reports each of
them as having no stated value to compare, naming which construct determines it.

Having found it three times by tripping over it, the fourth was found by looking. Every reader in
the package that takes a number off an SBML attribute was checked against both constructs:

| Reader | State |
| --- | --- |
| `manuscript_mismatches`, `ingest_spatial_sbml`, `compare_sbml_to_dossier` | had the defect; fixed |
| `certify._apply_overrides` | already refused both — the surface that had learned it |
| `ingest_fbc_sbml`, `ingest_stochastic_sbml`, `ingest_qual_sbml` | refuse a model carrying either construct outright |
| `population._typical` | reads a parameter's value as the population median, and a rule-determined one is refused one call later by the override guard. No defect: a fix written for it was reverted, because a redundant check that changes an established message is a cost, not a repair |
| `ingest_sbml` | records initial-assignment values, with a gap saying it does. The limit below |

The two rows that are *not* defects are the reason to write this down: the next round should not
re-audit them.

One thing was deliberately **not** fixed at the time. `ingest_sbml` excluded assignment-rule
parameters from the dossier and still recorded initial-assignment ones, which is why those 32
values were in the metformin dossier at all. The consistent rule would drop them — and that moves
the dossier's content digest, the published gap counts, and the "45 of 69 extracted values state no
unit" figure that three documents and a test quote. It was a deliberate change with its own blast
radius, not a tail-end edit, so it was written down here with its number rather than done quietly.

**It is done now, and dropping was only half of it** — see "The value the dossier had no way to
carry" below.

## The check had one input, and nothing wrote it

`archive-check --claims` makes the one comparison nothing in an archive can make on itself: does
the shipped experiment run the result the *paper* reports? It is the check that catches the
metformin archive scanning 389.2, 778.4 and 1167.6 mg while the paper's 1000 mg claim is 779.9 mg
of free base — every file valid, the run completing, the number plausible.

It needs a claims file. Nothing in the repository wrote one. The guide showed the schema and left
the author with a blank editor, which is the shape of gap that makes a capability sit unused: the
expensive half was built and the cheap half decided who could reach it.

`claims-template` writes it from the files the author already has. One stub per curve the
document plots — a plot being the document's own statement that a curve is a shown result, the
same line `enumerate_sedml_claims` draws — each naming the model output it reads, beside the
outputs a claim can read and the parameters a claim can set. On the metformin document that is 81
stubs from 81 curves; the author deletes the ones the paper does not show.

**What it must never do is the whole design.** A template that filled in `reported` from the
model would hand the check the model's own output as the paper's claim, and the comparison would
pass by construction — which is precisely the failure the check exists to catch, moved one file
upstream. So `reported` and `source_location` come out blank on every stub of every input, and a
file still carrying those blanks is refused by the loader with each one named, rather than parsed
into a claim with no reference. That property is tested over all 81 stubs of the real document,
not only the synthetic two-species one, and deleting it fails three tests.

Three things are reported rather than guessed at, each for the same reason: a curve that is an
expression over several elements (a claim reads one output), a curve reading something no time
course records (the metformin document plots 35 reaction fluxes), and a curve plotting values the
document itself ships (the paper's own recorded points, not a result the model owes). Each leaves
the output blank and says why, so the blank is what the loader reports rather than an id that
resolves and then fails one step further from its explanation.

The recurring inert-attribute lesson reached this the first time rather than the fourth: a
parameter an `initialAssignment` or an `assignmentRule` determines is listed apart from the
settable ones, because an override aimed at one is refused when the claim runs. On the metformin
model that is 78 of the 94 parameters, and the dose a claim actually sets is in the other 16.

This is **not** manuscript extraction, and the surfaces say so where they could be misread. It
makes the author-supplied path cheap; reading a paper's numbers out of its prose is still what
finding 2 names, and still not built.

## The value the dossier had no way to carry

The last round left one defect written down rather than fixed: `ingest_sbml` dropped
assignment-rule parameters, because SBML makes their `value` inert, and still recorded
**initial**-assignment ones, which does the same thing to the same attribute. On the metformin
model that was **32 of the dossier's 48 parameters** — every compartment volume, each recorded as
a quoted number the model computes over.

The note said the consistent rule would drop them and named the blast radius. Dropping was the
wrong fix on its own, and that is the finding: an initial-assignment target is a real parameter of
the model, and a dossier that simply forgets it declares a model that cannot be rebuilt — the
equations referring to it have nothing to refer to. The assignment-rule case looked like a
precedent because those targets are *already* carried, as `assignment` equations. Initial
assignments had no such carrier, so "be consistent with the neighbour" quietly meant "delete
information the neighbour keeps".

So the carrier was built first. `EquationKind.INITIAL_ASSIGNMENT` is the third kind — `target =
expression`, at the start of the run and not recomputed after it, which is neither a rate nor an
assignment and rebuilds as a different model if it is emitted as either. `ingest_sbml` reads the
32 expressions; `build_model_sbml` emits them as `initialAssignment` elements and declares their
targets constant and value-less. Only then does dropping the inert value lose nothing.

The proof is a round trip, not an inspection. A one-species decay whose rate constant states 99
and is assigned `base * 2` = 1.0: SBML says the model runs 1.0, the dossier used to record 99, and
a model rebuilt from it decayed ninety-nine times too fast with every file valid. Ingested and
rebuilt, it now runs e⁻¹, matching the original under the same engine.

What moved, as predicted: the metformin dossier's parameters 48 → 16, its equations 63 → 95, its
gaps 6 → 5 (the "32 initialAssignments override initial values" gap is not a gap once the dossier
carries them), and the published units figure from **45 of 69 to 13 of 37** — the 32 that left were
alias parameters whose units were as inert as their values. Every certificate, render and the
registry were regenerated; `algorithm_revision` moved with `sbml`.

The method that would have caught this a round earlier is the one the last round already named and
applied only to readers: **sweep the defect shape across every surface, not every reader.** The
inert-attribute rule reached four readers in a day. It never reached the *writer*, and the writer
was the reason the fourth reader could not simply be made consistent.

### And the same construct again, two lines over

Sweeping the fix rather than tripping over it caught the half the first pass missed. An initial
assignment makes a *species'* `initialAmount` and a `parameter + rateRule` state variable's value
inert in exactly the way it makes a constant's inert, and the first pass excluded constants only.
A model whose species starts at 3 and whose rate-driven parameter starts at 2 produced a dossier
recording 7 and 99 — the same defect, on the values a certificate's initial conditions rest on.
Both are still state variables: they have an initial condition, in math, so `build_model_sbml`
emits them without an `initialAmount` and lets the assignment supply it. A state variable with
*neither* a stated value nor an assignment is still a gap, which is its own test, because a fix
that swallows the case it resembles is worse than the defect.

No committed artifact moved for it — no model in the corpus uses the construct — which is the
reason to write it down: it was found by sweeping, not by anything failing.

## The dynamics the dossier had no shape for

The remaining half of the same problem. `ingest_sbml` carried a rule-based model well and a
**reaction**-based one not at all: rules became equations, reactions became a load-bearing gap
whose own text said the state variables it had just listed had no law of motion. A model rebuilt
from such a dossier did not move. Kholodenko's ten-reaction MAPK cascade — the model the gap was
written about — was the case.

It was the largest thing intake read past, and it had no shape to be read into. An equation is
`target = expression`; a reaction is a stoichiometry *and* a rate law, and the ODE system is
derived from the two. So `DossierReaction` carries it in the form the artifact states it. Deriving
the ODEs instead would have been the tempting shortcut and the wrong one: the derivation makes
choices the artifact did not — concentration or amount, which compartment divides what — and a
dossier that makes them silently describes a model the paper never wrote.

**Carried only where a rebuild reproduces the model as itself**, and the gap now names the reason
when it does not, because "not carried" and "has none" are different facts:

| Refused | Why |
| --- | --- |
| more than one compartment | reconstruction puts every species in one; a second is lost |
| a compartment of size ≠ 1 | every concentration in every rate law comes out divided by a different volume |
| a function definition | a law calling one refers to something a rebuild does not declare |
| a reaction with no rate law | it states no dynamics; a reaction in the dossier that moves nothing |
| a law naming a boundary or constant species | intake skips those on purpose, so a rebuild has no such element |

That covers three of the six committed kinetic models and refuses the metformin PBPK model on its
21 compartments — which it already carried a gap about.

**The proof is a round trip, not an inspection**: ingest, rebuild, run both under the same engine,
compare every state variable. MAPK comes back at **7.5e-15** relative over a hundred time units.
The repressilator (twelve reactions *and* nine assignment rules) at 1.4e-9 at t=0.01, 1.2e-7 at
t=1, 1.1e-6 at t=50 — a residual that *grows with the run*, which is what integration error does
through two files of identical math and different element order, and what a changed rate law does
not. Both ends are asserted, so a real difference cannot hide inside a tolerance chosen for the
long run.

One guard has no case in the corpus and is tested anyway: SBML lets a kinetic law's own parameter
shadow a global of the same name, and hoisting one to the model changes which value the law reads.
A synthetic reaction with a local `k` of 2 under a global `k` of 1000 runs five hundred times too
fast if the distinction is lost, with every file still valid.

A reaction-free dossier's dictionary is unchanged — `reactions` and `compartments` are omitted when
empty — so nothing written before this moved its digest.

### Auditing it found three, and the third was the interesting one

**A check guarding the way in and not the way out.** Ingestion refuses to carry a multi-compartment
network; `build_model_sbml` emitted the first compartment and dropped the rest. The result runs,
validates, and is not the model the dossier describes — every species in the second compartment
silently relocated. A hand-authored or reviewer-corrected dossier reaches that path, and reviewer
correction is a supported route. Both conditions are now refused on the way out as well as in.

**A justification that stopped being true.** `compare_sbml_to_dossier` returns early for any model
with reactions, because — its own comment said — such a dossier already carries the `reaction
network` gap saying the dynamics are missing. A carried network has no such gap, so the reason no
longer covered it.

**And the trap in fixing that.** Simply removing the early return would have been worse than
leaving it. The sweep's `needed` set is built from the model's *rules*, and MAPK has none — so on
exactly the models the fix opened it up to, it would have reported "no disagreement" over a model
it never read: a floor that cannot see what it never counted, for the third time in this record.
`needed` now includes what each rate law reads and what each reaction's participants are, and the
test deletes a state variable from a carried dossier and requires the sweep to name it.

### Round three: two SBML constructs the refusal list did not name

Re-auditing the same code against the standard rather than against the corpus found two more, both
in the first version of the carry.

A species reference whose stoichiometry a **rule** computes has no stated number, and libSBML hands
back **NaN** for it — which went straight into the dossier as a recorded value. That is the
inert-attribute defect a fourth time, on a fourth element type. And a **`fast`** reaction is solved
as a pseudo-equilibrium constraint rather than integrated; the rebuild emitted an ordinary reaction
that ran, validated, and was a different model.

The first fix for the stoichiometry was wrong in a way worth recording: it asked
`isSetStoichiometry()`, which is "is the attribute present", and Level 2 defaults an omitted
stoichiometry to 1 while reporting the attribute unset — so it refused every Level 2 model in the
corpus, MAPK included. The question is *is there a number*, and it is `isfinite` on the value, plus
Level 2's `stoichiometryMath`. Neither construct appears in the corpus, so both refusals are
carried by synthetic models; the corpus is not the standard.

## The one number read from a paper, checked against the paper

Everything else in this corpus is checked against its generator. The FBA growth rates reproduce
under COBRApy, the kinetic curves under libRoadRunner, the attractors under CANA, the closed-form
results against the mathematics. Two numbers are the exception — metformin's plasma Cmax at 500 and
1000 mg — and they are the entire basis of the README's "one checks a reconstruction against
numbers read from a paper". Nothing had ever checked them against the paper.

**One of them is not in it.** The 500 mg value was recorded as **6.2 nmol/mL**, cited to Table 4.
The paper prints **6.1** — in Table 6, in Table 4's own `Fitted` row, and in the sentence of its
Results that gives both values in words. 6.2 appears nowhere in the article.

**And both cited the wrong place.** Table 4 is the comparison against *measured* data: 5.7 nmol/mL
at 500 mg (Zaharenko) and 12.9 at 1000 mg (Chung). The values the claims target — 6.1 and 11.2 —
are the paper's own **simulation**, which is Table 6. The 1000 mg claim's source read "Chung
dataset", naming the experiment whose number is 12.9 while carrying 11.2.

The distinction is not pedantic. Reproducing a paper's own model output is exactly what a
reproducibility certificate attests to; reproducing an *experiment* is not, and a certificate that
looks like it claims the second is claiming something it cannot support. The dataset's own
description now says which kind each value is, and gives both pairs so the difference is on the
record.

Neither correction changed a verdict — 6.1 and 6.2 are both inside a 5% tolerance on the same
simulated peak — which is the uncomfortable part. A wrong reference value that still passes is
invisible from inside the pipeline, and it stayed invisible through nineteen audit passes. The only
thing that finds it is going back to the source.

So the source is now committed. `datasets/manuscripts/` quotes the cited rows under the article's
CC BY 4.0, `scripts/fetch_manuscript_tables.py` regenerates them from Europe PMC's open-access full
text (the fetching is dev-only, the way `regenerate_*_references.py` is), and a test in the
dependency-free gate reads only the committed rows. It checks that each claim states the number the
paper prints, that each cites the table the number is in, and — so the first check cannot pass by
coincidence — that the *measured* values are a different pair and are not what is claimed.

The general lesson has a name in this record already, from the eighteenth pass: read the finished
artifact as its reader. This is the version of it that points outward. **A reference value with no
committed source is not evidence, whatever the certificate around it says.** Twenty-nine of the
thirty certificates had one and it was checked; the thirtieth, the one the front page leads with,
did not.

And a one-off test would only have fixed the one entry. `check_claim_values` and
`reprolith claims-check` ask the same question of any claims file against any quoted tables, so
entry thirty-two arrives with the check already built. It asks the weakest question that catches
this defect — *is the number you state printed in the table you cite* — and refuses the stronger
ones on purpose: which cell is the right one is the curator's judgment, and a value matched by
rounding would accept the number a paper *would have* printed rather than the one it did. A claim
citing a figure or a table nobody supplied is **not checked**, in its own list, and never fails the
command; folding that in with the failures would report an absence of evidence as evidence of
absence, which is the mistake the whole module is written to avoid.

## The half of a claims file that comes from the paper

Thirty of the thirty-one PK/PD entries abstain, all for one reason: nobody has said which of each
paper's results to target. Today's earlier work gave an author the *model* half of a claims file —
one stub per plotted curve, naming the output it reads, with the number blank. `claims-propose`
gives the *paper* half: every number a table prints on its own in a cell, with the row's own labels
and the column heading as its source location.

The evidence it works is that it rediscovers, from the tables alone, the two claims a human
extracted from this paper by hand — 6.1 and 11.2 nmol/mL, both with `metric: cmax`, both located
to "Table 6, Tissue Plasma, Dose, mg 500 / 1000, Cmax, nmol/mL column". That is a stronger source
location than the hand-written one it replaces, which said "Table 4, Zaharenko dataset" and was
wrong.

**What it refuses is the design.** It never names a model output: matching a table's "Plasma" to
`mPlasmaVenous` is a judgment, and a wrong match checks a real number against the wrong species —
worse than proposing nothing. It states a metric only where the column heading states one, because
a defaulted `cmax` is a claim about the paper the paper did not make; "Tmax, h" and "Cmax measured-
fitted, %" both come back blank. A cell reading "5.7 (2.1)" states two things and is not proposed.
And a table whose rows are not all the width of its header is skipped and named, rather than
aligned — which brings up the part worth recording.

### A row span is how a number ends up under the wrong heading

JATS writes a cell that spans rows once, on the row it starts. Read positionally, the rows beneath
it come back one cell short, and every value in them shifts a column to the left: the metformin
paper's Table 6 has a `Plasma` cell spanning three doses, so its 1000 mg row reads as though 76.1
were the dose and 11.2 the AUC. That is precisely how a reference value becomes a number the paper
prints *somewhere else* — the defect this morning's corpus fix was about, arriving by a different
route.

So the spans are resolved once, in `scripts/fetch_manuscript_tables.py`, and what is committed is
rectangular. A test asserts it, and the proposer refuses any table that is not — because the fix
belongs in the data, and a reader that quietly tolerates ragged input is a reader that will one day
align it wrongly.

The three commands now compose: `claims-template` from the model, `claims-propose` from the paper,
`claims-check` to confirm each surviving value is printed where it says it is. What still has no
tool is the join between the first two — which table row is which model output — and it is left to
the curator on purpose.

They did not compose on the first try, which is the audit finding. `claims-propose` writes its
records under `candidates` deliberately — a number a table prints is not yet a claim — and both
checks read `claims`, so a candidates file reached either of them as `cannot read the claims:
'claims'`, a bare `KeyError` repr. Both keys are read now, so an unedited candidates file is
refused for the reason that actually applies (**no model output named**) rather than for the key it
is stored under, and a file with neither key is told which keys were expected and which it has.

Reading one tool's output with the other is also a real cross-check, so it is a test: all 63
candidates the metformin tables produce come back confirmed by `check_claim_values`. A proposer
that mis-numbered a column, mis-read a cell, or dropped a thousands separator would emit a value
its own cited table does not print, and the two read those rows by different code paths.

### The survey that would have published a false measurement

Pointing the proposer at the rest of the test set was meant to be a survey: of the thirty-one
entries, how many papers are open access, and how many print a reproducible result in a table?
Twenty-four carry a PubMed id in BioModels' metadata, twelve resolve to open-access full text, and
a scan of every table in those eight papers came back reading: **parameter tables, study
overviews, and diagnostics — no reported model outputs.** That would have been a clean, quotable
number confirming the figure boundary this note already describes.

It was wrong, and the tool was wrong in the same way. One of those papers has a table headed
*"Pharmacokinetic parameters for three models"* whose body is exactly what a reproduction targets —
in vivo against three model variants, AUC and Tmax and Cmax down the side. The scan scored it zero
because every cell reads `10.2 ± 1.18`, and both the scan and `propose_claims` counted only cells
that are a bare number. A floor that cannot see what it never counted, for the fourth time in this
record, and this time it was about to be published as a fact about the literature rather than about
the code.

So the rule changed rather than the survey: a value with a stated spread is a candidate, the value
is the candidate and the spread travels beside it in `reported_spread`, and the source location
quotes the cell as printed. The `±` is unambiguous in a way parentheses are not — those may hold a
range, an interval, or an *n* — so `5.7 (2.1)` is still refused.

The same paper broke a second rule. Its quantities are down the *side* — a `Parameter` column
reading AUC, Cmax, Tmax — and label columns were being recognised by a vocabulary of headings,
which did not include "Parameter". So the row label that says what the number *is* was dropped
from every candidate's source location. A column is now a label if its heading says so **or if
none of its cells is a number**, because a vocabulary has to anticipate every word a paper might
use and a measurement does not. Measuring alone is not enough either: a `Dose, mg` column is
numeric and is still a condition. Both, or the tool is wrong in one direction or the other.

A metric is now read from a row label too, on the same rule as a heading: only where the wording
states one, only when the heading states none, and only when the row names exactly one.

**The first survey was not published, and that is the point.** It rested on a filter that could not
see a third of what it was counting, and its answer looked entirely plausible.

### And then it was made again, and the answer was worth having

Re-run through `propose_claims` itself rather than a second implementation of it, the measurement
stands and is now committed as `datasets/manuscripts/table_survey.json`:

| | |
| --- | --- |
| seeded PK/PD entries | 31 |
| naming a paper the repository can be followed to | 31 |
| resolving to open-access full text | 17 entries, **10 distinct papers** |
| whose tables include a **reported model output** | **3** |

The other seven papers are not short of numbers — their tables hold over a hundred candidates
between them — but every one is a parameter set, a study overview, or a diagnostic. Inputs and
metadata, not results. Their results are in figures.

So the figure boundary is now a number rather than an assertion: on this set, reading tables
reaches **three papers in ten** of the open-access subset. A table reader is worth having and does
not close the claim gap, and the next thing that would is not a better table reader.

One of the three is the paper this repository already has committed claims for, which is the
survey validating itself: pointed at the whole set with no special-casing, its own tooling reaches
the entry a human extracted by hand, and finds its results tables. The other two are new.

### The first version of that table was wrong, for a reason worth keeping

It said 24 of 31 named a paper, 12 were open access over 8 papers, and **one** printed a results
table. Every one of those numbers was an artifact of how the survey found a paper: it read the
model repository's cross-reference only when that reference was a **PubMed id**. Seven entries
cite their paper by **DOI** instead — and four of those seven are the metformin entries, whose
paper is open access, prints its results in five tables, and is the one entry in this repository
with committed claims.

So the first survey measured which identifier a curator happened to use, and reported it as a fact
about the literature. It also excluded, from a census of "which papers state reproducible results",
the single paper this project has already proven states them.

Both identifiers are followed now. The limit that remains is stated in the file and is a different
one: entries outnumber papers — four metformin variants cite one article — so a rate quoted per
entry counts that paper four times, and the paper count is the one to quote.

### "Thirty abstain for want of claims" is not the whole account

Chasing the two newly-found results-table papers to their entries turned up the other half of the
problem. One ships an **R script** as its model; the other a **non-curated** PBPK/genome-scale
hybrid whose second half is a separate non-SBML file. Extracting either paper's claims perfectly
would still produce no certificate, because there is nothing here to run.

So the survey now records each entry's model format and curation status beside its paper, and the
two conditions can be crossed:

| | |
| --- | --- |
| entries shipping a curated SBML model | 21 of 31 |
| entries whose paper states results in a table | 4 (all one paper) |
| entries clearing **both** | **4 — the metformin variants** |

That is the honest state of the seeded set: the entries a certificate could be produced for today
are exactly the four variants of the one paper this repository already has claims for. Nine
entries ship SBML that is not curated, one ships no SBML at all, and the rest state their results
in figures.

It also names the immediate work, which is not a better extractor: **three of those four are the
same paper's other model variants**, sharing tables that have already been read and checked.

## The second entry, and a model named for twice the doses it carries

The survey's own conclusion named the work: three of the four entries clearing both blockers are
the same paper's other model variants, sharing tables already read and checked. One of them is
**BIOMD0000001029**, the twice-daily human model, and the paper's Table 7 gives its plasma Cmax at
three dose levels.

It reproduces, at every level:

| regimen | paper (Table 7) | reconstruction | relative error |
| --- | --- | --- | --- |
| 500 mg twice daily | 6.9 nmol/mL | 6.8907 | 0.13% |
| 1000 mg twice daily | 12.8 | 12.7894 | 0.08% |
| 1500 mg twice daily | 18.5 | 18.5611 | 0.33% |

That is the second entry in this repository certified against numbers read from a paper, and the
first one whose reference values were checked against the source *before* they were committed
rather than months afterwards — `claims-check` was run on them, and the test that pins the values
now iterates over every claimed entry rather than naming metformin, so a third cannot arrive
without its cited rows.

The two larger doses are assumption-qualified for the same reason the single-dose entry's is: the
paper's doses are metformin hydrochloride and the model's input is free base, so 1000 mg and
1500 mg enter as 779.9 and 1169.85. The 500 mg arm needs no assumption — it is the model's own
default.

### The model's name says eight doses; it carries four

`Dose_0_001h`, `Dose__12h`, `Dose_24h`, `Dose_36h`. Four events, in a model whose own name is
*"eight PO administrations with 12h interval"*. Nothing in the file marks the difference, and every
file involved is valid.

The honest thing is to say how much it matters, not to assert either way, so it was measured:
cloning the dose event out to 48, 60, 72 and 84 hours moves the plasma Cmax from **6.8907 to
6.8943** — 0.05%. Under twelve-hour dosing with a 3.9-hour half-life the peak is a steady-state
plateau by the third dose, so *that* claim is not load-bearing on the missing four.

**And the conclusion drawn from it was too wide.** It said "a claim about Cmax is not load-bearing
on the missing four", which is true of plasma and false of the paper's other tissues: red blood
cells have a 21.7-hour half-life, are still accumulating at the fourth dose, and come out **15%
short**. One measurement on one compartment was generalised to a metric. See "Two tissues that do
not reproduce" below, where it is measured on each.

This is the shape of finding the whole project is for: a deposited model that does not do what its
own description says, found by running it rather than by reading it, with the consequence for each
claim measured rather than assumed.

## Two arms that "did not reproduce", and why that verdict would have been wrong

The same paper's Table 5 validates the human single-dose model against four published datasets at
250, 500 and 750 mg. Its "Fitted" column is the model's own output, so those are four more claims
for an entry already certified — and running them was cheap, because the model is committed.

Two of the four came back badly:

| arm | paper | dose changed alone | relative error |
| --- | --- | --- | --- |
| Gusler 500 mg | 6.1 | 6.0663 | 0.55% |
| Chung 1000 mg | 11.2 | 11.2496 | 0.44% |
| **Chung 250 mg** | **3.9** | **3.3091** | **15.2%** |
| **Wen 750 mg** | **9.4** | **8.6816** | **7.6%** |

A claims file recording those four would have published two `not-reproduced` verdicts against a
model that reproduces them perfectly well. The paper says why, in its own Results, one paragraph
above the table:

> the human model was validated ... 250 mg dose dataset from Chung **with one 375 mg pre-dose 12
> hours before the main dose** ... 750 mg dataset from Wen **with one 500 mg pre-dose 12 hours
> before the main dose**

The two arms that failed are exactly the two with a pre-dose, and the one that has none is the one
that reproduces. That is a hypothesis until it is run, so it was run — a 375 mg dose at t=0 and the
250 mg at t=12, reading the peak after the second:

| arm | paper | with the pre-dose the paper states | relative error |
| --- | --- | --- | --- |
| Chung 250 mg | 3.9 | 4.0207 | 3.1% |
| Wen 750 mg | 9.4 | **9.4036** | **0.04%** |

Both reproduce. Nothing is wrong with the model, the paper, or the numbers: what is missing is a
**protocol**, and the protocol is in the prose.

### What that costs, precisely

A Reprolith claim carries `parameter_overrides` — a dose is a parameter, and setting one is how
every claim in this corpus expresses its arm. A *pre-dose twelve hours earlier* is not a parameter
value; it is a second administration, and the shape has no way to say it. So these two claims are
**reproducible, verified by hand, and not expressible**, which is a different kind of blocked from
every other entry in the set and the first one that is Reprolith's own limit rather than the
literature's.

It is also the first measured case of a claim whose protocol the *paper* states fully and the
*artifact* does not: the deposited single-dose model has one dose event, and the run the paper
describes needs two. `archive_mismatches` and `manuscript_mismatches` both look for disagreements
between files; neither can see a run that no file expresses.

What it named for the roadmap was concrete — a claim needs a dosing schedule, not only a parameter
override — and it is built now.

### The schedule, and the four things that had to carry it

A claim's `schedule` is a sequence of segments. Each runs **the author's own model** with its own
parameter values, starting from the state the previous segment ended in, so the model's own dose
event administers every dose and nothing is added to the model. Adding an event would be
reconstruction — a run the artifact does not describe — and would have to be declared as one. The
claim is judged over the last segment; the ones before it condition the state it starts from.

All three of the paper's pre-dosed arms now certify from the committed corpus:

| arm | protocol | paper | reconstruction | error |
| --- | --- | --- | --- | --- |
| Chung 250 mg | 375 mg 12 h earlier | 3.9 | 3.8595 | 1.0% |
| Wen 750 mg | 500 mg 12 h earlier | 9.4 | 9.4034 | **0.04%** |
| El Messaoudi 500 mg | six 500 mg doses, 12 h apart | 6.8 | 6.8943 | 1.4% |

The second agrees to four decimals with an independent by-hand run that added an event to the
model instead. The third is a **seven-segment** schedule and was not part of the design target —
it is the check that the shape generalises past the two segments it was built for, and its answer
lands on the same 6.894 steady-state plateau the *twice-daily* model reaches, which is two
different models and two different mechanisms arriving at one number.

Metformin's single-dose entry carries five claims where it carried two.

The interesting part is what else had to change, because three of the four were surfaces that
would otherwise have reported a run nobody made:

**The state carried forward is an amount, and `simulate` returns a concentration.** Written
straight across, the carried state is divided by the compartment volume — 2247 mL for this model's
venous plasma. Nothing fails and nothing warns: the prior dose simply vanishes, and the answer
comes back *exactly equal* to the no-pre-dose one. That is what a silently discarded segment looks
like, and it is the same units confusion that once put a certificate's 6.07 nmol/mL and 13,630.8
nmol two thousand-fold apart. It is a test now.

**Cross-engine corroboration ran the default arm.** The recipe step is built from
`Claim.parameter_overrides`, which is empty for a scheduled claim — so both new claims were
corroborated against the model's *unmodified 500 mg* run and published `engine_independent: True`
under their own claim ids. The comment directly above that code says corroboration is "driven off
the bundle's own recipe, overrides included, so what is corroborated is the run each claim actually
made and not just the model's default arm". True when written, and a new route walked straight
past it. Both engines walk the segments now, and agree to 1e-06.

**The published record said the default arm too.** `corroboration.json` reported `"overrides": {}`
for a claim that runs at 194.96 mg, because the dose lives in the schedule's last segment. The
milestone's own test compared that field against `step.parameter_overrides` and would have accepted
it.

**And the exporter would have written the defect this project exists to catch.** A uniform time
course cannot say "start from where another run ended", and `_plan` did not look at the schedule —
so the archive would have shipped a document running the reported window *alone*: a neighbouring
arm, producing a plausible number and flagging nothing. Exactly the metformin archive's own defect,
reproduced by Reprolith's writer. It is listed as unexpressed with the reason instead, which is the
mechanism that already existed for a step a document cannot state.

One capability, four surfaces, three of which reported something false until they were checked.

One more thing had to be true for any of it to be affordable. Carrying a model's state through
`simulate` costs one full simulation **per species** — twenty-one for this model, and five seconds
against the run's own quarter-second. The engine's time series already holds every column, so
`final_state` reads them in one run: 5.23 s to 1.09 s, same answer to four decimals.

And that optimisation immediately produced its own version of the same defect. Its first version
defaulted both engines to COPASI's reader, so the corroborating libRoadRunner run would have
carried state computed by COPASI — half the arithmetic shared with the thing it was corroborating,
still reported as two independent engines agreeing. `final_state_with_roadrunner` is the
counterpart, and a test holds the two to each other.

A **fifth** turned up when the suite ran: `manuscript_mismatches` — the check whose entire job is
saying *the archive never runs the dose your paper reports* — also read `parameter_overrides`, so
it saw nothing for the two claims whose dose is hardest for a reader to find, and said nothing
about them. It reports all three now: the paper's own shipped archive runs none of 779.9, 194.96
or 584.89.

A fourth surface turned up on re-reading the diff, and it is the same sentence again: the AUC
convergence guard added an hour earlier took `model`, which for a scheduled claim is the
*unmodified* SBML — the doses live in the segments. It would have measured a different integral's
convergence and reported it under the claim's id. It follows the schedule now. Three surfaces
reporting a run nobody made, then a fourth found by looking rather than by failing: the same
capability, the same mistake, four times.

The limit is in the mechanism and is refused rather than hidden. Each segment restarts the model's
clock — which is *how* the dose is administered, the author's own event firing again — so a model
carrying a second event would fire that one again too, at the same offset into every segment. A
time-triggered event is indistinguishable from a dose here, so a schedule on a model with more than
one event is refused by name. Both metformin models carry exactly one, which is the dose.

## An AUC is a property of the sample grid, and nothing said so

Chasing the mouse intravenous model — the fourth metformin variant, whose Table 2 reports plasma
AUC over 24 hours — turned up something about the engine rather than about the paper. The AUC does
not converge:

| samples | 240 | 480 | 960 | 1920 | 3840 | 7680 |
| --- | --- | --- | --- | --- | --- | --- |
| AUC24 | 658 | 406 | 280 | 218 | 188 | 174 |

Still moving 7.9% at the last doubling. The same measurement on the *human oral* model agrees to
six figures from 240 samples up — 41.4469, 41.4468, 41.4468, 41.4468 — which is why nothing had
ever noticed. A bolus intravenous profile puts almost all of its area in the first minutes of a
twenty-four hour window, and a trapezoidal sum over a uniform grid cannot see it.

`_metric(..., "auc")` has always been a sum over the sample points, and the protocol string has
always recorded the sample count, and the docstring beside it has always said "an AUC and a curve
distance both move with the sample count". All true, all published, and none of it a **check**: an
AUC claim could be judged `reproduced` or `not-reproduced` on a number that was an artifact of
`steps`, and the certificate would look exactly the same either way.

The rule now applied is the one the numbers themselves suggest. The AUC is measured again at twice
the resolution, and the change is compared against the width that separates a pass from a failure
for that claim. **When the metric's own sampling uncertainty is wider than that width, the
comparison cannot tell a pass from a failure**, so the claim abstains — `not-evaluable`, with the
two sample counts and both numbers in the reason. On the mouse model at 480 samples that reads:
*the AUC moves 30.9% between 480 and 960 samples, wider than the 5.0% that separates a pass from a
failure here.*

It is one-directional by construction: it can turn a judgment into an abstention and never the
reverse. And it cost the corpus nothing to adopt, because every committed claim reads a peak —
`cmax` — and not one of them integrates. That is the uncomfortable half: the guard was free
precisely because the metric it protects has never been used, and the first real use of it would
have been the one that got it wrong.

**The sweep that follows it comes back clean, and that is worth recording too.** `_metric` is
called from one place, so there is no sibling front-end computing an unguarded AUC — the shape
this record keeps finding, a rule reaching one surface and not its neighbour, is not present here.
And the curve comparison, which the same docstring says "moves with the sample count", needs no
counterpart: `judge_curve` refuses a reference and a prediction of different lengths, so a curve
claim's grid *is* the claim. An AUC's sample count is a free numerical choice with no bearing on
what the paper reported, which is exactly what makes "measure it again at twice the resolution"
meaningful; doubling a curve claim's grid would not refine the comparison, it would be a different
comparison against a reference that does not exist. That asymmetry is now a test, so the next round
does not chase it.

## Six tolerances fitted to one machine

CI failed on the dosing-schedule commit, and not on anything about dosing. Two of its new tests
asserted that a one-segment schedule gives the same answer as an ordinary run, and that a bulk
end-state read agrees with reading one species at a time — both true, both asserted at `1e-9` and
`1e-8` because that is what they measured *here*. On CI's interpreters the same comparisons come
back at 1.2e-9, 6.3e-8 and 1.7e-7.

The engine's own docstring has said since it was written that COPASI is not bit-identical across
repeated calls in one process, and quantified it at about 1e-11 on the models it was measured on.
What today added is that the size depends on the **installed build**, and the first explanation for
that was wrong. "A newer interpreter is noisier" fits the CI evidence — 3.9 passed, 3.11 and 3.12
failed — and is refuted by building a local 3.12 environment and measuring: **6.2e-12 and 1.8e-11**,
the same as 3.9 here. It is the platform-and-version build of `python-copasi`, not the interpreter,
and the consequence is worse than the wrong diagnosis was: **no local environment can see it**.

Which makes the rule the only defence. A tolerance calibrated against one machine is a threshold
with no basis — the shape this record already names for thresholds fitted to a single observation,
arriving by a route that looked like arithmetic rather than judgement.

Six of them were written today, and all six are now set by *what the check must catch* rather than
by what it happened to measure:

| check | was | now | what it must catch |
| --- | --- | --- | --- |
| one-segment schedule vs ordinary run | 1e-9 | 1e-5 | a dropped segment — 15% |
| bulk end state vs one at a time | 1e-8 | 1e-5 | the wrong column or row |
| MAPK round trip through the dossier | 1e-12 | 1e-4 | a dropped reaction — percent |
| repressilator, short window | 1e-8 | 1e-4 | a changed rate law — percent |
| repressilator, long window | 1e-5 | 1e-3 | the same |
| a local parameter hoisted to global | 1e-9 | 1e-5 | 500x too fast |
| two engines' end states | 1e-4 | 1e-3 | the corroboration criterion's own width |

Every one of them still fails on the defect it was written for, by three orders of magnitude or
more. The measurements stay in the docstrings, where they are a record of what was observed rather
than a bound anything depends on — which is what `EngineCorroboration.distance_bound` already does
for the number it publishes, and for the same reason.

### And one of them was not a tolerance problem at all

The bulk end-state check failed again at the loosened bound — 1.8e-5, on **Linux 3.9**, the one
build that had passed. Loosening it a third time would have been the third wrong answer to the same
question.

`mStomachLumen` starts near 390 and has decayed to **0.053** by twelve hours. The absolute
difference between the two reads is 1e-6. Against what is left, that is 2e-5; against what the
species ever was, it is 1e-10. The comparison was dividing by a vanishing denominator, and every
loosening was buying a little more room in a quantity that keeps shrinking.

It is compared against each species' own scale now — the largest value it reaches over the run —
and the worst case is **3.9e-9 against a 1e-5 budget**, three orders of headroom on a denominator
that does not move. Which is exactly what `judge_scalar` already does through `zero_scale`, in the
words of its own docstring: a value with no magnitude has nothing for a relative tolerance to mean
anything against. The engine layer met the same problem and did not recognise it, twice, because
each failure looked like the previous one.

Then the shape was swept rather than waited for. Two more of the day's checks divided by a value
that can vanish — the dossier round trip, which compares every state variable's **end** value, and
the two engines' end states — and both are measured against each species' own scale now. The round
trip's margins improve rather than loosen: 2.7e-15 on MAPK, 1.4e-9 and 1.1e-6 on the repressilator,
against bounds of 1e-4 and 1e-3. A denominator that does not move buys more room than any amount
of loosening does.

## A parameter with no caller, checked and left alone

`judge_scalar` takes a `zero_scale` — "the size the claim is zero relative to" — because a reported
zero has no magnitude for a relative tolerance to divide by. It is the fix a past round made after
*a lethal knockout judged in whatever units it happened to use*. Sweeping the vanishing-denominator
shape through the package turned up that **nothing passes it**: not `certify_model`, not the FBA
front-ends, not the stochastic one.

That reads like a dead parameter, and it is not. Measured, three cases:

| reported | predicted | scale | outcome |
| --- | --- | --- | --- |
| 0 | 0.05 | none | `not-evaluable`, naming what it needs |
| 0 | 0 | none | `reproduced` — exact agreement |
| 0 | 0.05 | 0.87 | raises: a failed verdict needs an attribution |

So every shipped surface **abstains** on a claim whose reported value is exactly zero, which is the
honest answer and the one the docstring promises. And it is not a hole in lethality checking, which
was the worry: `reaction_essentiality` returns a *set* of indices and is judged by set agreement,
so a lethal knockout never arrives at a scalar comparison against zero in the first place.

The third row raises rather than abstaining, which is the same shape `certify_model` fixed for
itself by supplying `undetermined_shortfall` — but it is unreachable, because reaching it needs a
caller that passes a scale and there is none. Written down so the next round does not chase either
of them.

## Reading the five-claim certificate as its reader

The method the eighteenth pass named, applied to what today changed. Two things a reader trips on,
and only one of them was a defect.

**Six copies of one clause.** The El Messaoudi arm's protocol read
`preceded by 12.0 at Metformin_Dose_in_Lumen_in_mg=389.93` six times over. Everything a person
needs from it — six doses, twelve hours apart, all the same — is exactly what the repetition
buries. Identical *adjacent* segments are counted now (`6 x 12.0 at …`), and only identical
adjacent ones, because a count that merged two different doses would be a protocol nobody could
re-run.

**And one that looked worse than it is.** `Cmax-500mg` is the only claim of the five that reads as
an unqualified pass, and it runs the model at its default 389.92 while asserting "after 500 mg
single oral dose" — an identification nothing in the model states. The parameter's own note gives
metformin's free-base molar mass and nothing else. That looks exactly like a claim reading clean
because the assumption it rests on is baked into a default rather than applied as an override,
which is a shape this record has found before.

It is not. The comparison never uses the conversion: the reference is the paper's own Table 6 row
labelled 500, the run is the model as shipped, and the label is the *paper's* word for its own
simulation. The assumption exists to reach the doses the model does **not** default to, and every
claim that needs it carries it. Written down because the wrong reading is the more natural one,
and because a later round that "fixes" this would be qualifying a claim that earned its clean pass.

## Thirty tissues, and a dose written two ways

Every claim in this corpus read one species. The paper's Table 6 publishes a simulated Cmax for
**twelve tissues at three doses** — thirty-six numbers — and one of them was checked. The other
thirty-five had a committed source and no verdict.

Ten of the twelve map to exactly one species the model declares. Two do not: the model splits
Intestine into a lumen, an enterocyte and a vascular compartment, and Kidney into plasma, tissue
and tubular, so *which* one the paper's row means is a judgement about the paper — the same
judgement `claims-propose` refuses to make, and refusing it here too costs two rows out of twelve.

The ten reproduce, at every dose:

| | worst | where |
| --- | --- | --- |
| 500 mg | 1.64% | red blood cells |
| 1000 mg | 1.80% | red blood cells |
| 1500 mg | 1.07% | red blood cells |

Every other tissue is inside 1%, and eight of thirty are inside 0.1%. The red-blood-cell rows are
the paper's own rounding: it prints 1.0, 1.9 and 2.7, and the model gives 1.016, 1.866 and 2.671.
The metformin single-dose entry now carries **thirty-three claims**, all reproduced, each checked
against a committed row.

### The dose that was written two ways, and one that was wrong

Generating twenty-eight claims mechanically exposed something a hand-written corpus had hidden.
The free-base dose is derived — the paper states hydrochloride, the model's input is free base, and
the assumption block gives the factor — and nothing had ever checked the arithmetic.

The 1500 mg twice-daily claim ran at **1169.85**. The conversion gives **1169.79**. It reproduced
— 18.5611 against the paper's 18.5, a 0.33% error inside a 5% tolerance — so no verdict, no gate,
and no reader could see it. A wrong number that still passes is invisible from inside the pipeline,
which is the third time today that sentence has been the finding.

And the 1000 mg dose was written **779.9** in one claim and **779.86** in another: both correct
roundings of 779.8575, and two derived models in the exported archive for one arm.

`tests/test_dose_conversion.py` makes the arithmetic checkable rather than trusted. Every dose any
claim sets must be the exact conversion of one of the paper's stated doses, rounded to one or two
decimals — checked as an exact rounding rather than within a tolerance, because a relative bound
cannot tell a legitimate one-decimal rounding from that typo: both sit 5.5e-5 from the true value.
It also holds one stated dose to one spelling, and requires the assumption block to name the
numbers the claims actually run.

### A document telling a reproducer to run the same model ten times

Thirty expressible claims produced thirty SED-ML tasks and twenty-one models over **three distinct
runs**. Every 500 mg claim reads a different species of one identical simulation, and each was
being written as its own task; every 1000 mg claim minted its own derived model carrying the same
`changeAttribute`.

A task is a run. Two claims reading different outputs of the same run are one task with two data
generators, and ten claims setting the same dose are one modified model. The exported archive is
now 4 models, 1 time course, 4 tasks and 30 reports — which is what actually happened — and it is
*smaller* than it was with two claims' worth of duplication in it.

## Two tissues that do not reproduce, for two different reasons

The same expansion, applied to the twice-daily entry's Table 7: ten tissues at three doses.
Twenty-four reproduce, worst 0.59%. **Six do not**, and they are the first non-reproducing claims
this corpus has ever published — the engine's failure path had never been exercised on real data.

They miss consistently at every dose, which is the signal that made them worth chasing rather than
loosening: red blood cells 15.3 / 15.7 / 15.2%, brain 20.1 / 20.1 / 20.6%. Two entirely different
causes, both established by measurement.

### The artifact runs less of the protocol than the paper states

The deposited model is named *"eight PO administrations with 12h interval"* and carries four dose
events — the discrepancy this record already noted, and dismissed for Cmax on one compartment's
evidence. Supplying the four missing administrations:

| | half-life | as deposited | with all eight | paper |
| --- | --- | --- | --- | --- |
| plasma | 3.9 h | 6.891 | 6.894 | 6.9 |
| red blood cells | 21.7 h | 2.710 | **3.163** | 3.2 |

15.3% short becomes 1.1%. Nothing in the file is missing or wrong; what is short is the *run*, and
which claims that reaches depends on each tissue's half-life. That is why it had to become a
failure mode nameable **per claim** rather than a property of the model:
`artifact-runs-less-of-the-protocol-than-the-paper-states`, the first PK/PD root cause a blind
verdict in this repository has actually attributed.

### A table cell that contradicts its own row

Brain does not move when the doses are supplied — 5.512 to 5.515 against the paper's 6.9. So the
missing doses are not its cause, and the paper's own numbers say what is:

| Brain ÷ plasma | Table 6 (single dose) | Table 7 (twice daily) |
| --- | --- | --- |
| AUC24 | 0.79 | 0.80 |
| Cmean | — | 0.80 |
| **Cmax** | **0.80** | **1.00** |

Every quantity in Table 7's Brain row is four fifths of plasma's except Cmax, which is exactly
equal to it. The model gives 0.80. A Cmax equal to plasma's cannot sit above an AUC and a Cmean
that are four fifths of it, and 0.80 × 6.9 = 5.52, which is what the model produces.
`apparent-manuscript-error`, faulted to the manuscript — the first time this engine has said that
about a published table, and it says it with the paper's own arithmetic.

### What had to change to say either of them

A dataset claim could not state a root cause. `Claim.from_record` parsed everything except
`shortfall`, with a docstring explaining that dataset claims "are the reproducing,
default-tolerance case" — true until today. Without it both findings would have published
`uncategorized`, *fault: reconstruction*, which is the right answer when nobody has diagnosed a
miss and a false one when somebody has. A half-written attribution is refused rather than
defaulted.

And the repository's own governance caught the rest: adding a failure mode with no
discipline-loop note failed `test_loop_notes`, exactly as designed. The note carries the
measurements above, and its basis is `observed` rather than `spec` — the first failure-mode note
in the record that a run produced rather than a specification anticipated.

## The most serious thing it says was its least explained line

Reading the new certificate as the people it is about — the paper's authors — found the worst
defect of the day.

The gap report rendered the brain claims as the bare token **`apparent-manuscript-error`**. That
is this engine asserting that a named paper's table is wrong, printed beside that paper's DOI, with
**none** of the evidence for it: not the measured discrepancy, not the cell it implicates, not the
ratios that make the case, and no sign that a fault is — in `Fault`'s own words — *"always a
hypothesis, never a proven cause"*. The line directly above it, about an assumption Reprolith
supplied, explained itself in full.

The cause is one call. The report took the **first** of `(root_cause, implicated, fault_hypothesis,
discrepancy)` and dropped the rest, above a comment saying that `implicated` and `fault_hypothesis`
"are causes too" and that the author-facing surface "already reads all three; this is the same rule
on the neighbouring surface". It was not the same rule: that surface joins them, this one chose
one. **A comment claiming a parity the code lacks**, which is a shape this record has named before
— and it was harmless for as long as every shortfall was `uncategorized` against the claim's own
quantity, because then the first field was the only informative one. The first real cause in the
corpus turned a latent defect into the front page.

It publishes all of it now, in the order a reader needs it — what was measured, the category and
the cell it implicates, and the fault marked as a hypothesis:

> relative error 0.2012; apparent-manuscript-error, Table 7's Brain Cmax, which equals plasma's
> while its AUC24 and Cmean are 0.80 of plasma's; fault hypothesis: manuscript

The public registry page carries the same sentence. An accusation without its evidence is worth
less than no accusation, and this one is aimed at people who can check it.

## "FIX BEFORE YOU SUBMIT" followed by a noun phrase

The same read, one surface over. The pre-submission report is the thing this project most wants an
author to run, and under a heading reading *FIX BEFORE YOU SUBMIT* it offered:

> fix: Table 7's Brain Cmax, which equals plasma's while its AUC24 and Cmean are 0.80 of plasma's

That is the finding, restated. It is not a fix, and an author cannot act on it. The field it came
from is `implicated`, which is by definition *the element implicated* — a noun phrase, correct in
its own right and wrong in that slot. It had been the fix text since the surface was written, and
was unnoticeable while every implicated element was the claim's own quantity.

**And it never named the fault direction.** An author told to fix a claim needs to know whether
Reprolith believes their *model* fell short or their *table* has a typo — those are different
pieces of work, and one of them is "check whether we are right about your paper". The two now read
differently, and both say the fault is a hypothesis:

> fix: check Table 7's Brain Cmax … — Reprolith's hypothesis is that the reported value is wrong
> rather than the model, so confirm it against your own run before changing anything

> fix: reconcile the model with what your paper reports: the four dose events the model carries …
> Reprolith's hypothesis is that the shipped model, not the reported value, is what falls short

`Fault` has said "always a hypothesis, never a proven cause" since it was written. Today is the
second surface found not passing that on — the certificate was the first, three commits ago. Both
were silent for the same reason: until this morning no claim in the corpus had a cause worth
stating, so every field carrying one was a placeholder and nothing that dropped or mis-slotted it
could be seen.

**So the third was swept for rather than waited on**, and it is not there. Every surface that reads
a claim's cause was checked against the first real one: the certificate's `certificate` view and the
`gaps` view both carry all four fields (the second because it reads the render's own `gap_items`,
so the fix reached it), and the registry page publishes the joined sentence. Two wrong, three right.
The `gaps` view is now pinned by a test, because it inherits whatever the render publishes and a
later change there could strip the evidence from the surface an *agent* reads with no person in the
loop to notice.

## The first clean pass, and the table nobody had fetched

The paper's mouse models had been written off. Its Table 2 — the intravenous one — reports AUC and
half-life and no Cmax, the AUC does not converge on a bolus profile, and the guard added this
morning abstains on it. That looked like the end of the paper.

It was not. **Table 1 had never been fetched.** The survey pulled Tables 2, 4, 5, 6 and 7 because
those were the ones a claim already cited, and Table 1 is the *oral* mouse table: Cmax, Tmax, AUC
and half-life for nine tissues, the paper's own fitted values. And the article says in as many
words why Table 2 has no Cmax — *"due to the IV curves' decreasing nature, only AUC24 and T1/2
values were calculated for the IV experimental data"* — which is the same fact the convergence
guard discovered numerically, stated in the prose.

Seven of the nine tissues map to one species each. They reproduce at **worst 0.17%**:

| plasma | portal vein | liver | heart | muscle | adipose | brain |
| --- | --- | --- | --- | --- | --- | --- |
| 0.16% | 0.09% | 0.05% | 0.02% | 0.17% | 0.05% | 0.03% |

And with **no assumption at all**: the mice were dosed with metformin, not the hydrochloride salt,
so nothing has to be converted and the model's default dose is already the paper's. That makes
BIOMD0000001027 the first entry in this class to certify as **`reproduced`** — an unqualified pass,
which the overall-verdict rule forbids to any certificate resting on a load-bearing assumption, and
which the two human entries therefore cannot reach.

It is also **the first agreement the blind self-validation run has recorded for this class**. That
number was 0 of 31 this morning and had been zero for the life of the repository; the surface
reporting it already carried the right caveat and needed no change.

The lesson is small and cheap: the survey fetched the tables that were *already cited*. A results
table nobody had claimed from was invisible to it, and it was the one that turned an entry written
off as blocked into the corpus's only clean pass.

### And the record it invalidated

The discipline-loop audit refused the commit, correctly, twice over. A `disagreement` note existed
explaining why BIOMD0000001027 abstained, and it no longer abstains — an orphaned note, "explaining
nothing", which is a failure by that audit's own rule. Its sibling listed thirty entries as
abstaining; three of them now certify.

Rewriting it turned up something the audit could not see. The note on the metformin entry quoted
"relative error 0.0216 and 0.0045" for its two claims — and 0.0216 is the error against **6.2**,
the reference value that turned out not to be in the paper and was corrected this morning. Against
the paper's actual 6.1 it is 0.0055. The note had been stale since that correction, and every one
of its evidence citations still matched, because they quote the certificate's *assumption* block
and not its numbers.

Which is the same shape as the corrected value itself: a number in a document that nothing
re-derives goes quietly out of date, and a citation check that passes tells you only that the
words are still there.

## The accusation, checked with a second metric

The brain claim says a cell of the paper's table is wrong. That rested on the table's own internal
arithmetic — Brain's AUC and mean concentration are 0.80 of plasma's, its Cmax is 1.00 — which is
an argument from the paper about the paper. The engine can do better than that, and it did:

| Table 7, twice-daily 500 mg | AUC24 | Cmax |
| --- | --- | --- |
| **Brain** | 67.4 vs 67.4 — **0.07%** | 5.512 vs 6.9 — **20.1%** |
| **Red blood cells** | 57.1 vs 90.3 — 36.8% | 2.710 vs 3.2 — 15.3% |
| Plasma | 84.3 vs 84.2 — 0.13% | 6.891 vs 6.9 — 0.13% |
| Liver | 701.1 vs 700.4 — 0.09% | 76.797 vs 76.7 — 0.13% |

**The model reproduces the paper's Brain row exactly, and fails on one cell of it.** That is a far
stronger statement than the ratio argument: not "these numbers are mutually inconsistent" but "we
regenerate every other number you published for this tissue".

And the two causes separate cleanly under a second metric, which is what makes it evidence rather
than coincidence. A **manuscript error** is one cell: the rest of the row reproduces. An
**incomplete protocol** is the whole profile: red blood cells miss on exposure *and* peak, because
four doses of eight leaves an accumulating tissue short everywhere, not at one point.

## The first AUC claims in the corpus

The convergence guard added this morning was, in its own note, "free precisely because the metric it
protects has never been used". It is used now. The mouse entry's Table 1 publishes a 24-hour
exposure beside every Cmax, and all seven reproduce — worst **0.37%**, every one converging four to
seven orders inside the pass tolerance, on a smooth oral profile where the guard costs nothing.

Which is the counterpart of the finding that produced the guard: the same metric on the same
paper's *intravenous* mouse model does not converge at all, and the paper says why in prose. One
metric, two models, and the difference is the shape of the curve.

## One entry, three verdicts

The intravenous mouse model was the last of the paper's four, and it had been written off twice —
once for having no Cmax to claim, once for an AUC that would not converge. Both were true and
neither was the whole picture. Its three claims land on **three different verdicts**, which no
other entry in this corpus does:

| | | |
| --- | --- | --- |
| **Stomach** | `reproduced` | 523.85 against 529.5 — 1.07% |
| **Liver** | `failed` | 914.84 against 523.5 — 74.75%, **no cause established** |
| **Plasma** | `not-evaluable` | the AUC still moves 22.2% when the run is sampled twice as finely |

Each is the honest answer to a different question. The stomach exposure reproduces. The liver
exposure does not, and nothing here has diagnosed why — so it publishes `uncategorized` with the
fault laid at the reconstruction, which is what an undiagnosed miss is *supposed* to look like and
the first time this corpus has produced one. And the plasma exposure is not judged at all, because
an intravenous bolus puts nearly all of its area in the first minutes of a twenty-four hour window
and a trapezoidal sum over a uniform grid cannot see it — the guard written this morning, firing on
a real published number for the first time.

An entry that holds a pass, a failure and an abstention at once is also the sharpest illustration of
why a binary ground-truth label cannot score this engine. Its label says `reproduced`.

### A guard caught the paper's own typo

`require_same_paper` refused the certificate outright: the catalog's title says *"single dose
intravenous"* and the deposited model's own `name` attribute says *"single dose intavenous"*. The
check compares the two sides of a filing and neither title named the other, so it would not file the
certificate — which is exactly its job, and the misspelling is in the artifact rather than in
anything here.

## Reading the prose, and finding out it does not help

The roadmap's next lift after tables was prose. The paper this corpus is built on states two of its
committed values in a sentence as well as in a table — *"concentrations in plasma reach a maximum
of 6.1 nmol/mL (0.79 mg/L) and 11.2 nmol/mL (1.45 mg/L)"* — so a prose reader was built to the same
rule as the table one: a candidate is a proposal, the model output is never guessed, and every
candidate carries its **whole sentence**, because "the measured value is 26.1 nmol\*h/mL, and the
simulated value is 91.4" needs the reader to see which half is which.

It works. It rediscovers 6.1 and 11.2 with `metric: cmax` from "reach a maximum of", and ignores
"Fig 4" and "reference 36" because a number with no unit beside it is a citation far more often
than a result.

**And it does not reach a single paper the table reader misses.** Measured across all ten
open-access papers in the set:

| | papers |
| --- | --- |
| state a result in a **table** | 3 |
| state a result in **prose**, naming the quantity | 2 |
| state one in prose but **not** in a table | **0** |

The seven papers with no results table have none in their text either. Their numbers are in the
figures, and the prose that surrounds those figures does not restate them. So prose extraction
broadens what can be read from a paper *already reachable* — worth having, and the natural
companion to the table reader — and moves the reach of this corpus by nothing at all.

That reorders what remains: **figure digitization is not the next lift after prose, it is the only
one.** The measurement is committed beside the table counts so the ordering rests on evidence
rather than on which capability was easiest to imagine building.

### The vocabulary that had to include what it cannot express

One error worth keeping. A sentence names a metric only if it names exactly one, and the first
version's vocabulary held only the metrics this engine *supports* — so *"T1/2 is measured at 0.50h
while the AUC simulations show 0.9h"* looked unambiguous and put `auc` on two half-lives. A term the
reader cannot express still has to make a sentence ambiguous, or the ambiguity check only sees the
half of the vocabulary it likes.

## One hundred and eighteen reactions, and rate laws for none of them

The four certified entries are all one paper. The survey says a fifth paper is in principle
reachable — [PMC5732473](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5732473/) prints a results
table and deposits SBML — so the obvious next move was to run its model. It is
[MODEL1711210003](https://www.ebi.ac.uk/biomodels/MODEL1711210003), an estradiol PBPK model coupled
to a genome-scale network.

It does not run, and the reason is worth writing down: **it ships 118 reactions and a rate law for
none of them.** 114 carry `<kineticLaw><math/></kineticLaw>` — the element present and empty, which
libSBML reports as 114 "container must not be empty" errors and then hands the model back anyway —
and the other 4 carry no `kineticLaw` at all. The deposited file is the reaction topology of the
model. The dynamics live in the companion FBA file and in whatever ran them, neither of which is
SBML.

So the entry is genuinely not reachable, and no extraction capability would change that. What is
worth building is the check that says so *before* an author deposits.

### Three engines, three failures, and not one of them says why

The two engines here were pointed at a model where one reaction of three states no rate:

| | no `kineticLaw` element | `kineticLaw` with empty `math` |
| --- | --- | --- |
| COPASI (the pinned engine) | imports it, abandons the run at t=1.0 of 4.0 | same |
| libRoadRunner | **runs it to completion, that flux taken as zero** | `ASTNode is NULL` |

Not one of those is "this reaction states no rate", which is the single fact that explains all
three. COPASI does not refuse anything: it imports the file, starts the course, and returns 2 of 5
samples, every one of them finite — it is Reprolith's own completion check that turns that into an
error, and a caller reading the series as-is has a short trajectory and no reason to doubt it.
libRoadRunner is loud about the empty shape and silent about the absent one, which is the wrong way
round: the silent case produces a complete, plausible time course in which `A` decays into `B`
exactly as it should while `C` — everything downstream of the rate-less reaction — sits at `0.0`
for the whole run.

So `reactions_without_rate_laws` reports both shapes — the author's fix is the same either way —
and `archive-check` leads its fix list with the finding, above every mismatch, because everything
else in that list assumes there is a run to check.

### The measurement that was an artifact of its own harness

The first version of this section said COPASI *refuses* these files, and the test under it asserted
exactly that. Both were wrong, and wrong in the way that is hardest to see: `importSBML` takes a
**filename**. Handed a document it tries to open a file named by the whole of that document, fails,
and raises — so an assertion that "COPASI rejects this SBML" passes for any string on earth,
including a model that is perfectly fine. The known-good metformin model failing the same way is
what exposed it, and only because it was run as a control.

The engine tests now go through `reprolith.simulate`, which uses `importSBMLFromString` as the rest
of the repository does, and each carries a control: the same model with every rate stated, which
must run the whole course. A test that an engine refuses something proves nothing unless something
it accepts is run beside it.

### The gate that keeps it from being wrong

The cost of this check being wrong is telling an author to repair a file that is already correct,
and there is an entire model class it would be wrong about: a constraint-based model has no rate
laws by construction, and `e_coli_core` would be reported for all 95 of its reactions. The check is
gated on `packages_no_time_course_describes` — the model's own declared package, not a list of
exceptions — so the next fbc model is excluded for the same reason this one is. Swept over every
model committed in this repository, it reports nothing on all twelve that a time course describes,
and the two classes it must not speak about are excluded by their own packages.

## "Entries whose models run" was never the lift

The roadmap has carried two candidate lifts for the corpus's reach: figure digitization, and
entries whose models run. The first had a number attached to it — seven of ten open-access papers
put their results in pictures. The second never did, so all nine non-curated SBML entries were
fetched and probed: loaded, counted, and handed to the pinned engine over a ladder of durations
from 0.1 to 10,000 with the longest completed course recorded.

**Five of the nine run.** Four complete the longest course on the ladder and one stops after 1.0.
Of the four that do not: one is the estradiol model above with no rate laws, one will not import at
all, and two abandon the course at the very first duration.

Then the two surveys were joined, and they turn out to be **disjoint**:

| | has a paper stating a result this can read | does not |
| --- | --- | --- |
| **model runs** | **0** | 5 |
| **model does not run** | 1 | 3 |

The single non-curated entry whose paper prints a results table is the estradiol model — the one
that does not run. Of the five that do run, four name no paper this repository can reach at all and
the fifth's paper prints no results table. Every entry fails, and no two fail on the same side.

So the lift was never models. Five already run, and running them buys nothing, because nothing has
said what their published result is. The corpus is blocked on **claims**, which is where the table
survey and the prose measurement had already pointed, and this closes the other direction: there is
no reserve of unreached entries waiting on a better engine.

The probe is deliberately weak, and says so in the file it writes. Nothing here knows the time scale
a paper used, so "completes a course" is a floor for runnable and "completes none" is a floor for
not-runnable — no claim is reproduced and no verdict is reached. One thing it does get right that
an earlier version of it did not: a state variable is a species *or* a rate rule's target. Three of
these models declare no species at all and keep their entire state in parameters, and probing
species alone would have reported them as un-runnable for a reason that was about the probe.

## Nothing had ever checked a model's inputs

Every certificate in this repository checks a model's **outputs** against numbers a paper prints.
The four deposited metformin models each declare ten tissue-plasma partition coefficients, the
paper prints all ten in its Table 3, and until now nothing compared the two. A deposit carrying a
coefficient its own paper does not report would have reproduced every claim in the corpus and said
nothing: the coefficients are what the reproduction *runs*, so a wrong one moves the outputs and
the tolerance absorbs it or the failure is root-caused to something else.

So `params-check` asks the other question, and the answer is clean: **40 of 40 agree** — ten
coefficients in each of the four models, all of them the numbers the paper prints. That includes
the human models, which carry the *mouse* coefficients, which is what the paper says it did:
"transferable Kt:p values … are transferable among different species."

Two rules keep the check from accusing a correct deposit.

**It compares at the precision the paper printed, and no finer.** The paper prints `0.7` for
adipose and the model carries `0.73`. Demanding equality would report a mismatch the paper's own
table cannot support — it cannot tell `0.73` from `0.749` — so the answer is agreement, and the
limit travels with it: this establishes the model is *consistent with* the printed value, not that
it holds the value the authors fitted. The paper's own arithmetic confirms the unrounded one, as it
happens: its "calculated–estimated, %" column reads 82.5% for adipose, which is `(0.73 − 0.4)/0.4`
and not `(0.7 − 0.4)/0.4`.

**It never compares a value an `initialAssignment` or a rule overrides.** That number is not what
runs, and agreement with it would be the most confident wrong answer available. This repository has
been caught by that exact shape three times in three different readers, so it is a distinct
outcome — *not compared* — reported apart from a mismatch, and it does not fail the command.

The pairing of a table row to a parameter id is the curator's, written down in
`datasets/pkpd_parameters.json` and never inferred: "Lungs" is `Ktp_Lung` and "Intestine" is
`Ktp_IntestineVascular`, and no rule would produce either.

## Status and what remains

The engine, the blind run over the 31-entry set (7.1), the agreement report (7.2), the milestone
artifact (8.1), this note (8.2), and the discipline-loop record (7.3, 7.4) are all done and
committed. Both deferred method fences are lifted: a population is simulated, not only judged, and
an estimate is re-derived, not only compared — each validated against closed-form mathematics, and
neither yet pointed at a paper, because no population figure and no shipped dataset are in the
corpus. The adopt-and-verify fast-path is closed on both sides, and the author-facing check reaches
it on an archive or on the two loose files most papers actually ship.

**The claim corpus reached the ceiling the survey predicted.** It began the day as one entry with
two claims, one of which was a number its paper does not contain. It is now **four entries — every
model that paper deposited — carrying eighty claims: 72 reproduce, 7 fail with stated causes, and
1 is honestly not evaluable.** Every reference value is quoted from the article, committed, and
checked against it by a test.

That ceiling is not modesty, it is the measurement: of the thirty-one seeded entries, 21 ship a
curated SBML model, four belong to a paper that states results in a table, and the four that clear
both conditions are exactly the four now certified. Nine ship SBML that is not curated, one ships
an R script, and the rest publish their results in figures. **No further entry in this test set is
reachable**, by this route, from anything already built.

What would lift it, in the order the measurements support:

* **Figures.** Reading tables reaches three papers in ten of the open-access subset. The other
  seven put their results in pictures, and nothing here digitizes one.
* **Figures, and only figures.** That list used to have three items on it. Prose came off it —
  built, and measured to reach no paper the tables miss. Runnable models came off it too: five of
  the nine non-curated entries already run, and not one of them has a paper stating a result this
  can read. Both measurements are committed, and both point the same way.

What *is* established, and was not this morning: the engine's three verdict paths have all now run
on real published numbers. A clean unqualified `reproduced`. Two distinct root-caused failures, one
of them an argument that a published table is wrong, corroborated by regenerating every other
number in that row. An undiagnosed miss that says `uncategorized` rather than inventing a cause.
And an abstention where the number cannot be established at any sampling this engine will call
converged. Every one of those exposed a latent defect in a surface written when no claim had ever
failed — the certificate, the author-facing report, the loop-note record, and the claim shape
itself.

Tasks 2.1-2.3 remain open for the half a table reader does not close.
